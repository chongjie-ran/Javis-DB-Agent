"""
内置验证器集合 (V3.0 Phase 3)

包含核心验证器：
1. CompletionBreakingValidator - 打破"完成声明"假设
2. SQLBoundaryValidator       - 构造SQL边界条件，打破"SQL安全"假设
3. TokenOverBudgetValidator   - 检查Token是否超预算
4. CodeQualityValidator      - 代码质量验证器

使用示例：
    from src.validation import get_validator_registry, CompletionBreakingValidator

    registry = get_validator_registry()
    registry.register("completion_claim", CompletionBreakingValidator())

    context = ctx  # AgentHookContext
    result = await registry.validate(context)
    if result.has_broken_claims():
        ctx.set_blocked(f"假设被打破: {result.get_broken_claims()}")
"""

import re
import logging
from typing import Optional

from .validator_registry import (
    Validator,
    BreakingValidator,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CompletionBreakingValidator - 打破"完成声明"
# ─────────────────────────────────────────────────────────────────────────────

class CompletionBreakingValidator(BreakingValidator):
    """
    打破"完成"声明的验证器

    目的：LLM可能在没有真正完成时声称"已完成"，此验证器主动构造
    边界条件来打破这个假设。

    打破逻辑：
    1. 分类声明类型（completion/fix/test_pass/quality）
    2. 尝试构造对应的失败用例
    3. 返回broken=True表示"成功打破了声明"

    声明模式（按置信度分类）：
    - 高置信度：任务完成、已经完成、完成修复、搞定、问题已解决
    - 中置信度：已经好了、没问题了、处理完了、修复完成、执行完毕
    - 低置信度：综上所述、总结一下、看起来没问题、应该可以了
    """

    name = "completion_claim"
    enabled = True

    # 声明模式（触发对抗性验证）
    BREAKING_PATTERNS = [
        r"完成了(.*?)修复",
        r"实现了(.*?)功能",
        r"测试通过了",
        r"验证成功",
        r"无问题",
        r"已解决",
        r"搞定",
        r"任务完成",
        r"全部完成",
        r"已经完成",
    ]

    def __init__(self, confidence_threshold: float = 0.5):
        """
        Args:
            confidence_threshold: 置信度阈值，超过则触发break检查
        """
        self.confidence_threshold = confidence_threshold

    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        """
        确认验证：检查基础功能是否正常工作

        检查：
        1. 工具是否真正执行了
        2. 返回结果是否合理
        """
        tool_results = context.tool_results
        llm = context.llm_response
        goal = context.goal

        if not llm and not tool_results:
            return ValidationResult(
                broken=False,
                validator_name=self.name,
                reason="No LLM response or tool results to validate",
            )

        # 检查工具是否执行
        if tool_results:
            for tr in tool_results:
                tr_name = tr.get("name", "") if isinstance(tr, dict) else str(tr)
                tr_result = tr.get("result", None) if isinstance(tr, dict) else None
                # 检查是否有执行失败
                if tr_result and isinstance(tr_result, dict):
                    if tr_result.get("error") or tr_result.get("exception"):
                        return ValidationResult(
                            broken=True,
                            validator_name=self.name,
                            reason=f"工具 {tr_name} 执行失败",
                            evidence=str(tr_result),
                            severity="critical",
                        )

        # 检查LLM响应是否为空或过短
        if llm and len(llm.strip()) < 10:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason="LLM响应过短，可能未正常处理",
                evidence=f"响应长度: {len(llm)}",
                severity="warning",
            )

        return ValidationResult(
            broken=False,
            validator_name=self.name,
            reason="基础功能检查通过",
        )

    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破声明

        Args:
            claim: 声明文本
            context: AgentHookContext

        Returns:
            bool: 是否成功打破了该声明
        """
        # 分类声明
        claim_type = self.classify_claim(claim)

        if claim_type == self.CLAIM_TYPE_COMPLETION:
            return self.break_completion_claim(claim, context)
        elif claim_type == self.CLAIM_TYPE_FIX:
            return self.break_fix_claim(claim, context)
        elif claim_type == self.CLAIM_TYPE_TEST_PASS:
            return self.break_test_claim(claim, context)
        elif claim_type == self.CLAIM_TYPE_QUALITY:
            return self.break_quality_claim(claim, context)

        return False

    def break_quality_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破"质量/无问题"声明

        检查：
        1. 是否有隐藏的边界情况
        2. 是否有错误处理缺失

        Returns:
            bool: 是否打破了该声明
        """
        llm = context.llm_response
        tool_results = context.tool_results

        # 检查LLM响应中是否包含错误处理相关词汇
        error_handling_keywords = ["错误", "异常", "失败", "exception", "error", "failed"]
        has_error_handling = any(kw in llm.lower() for kw in error_handling_keywords)

        # 检查是否有工具执行但没有结果验证
        if tool_results and not has_error_handling:
            # 声称"无问题"但没有任何错误处理，可能是虚假声明
            return True

        return False

    def extract_claims(self, context: "AgentHookContext") -> list[str]:
        """
        从上下文中提取声明

        Returns:
            list[str]: 声明列表
        """
        claims: list[str] = []
        llm = context.llm_response

        if not llm:
            return claims

        for pattern in self.BREAKING_PATTERNS:
            for match in re.finditer(pattern, llm):
                # 提取完整句子
                start = max(0, match.start() - 30)
                end = min(len(llm), match.end() + 30)
                sentence = llm[start:end].strip()
                # 截取到标点
                for punct in ["。", "！", "？", "\n"]:
                    if punct in sentence:
                        sentence = sentence[:sentence.index(punct) + 1].strip()
                        break
                if sentence and sentence not in claims:
                    claims.append(sentence)

        return claims


