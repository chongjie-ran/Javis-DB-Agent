"""P0-3测试: 知识库向量化（Chroma）"""
import pytest
import tempfile
import os
import yaml

from src.knowledge.vector_store import (
    VectorStore,
    _load_alert_rules,
    _load_sops,
    KnowledgeItem,
    get_vector_store,
)


def _embedding_available():
    """检查embedding模型是否可用（需要网络下载，首次调用会触发下载）"""
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        return True  # 只要模块可用即可，实际embedding在测试中验证
    except Exception:
        return False


EMBEDDING_SKIP = pytest.mark.skipif(
    not _embedding_available(),
    reason="SentenceTransformer embedding model not available (network/download issue)"
)


class TestKnowledgeLoading:
    """知识加载测试（无需embedding）"""

    def test_load_alert_rules_from_yaml(self):
        rules = _load_alert_rules("knowledge/alert_rules.yaml")
        assert len(rules) >= 15, f"应该有15条规则，实际{len(rules)}条"
        for r in rules:
            assert r.id.startswith("alert_")
            assert r.category == "alert_rule"
            assert r.content
            assert r.metadata.get("alert_type")
            assert r.metadata.get("severity")

    def test_load_sops_from_dir(self):
        sops = _load_sops("knowledge/sop")
        assert len(sops) >= 10, f"应该有10个SOP，实际{len(sops)}个"
        for s in sops:
            assert s.id.startswith("sop_")
            assert s.category == "sop"
            assert s.content

    def test_alert_rules_cover_key_scenarios(self):
        rules = _load_alert_rules("knowledge/alert_rules.yaml")
        alert_types = {r.metadata.get("alert_type") for r in rules}
        expected = {
            "LOCK_WAIT_TIMEOUT", "DEADLOCK_DETECTED", "SLOW_QUERY_DETECTED",
            "CPU_HIGH", "MEMORY_HIGH", "DISK_FULL", "CONNECTION_HIGH",
            "CONNECTION_POOL_EXHAUSTED", "REPLICATION_LAG", "REPLICATION_BROKEN",
            "INSTANCE_DOWN", "INSTANCE_SLOW", "BACKUP_FAILED", "FAILED_LOGIN",
            "PRIVILEGE_ESCALATION",
        }
        assert expected.issubset(alert_types), f"缺少规则: {expected - alert_types}"

    def test_alert_rules_content_has_required_sections(self):
        rules = _load_alert_rules("knowledge/alert_rules.yaml")
        for r in rules:
            content = r.content
            assert "描述" in content or "description" in content.lower()
            assert "症状" in content or "symptom" in content.lower()
            assert "解决方案" in content or "resolution" in content.lower()


@EMBEDDING_SKIP
class TestVectorStore:
    """VectorStore测试（需要embedding模型）"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_dir = os.path.join(self._tmpdir, "chroma_test")
        self._vs = VectorStore(persist_dir=self._db_dir)  # 使用DefaultEmbeddingFunction

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_knowledge(self):
        result = self._vs.load_knowledge(
            rules_path="knowledge/alert_rules.yaml",
            sop_dir="knowledge/sop",
            force_reload=True,
        )
        assert result["alert_rules"] >= 15
        assert result["sops"] >= 10

    def test_stats_after_load(self):
        self._vs.load_knowledge(force_reload=True)
        stats = self._vs.get_stats()
        assert stats["alert_rules_count"] >= 15
        assert stats["sops_count"] >= 10

    def test_semantic_search_rules_lock_wait(self):
        self._vs.load_knowledge(force_reload=True)
        results = self._vs.semantic_search_rules("锁等待超时死锁", top_k=3)
        assert len(results) <= 3
        assert all(r["category"] == "alert_rule" for r in results)
        found_types = {r["metadata"].get("alert_type") for r in results}
        assert found_types, "应该找到相关规则"

    def test_semantic_search_rules_cpu(self):
        self._vs.load_knowledge(force_reload=True)
        results = self._vs.semantic_search_rules("CPU使用率过高负载高", top_k=3)
        found_types = {r["metadata"].get("alert_type") for r in results}
        assert "CPU_HIGH" in found_types

    def test_semantic_search_rules_disk(self):
        self._vs.load_knowledge(force_reload=True)
        results = self._vs.semantic_search_rules("磁盘空间不足", top_k=3)
        found_types = {r["metadata"].get("alert_type") for r in results}
        assert "DISK_FULL" in found_types

    def test_semantic_search_sops(self):
        self._vs.load_knowledge(force_reload=True)
        results = self._vs.semantic_search_sops("锁等待如何处理", top_k=3)
        assert len(results) <= 3
        assert all(r["category"] == "sop" for r in results)

    def test_retrieve_for_diagnosis(self):
        self._vs.load_knowledge(force_reload=True)
        ctx = self._vs.retrieve_for_diagnosis(
            alert_description="实例发生锁等待超时",
            context="等待时间超过30秒",
            top_k=5,
        )
        assert "relevant_rules" in ctx
        assert "relevant_sops" in ctx
        assert ctx["query_used"]
        assert ctx["total_rules_found"] >= 1

    def test_distance_scores_reasonable(self):
        self._vs.load_knowledge(force_reload=True)
        results = self._vs.semantic_search_rules("死锁检测", top_k=5)
        for r in results:
            assert r["distance"] >= 0.0
            assert r["distance"] <= 2.0  # Chroma余弦距离上限约2.0

    def test_persistence(self):
        """验证向量库持久化"""
        self._vs.load_knowledge(force_reload=True)
        stats1 = self._vs.get_stats()

        vs2 = VectorStore(persist_dir=self._db_dir)
        stats2 = vs2.get_stats()
        assert stats2["alert_rules_count"] == stats1["alert_rules_count"]
        assert stats2["sops_count"] == stats1["sops_count"]
