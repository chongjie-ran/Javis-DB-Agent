"""SQL监控 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import JavisRealClient


async def get_slow_sql(
    client: "JavisRealClient",
    instance_id: str,
    limit: int = 10,
    order_by: str = "elapsed_time",
) -> dict:
    """GET /api/v1/sqls/slow"""
    params = {"instance_id": instance_id, "limit": limit, "order_by": order_by}
    result = await client._request("GET", "/sqls/slow", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def get_sql_plan(client: "JavisRealClient", sql_id: str, instance_id: Optional[str] = None) -> dict:
    """GET /api/v1/sqls/{sql_id}/plan"""
    params = {}
    if instance_id:
        params["instance_id"] = instance_id
    result = await client._request("GET", f"/sqls/{sql_id}/plan", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
