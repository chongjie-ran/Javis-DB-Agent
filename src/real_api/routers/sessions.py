"""会话管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import JavisRealClient


async def get_sessions(
    client: "JavisRealClient",
    instance_id: str,
    limit: int = 20,
    filter_expr: Optional[str] = None,
) -> dict:
    """GET /api/v1/sessions"""
    params = {"instance_id": instance_id, "limit": limit}
    if filter_expr:
        params["filter"] = filter_expr
    result = await client._request("GET", "/sessions", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def get_session_detail(
    client: "JavisRealClient",
    instance_id: str,
    sid: int,
    serial: int,
) -> dict:
    """GET /api/v1/sessions/{sid}/{serial}"""
    result = await client._request("GET", f"/sessions/{sid}/{serial}", params={"instance_id": instance_id})
    if result.get("code") == 0:
        return result.get("data", {})
    return {}
