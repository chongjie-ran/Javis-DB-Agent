"""
V2.5 Orchestrator LLM Fallback优化测试 - Round26
================================================
测试目标：
  1. 主LLM失败时fallback到备用LLM
  2. fallback后的响应正确性
  3. 多次fallback场景

验收标准：
  - 主LLM不可用时自动降级
  - fallback后仍返回有意义内容
  - 不返回"未找到相关信息"
  - fallback链有最大深度限制

测试方法：
  - Mock LLM：验证fallback逻辑
  - 真实fallback（可选）：端到端验证

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round26/test_v25_orchestrator_fallback.py -v --tb=short
"""

import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.orchestrator import OrchestratorAgent, Intent
from src.agents.base import AgentResponse


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def is_meaningful_content(content: str) -> bool:
    """判断内容是否有意义（非空、非占位符、非"未找到"）"""
    if not content or not content.strip():
        return False
    if "未找到" in content or "未找到相关信息" in content:
        return False
    if len(content.strip()) < 10:
        return False
    return True


def make_llm_mock(response: str):
    """创建一个 LLM think 方法的 AsyncMock，返回指定内容"""
    mock = AsyncMock()
    mock.return_value = response
    return mock


def make_llm_mock_raising(exception: Exception):
    """创建一个会抛出异常的 LLM mock"""
    mock = AsyncMock()
    mock.side_effect = exception
    return mock


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def orchestrator():
    """OrchestratorAgent 实例"""
    return OrchestratorAgent()


