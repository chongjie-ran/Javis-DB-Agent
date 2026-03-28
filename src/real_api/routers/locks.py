"""锁管理 Router"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.real_api.client import ZCloudRealClient


async def get_locks(client: "ZCloudRealClient", instance_id: str, include_blocker: bool = True) -> dict:
    """GET /api/v1/locks"""
    params = {"instance_id": instance_id, "include_blocker": include_blocker}
    result = await client._request("GET", "/locks", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
