"""复制管理 Router"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.real_api.client import ZCloudRealClient


async def get_replication_status(client: "ZCloudRealClient", instance_id: str) -> dict:
    """GET /api/v1/replication"""
    result = await client._request("GET", "/replication", params={"instance_id": instance_id})
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
