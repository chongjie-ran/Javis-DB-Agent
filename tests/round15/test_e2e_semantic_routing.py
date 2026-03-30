"""
Round 15 - v1.3 Round 2: 语义路由端到端测试

覆盖:
1. 语义路由整体流程测试
2. 用户实际问法测试 ("MySQL instances" / "show me all databases")
3. 语义工具选择测试
4. 样本自演化测试
5. Fallback 降级逻辑测试
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import subprocess

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


def _check_ollama_available():
    """检查 Ollama 服务是否可用"""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


OLLAMA_AVAILABLE = _check_ollama_available()


class TestE2ESemanticRouting:
    """端到端语义路由测试"""

    @pytest.mark.asyncio
    async def test_mysql_instances_routes_to_inspect(self):
        """
        【用户反馈修复】"MySQL instances" 应该路由到 inspect 意图
        """
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # Mock LLM fallback to return inspect
        with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (Intent.INSPECT, 0.9)
            
            intent = await agent._recognize_intent("MySQL instances")
            assert intent == Intent.INSPECT, \
                f"'MySQL instances' 应该路由到 inspect，实际: {intent}"

    @pytest.mark.asyncio
    async def test_show_me_all_databases_routes_to_inspect(self):
        """【用户反馈修复】"show me all databases" 应该路由到 inspect 意图"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (Intent.INSPECT, 0.9)
            
            intent = await agent._recognize_intent("show me all databases")
            assert intent == Intent.INSPECT, \
                f"'show me all databases' 应该路由到 inspect，实际: {intent}"

    @pytest.mark.asyncio
    async def test_all_mysql_databases_routes_to_inspect(self):
        """【用户反馈修复】"所有mysql数据库" 应该路由到 inspect 意图"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (Intent.INSPECT, 0.9)
            
            intent = await agent._recognize_intent("所有mysql数据库")
            assert intent == Intent.INSPECT, \
                f"'所有mysql数据库' 应该路由到 inspect，实际: {intent}"

    @pytest.mark.asyncio
    async def test_inspect_intent_selects_inspector_agent(self):
        """inspect 意图应该选择 inspector Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        selected = agent._select_agents(Intent.INSPECT, "MySQL instances")
        agent_names = [a.name for a in selected]
        
        assert "inspector" in agent_names, \
            f"inspect 意图应该选择 inspector，实际选择: {agent_names}"

    @pytest.mark.asyncio
    async def test_end_to_end_mysql_instances_flow(self):
        """端到端流程：MySQL instances -> inspect -> inspector"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # Mock 语义识别和执行
        with patch.object(agent, '_recognize_intent', new_callable=AsyncMock) as mock_recognize:
            mock_recognize.return_value = Intent.INSPECT
            
            with patch.object(agent, '_execute_plan', new_callable=AsyncMock) as mock_execute:
                mock_execute.return_value = []
                
                response = await agent._process_direct("MySQL instances", {})
                
                assert response.metadata["intent"] == "inspect"
                assert "inspector" in response.metadata["agents_used"]

    @pytest.mark.asyncio
    async def test_chinese_inspect_phrases(self):
        """中文巡检相关表达应该路由到 inspect"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        test_cases = [
            "查看实例列表",
            "有哪些数据库",
            "实例状态怎么样",
            "健康检查",
        ]
        
        with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (Intent.INSPECT, 0.9)
            
            for phrase in test_cases:
                intent = await agent._recognize_intent(phrase)
                assert intent == Intent.INSPECT, \
                    f"'{phrase}' 应该路由到 inspect，实际: {intent}"


