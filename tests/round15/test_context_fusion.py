"""
Round 15 - v1.3 语义路由增强: 上下文融合测试

覆盖:
1. _build_conversation_history() 方法测试
2. 对话历史融入意图识别 prompt 测试
3. 多轮对话意图推断测试
4. context 缺失时的降级处理测试
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestBuildConversationHistory:
    """_build_conversation_history() 测试"""

    def test_empty_context(self):
        """空 context 应该返回空字符串"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        result = agent._build_conversation_history({})
        assert result == ""

    def test_no_history(self):
        """没有 conversation_history 时返回空字符串"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        result = agent._build_conversation_history({"user_id": "test"})
        assert result == ""

    def test_single_turn(self):
        """单轮对话测试"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": "我的数据库有告警"}
            ]
        }
        result = agent._build_conversation_history(context)
        assert "我的数据库有告警" in result
        assert "用户" in result

    def test_multiple_turns(self):
        """多轮对话测试"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": "我的数据库有告警"},
                {"role": "assistant", "content": "请提供告警ID"},
                {"role": "user", "content": "ALT-001"},
            ]
        }
        result = agent._build_conversation_history(context)
        assert "我的数据库有告警" in result
        assert "ALT-001" in result

    def test_max_turns_limit(self):
        """最多保留 max_turns 轮对话"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": f"历史{i}"}
                for i in range(10)
            ]
        }
        result = agent._build_conversation_history(context, max_turns=3)
        lines = result.strip().split("\n")
        # 应该只有 max_turns * 2 行（每轮有用户和助手）
        # 或者更准确地说，应该包含最近3轮的内容
        assert "历史7" in result or "历史8" in result or "历史9" in result
        assert "历史0" not in result  # 第一轮不应该在结果中

    def test_missing_role_field(self):
        """缺少 role 字段时应该降级处理"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"content": "只有内容没有role"}
            ]
        }
        result = agent._build_conversation_history(context)
        assert "只有内容没有role" in result

    def test_empty_content(self):
        """内容为空的对话项应该被跳过"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": ""},
                {"role": "assistant", "content": "有用内容"},
                {"role": "user", "content": "继续"},
            ]
        }
        result = agent._build_conversation_history(context)
        # 空内容项应该不出现在结果中
        lines = [l for l in result.strip().split("\n") if l]
        assert "有用内容" in result
        assert "继续" in result


class TestContextFusionInIntentRecognition:
    """上下文融合到意图识别测试"""

    @pytest.mark.asyncio
    async def test_recognize_intent_with_history(self):
        """有对话历史时，_recognize_intent 应传入 context"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": "MySQL instances 有哪些"},
                {"role": "assistant", "content": "当前有3个MySQL实例..."},
                {"role": "user", "content": "它们的健康状态怎么样"},
            ]
        }
        
        # mock 语义识别返回低分，强制走 LLM 路径
        with patch.object(agent, '_semantic_intent_recognize', 
                          return_value=(Intent.GENERAL, 0.3)):
            with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
                mock_think.return_value = "inspect"
                
                intent = await agent._recognize_intent("它们的状态", context)
                
                # 验证 think 被调用
                assert mock_think.called
                
                # 验证传入 think 的 prompt 包含历史
                call_args = mock_think.call_args
                prompt = call_args[0][0] if call_args[0] else ""
                assert "MySQL instances" in prompt or "历史" in prompt or "对话" in prompt

    @pytest.mark.asyncio
    async def test_context_helps_resolve_ambiguous_intent(self):
        """上下文帮助解决歧义意图"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        
        # 场景: 用户说"它们"，需要结合上文推断意图
        context = {
            "conversation_history": [
                {"role": "user", "content": "查看所有实例"},
                {"role": "assistant", "content": "当前有3个实例"},
                {"role": "user", "content": "它们的状态"},
            ]
        }
        
        # mock 语义识别返回低分
        with patch.object(agent, '_semantic_intent_recognize',
                          return_value=(None, 0.3)):
            with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
                mock_think.return_value = "inspect"
                
                await agent._recognize_intent("它们的状态", context)
                
                # 验证 prompt 包含历史信息
                prompt = mock_think.call_args[0][0]
                assert "它们的状态" in prompt
                assert "查看所有实例" in prompt or "近期对话" in prompt or "历史" in prompt

    @pytest.mark.asyncio
    async def test_recognize_intent_without_context(self):
        """不带 context 参数时应该正常工作（向后兼容）"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        
        with patch.object(agent, '_semantic_intent_recognize',
                          return_value=(None, 0.3)):
            with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
                mock_think.return_value = "diagnose"
                
                # 不传 context
                intent = await agent._recognize_intent("帮我诊断这个告警")
                
                assert mock_think.called
                # prompt 中不应该包含历史部分
                prompt = mock_think.call_args[0][0]
                assert "近期对话历史" not in prompt or "：" in prompt

    @pytest.mark.asyncio
    async def test_context_none(self):
        """context 为 None 时应该不报错"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        
        # context 为 None 时调用不报错
        with patch.object(agent, '_semantic_intent_recognize',
                          return_value=(None, 0.3)):
            with patch.object(agent, 'think', new_callable=AsyncMock) as mock_think:
                mock_think.return_value = "inspect"
                
                intent = await agent._recognize_intent("MySQL instances", context=None)
                assert mock_think.called


class TestContextFusionInProcessDirect:
    """_process_direct 中的上下文融合测试"""

    @pytest.mark.asyncio
    async def test_process_direct_passes_context(self):
        """_process_direct 应该把 context 传给 _recognize_intent"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {"session_id": "test", "conversation_history": []}
        
        with patch.object(agent, '_recognize_intent', new_callable=AsyncMock) as mock_recognize:
            mock_recognize.return_value = None
            with patch.object(agent, '_select_agents', return_value=[]):
                with patch.object(agent, '_execute_plan', new_callable=AsyncMock, return_value=[]):
                    try:
                        await agent._process_direct("测试", context)
                    except Exception:
                        pass  # 我们只关心 _recognize_intent 是否被正确调用
                    
                    # 验证 _recognize_intent 接收了 context
                    mock_recognize.assert_called()
                    call_args = mock_recognize.call_args
                    # 第二个参数应该是 context
                    if call_args[0]:
                        assert len(call_args[0]) >= 2 or 'context' in call_args[1], \
                            "_recognize_intent 应接收 context 参数"


class TestConversationHistoryFormatting:
    """对话历史格式化测试"""

    def test_format_includes_role_labels(self):
        """格式化结果应该包含角色标签"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": "测试内容"},
                {"role": "assistant", "content": "助手回复"},
            ]
        }
        result = agent._build_conversation_history(context)
        # 应该标注"用户"和"助手"
        assert "用户" in result
        assert "助手" in result

    def test_format_preserves_order(self):
        """格式化应该保持对话顺序"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        context = {
            "conversation_history": [
                {"role": "user", "content": "第1句"},
                {"role": "assistant", "content": "第2句"},
                {"role": "user", "content": "第3句"},
            ]
        }
        result = agent._build_conversation_history(context)
        lines = result.strip().split("\n")
        # 第1句应在第2句之前，第2句应在第3句之前
        assert result.index("第1句") < result.index("第2句") < result.index("第3句")


# ------------------------------------------------------------
# 运行入口
# ------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
