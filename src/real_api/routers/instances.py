"""实例管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import ZCloudRealClient


async def get_instance(client: "ZCloudRealClient", instance_id: str) -> Optional[dict]:
    """GET /api/v1/instances/{instance_id}"""
    result = await client._request("GET", f"/instances/{instance_id}")
    if result.get("code") == 0:
        return result.get("data")
    return None


async def list_instances(client: "ZCloudRealClient", status: Optional[str] = None) -> list[dict]:
    """GET /api/v1/instances"""
    params = {}
    if status:
        params["status"] = status
    result = await client._request("GET", "/instances", params=params)
    if result.get("code") == 0:
        return result.get("data", [])
    return []


async def get_instance_metrics(
    client: "ZCloudRealClient",
    instance_id: str,
    metrics: Optional[list[str]] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
) -> dict:
    """GET /api/v1/instances/{instance_id}/metrics"""
    params = {}
    if metrics:
        params["metrics"] = ",".join(metrics)
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    result = await client._request("GET", f"/instances/{instance_id}/metrics", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
