"""巡检管理 Router"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.real_api.client import JavisRealClient


async def get_inspection_results(client: "JavisRealClient", instance_id: str) -> dict:
    """GET /api/v1/inspection"""
    result = await client._request("GET", "/inspection", params={"instance_id": instance_id})
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def trigger_inspection(client: "JavisRealClient", instance_id: str) -> dict:
    """POST /api/v1/inspection/trigger"""
    result = await client._request("POST", "/inspection/trigger", json_data={"instance_id": instance_id})
    return result
