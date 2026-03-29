"""容量管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import JavisRealClient


async def get_tablespaces(
    client: "JavisRealClient",
    instance_id: str,
    tablespace_name: Optional[str] = None,
) -> dict:
    """GET /api/v1/capacity/tablespaces"""
    params = {"instance_id": instance_id}
    if tablespace_name:
        params["tablespace_name"] = tablespace_name
    result = await client._request("GET", "/capacity/tablespaces", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def get_backup_status(
    client: "JavisRealClient",
    instance_id: str,
    backup_type: Optional[str] = None,
) -> dict:
    """GET /api/v1/capacity/backups"""
    params = {"instance_id": instance_id}
    if backup_type:
        params["backup_type"] = backup_type
    result = await client._request("GET", "/capacity/backups", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def get_audit_logs(
    client: "JavisRealClient",
    instance_id: str,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    operation_type: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """GET /api/v1/capacity/audit_logs"""
    params = {"instance_id": instance_id, "limit": limit}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    if operation_type:
        params["operation_type"] = operation_type
    result = await client._request("GET", "/capacity/audit_logs", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
