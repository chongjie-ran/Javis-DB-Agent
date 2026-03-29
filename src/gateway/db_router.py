"""双引擎工具路由器
根据db_type路由工具到对应的引擎实现
"""
from typing import Optional, Callable, Any
from dataclasses import dataclass

from src.db.base import DBType, DBConnector, get_db_connector
from src.tools.base import BaseTool, ToolResult


@dataclass
class ToolExecutionContext:
    """工具执行上下文"""
    instance_id: str
    db_type: str  # mysql / postgresql
    host: str
    port: int
    username: str = ""
    password: str = ""
    # 缓存的连接器
    _db_connector: Optional[DBConnector] = None


class DualEngineToolExecutor:
    """双引擎工具执行器
    
    根据db_type路由到对应引擎的工具实现：
    - mysql: 使用MySQL工具
    - postgresql: 使用PostgreSQL工具
    
    同时维护DBConnector连接池，统一采集数据
    """
    
    def __init__(self):
        self._connectors: dict[str, DBConnector] = {}
        # 注册工具路由
        self._tool_routes: dict[str, tuple[str, str]] = {
            # tool_name: (mysql_handler, postgresql_handler)
            "query_session": ("query_mysql_session", "pg_session_analysis"),
            "query_lock": ("query_mysql_lock", "pg_lock_analysis"),
            "query_replication": ("query_mysql_replication", "pg_replication_status"),
            "query_disk_usage": ("query_mysql_capacity", "query_pg_capacity"),
            "query_instance_status": ("query_mysql_performance", "query_pg_performance"),
        }
    
    def get_db_connector(self, context: ToolExecutionContext) -> DBConnector:
        """获取指定db_type的连接器"""
        key = f"{context.instance_id}:{context.db_type}"
        
        if key not in self._connectors:
            connector = get_db_connector(
                db_type=context.db_type,
                host=context.host,
                port=context.port,
                username=context.username,
                password=context.password,
            )
            self._connectors[key] = connector
        
        return self._connectors[key]
    
    async def execute_tool(
        self,
        tool_name: str,
        params: dict,
        context: ToolExecutionContext,
        mysql_handler: Callable,
        postgres_handler: Callable,
    ) -> ToolResult:
        """执行工具，自动路由到对应引擎
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            context: 执行上下文（包含db_type）
            mysql_handler: MySQL处理器
            postgres_handler: PostgreSQL处理器
        
        Returns:
            ToolResult
        """
        # 获取数据库连接器
        db_connector = self.get_db_connector(context)
        
        # 构建工具执行上下文（传递给handler）
        tool_context = {
            "instance_id": context.instance_id,
            "db_type": context.db_type,
            "db_connector": db_connector,
            "session_id": params.get("session_id", ""),
            "user_id": params.get("user_id", ""),
        }
        
        # 根据db_type路由
        if context.db_type == "mysql":
            return await mysql_handler(params, tool_context)
        elif context.db_type == "postgresql":
            return await postgres_handler(params, tool_context)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported db_type: {context.db_type}",
            )
    
    def route_tool(self, tool_name: str, db_type: str) -> str:
        """路由工具到对应引擎的具体实现
        
        Args:
            tool_name: 通用工具名
            db_type: mysql / postgresql
        
        Returns:
            具体工具名
        """
        if tool_name not in self._tool_routes:
            return tool_name  # 无映射，直接使用原名
        
        mysql_tool, pg_tool = self._tool_routes[tool_name]
        return pg_tool if db_type == "postgresql" else mysql_tool
    
    def list_supported_tools(self, db_type: str) -> list[str]:
        """列出支持的工具"""
        return [
            tool for tool, (mysql_t, pg_t) in self._tool_routes.items()
            if db_type in ("mysql", "postgresql")
        ]
    
    async def close_all(self):
        """关闭所有连接"""
        for conn in self._connectors.values():
            await conn.close()
        self._connectors.clear()


# 全局实例
_executor: Optional[DualEngineToolExecutor] = None


def get_dual_engine_executor() -> DualEngineToolExecutor:
    global _executor
    if _executor is None:
        _executor = DualEngineToolExecutor()
    return _executor
