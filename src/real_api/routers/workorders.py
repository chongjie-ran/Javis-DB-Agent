"""工单管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import ZCloudRealClient


async def list_workorders(
    client: "ZCloudRealClient",
    instance_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """GET /api/v1/workorders"""
    params = {}
    if instance_id:
        params["instance_id"] = instance_id
    if status:
        params["status"] = status
    result = await client._request("GET", "/workorders", params=params)
    if result.get("code") == 0:
        return result.get("data", [])
    return []


async def get_workorder_detail(client: "ZCloudRealClient", workorder_id: str) -> dict:
    """GET /api/v1/workorders/{workorder_id}"""
    result = await client._request("GET", f"/workorders/{workorder_id}")
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
