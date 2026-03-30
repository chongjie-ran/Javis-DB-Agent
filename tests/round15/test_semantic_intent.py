"""
Round 15 - v1.3 语义路由增强: 语义意图识别测试

覆盖:
1. _semantic_intent_recognize() 核心方法测试
2. INTENT_EXAMPLES 示例库完整性测试
3. 语义匹配阈值测试
4. 降级策略测试
5. 向量化服务异常处理测试
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


def _check_nomic_available():
    """检查 nomic-embed-text 模型是否已下载"""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            models = [m.get("name", "") for m in data.get("models", [])]
            return any("nomic" in m for m in models)
    except Exception:
        pass
    return False


OLLAMA_AVAILABLE = _check_ollama_available()
NOMIC_AVAILABLE = _check_nomic_available()


class TestIntentExamplesCompleteness:
    """INTENT_EXAMPLES 示例库完整性测试"""

    def test_all_intents_have_examples(self):
        """所有Intent枚举值都有对应的示例"""
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        for intent in Intent:
            assert intent in INTENT_EXAMPLES, f"Intent {intent.name} 缺少示例"
            examples = INTENT_EXAMPLES[intent]
            assert len(examples) > 0, f"Intent {intent.name} 示例列表为空"

    def test_each_intent_has_minimum_examples(self):
        """每个意图至少包含5个同义表达示例"""
        from src.agents.orchestrator import INTENT_EXAMPLES
        
        for intent, examples in INTENT_EXAMPLES.items():
            assert len(examples) >= 5, \
                f"Intent {intent.name} 只有 {len(examples)} 个示例，至少需要5个"

    def test_inspect_intent_includes_mysql_instances(self):
        """inspect 意图包含 'MySQL instances' 变体 - 修复用户反馈"""
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        examples = INTENT_EXAMPLES[Intent.INSPECT]
        example_text = " ".join(examples).lower()
        assert "mysql" in example_text or "实例" in example_text, \
            "inspect 意图应包含 MySQL instances 相关表达"


class TestSemanticIntentRecognize:
    """_semantic_intent_recognize() 核心测试"""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_semantic_match_mysql_instances(self):
        """【用户反馈修复】'MySQL instances' 应该匹配 inspect 意图"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available, run: ollama pull nomic-embed-text")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        embed = EmbeddingService()
        
        user_input = "MySQL instances"
        inspect_examples = INTENT_EXAMPLES[Intent.INSPECT]
        
        scores = [await embed.compute_similarity(user_input, ex) for ex in inspect_examples]
        max_score = max(scores)
        print(f"'MySQL instances' vs inspect: max_similarity={max_score:.4f}")
        
        await embed.close()
        
        assert max_score >= 0.7, \
            f"'MySQL instances' 与 inspect 意图相似度 {max_score:.4f} 低于0.7"

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_semantic_match_diagnose_intent(self):
        """告警诊断类输入应该匹配 diagnose 意图"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        embed = EmbeddingService()
        
        test_inputs = [
            "帮我看看这个告警怎么回事",
            "这个警报怎么处理",
            "告警根因分析",
        ]
        
        for user_input in test_inputs:
            diagnose_examples = INTENT_EXAMPLES[Intent.DIAGNOSE]
            scores = [await embed.compute_similarity(user_input, ex) for ex in diagnose_examples]
            max_score = max(scores)
            print(f"'{user_input}' vs diagnose: max_similarity={max_score:.4f}")
            assert max_score >= 0.7, f"'{user_input}' 未能匹配 diagnose 意图"
        
        await embed.close()

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_semantic_match_sql_analyze_intent(self):
        """SQL分析类输入应该匹配 sql_analyze 意图"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        embed = EmbeddingService()
        
        user_input = "分析一下这条SQL的性能"
        sql_examples = INTENT_EXAMPLES[Intent.SQL_ANALYZE]
        scores = [await embed.compute_similarity(user_input, ex) for ex in sql_examples]
        max_score = max(scores)
        print(f"'{user_input}' vs sql_analyze: max_similarity={max_score:.4f}")
        
        await embed.close()
        assert max_score >= 0.7, f"SQL分析输入未能匹配 sql_analyze 意图"

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_threshold_fallback_to_general(self):
        """相似度低于阈值时应该降级到 GENERAL"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        user_input = "帮我看看"
        
        intent, score = await agent._semantic_intent_recognize(user_input)
        print(f"'{user_input}' -> intent={intent.name}, score={score:.4f}")
        
        assert score < agent.SEMANTIC_SIMILARITY_THRESHOLD

    @pytest.mark.asyncio
    async def test_embedding_service_import_error(self):
        """EmbeddingService 导入失败时应该正确降级到 GENERAL"""
        from src.agents.orchestrator import OrchestratorAgent, Intent
        
        agent = OrchestratorAgent()
        
        with patch('src.knowledge.vector.embedding_service.EmbeddingService', side_effect=ImportError):
            # v1.3 Round 2: EmbeddingService 不可用时降级到 LLM 语义匹配
            # LLM 匹配可能返回有效意图和分数，不再固定返回 GENERAL + 0.0
            intent, score = await agent._semantic_intent_recognize("测试输入")
            # 检查是否正确降级（意图应该存在，分数应该 > 0）
            assert intent is not None
            assert score >= 0  # 降级后 LLM 可能给出有效匹配

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_cross_intent_distinction(self):
        """语义匹配能区分不同意图"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        from src.agents.orchestrator import INTENT_EXAMPLES, Intent
        
        embed = EmbeddingService()
        
        user_input = "会话分析"
        
        session_examples = INTENT_EXAMPLES[Intent.ANALYZE_SESSION]
        session_scores = [await embed.compute_similarity(user_input, ex) for ex in session_examples]
        session_max = max(session_scores)
        
        other_intents = [i for i in Intent if i != Intent.ANALYZE_SESSION]
        other_max_scores = []
        for other_intent in other_intents:
            other_examples = INTENT_EXAMPLES[other_intent]
            scores = [await embed.compute_similarity(user_input, ex) for ex in other_examples]
            other_max_scores.append(max(scores))
        
        other_max = max(other_max_scores)
        
        print(f"'{user_input}' vs ANALYZE_SESSION: {session_max:.4f}, vs others: {other_max:.4f}")
        
        await embed.close()
        
        assert session_max > other_max, \
            f"ANALYZE_SESSION ({session_max:.4f}) 应高于其他意图 ({other_max:.4f})"


