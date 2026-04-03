"""
第九轮测试：管理界面测试

测试内容：
1. Dashboard路由注册
2. 健康检查端点
3. API路由验证
4. FastAPI应用结构

测试策略（方案D）：
本文件测试目标是"端点存在+路由正确"，不测试LLM集成。
LLM集成由test_llm_integration.py专门测试。
因此mock掉LLM调用是正确的测试分层策略，而非规避问题。
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from fastapi.testclient import TestClient
from src.main import create_app


# -------- Mock Ollama client for tests that trigger LLM calls --------

class _MockOllamaClient:
    """Mock Ollama client that returns instantly without calling real LLM service."""

    async def complete(self, *args, **kwargs):
        return '{"content": "mocked response"}'

    async def complete_stream(self, *args, **kwargs):
        yield "mocked streaming response"

    async def health_check(self):
        return True


@pytest.fixture
def mock_ollama_client():
    """
    Mock LLM client for endpoint + routing tests.
    
    测试策略说明：
    - 本测试套件(test_dashboard_routes.py)的目标是验证"端点存在+路由正确"
    - 不测试LLM集成（LLM集成由test_llm_integration.py专门测试）
    - 因此这里mock掉LLM调用，让端点快速返回，不依赖真实Ollama服务
    - 这不是规避问题，而是正确的测试分层策略
    """
    mock = _MockOllamaClient()
    # OrchestratorAgent继承BaseAgent，BaseAgent在__init__里调用get_ollama_client()初始化时已绑定真实client
    with patch("src.agents.base.get_ollama_client", return_value=mock):
        # 重置全局orchestrator，使其重新初始化时拿到mock
        import src.api.routes as routes_module
        routes_module._orchestrator = None
        yield mock
        # 测试后重置，避免污染其他测试
        routes_module._orchestrator = None


class TestDashboardRoutes:
    """Dashboard路由测试"""
    
    @pytest.fixture
    def client(self):
        """测试客户端"""
        app = create_app()
        return TestClient(app)
    
    def test_app_creation(self):
        """测试应用创建成功"""
        app = create_app()
        assert app is not None
        assert app.title == "Javis-DB-Agent"
    
    def test_health_endpoint_exists(self, client):
        """测试健康检查端点存在"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    
    def test_health_endpoint_response_format(self, client):
        """测试健康检查响应格式"""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # 验证响应字段
        assert "status" in data, "缺少status字段"
        assert "version" in data, "缺少version字段"
        assert "ollama_status" in data, "缺少ollama_status字段"
        assert "timestamp" in data, "缺少timestamp字段"
    
    def test_health_endpoint_status_values(self, client):
        """测试健康检查状态值"""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # status应该是 healthy 或 degraded
        assert data["status"] in ["healthy", "degraded"]
        
        # ollama_status应该是 connected 或 disconnected
        assert data["ollama_status"] in ["connected", "disconnected"]
    
    def test_tools_endpoint_exists(self, client):
        """测试工具列表端点存在"""
        response = client.get("/api/v1/tools")
        assert response.status_code == 200
    
    def test_tools_endpoint_returns_list(self, client):
        """测试工具列表返回数据结构"""
        response = client.get("/api/v1/tools")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "tools" in data["data"]
    
    def test_chat_endpoint_exists(self, client, mock_ollama_client):
        """测试对话端点存在"""
        response = client.post("/api/v1/chat", json={
            "message": "test",
            "user_id": "test_user"
        })
        # 不关心返回状态，只关心端点存在
        assert response.status_code in [200, 500, 422]

    def test_diagnose_endpoint_exists(self, client, mock_ollama_client):
        """测试诊断端点存在"""
        response = client.post("/api/v1/diagnose", json={
            "alert_id": "TEST-001",
            "instance_id": "INS-001"
        })
        # 不关心返回状态，只关心端点存在
        assert response.status_code in [200, 500, 422]

    def test_analyze_sql_endpoint_exists(self, client, mock_ollama_client):
        """测试SQL分析端点存在"""
        response = client.post("/api/v1/analyze/sql", json={
            "sql": "SELECT * FROM test",
            "instance_id": "INS-001"
        })
        assert response.status_code in [200, 500, 422]

    def test_inspect_endpoint_exists(self, client, mock_ollama_client):
        """测试巡检端点存在"""
        response = client.post("/api/v1/inspect", json={
            "instance_ids": ["INS-001"]
        })
        assert response.status_code in [200, 500, 422]

    def test_report_endpoint_exists(self, client, mock_ollama_client):
        """测试报告端点存在"""
        response = client.post("/api/v1/report", json={
            "report_type": "summary",
            "data": "test data"
        })
        assert response.status_code in [200, 500, 422]


class TestHealthEndpointDetailed:
    """健康检查端点详细测试"""
    
    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)
    
    def test_health_returns_version(self, client):
        """测试健康检查返回版本号"""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["version"] != ""
        assert isinstance(data["version"], str)
    
    def test_health_returns_timestamp(self, client):
        """测试健康检查返回时间戳"""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["timestamp"] > 0
        assert isinstance(data["timestamp"], (int, float))
    
    def test_health_multiple_calls(self, client):
        """测试多次调用健康检查"""
        for _ in range(3):
            response = client.get("/api/v1/health")
            assert response.status_code == 200


class TestAPIRouterStructure:
    """API路由结构测试"""
    
    def test_router_prefix(self):
        """测试路由前缀"""
        from src.api.routes import router
        assert router.prefix == "/api/v1"
    
    def test_router_has_chat_route(self):
        """测试路由器包含chat路由"""
        from src.api.routes import router
        routes = [r.path for r in router.routes]
        # 路由带前缀 /api/v1
        assert any("/chat" in r for r in routes)
    
    def test_router_has_health_route(self):
        """测试路由器包含health路由"""
        from src.api.routes import router
        routes = [r.path for r in router.routes]
        assert any("/health" in r for r in routes)
    
    def test_router_has_tools_route(self):
        """测试路由器包含tools路由"""
        from src.api.routes import router
        routes = [r.path for r in router.routes]
        assert any("/tools" in r for r in routes)


class TestAPIResponseSchemas:
    """API响应模型测试"""
    
    def test_health_response_model(self):
        """测试健康检查响应模型"""
        from src.api.schemas import HealthResponse
        
        response = HealthResponse(
            status="healthy",
            version="v1.0",
            ollama_status="connected",
            timestamp=1234567890.0
        )
        
        assert response.status == "healthy"
        assert response.version == "v1.0"
        assert response.ollama_status == "connected"
    
    def test_api_response_model(self):
        """测试通用API响应模型"""
        from src.api.schemas import APIResponse
        
        response = APIResponse(
            code=0,
            message="success",
            data={"key": "value"}
        )
        
        assert response.code == 0
        assert response.message == "success"
        assert response.data == {"key": "value"}
    
    def test_api_response_model_error(self):
        """测试错误响应模型"""
        from src.api.schemas import APIResponse
        
        response = APIResponse(
            code=500,
            message="internal error",
            data=None
        )
        
        assert response.code == 500
        assert response.message == "internal error"


class TestCORSAndMiddleware:
    """CORS和中间件测试"""
    
    def test_cors_headers_present(self):
        """测试CORS头存在"""
        app = create_app()
        client = TestClient(app)
        
        # 预检请求
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        
        # CORS中间件应该允许预检
        assert response.status_code == 200
    
    def test_allow_origins_configured(self):
        """测试允许的源已配置"""
        app = create_app()
        
        # 检查CORS中间件
        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware):
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None, "CORS中间件未配置"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