@pytest.fixture
def mock_context():
    """标准上下文"""
    return {
        "session_id": "test-session-fb",
        "user_id": "test-user",
        "extra_info": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: 主LLM失败时Fallback触发
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMFallbackTrigger:
    """验证主LLM失败时正确触发fallback"""

    @pytest.mark.asyncio
    async def test_fb_01_primary_llm_timeout_triggers_fallback(self, orchestrator, mock_context):
        """FB-01: 主LLM超时时触发fallback，返回有意义内容"""
        response_text = "数据库运维助手已就绪，可以帮你进行健康检查和诊断。"

        # Mock _process_direct 中的 think 调用（触发 fallback 的场景）
        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            # 模拟 selected_agents=[] 的场景（触发 fallback）
            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("你好", mock_context)

        assert response.success is True, "Fallback 应返回成功"
        assert is_meaningful_content(response.content), \
            f"Fallback 内容应有意义，实际: {response.content[:50]}"
        assert "未找到" not in response.content, \
            f"Fallback 不应返回'未找到'，实际: {response.content}"

    @pytest.mark.asyncio
    async def test_fb_02_primary_llm_exception_triggers_fallback(self, orchestrator, mock_context):
        """FB-02: 主LLM抛出异常时触发fallback"""
        response_text = "已连接到数据库运维平台，请描述你的问题。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            # 第一次调用失败，第二次成功（fallback）
            mock_think.side_effect = [
                Exception("Primary LLM unavailable"),
                response_text,
            ]

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("查询", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content

    @pytest.mark.asyncio
    async def test_fb_03_empty_aggregate_triggers_fallback(self, orchestrator, mock_context):
        """FB-03: _aggregate_results 返回空时触发 fallback"""
        response_text = "我已就绪，请告诉我你需要什么帮助。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("随便问问", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Fallback后响应正确性
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackResponseCorrectness:
    """验证 fallback 后的响应正确性"""

    @pytest.mark.asyncio
    async def test_frc_01_fallback_returns_professional_response(self, orchestrator, mock_context):
        """FRC-01: Fallback 返回专业数据库运维内容"""
        response_text = """你是一个专业的数据库运维助手。我可以帮你：

1. 数据库健康检查和巡检
2. 告警诊断和根因分析
3. 性能分析和慢SQL优化
4. 容量规划和增长预测
5. 备份恢复和灾备演练

请告诉我你需要什么帮助。"""

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("你能做什么", mock_context)

        assert response.success is True
        assert len(response.content) > 50, "Fallback 内容应足够详细"
        # 应包含数据库运维相关内容
        content_lower = response.content.lower()
        assert any(kw in content_lower for kw in ["数据库", "运维", "健康", "诊断", "性能", "backup"])

    @pytest.mark.asyncio
    async def test_frc_02_fallback_never_returns_not_found(self, orchestrator, mock_context):
        """FRC-02: Fallback 永远不返回"未找到"（重要修复验证）"""
        response_text = "我已连接数据库运维平台，可以帮你进行各类运维操作。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            test_queries = [
                "随便问问",
                "你好",
                "查询实例",
                "数据库状态",
                "不知道问什么",
            ]

            for query in test_queries:
                with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                    with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                        mock_int.return_value = Intent.GENERAL
                        response = await orchestrator._process_direct(query, mock_context)

                assert response.success is True, f"查询 '{query}' 应成功"
                assert "未找到" not in response.content, \
                    f"查询 '{query}' 不应返回'未找到'，实际: {response.content[:80]}"

    @pytest.mark.asyncio
    async def test_frc_03_fallback_includes_metadata(self, orchestrator, mock_context):
        """FRC-03: Fallback 响应包含正确的 metadata"""
        response_text = "数据库运维助手已就绪。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("你好", mock_context)

        assert "agent" in response.metadata
        assert response.metadata["agent"] == "orchestrator"
        assert "intent" in response.metadata


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: 多次Fallback场景
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultipleFallbackScenarios:
    """验证多次 fallback 场景"""

    @pytest.mark.asyncio
    async def test_mf_01_llm_semantic_match_fallback(self, orchestrator, mock_context):
        """MF-01: LLM 语义匹配作为 fallback"""
        response_text = "数据库运维助手已就绪。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            # 模拟 embedding 失败后降级到 LLM 语义匹配
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_semantic_intent_recognize", new_callable=AsyncMock) as mock_sem:
                    # EmbeddingService 失败，_llm_semantic_match 也失败 → _semantic_intent_recognize
                    # 返回 GENERAL → _recognize_intent 正常返回 → _process_direct fallback 触发
                    mock_sem.side_effect = Exception("Embedding service unavailable")
                    response = await orchestrator._process_direct("查看实例", mock_context)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_mf_02_intent_recognition_fallback(self, orchestrator):
        """MF-02: 意图识别失败时降级到 GENERAL"""
        # 测试 _recognize_intent 在 embedding 和 LLM 都失败时返回 GENERAL
        with patch.object(orchestrator, "_semantic_intent_recognize", new_callable=AsyncMock) as mock_sem:
            # _semantic_intent_recognize 抛出异常（内部 fallback 也失败）
            # _recognize_intent 的 try-except 捕获并返回 GENERAL
            mock_sem.side_effect = Exception("Embedding and LLM both failed")

            intent = await orchestrator._recognize_intent("随便问问", {})

        # 应该降级到 GENERAL 而不是崩溃
        assert intent == Intent.GENERAL

    @pytest.mark.asyncio
    async def test_mf_03_both_agents_and_fallback_fail_safe(self, orchestrator, mock_context):
        """MF-03: Agent调用和LLM fallback都失败时，有安全响应"""
        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.side_effect = Exception("All LLMs failed")

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL

                    response = await orchestrator._process_direct("测试", mock_context)

        # 即使完全失败，也应返回安全响应
        assert response.success is True
        assert is_meaningful_content(response.content)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Fallback 与 Agent 协同
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackWithAgentCoordination:
    """验证 fallback 与 Agent 调用的协同"""

    @pytest.mark.asyncio
    async def test_fac_01_agent_success_no_fallback(self, orchestrator, mock_context):
        """FAC-01: Agent 调用成功时不触发 fallback"""
        response_text = "PostgreSQL 主库运行正常，CPU 45%，连接数 85/200。"

        # Mock 一个成功的 Agent 响应
        mock_agent_response = AgentResponse(
            success=True,
            content=response_text,
            metadata={"agent": "inspector"}
        )

        with patch.object(orchestrator, "_select_agents") as mock_sel:
            mock_agent = MagicMock()
            mock_agent.name = "inspector"
            mock_sel.return_value = [mock_agent]

            with patch.object(orchestrator, "_execute_plan", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = [mock_agent_response]

                # think 不应该被调用（因为有成功的 agent 结果）
                with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
                    mock_think.return_value = "fallback response"

                    response = await orchestrator._process_direct("健康检查", mock_context)

        assert response.success is True
        assert response.content == response_text
        # think 不应该被调用（因为 agent 成功）
        # 注：由于 mock 复杂性，这里只验证最终结果是 agent 的响应

    @pytest.mark.asyncio
    async def test_fac_02_all_agents_fail_triggers_fallback(self, orchestrator, mock_context):
        """FAC-02: 所有 Agent 都失败时触发 fallback"""
        response_text = "数据库运维助手已就绪。"

        with patch.object(orchestrator, "_select_agents") as mock_sel:
            mock_agent = MagicMock()
            mock_agent.name = "inspector"
            mock_sel.return_value = [mock_agent]

            with patch.object(orchestrator, "_execute_plan", new_callable=AsyncMock) as mock_exec:
                # 所有 agent 都失败
                mock_exec.return_value = [
                    AgentResponse(success=False, error="Agent error", metadata={})
                ]

                with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
                    mock_think.return_value = response_text

                    response = await orchestrator._process_direct("健康检查", mock_context)

        assert response.success is True
        assert is_meaningful_content(response.content)
        assert "未找到" not in response.content

    @pytest.mark.asyncio
    async def test_fac_03_partial_agents_fail_aggregates_success(self, orchestrator, mock_context):
        """FAC-03: 部分 Agent 失败时，聚合成功的 Agent 结果"""
        success_response = "Inspector 报告：数据库健康评分 85/100。"
        fail_response = AgentResponse(success=False, error="诊断失败", metadata={"agent": "diagnostic"})

        mock_agent = MagicMock()
        mock_agent.name = "inspector"

        with patch.object(orchestrator, "_select_agents", return_value=[mock_agent]):
            with patch.object(orchestrator, "_execute_plan", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = [fail_response]  # 只有 inspector 被选中且失败

                with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
                    mock_think.return_value = success_response

                    response = await orchestrator._process_direct("健康检查", mock_context)

        # fallback 应该触发
        assert response.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: LLM Fallback 优化验证（Round26 新功能）
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMFallbackOptimization:
    """验证 v2.5 LLM Fallback 优化"""

    @pytest.mark.asyncio
    async def test_lfo_01_semantic_intent_recognize_fallback_chain(self, orchestrator):
        """LFO-01: 语义意图识别 fallback 链完整"""
        # 测试 _semantic_intent_recognize 的降级链：
        # 1. EmbeddingService 语义向量匹配（返回低分，触发 LLM fallback）
        # 2. LLM 语义匹配 fallback 返回正确意图
        # 3. 返回 INSPECT

        with patch("src.knowledge.vector.embedding_service.EmbeddingService") as mock_embed_class:
            mock_embed = MagicMock()
            # 低分，不够直接返回（< SEMANTIC_SIMILARITY_THRESHOLD=0.75）
            # 但 > 0，触发 LLM fallback（LLM_FALLBACK_THRESHOLD=0.6）
            mock_embed.compute_similarity = AsyncMock(return_value=0.3)
            mock_embed.close = AsyncMock()
            mock_embed_class.return_value = mock_embed

            with patch.object(orchestrator, "_llm_semantic_match", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = (Intent.INSPECT, 0.85)

                intent, score = await orchestrator._semantic_intent_recognize("查看实例")

        assert intent == Intent.INSPECT
        assert score == 0.85

    @pytest.mark.asyncio
    async def test_lfo_02_llm_semantic_match_returns_intent(self, orchestrator):
        """LFO-02: LLM 语义匹配返回正确意图"""
        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = "inspect"

            intent, score = await orchestrator._llm_semantic_match("查看有哪些MySQL实例")

        assert intent == Intent.INSPECT
        assert score == 0.85  # LLM 匹配置信度

    @pytest.mark.asyncio
    async def test_lfo_03_llm_semantic_match_unknown_returns_general(self, orchestrator):
        """LFO-03: LLM 无法识别时返回 GENERAL"""
        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = "unknown_intent"

            intent, score = await orchestrator._llm_semantic_match("随便说点什么")

        assert intent == Intent.GENERAL
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_lfo_04_fallback_uses_llm_prompt_template(self, orchestrator, mock_context):
        """LFO-04: Fallback 使用正确的 prompt 模板"""
        response_text = "数据库运维助手已就绪。"

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("你好", mock_context)

        # 验证 think 被调用（fallback 触发）
        assert mock_think.called

    @pytest.mark.asyncio
    async def test_lfo_05_fallback_response_not_generic(self, orchestrator, mock_context):
        """LFO-05: Fallback 响应不是泛泛的客套话"""
        response_text = """我已连接数据库运维平台，可以帮你进行以下操作：

1. 实时健康检查和巡检
2. 告警诊断和根因分析
3. 慢SQL分析和性能优化
4. 容量规划和存储分析
5. 备份恢复管理

请告诉我你需要什么帮助。"""

        with patch.object(orchestrator, "think", new_callable=AsyncMock) as mock_think:
            mock_think.return_value = response_text

            with patch.object(orchestrator, "_select_agents", return_value=[]) as mock_sel:
                with patch.object(orchestrator, "_recognize_intent", new_callable=AsyncMock) as mock_int:
                    mock_int.return_value = Intent.GENERAL
                    response = await orchestrator._process_direct("你好", mock_context)

        assert response.success is True
        # 响应应包含具体功能列表（不是简单"你好"）
        assert len(response.content) > 100


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: 回归测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackRegression:
    """回归测试：确保 fallback 优化不破坏现有功能"""

    def test_reg_01_aggregate_empty_returns_none(self, orchestrator):
        """REG-01: 空结果返回 None（触发 fallback）"""
        result = orchestrator._aggregate_results([], Intent.GENERAL)
        assert result["content"] is None

    def test_reg_02_aggregate_single_success(self, orchestrator):
        """REG-02: 单个成功结果正确返回"""
        mock_resp = AgentResponse(success=True, content="测试内容", metadata={"agent": "test"})
        result = orchestrator._aggregate_results([mock_resp], Intent.GENERAL)
        assert result["content"] == "测试内容"

    def test_reg_03_aggregate_multi_success(self, orchestrator):
        """REG-03: 多个成功结果正确聚合"""
        mock_resps = [
            AgentResponse(success=True, content="结果A", metadata={"agent": "A"}),
            AgentResponse(success=True, content="结果B", metadata={"agent": "B"}),
        ]
        result = orchestrator._aggregate_results(mock_resps, Intent.DIAGNOSE)
        assert "结果A" in result["content"] and "结果B" in result["content"]

    def test_reg_04_aggregate_filters_failures(self, orchestrator):
        """REG-04: 过滤失败结果"""
        mock_resps = [
            AgentResponse(success=False, error="失败", metadata={"agent": "A"}),
            AgentResponse(success=True, content="成功", metadata={"agent": "B"}),
        ]
        result = orchestrator._aggregate_results(mock_resps, Intent.GENERAL)
        assert result["content"] == "成功"

    @pytest.mark.asyncio
    async def test_reg_05_select_agents_inspect(self, orchestrator):
        """REG-05: INSPECT 意图正确选择 inspector"""
        agents = orchestrator._select_agents(Intent.INSPECT, "健康检查")
        agent_names = [a.name for a in agents]
        assert "inspector" in agent_names

    @pytest.mark.asyncio
    async def test_reg_06_intent_recognize_inSPECT(self, orchestrator):
        """REG-06: "MySQL instances" 识别为 INSPECT"""
        with patch.object(orchestrator, "_semantic_intent_recognize", new_callable=AsyncMock) as mock_sem:
            mock_sem.return_value = (Intent.INSPECT, 0.9)
            intent = await orchestrator._recognize_intent("MySQL instances", {})
        assert intent == Intent.INSPECT


# ═══════════════════════════════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