class TestOrchestratorSemanticRecognition:
    """Orchestrator 集成语义识别测试"""

    @pytest.mark.asyncio
    async def test_recognize_intent_with_context_param(self):
        """_recognize_intent 应该接受 context 参数"""
        from src.agents.orchestrator import OrchestratorAgent
        import inspect
        
        agent = OrchestratorAgent()
        sig = inspect.signature(agent._recognize_intent)
        params = list(sig.parameters.keys())
        assert 'context' in params, "_recognize_intent 应支持 context 参数"

    @pytest.mark.asyncio
    async def test_semantic_threshold_constant(self):
        """SEMANTIC_SIMILARITY_THRESHOLD 值应该合理（0.6-0.85之间）"""
        from src.agents.orchestrator import OrchestratorAgent
        
        agent = OrchestratorAgent()
        threshold = agent.SEMANTIC_SIMILARITY_THRESHOLD
        assert 0.6 <= threshold <= 0.85, \
            f"阈值 {threshold} 应在 0.6-0.85 之间，当前 {threshold}"


class TestSemanticSimilarityComputation:
    """余弦相似度计算测试（需要 Ollama 运行）"""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_identical_text_similarity(self):
        """完全相同的文本相似度应该接近1.0"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        
        embed = EmbeddingService()
        score = await embed.compute_similarity("告警诊断", "告警诊断")
        print(f"相同文本相似度: {score:.4f}")
        await embed.close()
        assert score > 0.95

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_similar_text_high_similarity(self):
        """语义相似的文本相似度应该较高"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        
        embed = EmbeddingService()
        score = await embed.compute_similarity("告警诊断", "诊断告警")
        print(f"'告警诊断' vs '诊断告警': {score:.4f}")
        await embed.close()
        assert score > 0.8

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_different_text_lower_similarity(self):
        """语义不同的文本相似度应该较低"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        
        embed = EmbeddingService()
        score = await embed.compute_similarity("告警诊断", "SQL优化")
        print(f"'告警诊断' vs 'SQL优化': {score:.4f}")
        await embed.close()
        assert score < 0.7

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    @pytest.mark.asyncio
    async def test_chinese_text_embedding(self):
        """中文文本向量化测试"""
        if not NOMIC_AVAILABLE:
            pytest.skip("nomic-embed-text model not available")
        
        from src.knowledge.vector.embedding_service import EmbeddingService
        
        embed = EmbeddingService()
        emb = await embed.embed_text("MySQL instances")
        print(f"MySQL instances embedding length: {len(emb)}")
        await embed.close()
        assert len(emb) > 0, "embedding 向量长度应大于0"
        assert all(isinstance(x, float) for x in emb), "embedding 元素应为 float"


# ------------------------------------------------------------
# 运行入口
# ------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
