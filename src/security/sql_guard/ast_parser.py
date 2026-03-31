"""SQL AST解析器 - 基于sqlglot"""
import sqlglot
from sqlglot import exp
from typing import Optional, List, Dict, Any, Set


class ASTParser:
    """SQL AST解析器，支持MySQL/PostgreSQL/Oracle/OceanBase"""

    # 支持的数据库方言
    SUPPORTED_DIALECTS = {"mysql", "postgresql", "oracle", "oceanbase"}

    # sqlglot方言映射
    DIALECT_MAP = {
        "mysql": "mysql",
        "postgresql": "postgres",
        "oracle": "oracle",
        "oceanbase": "mysql",  # OceanBase兼容MySQL
    }

    def __init__(self):
        self.supported_dialects = list(self.SUPPORTED_DIALECTS)

    def parse(self, sql: str, dialect: str = "mysql") -> Optional[exp.Expression]:
        """
        解析SQL为AST

        Args:
            sql: SQL语句
            dialect: 数据库类型 (mysql/postgresql/oracle/oceanbase)

        Returns:
            sqlglot Expression AST或None（解析失败时）
        """
        if not sql or not sql.strip():
            return None

        target_dialect = self.DIALECT_MAP.get(dialect.lower(), "mysql")
        try:
            return sqlglot.parse_one(sql.strip(), dialect=target_dialect)
        except Exception:
            return None

    def get_tables(self, sql: str, dialect: str = "mysql") -> List[str]:
        """
        提取SQL中引用的所有表名

        Args:
            sql: SQL语句
            dialect: 数据库类型

        Returns:
            表名列表（去重）
        """
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return []

        tables: Set[str] = set()
        for table in ast_node.find_all(exp.Table):
            if table.name:
                tables.add(table.name)
        return list(tables)

    def get_operations(self, sql: str, dialect: str = "mysql") -> List[str]:
        """
        提取SQL操作类型

        Returns:
            操作类型列表，如 ['SELECT', 'INSERT', 'WHERE']
        """
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return []

        ops: List[str] = []
        sql_upper = sql.strip().upper()

        # 基于AST节点类型判断
        if isinstance(ast_node, exp.Select):
            ops.append("SELECT")
        elif isinstance(ast_node, exp.Insert):
            ops.append("INSERT")
        elif isinstance(ast_node, exp.Update):
            ops.append("UPDATE")
        elif isinstance(ast_node, exp.Delete):
            ops.append("DELETE")
        elif isinstance(ast_node, exp.Create):
            ops.append("CREATE")
        elif isinstance(ast_node, exp.Drop):
            ops.append("DROP")
        elif isinstance(ast_node, exp.Alter):
            ops.append("ALTER")
        elif isinstance(ast_node, exp.TruncateTable):
            ops.append("TRUNCATE")
        elif isinstance(ast_node, exp.Grant):
            ops.append("GRANT")
        elif isinstance(ast_node, exp.Revoke):
            ops.append("REVOKE")
        elif isinstance(ast_node, exp.Set):
            ops.append("SET")
        elif isinstance(ast_node, exp.Copy):
            ops.append("COPY")

        # Command fallback: 检测关键字命令（sqlglot无法完全解析时）
        if isinstance(ast_node, exp.Command) or not ops:
            if "SHUTDOWN" in sql_upper:
                ops.append("SHUTDOWN")
            elif sql_upper.startswith("GRANT"):
                ops.append("GRANT")
            elif sql_upper.startswith("REVOKE"):
                ops.append("REVOKE")
            elif "ALTER SYSTEM" in sql_upper:
                ops.append("ALTER SYSTEM")
            elif sql_upper.startswith("TRUNCATE"):
                ops.append("TRUNCATE")
            elif sql_upper.startswith("DROP"):
                ops.append("DROP")

        # 附加信息
        if ast_node.find(exp.Where):
            ops.append("WHERE")
        if ast_node.find(exp.Join):
            ops.append("JOIN")
        if ast_node.find(exp.Union):
            ops.append("UNION")
        if ast_node.find(exp.Intersect):
            ops.append("INTERSECT")
        if ast_node.find(exp.Except):
            ops.append("EXCEPT")

        return ops

    def get_columns(self, sql: str, dialect: str = "mysql") -> List[str]:
        """
        提取SELECT语句中引用的列名

        Returns:
            列名列表
        """
        ast_node = self.parse(sql, dialect)
        if not ast_node or not isinstance(ast_node, exp.Select):
            return []

        cols: List[str] = []
        for col in ast_node.find_all(exp.Column):
            if col.name:
                cols.append(col.name)
        return cols

    def has_where_clause(self, sql: str, dialect: str = "mysql") -> bool:
        """检查SQL是否有WHERE子句"""
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return False
        return ast_node.find(exp.Where) is not None

    def has_limit_clause(self, sql: str, dialect: str = "mysql") -> bool:
        """检查SQL是否有LIMIT子句"""
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return False
        return ast_node.find(exp.Limit) is not None

    def is_read_only(self, sql: str, dialect: str = "mysql") -> bool:
        """判断SQL是否为只读（不修改数据）"""
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return False

        # 只读操作类型
        readonly_types = (
            exp.Select,
            exp.Show,
            exp.Subquery,
            exp.Table,
            exp.Analyze,  # ANALYZE orders (PostgreSQL statistics collection)
        )

        # Command类型需要按名称判断
        if isinstance(ast_node, exp.Command):
            cmd_upper = sql.strip().upper()
            # 非只读命令（优先级最高，即使以只读命令开头也要排除）
            non_readonly = {"EXPLAIN ANALYZE", "SET", "RESET"}
            if any(cmd_upper.startswith(n) for n in non_readonly):
                return False
            # 只读命令
            readonly_commands = {"EXPLAIN", "VACUUM", "ANALYZE"}
            if any(cmd_upper.startswith(c) for c in readonly_commands):
                return True

        return isinstance(ast_node, readonly_types)

    def get_subqueries(self, sql: str, dialect: str = "mysql") -> List[str]:
        """提取SQL中的子查询"""
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return []

        subqueries: List[str] = []
        for subquery in ast_node.find_all(exp.Subquery):
            if subquery.parent:
                subqueries.append(subquery.parent.sql(dialect=self.DIALECT_MAP.get(dialect, "mysql")))
        return subqueries

    def extract_parameters(self, sql: str, dialect: str = "mysql") -> List[str]:
        """提取SQL中的参数（?或%s或$1等）"""
        ast_node = self.parse(sql, dialect)
        if not ast_node:
            return []

        params: List[str] = []
        for param in ast_node.find_all((exp.Parameter, exp.Placeholder)):
            params.append(param.sql())
        return params
