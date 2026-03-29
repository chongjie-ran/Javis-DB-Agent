"""管理界面 Dashboard 路由"""
import os
import time
import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "configs" / "config.yaml"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class ModeStatus(BaseModel):
    mode: str
    use_mock: bool
    base_url: str
    auth_type: Optional[str] = None
    api_key_configured: bool = False
    ollama_status: str = "unknown"
    timestamp: float


class SwitchRequest(BaseModel):
    mode: str  # "mock" | "real"


def load_api_config() -> dict:
    """加载API配置"""
    if not CONFIG_FILE.exists():
        raise HTTPException(status_code=500, detail=f"配置文件不存在: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_api_config(config: dict):
    """保存API配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.get("/", response_class=HTMLResponse)
async def dashboard_index():
    """Dashboard主页"""
    html_path = TEMPLATES_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="dashboard.html not found")
    return FileResponse(str(html_path))


@router.get("/status", response_model=ModeStatus)
async def get_status():
    """获取当前API模式状态"""
    config = load_api_config()
    javis_api = config.get("javis_api", {})
    real_api = config.get("javis_real_api", {})
    
    use_mock = javis_api.get("use_mock", True)
    
    # 检查Ollama状态
    ollama_status = "unknown"
    try:
        import httpx
        ollama_base = config.get("ollama", {}).get("base_url", "http://localhost:11434")
        response = httpx.get(f"{ollama_base}/api/tags", timeout=5)
        if response.status_code == 200:
            ollama_status = "connected"
        else:
            ollama_status = "error"
    except Exception:
        ollama_status = "disconnected"
    
    return ModeStatus(
        mode="Mock" if use_mock else "Real API",
        use_mock=use_mock,
        base_url=real_api.get("base_url", javis_api.get("base_url", "")) if not use_mock else javis_api.get("base_url", ""),
        auth_type=real_api.get("auth_type"),
        api_key_configured=bool(real_api.get("api_key")),
        ollama_status=ollama_status,
        timestamp=time.time(),
    )


@router.post("/switch")
async def switch_mode(request: SwitchRequest):
    """切换API模式"""
    config = load_api_config()
    
    if "javis_api" not in config:
        config["javis_api"] = {}
    
    if request.mode == "mock":
        config["javis_api"]["use_mock"] = True
        save_api_config(config)
        return {"success": True, "mode": "Mock", "message": "已切换到 Mock 模式"}
    
    elif request.mode == "real":
        # 验证真实API配置
        real_api = config.get("javis_real_api", {})
        if not real_api.get("base_url"):
            raise HTTPException(status_code=400, detail="真实API base_url 未配置，请先配置 javis_real_api.base_url")
        
        if real_api.get("auth_type") == "api_key" and not real_api.get("api_key"):
            raise HTTPException(status_code=400, detail="API Key 未配置，请先配置 javis_real_api.api_key")
        
        if real_api.get("auth_type") == "oauth2" and not real_api.get("oauth_client_id"):
            raise HTTPException(status_code=400, detail="OAuth2 client_id 未配置，请先配置 javis_real_api.oauth_client_id")
        
        config["javis_api"]["use_mock"] = False
        save_api_config(config)
        return {"success": True, "mode": "Real API", "message": "已切换到真实API模式"}
    
    raise HTTPException(status_code=400, detail=f"未知模式: {request.mode}")


@router.get("/health-check")
async def health_check():
    """健康检查"""
    config = load_api_config()
    javis_api = config.get("javis_api", {})
    use_mock = javis_api.get("use_mock", True)
    
    result = {
        "timestamp": time.time(),
        "mode": "Mock" if use_mock else "Real API",
        "checks": {},
    }
    
    # Ollama检查
    try:
        import httpx
        ollama_base = config.get("ollama", {}).get("base_url", "http://localhost:11434")
        r = httpx.get(f"{ollama_base}/api/tags", timeout=5)
        result["checks"]["ollama"] = "✅ connected" if r.status_code == 200 else f"❌ status {r.status_code}"
    except Exception as e:
        result["checks"]["ollama"] = f"❌ {str(e)}"
    
    if not use_mock:
        # 真实API检查
        real_api = config.get("javis_real_api", {})
        base_url = real_api.get("base_url", "")
        try:
            import httpx
            r = httpx.get(f"{base_url}/health", timeout=10)
            result["checks"]["real_api"] = "✅ connected" if r.status_code == 200 else f"⚠️ status {r.status_code}"
        except Exception as e:
            result["checks"]["real_api"] = f"❌ {str(e)}"
    else:
        result["checks"]["mock_api"] = "✅ running on localhost:18080"
    
    return result