# ─────────────────────────────────────────────────────────────────────────────
# SQLBoundaryValidator - SQL边界条件测试
# ─────────────────────────────────────────────────────────────────────────────

class SQLBoundaryValidator(BreakingValidator):
    """
    构造SQL边界条件来打破"SQL安全"的假设

    目的：验证SQL执行器是否正确处理了各种恶意/边界SQL。

    构造的边界条件：
    1. SQL注入：' OR '1'='1, '; DROP TABLE; --
    2. 超长输入：超长字符串（>10000字符）
    3. 空值处理：NULL, '', 空字符串
    4. 特殊字符：\\x00, \\n, \\r, Unicode特殊字符
    5. 数字溢出：超出INT/BIGINT范围
    6. 嵌套查询：多层子查询
    """

    name = "sql_boundary"
    enabled = True

    BOUNDARY_SQL_TEMPLATES = [
        ("sql_injection_or", "SELECT * FROM users WHERE id=1 OR 1=1"),
        ("sql_injection_union", "SELECT * FROM users WHERE id=1 UNION SELECT * FROM users"),
        ("sql_injection_drop", "'; DROP TABLE users; --"),
        ("long_string_10k", "SELECT * FROM users WHERE name='{}'".format("A" * 10000)),
        ("long_string_100k", "SELECT * FROM users WHERE name='{}'".format("A" * 100000)),
        ("null_compare", "SELECT * FROM users WHERE name=NULL"),
        ("empty_string", "SELECT * FROM users WHERE name=''"),
        ("int_overflow", "SELECT * FROM users WHERE id=99999999999999999999"),
        ("special_char_newline", "SELECT * FROM users WHERE name='test\\nadmin'"),
        ("special_char_null", "SELECT * FROM users WHERE name='test\\x00admin'"),
    ]

    def __init__(self, max_test_cases: int = 5):
        self.max_test_cases = max_test_cases

    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        """确认验证：检查基础SQL执行"""
        goal = context.goal.lower()
        tools = context.tools_to_execute

        is_sql_context = self._is_sql_context(goal, tools)
        if not is_sql_context:
            return ValidationResult(
                broken=False,
                validator_name=self.name,
                reason="Not a SQL context, skipping boundary test",
            )

        # 检查是否有明显安全问题
        llm = context.llm_response
        sql_claims = self._extract_sql_claims(llm)

        for sql in sql_claims[:self.max_test_cases]:
            result = self._test_sql_boundaries(sql)
            if result.broken:
                return result

        return ValidationResult(
            broken=False,
            validator_name=self.name,
            reason=f"Tested {len(sql_claims[:self.max_test_cases])} SQL claims, all passed boundary tests",
        )

    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """打破声明：检测到SQL相关声明时进行边界测试"""
        goal = context.goal.lower()

        # 如果声明涉及SQL但没有安全验证，则打破
        sql_keywords = ["sql", "query", "select", "insert", "update", "delete", "数据库"]
        if any(kw in goal for kw in sql_keywords):
            llm = context.llm_response
            # 检查LLM响应中是否有SQL但没有安全检查
            sql_pattern = r"(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\s+"
            if re.search(sql_pattern, llm, re.IGNORECASE):
                # 检查是否有参数绑定等安全措施
                if not re.search(r"(param|bind|escape|sanitize|\$\{|:\w+\})", llm, re.IGNORECASE):
                    return True  # 打破：涉及SQL但没有安全措施

        return False

    def _is_sql_context(self, goal: str, tools: list[dict]) -> bool:
        goal_lower = goal.lower()
        sql_keywords = ["sql", "query", "select", "insert", "update", "delete", "数据库"]
        return any(kw in goal_lower for kw in sql_keywords) or any(
            t.get("name", "").lower() in ["execute_sql", "query", "pg_query"]
            for t in tools
        )

    def _extract_sql_claims(self, text: str) -> list[str]:
        sql_pattern = r"(?:SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+[^\n;]{10,}"
        matches = re.findall(sql_pattern, text, re.IGNORECASE)
        return [m.strip() for m in matches if len(m) > 10]

    def _test_sql_boundaries(self, sql: str) -> ValidationResult:
        """对单条SQL进行边界条件测试"""
        dangerous_patterns = [
            (r"DROP\s+TABLE", "DROP TABLE detected"),
            (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "DELETE without WHERE"),
            (r"TRUNCATE", "TRUNCATE detected"),
            (r"'\s*OR\s+'1'\s*=\s*'1", "Classic SQL injection pattern"),
            (r"\bOR\s+1\s*=\s*1", "Classic OR 1=1 injection pattern"),
            (r"\bOR\s+\w+\s*=\s*\w+", "OR-based SQL injection pattern"),
        ]

        for pattern, reason in dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                return ValidationResult(
                    broken=True,
                    validator_name=self.name,
                    reason=reason,
                    evidence=sql[:100],
                    suggestion="请确认此SQL是否经过安全验证",
                    severity="critical",
                )

        return ValidationResult(broken=False, validator_name=self.name)


