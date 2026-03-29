"""真实zCloud API Client"""
import httpx
import time
from typing import Optional, Any
from src.real_api.auth import AuthProvider, APIKeyProvider, create_auth_provider
from src.real_api.config import RealAPIConfig, get_real_api_config
from src.real_api.routers import (
    instances, alerts, sessions, locks,
    sqls, replication, parameters, capacity,
    inspection, workorders,
)


class ZCloudRealClient:
    """
    真实zCloud API客户端
    
    接口设计原则：
    - 与 MockZCloudClient 保持接口一致
    - 支持 config 中 use_mock 开关切换
    - 保留 Mock 作为 fallback
    """
    
    def __init__(
        self,
        config: Optional[RealAPIConfig] = None,
        auth_provider: Optional[AuthProvider] = None,
    ):
        self.config = config or get_real_api_config()
        self._auth = auth_provider or self._create_auth()
        self._client: Optional[httpx.AsyncClient] = None
    
    def _create_auth(self) -> AuthProvider:
        """根据配置创建认证提供者"""
        return create_auth_provider({
            "auth_type": self.config.auth_type,
            "api_key": self.config.api_key,
            "api_key_header": self.config.api_key_header,
            "oauth_token_url": self.config.oauth_token_url,
            "oauth_client_id": self.config.oauth_client_id,
            "oauth_client_secret": self.config.oauth_client_secret,
            "oauth_scope": self.config.oauth_scope,
            "timeout": self.config.timeout,
        })
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建HTTP客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout),
                headers=await self._get_headers(),
            )
        return self._client
    
    async def _get_headers(self) -> dict:
        """获取HTTP头"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        headers.update(self._auth.get_auth_headers())
        return headers
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        retry: int = 0,
    ) -> dict:
        """统一请求方法"""
        client = await self._get_client()
        
        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
            )
            
            # 处理429限流
            if response.status_code == 429 and retry < self.config.max_retries:
                retry_after = float(response.headers.get("retry-after", 1))
                time.sleep(retry_after)
                return await self._request(method, path, params, json_data, retry + 1)
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401 and retry < 1:
                # Token过期，刷新后重试
                self._auth = self._create_auth()
                return await self._request(method, path, params, json_data, retry + 1)
            raise
        
        except httpx.RequestError as e:
            if retry < self.config.max_retries:
                time.sleep(0.5 * (retry + 1))
                return await self._request(method, path, params, json_data, retry + 1)
            raise
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    # ==================== 实例管理 ====================
    
    async def get_instance(self, instance_id: str) -> Optional[dict]:
        return await instances.get_instance(self, instance_id)
    
    async def list_instances(self, status: Optional[str] = None) -> list[dict]:
        return await instances.list_instances(self, status)
    
    async def get_instance_metrics(
        self,
        instance_id: str,
        metrics: Optional[list[str]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> dict:
        return await instances.get_instance_metrics(self, instance_id, metrics, start_time, end_time)
    
    # ==================== 告警管理 ====================
    
    async def get_alerts(
        self,
        instance_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        return await alerts.get_alerts(self, instance_id, severity, status, limit)
    
    async def get_alert_detail(self, alert_id: str) -> Optional[dict]:
        return await alerts.get_alert_detail(self, alert_id)
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str, comment: str = "") -> dict:
        return await alerts.acknowledge_alert(self, alert_id, acknowledged_by, comment)
    
    async def resolve_alert(self, alert_id: str, resolved_by: str, resolution: str, resolution_type: str = "fixed") -> dict:
        return await alerts.resolve_alert(self, alert_id, resolved_by, resolution, resolution_type)
    
    # ==================== 会话管理 ====================
    
    async def get_sessions(
        self,
        instance_id: str,
        limit: int = 20,
        filter_expr: Optional[str] = None,
    ) -> dict:
        return await sessions.get_sessions(self, instance_id, limit, filter_expr)
    
    async def get_session_detail(self, instance_id: str, sid: int, serial: int) -> dict:
        return await sessions.get_session_detail(self, instance_id, sid, serial)
    
    # ==================== 锁管理 ====================
    
    async def get_locks(self, instance_id: str, include_blocker: bool = True) -> dict:
        return await locks.get_locks(self, instance_id, include_blocker)
    
    # ==================== SQL监控 ====================
    
    async def get_slow_sql(
        self,
        instance_id: str,
        limit: int = 10,
        order_by: str = "elapsed_time",
    ) -> dict:
        return await sqls.get_slow_sql(self, instance_id, limit, order_by)
    
    async def get_sql_plan(self, sql_id: str, instance_id: Optional[str] = None) -> dict:
        return await sqls.get_sql_plan(self, sql_id, instance_id)
    
    # ==================== 复制状态 ====================
    
    async def get_replication_status(self, instance_id: str) -> dict:
        return await replication.get_replication_status(self, instance_id)
    
    # ==================== 参数管理 ====================
    
    async def get_parameters(self, instance_id: str, category: Optional[str] = None) -> dict:
        return await parameters.get_parameters(self, instance_id, category)
    
    async def update_parameter(self, instance_id: str, param_name: str, param_value: str) -> dict:
        return await parameters.update_parameter(self, instance_id, param_name, param_value)
    
    # ==================== 容量管理 ====================
    
    async def get_tablespaces(self, instance_id: str, tablespace_name: Optional[str] = None) -> dict:
        return await capacity.get_tablespaces(self, instance_id, tablespace_name)
    
    async def get_backup_status(self, instance_id: str, backup_type: Optional[str] = None) -> dict:
        return await capacity.get_backup_status(self, instance_id, backup_type)
    
    async def get_audit_logs(
        self,
        instance_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        operation_type: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        return await capacity.get_audit_logs(self, instance_id, start_time, end_time, operation_type, limit)
    
    # ==================== 巡检管理 ====================
    
    async def get_inspection_results(self, instance_id: str) -> dict:
        return await inspection.get_inspection_results(self, instance_id)
    
    async def trigger_inspection(self, instance_id: str) -> dict:
        return await inspection.trigger_inspection(self, instance_id)
    
    # ==================== 工单管理 ====================
    
    async def list_workorders(self, instance_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        return await workorders.list_workorders(self, instance_id, status)
    
    async def get_workorder_detail(self, workorder_id: str) -> dict:
        return await workorders.get_workorder_detail(self, workorder_id)
    
    # ==================== 健康检查 ====================
    
    async def health_check(self) -> dict:
        """API健康检查"""
        try:
            result = await self._request("GET", "/health")
            return {"status": "ok", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# 单例
_real_client: Optional[ZCloudRealClient] = None


def get_real_client() -> ZCloudRealClient:
    """获取真实API客户端单例"""
    global _real_client
    if _real_client is None:
        _real_client = ZCloudRealClient()
    return _real_client


def reset_real_client():
    """重置客户端（切换配置后调用）"""
    global _real_client
    if _real_client:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # 如果有running loop，用create_task
            loop.create_task(_real_client.close())
        except RuntimeError:
            # 没有running loop，用run_until_complete
            asyncio.get_event_loop().run_until_complete(_real_client.close())
    _real_client = None
