"""参数管理 Router"""
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.real_api.client import ZCloudRealClient


async def get_parameters(client: "ZCloudRealClient", instance_id: str, category: Optional[str] = None) -> dict:
    """GET /api/v1/parameters"""
    params = {"instance_id": instance_id}
    if category:
        params["category"] = category
    result = await client._request("GET", "/parameters", params=params)
    if result.get("code") == 0:
        return result.get("data", {})
    return {}


async def update_parameter(client: "ZCloudRealClient", instance_id: str, param_name: str, param_value: str) -> dict:
    """PUT /api/v1/parameters/{param_name}"""
    result = await client._request(
        "PUT",
        f"/parameters/{param_name}",
        json_data={"instance_id": instance_id, "value": param_value},
    )
    return result