# ─────────────────────────────────────────────────────────────────────────────
# TokenOverBudgetValidator - Token预算检查
# ─────────────────────────────────────────────────────────────────────────────

class TokenOverBudgetValidator(Validator):
    """
    检查Token是否超预算

    目的：在after_iteration中检测token_count是否达到token_budget，
    触发记忆整合（Phase 2）或强制停止。
    """

    name = "token_over_budget"
    enabled = True

    WARNING_THRESHOLD = 0.8   # 80% 警告
    CRITICAL_THRESHOLD = 0.95  # 95% 强制整合

    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        token_count = context.token_count
        token_budget = context.token_budget
        iteration = context.iteration
        max_iterations = context.max_iterations

        if token_budget <= 0:
            return ValidationResult(broken=False, validator_name=self.name)

        ratio = token_count / token_budget

        if ratio >= self.CRITICAL_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"Token预算严重超限（{ratio:.0%}），必须触发记忆整合",
                evidence=f"token_count={token_count}, budget={token_budget}",
                suggestion="Phase 2: 触发Consolidator进行记忆整合",
                severity="critical",
            )

        if ratio >= self.WARNING_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"Token预算接近上限（{ratio:.0%}），建议触发记忆整合",
                evidence=f"token_count={token_count}, budget={token_budget}",
                suggestion="Phase 2: 考虑触发Consolidator",
                severity="warning",
            )

        # 检查迭代效率
        expected_iterations = min(max_iterations, 5)
        if iteration > expected_iterations and ratio < self.WARNING_THRESHOLD:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason=f"迭代效率低（迭代{iteration}次但token仅消耗{ratio:.0%}）",
                evidence=f"iteration={iteration}, token_ratio={ratio:.0%}",
                suggestion="考虑优化迭代策略",
                severity="info",
            )

        return ValidationResult(broken=False, validator_name=self.name)

    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """Token超预算声明"""
        return False  # Token超预算是确认模式，不是打破模式


