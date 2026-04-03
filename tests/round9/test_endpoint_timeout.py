"""Round 9 测试：API端点超时行为测试

验证所有5个核心端点在LLM响应超时时统一返回HTTP 504：
- POST /api/v1/chat
- POST /api/v1/diagnose
- POST /api/v1/analyze/sql
- POST /api/v1/inspect
- POST /api/v1/report

行为要求：
- 超时统一抛出 HTTPException(status_code=504)
- 错误详情包含超时提示信息
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestEndpointTimeout:
    """测试5个核心API端点的超时行为一致性"""

    @pytest.fixture(autouse=True)
    def setup_app(self):
        """加载FastAPI应用"""
        # 延迟导入避免循环依赖
        from src.main import app
        self.client = TestClient(app)
        yield

    def _mock_slow_llm(self, delay_seconds: float = 35.0):
        """模拟慢速LLM响应（超过30秒超时阈值）"""
        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(delay_seconds)
            return {"response": "should not reach here"}

        return slow_generate

    # ==================== /chat 端点超时测试 ====================

    def test_chat_endpoint_timeout_returns_504(self):
        """POST /api/v1/chat 超时时返回504"""
        payload = {
            "message": "查看实例状态",
            "user_id": "test_user",
            "session_id": None,
            "context": {},
        }

        with patch("src.llm.ollama_client.OllamaClient.generate", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/chat", json=payload)

            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"
            assert "超时" in response.json().get("detail", "") or \
                   "timeout" in response.json().get("detail", "").lower(), \
                f"Expected timeout message in detail, got: {response.json()}"

    def test_chat_endpoint_normal_returns_200(self):
        """POST /api/v1/chat 正常响应返回200"""
        payload = {
            "message": "查看实例状态",
            "user_id": "test_user",
            "session_id": None,
            "context": {},
        }

        mock_response = MagicMock()
        mock_response.content = "实例运行正常"
        mock_response.metadata = {"agent": "orchestrator"}

        with patch("src.agents.orchestrator.OrchestratorAgent.handle_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            response = self.client.post("/api/v1/chat", json=payload)

            assert response.status_code == 200, \
                f"Expected 200, got {response.status_code}: {response.text}"

    # ==================== /diagnose 端点超时测试 ====================

    def test_diagnose_endpoint_timeout_returns_504(self):
        """POST /api/v1/diagnose 超时时返回504"""
        payload = {
            "alert_id": "ALT-001",
            "instance_id": "INS-001",
            "context": {},
        }

        with patch("src.agents.orchestrator.OrchestratorAgent.handle_diagnose", new_callable=AsyncMock) as mock_diag:
            mock_diag.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/diagnose", json=payload)

            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"
            assert "超时" in response.json().get("detail", "") or \
                   "timeout" in response.json().get("detail", "").lower(), \
                f"Expected timeout message in detail, got: {response.json()}"

    # ==================== /analyze/sql 端点超时测试 ====================

    def test_analyze_sql_endpoint_timeout_returns_504(self):
        """POST /api/v1/analyze/sql 超时时返回504"""
        payload = {
            "sql": "SELECT * FROM users WHERE id = 1",
            "instance_id": "INS-001",
            "session_id": None,
        }

        with patch("src.agents.sql_analyzer.SQLAnalyzerAgent.analyze_sql", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/analyze/sql", json=payload)

            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"
            assert "超时" in response.json().get("detail", "") or \
                   "timeout" in response.json().get("detail", "").lower(), \
                f"Expected timeout message in detail, got: {response.json()}"

    # ==================== /inspect 端点超时测试 ====================

    def test_inspect_endpoint_timeout_returns_504(self):
        """POST /api/v1/inspect 超时时返回504（与其他端点行为一致）

        修复前：超时时追加到results继续执行（行为不一致，Bug）
        修复后：超时时抛出HTTPException 504（与其他端点一致）
        """
        payload = {
            "instance_ids": ["INS-001", "INS-002"],
        }

        with patch("src.agents.inspector.InspectorAgent.inspect_instance", new_callable=AsyncMock) as mock_inspect:
            # 模拟第一个实例超时
            mock_inspect.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/inspect", json=payload)

            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"
            assert "超时" in response.json().get("detail", "") or \
                   "timeout" in response.json().get("detail", "").lower(), \
                f"Expected timeout message in detail, got: {response.json()}"

    def test_inspect_endpoint_partial_timeout_still_fails_504(self):
        """POST /api/v1/inspect 多个实例中任一超时也应返回504

        验证多实例场景：第一个实例超时，后续实例不应继续执行
        """
        payload = {
            "instance_ids": ["INS-001", "INS-002", "INS-003"],
        }

        call_count = 0

        async def partial_slow(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            # 如果第一个超时后继续执行第二个，说明Bug未修复
            await asyncio.sleep(0.1)
            mock_resp = MagicMock()
            mock_resp.content = f"instance-{call_count}"
            return mock_resp

        with patch("src.agents.inspector.InspectorAgent.inspect_instance", new_callable=AsyncMock) as mock_inspect:
            mock_inspect.side_effect = partial_slow
            response = self.client.post("/api/v1/inspect", json=payload)

            # 如果Bug存在，第一个超时后会继续执行第二个，call_count会大于1
            assert call_count == 1, \
                f"Expected 1 call (first timeout stops execution), got {call_count} calls"
            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"

    # ==================== /report 端点超时测试 ====================

    def test_report_endpoint_timeout_returns_504(self):
        """POST /api/v1/report 超时时返回504"""
        payload = {
            "report_type": "summary",
            "data": "summary data here",
            "instance_id": "INS-001",
            "incident_id": None,
        }

        with patch("src.agents.reporter.ReporterAgent.generate_summary", new_callable=AsyncMock) as mock_report:
            mock_report.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/report", json=payload)

            assert response.status_code == 504, \
                f"Expected 504, got {response.status_code}: {response.text}"
            assert "超时" in response.json().get("detail", "") or \
                   "timeout" in response.json().get("detail", "").lower(), \
                f"Expected timeout message in detail, got: {response.json()}"

    # ==================== 超时边界条件测试 ====================

    def test_timeout_message_contains_service_hint(self):
        """所有504响应错误详情应包含Ollama服务提示"""
        payload = {
            "message": "查看状态",
            "user_id": "test_user",
        }

        with patch("src.agents.orchestrator.OrchestratorAgent.handle_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = asyncio.TimeoutError()
            response = self.client.post("/api/v1/chat", json=payload)

            detail = response.json().get("detail", "").lower()
            # 错误信息应提示检查Ollama服务
            assert "ollama" in detail or "服务" in detail, \
                f"Expected Ollama service hint in error detail, got: {detail}"


class TestTimeoutConfiguration:
    """测试超时配置一致性"""

    def test_all_endpoints_use_same_timeout_value(self):
        """验证所有端点使用相同的30秒超时配置"""
        from src.api.routes import _ENDPOINT_TIMEOUT

        assert _ENDPOINT_TIMEOUT == 30.0, \
            f"Expected timeout 30.0s, got {_ENDPOINT_TIMEOUT}s"

    def test_timeout_error_detail_format_consistent(self):
        """验证超时错误详情格式一致"""
        expected_phrases = ["30s", "超时"]

        # 从routes.py源码检查所有端点是否使用相同的错误格式
        import inspect
        from src.api import routes

        source = inspect.getsource(routes)

        # 统计各端点的超时错误信息
        chat_detail = '请检查Ollama服务或稍后重试'
        diagnose_detail = '请检查Ollama服务或稍后重试'
        analyze_detail = '请检查Ollama服务或稍后重试'
        inspect_detail = '请检查Ollama服务或稍后重试'
        report_detail = '请检查Ollama服务或稍后重试'

        # 确认所有端点使用相同的错误详情模板
        assert source.count(chat_detail) >= 5, \
            "Expected 5 endpoints with same timeout error detail format"