class TestSemanticToolSelection:
    """语义工具选择测试"""

    def test_basic_intent_to_agent_mapping(self):
        """基础意图->Agent映射测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        test_cases = [
            (Intent.DIAGNOSE, ["diagnostic", "risk"]),
            (Intent.SQL_ANALYZE, ["sql_analyzer", "risk"]),
            (Intent.ANALYZE_SESSION, ["session_analyzer"]),
            (Intent.INSPECT, ["inspector"]),
            (Intent.REPORT, ["reporter"]),
            (Intent.RISK_ASSESS, ["risk"]),
        ]
        
        for intent, expected_agents in test_cases:
            selected = agent._select_agents(intent, "test")
            selected_names = [a.name for a in selected]
            for expected in expected_agents:
                assert expected in selected_names, \
                    f"{intent.name} 应该选择 {expected}，实际: {selected_names}"

    def test_semantic_tool_fine_tune_risk_keyword(self):
        """语义关键词微调：风险相关词应该添加 risk Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # inspect + 风险 -> 应该添加 risk
        base_agents = [agent._agent_registry["inspector"]]
        fine_tuned = agent._semantic_tool_fine_tune(
            Intent.INSPECT, 
            "检查状态和风险",
            base_agents
        )
        fine_tuned_names = [a.name for a in fine_tuned]
        
        assert "risk" in fine_tuned_names, \
            f"包含'风险'关键词应该添加 risk Agent，实际: {fine_tuned_names}"

    def test_semantic_tool_fine_tune_session_keyword(self):
        """语义关键词微调：连接相关词应该添加 session_analyzer"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        base_agents = [agent._agent_registry["inspector"]]
        fine_tuned = agent._semantic_tool_fine_tune(
            Intent.INSPECT,
            "检查实例和连接情况",
            base_agents
        )
        fine_tuned_names = [a.name for a in fine_tuned]
        
        assert "session_analyzer" in fine_tuned_names, \
            f"包含'连接'关键词应该添加 session_analyzer，实际: {fine_tuned_names}"

    def test_semantic_tool_fine_tune_sql_keyword(self):
        """语义关键词微调：索引/慢查询相关词应该添加 sql_analyzer"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        base_agents = [agent._agent_registry["inspector"]]
        fine_tuned = agent._semantic_tool_fine_tune(
            Intent.INSPECT,
            "检查状态和慢查询",
            base_agents
        )
        fine_tuned_names = [a.name for a in fine_tuned]
        
        assert "sql_analyzer" in fine_tuned_names, \
            f"包含'慢查询'关键词应该添加 sql_analyzer，实际: {fine_tuned_names}"

    def test_semantic_removal_exclusive_keywords(self):
        """语义互斥关键词应该移除对应Agent"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # "只巡检" 应该移除 risk, diagnostic, alert
        base_agents = [
            agent._agent_registry["inspector"],
            agent._agent_registry["risk"],
            agent._agent_registry["diagnostic"],
            agent._agent_registry["alert"],
        ]
        fine_tuned = agent._semantic_tool_fine_tune(
            Intent.INSPECT,
            "只巡检",
            base_agents
        )
        fine_tuned_names = [a.name for a in fine_tuned]
        
        assert "risk" not in fine_tuned_names, \
            f"'只巡检' 应该移除 risk，实际: {fine_tuned_names}"
        assert "diagnostic" not in fine_tuned_names, \
            f"'只巡检' 应该移除 diagnostic，实际: {fine_tuned_names}"
        assert "alert" not in fine_tuned_names, \
            f"'只巡检' 应该移除 alert，实际: {fine_tuned_names}"


class TestIntentExampleCollector:
    """样本自演化收集器测试"""

    def test_collector_initialization(self):
        """收集器初始化测试"""
        from src.agents.orchestrator import IntentExampleCollector
        
        collector = IntentExampleCollector()
        assert collector is not None
        assert len(collector._feedback_buffer) == 0

    def test_record_feedback(self):
        """记录用户反馈测试"""
        from src.agents.orchestrator import IntentExampleCollector, Intent
        
        collector = IntentExampleCollector()
        
        collector.record_feedback(
            user_input="MySQL instances",
            recognized_intent=Intent.INSPECT,
            user_accepted=True
        )
        
        assert len(collector._feedback_buffer) == 1
        feedback = collector._feedback_buffer[0]
        assert feedback.user_input == "MySQL instances"
        assert feedback.recognized_intent == Intent.INSPECT
        assert feedback.user_accepted is True

    def test_record_feedback_correction(self):
        """记录用户纠正反馈测试"""
        from src.agents.orchestrator import IntentExampleCollector, Intent
        
        collector = IntentExampleCollector()
        
        # 用户纠正了意图
        collector.record_feedback(
            user_input="我的告警是什么",
            recognized_intent=Intent.INSPECT,
            user_accepted=False,
            corrected_intent=Intent.DIAGNOSE
        )
        
        assert len(collector._feedback_buffer) == 1
        feedback = collector._feedback_buffer[0]
        assert feedback.user_accepted is False
        assert feedback.corrected_intent == Intent.DIAGNOSE
        
        # 验证待学习列表中有新样本
        pending = collector._pending_additions[Intent.DIAGNOSE]
        assert "我的告警是什么" in pending

    @pytest.mark.asyncio
    async def test_auto_learn_from_feedback(self):
        """从反馈自动学习测试"""
        from src.agents.orchestrator import IntentExampleCollector, Intent, INTENT_EXAMPLES
        
        collector = IntentExampleCollector()
        
        # 记录用户纠正
        collector.record_feedback(
            user_input="查看连接池状态",
            recognized_intent=Intent.INSPECT,
            user_accepted=False,
            corrected_intent=Intent.ANALYZE_SESSION
        )
        
        # 执行自动学习
        new_additions = await collector.auto_learn_from_feedback()
        
        # 验证学习结果
        assert Intent.ANALYZE_SESSION in new_additions
        assert "查看连接池状态" in new_additions[Intent.ANALYZE_SESSION]
        
        # 验证样本已添加到 INTENT_EXAMPLES
        inspect_examples = INTENT_EXAMPLES[Intent.ANALYZE_SESSION]
        assert "查看连接池状态" in inspect_examples

    def test_get_stats(self):
        """获取统计信息测试"""
        from src.agents.orchestrator import IntentExampleCollector
        
        collector = IntentExampleCollector()
        stats = collector.get_stats()
        
        assert "total_intents" in stats
        assert "intent_counts" in stats
        assert "pending_learning" in stats
        assert stats["total_intents"] > 0


class TestFallbackLogic:
    """Fallback 降级逻辑测试"""

    @pytest.mark.asyncio
    async def test_embedding_unavailable_fallback_to_llm(self):
        """Embedding 不可用时降级到 LLM 测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # Mock EmbeddingService 导入失败
        with patch('src.knowledge.vector.embedding_service.EmbeddingService', side_effect=ImportError):
            with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = (Intent.INSPECT, 0.85)
                
                intent, score = await agent._semantic_intent_recognize("MySQL instances")
                
                assert intent == Intent.INSPECT
                assert score == 0.85
                # 验证 LLM fallback 被调用
                mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_embedding_score_triggers_llm_fallback(self):
        """低 embedding 分数触发 LLM fallback 测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # Mock embedding 返回低分
        with patch('src.knowledge.vector.embedding_service.EmbeddingService') as MockEmbed:
            mock_instance = MagicMock()
            mock_instance.compute_similarity = AsyncMock(return_value=0.3)  # 低分
            mock_instance.close = AsyncMock()
            MockEmbed.return_value = mock_instance
            
            with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = (Intent.INSPECT, 0.85)
                
                intent, score = await agent._semantic_intent_recognize("模糊查询")
                
                # 应该触发 LLM fallback
                mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_fallback_threshold(self):
        """LLM fallback 阈值测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        # Mock embedding 返回刚好低于阈值的分数
        with patch('src.knowledge.vector.embedding_service.EmbeddingService') as MockEmbed:
            mock_instance = MagicMock()
            mock_instance.compute_similarity = AsyncMock(return_value=0.74)  # 低于 0.75
            mock_instance.close = AsyncMock()
            MockEmbed.return_value = mock_instance
            
            with patch.object(agent, '_llm_semantic_match', new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = (Intent.GENERAL, 0.5)  # LLM 也低于阈值
                
                intent, score = await agent._semantic_intent_recognize("你好")
                
                # 分数不足，返回 GENERAL
                assert intent == Intent.GENERAL


class TestLLMSemanticMatch:
    """LLM 语义匹配测试"""

    @pytest.mark.asyncio
    async def test_llm_match_returns_correct_intent(self):
        """LLM 匹配返回正确意图测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
            mock_think.return_value = "inspect"
            
            intent, score = await agent._llm_semantic_match("MySQL instances")
            
            assert intent == Intent.INSPECT
            assert score >= 0.8

    @pytest.mark.asyncio
    async def test_llm_match_unknown_returns_general(self):
        """LLM 匹配未知返回 GENERAL 测试"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
            mock_think.return_value = "unknown_intent"
            
            intent, score = await agent._llm_semantic_match("随机字符串 xyz")
            
            assert intent == Intent.GENERAL


# ------------------------------------------------------------
# 运行入口
# ------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
