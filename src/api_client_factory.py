"""统一API客户端工厂 - 根据配置自动选择Mock或Real API"""
import os
import yaml
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.mock_api.zcloud_client import MockZCloudClient
    from src.real_api.client import ZCloudRealClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "configs", "config.yaml")


def load_api_config() -> dict:
    """从配置文件加载API配置"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def is_use_mock() -> bool:
    """检查是否使用Mock模式"""
    config = load_api_config()
    return config.get("zcloud_api", {}).get("use_mock", True)


class UnifiedZCloudClient:
    """
    统一API客户端 - 根据配置自动路由到Mock或Real API
    
    使用方式：
        from src.api_client_factory import get_unified_client
        
        client = get_unified_client()
        data = await client.get_instance("INS-001")
    
    配置切换：
        - use_mock: true  → 使用 MockZCloudClient（本地开发测试）
        - use_mock: false → 使用 ZCloudRealClient（连接真实zCloud）
    """
    
    def __init__(self):
        self._use_mock = is_use_mock()
        self._mock_client: Optional["MockZCloudClient"] = None
        self._real_client: Optional["ZCloudRealClient"] = None
    
    @property
    def use_mock(self) -> bool:
        return self._use_mock
    
    @property
    def _client(self):
        """获取当前活跃的客户端"""
        if self._use_mock:
            if self._mock_client is None:
                from src.mock_api.zcloud_client import get_mock_zcloud_client
                self._mock_client = get_mock_zcloud_client()
            return self._mock_client
        else:
            if self._real_client is None:
                from src.real_api.client import get_real_client
                self._real_client = get_real_client()
            return self._real_client
    
    def _reload_config(self):
        """重新加载配置（切换模式后调用）"""
        self._use_mock = is_use_mock()
        self._mock_client = None
        self._real_client = None
    
    # ==================== 实例管理 ====================
    
    async def get_instance(self, instance_id: str):
        return await self._client.get_instance(instance_id)
    
    async def list_instances(self, status: Optional[str] = None):
        return await self._client.list_instances(status)
    
    async def get_instance_metrics(self, instance_id: str, metrics: Optional[list] = None,
                                   start_time: Optional[float] = None, end_time: Optional[float] = None):
        return await self._client.get_instance_metrics(instance_id, metrics, start_time, end_time)
    
    # ==================== 告警管理 ====================
    
    async def get_alerts(self, instance_id: Optional[str] = None, severity: Optional[str] = None,
                         status: Optional[str] = None, limit: int = 50):
        return await self._client.get_alerts(instance_id, severity, status, limit)
    
    async def get_alert_detail(self, alert_id: str):
        return await self._client.get_alert_detail(alert_id)
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str, comment: str = ""):
        return await self._client.acknowledge_alert(alert_id, acknowledged_by, comment)
    
    async def resolve_alert(self, alert_id: str, resolved_by: str, resolution: str, resolution_type: str = "fixed"):
        return await self._client.resolve_alert(alert_id, resolved_by, resolution, resolution_type)
    
    # ==================== 会话管理 ====================
    
    async def get_sessions(self, instance_id: str, limit: int = 20, filter_expr: Optional[str] = None):
        return await self._client.get_sessions(instance_id, limit, filter_expr)
    
    async def get_session_detail(self, instance_id: str, sid: int, serial: int):
        return await self._client.get_session_detail(instance_id, sid, serial)
    
    # ==================== 锁管理 ====================
    
    async def get_locks(self, instance_id: str, include_blocker: bool = True):
        return await self._client.get_locks(instance_id, include_blocker)
    
    # ==================== SQL监控 ====================
    
    async def get_slow_sql(self, instance_id: str, limit: int = 10, order_by: str = "elapsed_time"):
        return await self._client.get_slow_sql(instance_id, limit, order_by)
    
    async def get_sql_plan(self, sql_id: str, instance_id: Optional[str] = None):
        return await self._client.get_sql_plan(sql_id, instance_id)
    
    # ==================== 复制状态 ====================
    
    async def get_replication_status(self, instance_id: str):
        return await self._client.get_replication_status(instance_id)
    
    # ==================== 参数管理 ====================
    
    async def get_parameters(self, instance_id: str, category: Optional[str] = None):
        return await self._client.get_parameters(instance_id, category)
    
    async def update_parameter(self, instance_id: str, param_name: str, param_value: str):
        return await self._client.update_parameter(instance_id, param_name, param_value)
    
    # ==================== 容量管理 ====================
    
    async def get_tablespaces(self, instance_id: str, tablespace_name: Optional[str] = None):
        return await self._client.get_tablespaces(instance_id, tablespace_name)
    
    async def get_backup_status(self, instance_id: str, backup_type: Optional[str] = None):
        return await self._client.get_backup_status(instance_id, backup_type)
    
    async def get_audit_logs(self, instance_id: str, start_time: Optional[float] = None,
                             end_time: Optional[float] = None, operation_type: Optional[str] = None, limit: int = 50):
        return await self._client.get_audit_logs(instance_id, start_time, end_time, operation_type, limit)
    
    # ==================== 巡检管理 ====================
    
    async def get_inspection_results(self, instance_id: str):
        return await self._client.get_inspection_results(instance_id)
    
    async def trigger_inspection(self, instance_id: str):
        return await self._client.trigger_inspection(instance_id)
    
    # ==================== 工单管理 ====================
    
    async def list_workorders(self, instance_id: Optional[str] = None, status: Optional[str] = None):
        return await self._client.list_workorders(instance_id, status)
    
    async def get_workorder_detail(self, workorder_id: str):
        return await self._client.get_workorder_detail(workorder_id)
    
    # ==================== 健康检查 ====================
    
    async def health_check(self):
        return await self._client.health_check()
    
    async def close(self):
        """关闭客户端"""
        if self._real_client:
            await self._real_client.close()


# 全局单例
_unified_client: Optional[UnifiedZCloudClient] = None


def get_unified_client() -> UnifiedZCloudClient:
    """获取统一API客户端单例"""
    global _unified_client
    if _unified_client is None:
        _unified_client = UnifiedZCloudClient()
    return _unified_client


def reset_unified_client():
    """重置客户端（切换配置后调用）"""
    global _unified_client
    if _unified_client:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_unified_client.close())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_unified_client.close())
            finally:
                loop.close()
    _unified_client = None