# ─────────────────────────────────────────────────────────────────────────────
# CodeQualityValidator - 代码质量验证器
# ─────────────────────────────────────────────────────────────────────────────

class CodeQualityValidator(BreakingValidator):
    """
    代码质量验证器

    目的：检查代码是否有常见质量问题，并主动构造边界情况来打破"代码正确"的假设。

    检查维度：
    1. 内存泄漏：未关闭的资源、未释放的引用
    2. 边界情况：空值、极端值、类型错误
    3. 错误处理：缺少异常捕获、裸raise
    4. 安全问题：硬编码凭证、SQL注入风险
    """

    name = "code_quality"
    enabled = True

    # 代码质量声明模式
    QUALITY_CLAIM_PATTERNS = [
        r"代码正确",
        r"无内存泄漏",
        r"无问题",
        r"实现正确",
        r"符合规范",
        r"代码健壮",
        r"已优化",
    ]

    def __init__(self, check_memory_leak: bool = True, check_boundary: bool = True):
        self.check_memory_leak = check_memory_leak
        self.check_boundary = check_boundary

    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        """确认验证：检查代码质量基础问题"""
        tool_results = context.tool_results
        llm = context.llm_response

        issues: list[str] = []

        # 检查是否有代码修改
        has_code_change = False
        for tr in tool_results:
            tr_name = tr.get("name", "") if isinstance(tr, dict) else str(tr)
            if any(kw in tr_name.lower() for kw in ["write", "edit", "create", "modify", "file"]):
                has_code_change = True
                break

        if not has_code_change:
            return ValidationResult(
                broken=False,
                validator_name=self.name,
                reason="No code changes detected, skipping quality check",
            )

        # 检查LLM响应中的代码质量声明
        for pattern in self.QUALITY_CLAIM_PATTERNS:
            if re.search(pattern, llm, re.IGNORECASE):
                # 声称代码质量好，需要进一步验证
                break_result = self._check_quality_issues(llm, tool_results)
                if break_result.broken:
                    return break_result

        return ValidationResult(
            broken=False,
            validator_name=self.name,
            reason=f"Code quality issues found: {len(issues)}",
            evidence="; ".join(issues[:3]) if issues else "No obvious issues",
        )

    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破代码质量声明

        尝试构造：
        1. 内存泄漏场景
        2. 边界case失败
        3. 错误处理缺失

        Returns:
            bool: 是否打破了该声明
        """
        llm = context.llm_response

        # 检查claim或llm中是否有代码质量声明
        text_to_check = f"{claim} {llm}"
        has_quality_claim = any(
            re.search(p, text_to_check, re.IGNORECASE) for p in self.QUALITY_CLAIM_PATTERNS
        )

        if not has_quality_claim:
            return False

        # 尝试构造边界case
        tool_results = context.tool_results

        # 检查是否有资源管理代码
        if self.check_memory_leak:
            if not re.search(r"(close|flush|release|dispose|__del__|finally)", llm, re.IGNORECASE):
                # 有文件/网络操作但没有资源管理
                return True

        # 检查是否有边界情况处理
        if self.check_boundary:
            has_null_check = re.search(r"(if.*None|if.*==.*null|\btry\b|\bcatch\b)", llm, re.IGNORECASE)
            has_code = re.search(r"(def |class |import |async def )", llm)
            if has_code and not has_null_check:
                # 有代码但没有错误处理
                return True

        return False

    def _check_quality_issues(self, llm: str, tool_results: list) -> ValidationResult:
        """检查代码质量"""
        issues: list[str] = []

        # 检查裸异常捕获
        if re.search(r"except\s*:", llm):
            issues.append("发现裸except块（捕获所有异常）")

        # 检查硬编码凭证
        if re.search(r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]{8,}", llm, re.IGNORECASE):
            issues.append("发现可能的硬编码凭证")

        # 检查SQL拼接
        if re.search(r"(execute|query|cursor)\s*\([^)]*\+", llm, re.IGNORECASE):
            issues.append("发现SQL字符串拼接（注入风险）")

        if issues:
            return ValidationResult(
                broken=True,
                validator_name=self.name,
                reason="代码质量问题",
                evidence="; ".join(issues[:3]),
                suggestion="请修复以上代码质量问题",
                severity="warning",
            )

        return ValidationResult(broken=False, validator_name=self.name)
