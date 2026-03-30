"""SQL白名单模板注册表"""
import re
from typing import Dict, Set, Optional, List, Tuple
from dataclasses import dataclass, field
import sqlglot.expressions as exp


@dataclass
class SQLTemplate:
    """SQL模板定义"""
    name: str
    pattern: str  # 正则表达式
    is_regex: bool = True
    risk_level: str = "L1"  # L0-L5
    description: str = ""
    compiled: Optional[re.Pattern] = None

    def __post_init__(self):
        if self.is_regex and self.compiled is None:
            try:
                self.compiled = re.compile(self.pattern, re.IGNORECASE)
            except re.error:
                self.compiled = None


class TemplateRegistry:
    """SQL白名单模板注册表"""

    def __init__(self):
        self._templates: Dict[str, List[SQLTemplate]] = {
            "mysql": [],
            "postgresql": [],
            "oracle": [],
            "oceanbase": [],
        }
        self._init_default_templates()

    def _init_default_templates(self):
        """初始化默认白名单模板"""
        # MySQL白名单
        mysql_templates = [
            # 探活SQL
            SQLTemplate(
                name="probe_select_1",
                pattern=r"^\s*SELECT\s+1\s*$",
                risk_level="L0",
                description="探活SQL",
            ),
            # 基础SELECT
            SQLTemplate(
                name="select_all_from",
                pattern=r"SELECT\s+\*\s+FROM\s+\w+",
                risk_level="L1",
                description="SELECT * FROM单表",
            ),
            # 带WHERE的SELECT
            SQLTemplate(
                name="select_with_where",
                pattern=r"SELECT\s+.+\s+FROM\s+\w+\s+WHERE\s+.+",
                risk_level="L1",
                description="带WHERE条件的SELECT",
            ),
            # 带LIMIT的SELECT
            SQLTemplate(
                name="select_with_limit",
                pattern=r"SELECT\s+.+\s+FROM\s+\w+\s+LIMIT\s+\d+",
                risk_level="L1",
                description="带LIMIT的SELECT",
            ),
            # JOIN查询
            SQLTemplate(
                name="select_join",
                pattern=r"SELECT\s+.+\s+FROM\s+\w+\s+(INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+)?JOIN\s+\w+",
                risk_level="L1",
                description="多表JOIN查询",
            ),
            # COUNT查询
            SQLTemplate(
                name="count_query",
                pattern=r"SELECT\s+COUNT\s*\(.+\)\s+FROM\s+\w+",
                risk_level="L1",
                description="COUNT聚合查询",
            ),
            # EXPLAIN查询
            SQLTemplate(
                name="explain_query",
                pattern=r"EXPLAIN\s+.+",
                risk_level="L1",
                description="执行计划分析",
            ),
            # SHOW TABLES
            SQLTemplate(
                name="show_tables",
                pattern=r"SHOW\s+(TABLES|DATABASES|STATUS)",
                risk_level="L1",
                description="SHOW命令",
            ),
            # USE DATABASE
            SQLTemplate(
                name="use_database",
                pattern=r"USE\s+\w+",
                risk_level="L1",
                description="切换数据库",
            ),
            # DESC TABLE
            SQLTemplate(
                name="desc_table",
                pattern=r"(DESC|DESCRIBE)\s+\w+",
                risk_level="L1",
                description="表结构查看",
            ),
        ]

        # PostgreSQL白名单
        pg_templates = [
            SQLTemplate(
                name="probe_select_1",
                pattern=r"^\s*SELECT\s+1\s*$",
                risk_level="L0",
                description="探活SQL",
            ),
            SQLTemplate(
                name="select_all_from",
                pattern=r"SELECT\s+\*\s+FROM\s+\w+",
                risk_level="L1",
                description="SELECT * FROM单表",
            ),
            SQLTemplate(
                name="select_with_where",
                pattern=r"SELECT\s+.+\s+FROM\s+\w+\s+WHERE\s+.+",
                risk_level="L1",
                description="带WHERE条件的SELECT",
            ),
            SQLTemplate(
                name="select_limit_offset",
                pattern=r"SELECT\s+.+\s+FROM\s+\w+\s+(WHERE\s+.+\s+)?LIMIT\s+\d+(\s+OFFSET\s+\d+)?",
                risk_level="L1",
                description="带LIMIT/OFFSET的SELECT",
            ),
            SQLTemplate(
                name="pg_explain",
                pattern=r"(EXPLAIN|EXPLAIN\s+\(ANALYZE\s+(TRUE|FALSE|ON|OFF)\s*,?\s*)?(FORMAT\s+(TEXT|JSON|XML|yaml))\s*.+",
                risk_level="L1",
                description="PostgreSQL执行计划",
            ),
            SQLTemplate(
                name="pg_show",
                pattern=r"SHOW\s+\w+",
                risk_level="L1",
                description="PG SHOW命令",
            ),
            SQLTemplate(
                name="select_with_cte",
                pattern=r"WITH\s+.+\s+SELECT\s+.+\s+FROM\s+\w+",
                risk_level="L1",
                description="CTE查询",
            ),
        ]

        # Oracle白名单
        oracle_templates = [
            SQLTemplate(
                name="probe_select_1",
                pattern=r"^\s*SELECT\s+1\s+FROM\s+DUAL\s*$",
                risk_level="L0",
                description="Oracle探活SQL",
            ),
            SQLTemplate(
                name="select_from_dual",
                pattern=r"SELECT\s+.+\s+FROM\s+DUAL",
                risk_level="L1",
                description="Oracle DUAL表查询",
            ),
        ]

        # OceanBase（兼容MySQL）
        ob_templates = mysql_templates.copy()

        for t in mysql_templates:
            self.add_template("mysql", t)
        for t in pg_templates:
            self.add_template("postgresql", t)
        for t in oracle_templates:
            self.add_template("oracle", t)
        for t in ob_templates:
            self.add_template("oceanbase", t)

    def add_template(self, db_type: str, template: SQLTemplate):
        """添加白名单模板"""
        db_type = db_type.lower()
        if db_type not in self._templates:
            self._templates[db_type] = []
        self._templates[db_type].append(template)

    def remove_template(self, db_type: str, template_name: str) -> bool:
        """移除白名单模板"""
        db_type = db_type.lower()
        if db_type not in self._templates:
            return False
        self._templates[db_type] = [
            t for t in self._templates[db_type] if t.name != template_name
        ]
        return True

    def is_whitelisted(self, sql: str, db_type: str = "mysql") -> Tuple[bool, Optional[SQLTemplate]]:
        """
        检查SQL是否匹配白名单模板

        Returns:
            (is_matched, matched_template)
        """
        db_type = db_type.lower()
        templates = self._templates.get(db_type, [])

        # 先尝试精确匹配
        sql_stripped = sql.strip()
        for t in templates:
            if t.compiled and t.compiled.search(sql_stripped):
                return True, t

        return False, None

    def get_templates(self, db_type: str) -> List[SQLTemplate]:
        """获取指定数据库类型的所有模板"""
        return self._templates.get(db_type.lower(), [])

    def list_db_types(self) -> List[str]:
        """列出所有已注册的数据库类型"""
        return list(self._templates.keys())

    def clear_templates(self, db_type: Optional[str] = None):
        """清空模板注册表"""
        if db_type:
            self._templates[db_type.lower()] = []
        else:
            for k in self._templates:
                self._templates[k] = []
