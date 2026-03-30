"""SQL安全护栏 - AST解析 + 白名单 + 危险检测"""
from typing import Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import re

from .ast_parser import ASTParser
from .template_registry import TemplateRegistry


class SQLGuardStatus(Enum):
    """SQL护栏状态"""
    ALLOWED = "allowed"
    DENIED = "denied"
    NEED_APPROVAL = "need_approval"
    TEMPLATE_MATCHED = "template_matched"


class RiskLevel(Enum):
    """风险等级"""
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


@dataclass
class SQLGuardResult:
    """SQL校验结果"""
    status: SQLGuardStatus
    allowed: bool
    risk_level: str
    blocked_reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    rewritten_sql: Optional[str] = None
    matched_template: Optional[str] = None
    ast_tree: Optional[object] = None
    tables_accessed: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)


class SQLGuard:
    """
    SQL安全护栏

    校验流程：
    1. 空SQL检查
    2. 长度检查（防DoS）
    3. AST解析 + 危险检测（操作/函数/布尔注入/关键字）
    4. 白名单模板匹配（危险检测通过后才检查）
    5. DML边界检查（WHERE/LIMIT）
    6. 高风险操作 → 需要审批
    7. 敏感字段脱敏检查
    8. 只读操作 → L1
    """

    # 危险操作（直接拒绝）
    DANGEROUS_OPERATIONS = {
        "DROP", "TRUNCATE", "SHUTDOWN",
        "CREATE_USER", "GRANT", "REVOKE",
        "ALTER SYSTEM", "CREATE DATABASE",
    }

    # 警告关键字（记录但不直接拒绝）
    WARNING_KEYWORDS = [
        "--", "/*", "INTO OUTFILE", "LOAD_FILE",
        "LOAD DATA", "BENCHMARK", "SLEEP", "GET_LOCK",
        "COPY", "--",
    ]

    # 危险函数（SELECT上下文中也危险）
    DANGEROUS_FUNCTIONS = {
        "pg_terminate_backend", "pg_cancel_backend", "pg_signal_backend",
        "kill", "mysql_kill",
    }

    # 高风险操作（需要审批）
    HIGH_RISK_OPERATIONS = {
        "ALTER", "CREATE", "DELETE", "UPDATE",
    }

    # 无WHERE的高风险操作列表
    DML_REQUIRES_WHERE = {"DELETE", "UPDATE"}

    # 敏感字段（脱敏）
    SENSITIVE_FIELDS = {
        "password", "passwd", "pwd", "token", "api_key",
        "apikey", "secret", "private_key", "credential",
    }

    def __init__(self):
        self.parser = ASTParser()
        self.template_registry = TemplateRegistry()

    async def validate(self, sql: str, context: Optional[dict] = None) -> SQLGuardResult:
        """校验SQL安全性"""
        context = context or {}
        db_type = context.get("db_type", "mysql")

        # 1. 空SQL检查
        if not sql or not sql.strip():
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L5",
                blocked_reason="空SQL或仅包含空白字符",
            )

        sql_stripped = sql.strip()

        # 2. 长度检查（>10MB拒绝）
        if len(sql_stripped) > 10 * 1024 * 1024:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L5",
                blocked_reason=f"SQL长度超过限制（{len(sql_stripped)//1024//1024}MB > 10MB）",
            )

        # 3. AST解析
        ast_tree = self.parser.parse(sql_stripped, db_type)
        tables = self.parser.get_tables(sql_stripped, db_type)
        operations = self.parser.get_operations(sql_stripped, db_type)

        if not ast_tree:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L4",
                blocked_reason=f"无法解析SQL（语法错误或不支持的方言: {db_type}）",
                tables_accessed=tables,
                operations=operations,
            )

        # 3b. 危险操作检测
        dangerous = self._check_dangerous_operations(operations)
        if dangerous:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L5",
                blocked_reason=f"危险操作: {', '.join(dangerous)}",
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 3c. 危险函数检测
        dangerous_funcs = self._check_dangerous_functions(sql_stripped)
        if dangerous_funcs:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L5",
                blocked_reason=f"危险函数: {', '.join(dangerous_funcs)}",
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 3d. 子查询布尔型注入检测
        if self._check_boolean_injection(sql_stripped, operations):
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L4",
                blocked_reason="检测到子查询注入",
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 3e. 危险关键字检测（UNION等）
        warnings = self._check_dangerous_keywords(sql_stripped)
        has_union_keyword = any("UNION" in w for w in warnings)
        has_union_all = "UNION ALL" in sql_stripped.upper()
        if has_union_keyword and not has_union_all:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L4",
                blocked_reason="检测到UNION注入",
                warnings=warnings,
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 4. 白名单模板匹配（危险检测通过后才检查白名单）
        is_whitelisted, matched_template = self.template_registry.is_whitelisted(sql_stripped, db_type)
        if is_whitelisted and matched_template:
            return SQLGuardResult(
                status=SQLGuardStatus.TEMPLATE_MATCHED,
                allowed=True,
                risk_level=matched_template.risk_level,
                matched_template=matched_template.name,
            )

        # 5. DML边界检查（WHERE/LIMIT）
        dml_violations = self._check_dml_bounds(sql_stripped, operations, db_type)
        if dml_violations:
            return SQLGuardResult(
                status=SQLGuardStatus.DENIED,
                allowed=False,
                risk_level="L4",
                blocked_reason=f"DML边界违规: {', '.join(dml_violations)}",
                warnings=warnings,
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 6. 高风险操作 → 需要审批
        high_risk = self._check_high_risk_operations(operations)
        if high_risk:
            return SQLGuardResult(
                status=SQLGuardStatus.NEED_APPROVAL,
                allowed=True,
                risk_level="L4",
                blocked_reason=f"高风险操作: {', '.join(high_risk)}，需要审批",
                warnings=warnings,
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 7. 敏感字段脱敏检查
        rewritten_sql = self._check_sensitive_fields(sql_stripped, db_type)
        if rewritten_sql != sql_stripped:
            warnings.append("SQL已重写（字段脱敏）")

        # 8. 只读操作 → L1
        if self.parser.is_read_only(sql_stripped, db_type):
            return SQLGuardResult(
                status=SQLGuardStatus.ALLOWED,
                allowed=True,
                risk_level="L1",
                warnings=warnings,
                rewritten_sql=rewritten_sql if rewritten_sql != sql_stripped else None,
                tables_accessed=tables,
                operations=operations,
                ast_tree=ast_tree,
            )

        # 默认：L2（诊断类操作）
        return SQLGuardResult(
            status=SQLGuardStatus.ALLOWED,
            allowed=True,
            risk_level="L2",
            warnings=warnings,
            rewritten_sql=rewritten_sql if rewritten_sql != sql_stripped else None,
            tables_accessed=tables,
            operations=operations,
            ast_tree=ast_tree,
        )

    def _check_dangerous_operations(self, operations: List[str]) -> List[str]:
        """检查危险操作"""
        return [op for op in operations if op in self.DANGEROUS_OPERATIONS]

    def _check_dangerous_functions(self, sql: str) -> List[str]:
        """检查危险函数（包括SELECT上下文中也危险）"""
        sql_upper = sql.upper()
        found = []
        for func in self.DANGEROUS_FUNCTIONS:
            if func.upper() in sql_upper:
                found.append(func)
        return found

    def _check_boolean_injection(self, sql: str, operations: List[str]) -> bool:
        """检测布尔型SQL注入"""
        if "SELECT" not in operations:
            return False

        dangerous_patterns = [
            r"ASCII\s*\(\s*SUBSTRING",
            r"ASCII\s*\(\s*SUBSTR",
            r"SUBSTRING\s*\(\s*SELECT",
            r"SUBSTR\s*\(\s*SELECT",
            r"CHAR\s*\(\s*SELECT",
            r"HEX\s*\(\s*SELECT",
        ]

        sql_upper = sql.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_upper, re.IGNORECASE):
                return True

        return False

    def _check_dangerous_keywords(self, sql: str) -> List[str]:
        """检查危险关键字"""
        warnings = []
        sql_upper = sql.upper()
        for keyword in self.WARNING_KEYWORDS:
            if keyword.upper() in sql_upper:
                warnings.append(f"警告: 发现可疑关键字 {keyword}")
        return warnings

    def _check_dml_bounds(self, sql: str, operations: List[str], db_type: str) -> List[str]:
        """检查DML边界（WHERE/LIMIT）"""
        violations = []

        for op in operations:
            if op in self.DML_REQUIRES_WHERE:
                if not self.parser.has_where_clause(sql, db_type):
                    violations.append(f"{op}缺少WHERE条件")
                if op == "DELETE" and not self.parser.has_limit_clause(sql, db_type):
                    violations.append(f"{op}缺少LIMIT限制")

        return violations

    def _check_high_risk_operations(self, operations: List[str]) -> List[str]:
        """检查高风险操作"""
        return [op for op in operations if op in self.HIGH_RISK_OPERATIONS]

    def _check_sensitive_fields(self, sql: str, db_type: str) -> str:
        """检查并脱敏敏感字段"""
        sql_upper = sql.upper()
        for field_name in self.SENSITIVE_FIELDS:
            pattern = rf"SELECT\s+.+\b{field_name}\b"
            if re.search(pattern, sql_upper):
                return re.sub(rf"(\b{field_name}\b)", r"***_\1***", sql, flags=re.IGNORECASE)
        return sql

    def register_template(self, name: str, pattern: str, db_type: str = "mysql",
                          risk_level: str = "L1", is_regex: bool = True):
        """注册白名单模板"""
        from .template_registry import SQLTemplate
        template = SQLTemplate(
            name=name,
            pattern=pattern,
            is_regex=is_regex,
            risk_level=risk_level,
        )
        self.template_registry.add_template(db_type, template)

    def get_supported_dialects(self) -> List[str]:
        """获取支持的数据库方言"""
        return self.parser.supported_dialects
