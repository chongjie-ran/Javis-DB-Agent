"""SQL AST护栏模块

提供SQL AST解析、白名单模板匹配、危险SQL检测能力。
基于sqlglot库实现，支持MySQL/PostgreSQL/Oracle/OceanBase。
"""
from .ast_parser import ASTParser
from .sql_guard import SQLGuard, SQLGuardResult, SQLGuardStatus, RiskLevel
from .template_registry import TemplateRegistry, SQLTemplate

__all__ = [
    "ASTParser",
    "SQLGuard",
    "SQLGuardResult",
    "SQLGuardStatus",
    "RiskLevel",
    "TemplateRegistry",
    "SQLTemplate",
]
