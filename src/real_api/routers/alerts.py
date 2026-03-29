"""告警管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import JavisRealClient


async def get_alerts(
    client: "JavisRealClient",
    instance_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """GET /api/v1/alerts"""
    params = {"limit": limit}
    if instance_id:
        params["instance_id"] = instance_id
    if severity:
        params["severity"] = severity
    if status:
        params["status"] = status
    result = await client._request("GET", "/alerts", params=params)
    if result.get("code") == 0:
        return result.get("data", [])
    return []


async def get_alert_detail(client: "JavisRealClient", alert_id: str) -> Optional[dict]:
    """GET /api/v1/alerts/{alert_id}"""
    result = await client._request("GET", f"/alerts/{alert_id}")
    if result.get("code") == 0:
        return result.get("data")
    return None


async def acknowledge_alert(
    client: "JavisRealClient",
    alert_id: str,
    acknowledged_by: str,
    comment: str = "",
) -> dict:
    """POST /api/v1/alerts/{alert_id}/acknowledge"""
    result = await client._request(
        "POST",
        f"/alerts/{alert_id}/acknowledge",
        json_data={
            "acknowledged_by": acknowledged_by,
            "comment": comment,
        },
    )
    return result


async def resolve_alert(
    client: "JavisRealClient",
    alert_id: str,
    resolved_by: str,
    resolution: str,
    resolution_type: str = "fixed",
) -> dict:
    """POST /api/v1/alerts/{alert_id}/resolve"""
    result = await client._request(
        "POST",
        f"/alerts/{alert_id}/resolve",
        json_data={
            "resolved_by": resolved_by,
            "resolution": resolution,
            "resolution_type": resolution_type,
        },
    )
    return result
