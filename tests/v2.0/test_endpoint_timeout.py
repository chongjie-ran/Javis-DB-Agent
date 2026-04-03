"""
端点超时测试 - 验证LLM响应超时时返回504

覆盖端点:
- POST /api/v1/chat
- POST /api/v1/diagnose
- POST /api/v1/analyze/sql
- POST /api/v1/inspect
- POST /api/v1/report

超时阈值: 30秒 (由 routes.py 中 _ENDPOINT_TIMEOUT 控制)
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import patch, AsyncMock

from src.llm.ollama_client import OllamaClient
from src.api import routes as api_routes
from src.main import app


# ============================================================================
# 慢响应 Mock (超过30s超时阈值)
# ============================================================================

async def slow_complete_35s(*args, **kwargs):
    """模拟慢LLM响应: 35秒 > 30秒超时阈值"""
    await asyncio.sleep(35)
    return "mocked_slow_response"


# ============================================================================
# Fixture: 重置全局 Orchestrator (每次测试获取新的mocked实例)
# ============================================================================

@pytest.fixture(autouse=True)
def reset_orchestrator():
    """每个测试前重置全局OrchestratorAgent实例，强制使用当前patched的LLM"""
    api_routes._orchestrator = None
    yield
    api_routes._orchestrator = None


# ============================================================================
# Fixture: App TestClient
# ============================================================================

@pytest.fixture
def client():
    """FastAPI TestClient"""
    from fastapi.testclient import TestClient
    return TestClient(app)


# ============================================================================
# 测试用例
# ============================================================================

class TestEndpointTimeout:
    """端点超时测试"""

    @pytest.mark.timeout(60)
    async def test_chat_timeout_returns_504(self, client):
        """POST /api/v1/chat - LLM超时应返回504"""
        with patch.object(OllamaClient, "complete", slow_complete_35s):
            response = client.post(
                "/api/v1/chat",
                json={
                    "message": "帮我分析这个告警",
                    "user_id": "test_user",
                    "context": {},
                },
            )
        assert response.status_code == 504, (
            f"Expected 504, got {response.status_code}: {response.text}"
        )
        assert "超时" in response.json().get("detail", "")

    @pytest.mark.timeout(60)
    async def test_diagnose_timeout_returns_504(self, client):
        """POST /api/v1/diagnose - LLM超时应返回504"""
        with patch.object(OllamaClient, "complete", slow_complete_35s):
            response = client.post(
                "/api/v1/diagnose",
                json={
                    "alert_id": "ALT-TEST-001",
                    "instance_id": "INS-TEST-001",
                    "context": {},
                },
            )
        assert response.status_code == 504, (
            f"Expected 504, got {response.status_code}: {response.text}"
        )
        assert "超时" in response.json().get("detail", "")

    @pytest.mark.timeout(60)
    async def test_analyze_sql_timeout_returns_504(self, client):
        """POST /api/v1/analyze/sql - LLM超时应返回504"""
        with patch.object(OllamaClient, "complete", slow_complete_35s):
            response = client.post(
                "/api/v1/analyze/sql",
                json={
                    "sql": "SELECT * FROM orders WHERE created_at > '2026-01-01'",
                    "instance_id": "INS-TEST-001",
                },
            )
        assert response.status_code == 504, (
            f"Expected 504, got {response.status_code}: {response.text}"
        )
        assert "超时" in response.json().get("detail", "")

    @pytest.mark.timeout(60)
    async def test_inspect_timeout_returns_504(self, client):
        """POST /api/v1/inspect - LLM超时应返回504"""
        with patch.object(OllamaClient, "complete", slow_complete_35s):
            response = client.post(
                "/api/v1/inspect",
                json={
                    "instance_ids": ["INS-TEST-001"],
                    "inspection_type": "quick",
                },
            )
        assert response.status_code == 504, (
            f"Expected 504, got {response.status_code}: {response.text}"
        )
        assert "超时" in response.json().get("detail", "")

    @pytest.mark.timeout(60)
    async def test_report_timeout_returns_504(self, client):
        """POST /api/v1/report - LLM超时应返回504"""
        with patch.object(OllamaClient, "complete", slow_complete_35s):
            response = client.post(
                "/api/v1/report",
                json={
                    "report_type": "summary",
                    "instance_id": "INS-TEST-001",
                    "data": "测试数据",
                },
            )
        assert response.status_code == 504, (
            f"Expected 504, got {response.status_code}: {response.text}"
        )
        assert "超时" in response.json().get("detail", "")
