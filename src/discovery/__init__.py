"""
Javis-DB-Agent 数据库发现模块

提供本地数据库实例的自动发现、识别、注册和管理能力。
"""

from .scanner import DatabaseScanner, DiscoveredInstance, DBType
from .identifier import DatabaseIdentifier, IdentifiedInstance
from .registry import LocalRegistry, ManagedInstance

__all__ = [
    # Scanner
    "DatabaseScanner",
    "DiscoveredInstance",
    "DBType",
    # Identifier
    "DatabaseIdentifier",
    "IdentifiedInstance",
    # Registry
    "LocalRegistry",
    "ManagedInstance",
]
