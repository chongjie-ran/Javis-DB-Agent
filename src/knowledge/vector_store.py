"""知识库向量化 - 基于Chroma向量库"""
import os
import yaml
from typing import Optional
from dataclasses import dataclass


@dataclass
class KnowledgeItem:
    """知识条目"""
    id: str
    content: str
    title: str
    category: str  # "alert_rule" | "sop"
    metadata: dict


def _load_alert_rules(rules_path: str = "knowledge/alert_rules.yaml") -> list[KnowledgeItem]:
    """加载告警规则"""
    items = []
    if not os.path.exists(rules_path):
        return items
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for rule in data.get("alert_rules", []):
        content_parts = [
            f"# {rule.get('name', rule.get('alert_type', ''))}",
            f"## 描述",
            rule.get("description", ""),
            f"## 告警类型",
            rule.get("alert_type", ""),
            f"## 严重程度",
            rule.get("severity", ""),
            f"## 风险级别",
            rule.get("risk_level", ""),
            f"## 症状",
            "\n".join(rule.get("symptoms", [])),
            f"## 可能原因",
            "\n".join(rule.get("possible_causes", [])),
            f"## 检查步骤",
            "\n".join(rule.get("check_steps", [])),
            f"## 解决方案",
            "\n".join(rule.get("resolution", [])),
        ]
        items.append(KnowledgeItem(
            id=f"alert_{rule.get('alert_type', rule.get('alert_code', ''))}",
            content="\n".join(content_parts),
            title=rule.get("name", rule.get("alert_type", "")),
            category="alert_rule",
            metadata={
                "alert_type": rule.get("alert_type", ""),
                "severity": rule.get("severity", ""),
                "risk_level": rule.get("risk_level", ""),
                "alert_code": rule.get("alert_code", ""),
            }
        ))
    return items


def _load_sops(sop_dir: str = "knowledge/sop") -> list[KnowledgeItem]:
    """加载SOP文档"""
    items = []
    if not os.path.exists(sop_dir):
        return items
    for filename in os.listdir(sop_dir):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(sop_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            title = filename.replace(".md", "")
            items.append(KnowledgeItem(
                id=f"sop_{title}",
                content=content,
                title=title,
                category="sop",
                metadata={"filename": filename}
            ))
        except Exception:
            pass
    return items


class VectorStore:
    """向量知识库（Chroma后端）"""

    def __init__(
        self,
        persist_dir: str = "data/chroma_db",
        embedding_model: Optional[str] = None,  # None = use DefaultEmbeddingFunction
    ):
        self._persist_dir = persist_dir
        self._embedding_model = embedding_model
        self._client = None
        self._collection_alerts = None
        self._collection_sops = None
        self._embedding_function = None
        self._connect()

    def _connect(self):
        """连接到Chroma"""
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        os.makedirs(self._persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir)

        # 默认使用DefaultEmbeddingFunction（轻量、无需下载模型）
        # 如需更高质量embedding，传入embedding_model参数使用sentence-transformers
        self._embedding_function = DefaultEmbeddingFunction()

        # 告警规则集合
        try:
            self._collection_alerts = self._client.get_or_create_collection(
                name="alert_rules",
                embedding_function=self._embedding_function,
                metadata={"description": "告警规则知识库"},
            )
        except Exception:
            self._collection_alerts = self._client.get_collection("alert_rules")

        # SOP集合
        try:
            self._collection_sops = self._client.get_or_create_collection(
                name="sops",
                embedding_function=self._embedding_function,
                metadata={"description": "SOP标准操作流程知识库"},
            )
        except Exception:
            self._collection_sops = self._client.get_collection("sops")

    def load_knowledge(
        self,
        rules_path: str = "knowledge/alert_rules.yaml",
        sop_dir: str = "knowledge/sop",
        force_reload: bool = False,
    ) -> dict:
        """加载知识到向量库"""
        results = {"alert_rules": 0, "sops": 0}

        # 检查是否已有数据
        if not force_reload:
            if self._collection_alerts.count() > 0 and self._collection_sops.count() > 0:
                return {"status": "already_loaded", "alert_rules": self._collection_alerts.count(), "sops": self._collection_sops.count()}

        # 加载告警规则
        rules = _load_alert_rules(rules_path)
        if rules:
            if force_reload:
                try:
                    self._client.delete_collection("alert_rules")
                    self._collection_alerts = self._client.get_or_create_collection(
                        name="alert_rules", embedding_function=self._embedding_function
                    )
                except Exception:
                    pass
            ids = [r.id for r in rules]
            contents = [r.content for r in rules]
            metadatas = [r.metadata for r in rules]
            self._collection_alerts.upsert(ids=ids, documents=contents, metadatas=metadatas)
            results["alert_rules"] = len(rules)

        # 加载SOP
        sops = _load_sops(sop_dir)
        if sops:
            if force_reload:
                try:
                    self._client.delete_collection("sops")
                    self._collection_sops = self._client.get_or_create_collection(
                        name="sops", embedding_function=self._embedding_function
                    )
                except Exception:
                    pass
            ids = [s.id for s in sops]
            contents = [s.content for s in sops]
            metadatas = [s.metadata for s in sops]
            self._collection_sops.upsert(ids=ids, documents=contents, metadatas=metadatas)
            results["sops"] = len(sops)

        return results

    def semantic_search_rules(
        self,
        query: str,
        top_k: int = 5,
        severity_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        语义搜索告警规则
        LLM诊断前先检索相关规则
        """
        where = {"severity": severity_filter} if severity_filter else None
        results = self._collection_alerts.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results and results.get("ids"):
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "category": "alert_rule",
                })
        return items

    def semantic_search_sops(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[dict]:
        """语义搜索SOP"""
        results = self._collection_sops.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results and results.get("ids"):
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "category": "sop",
                })
        return items

    def retrieve_for_diagnosis(
        self,
        alert_description: str,
        context: Optional[str] = None,
        top_k: int = 5,
    ) -> dict:
        """
        诊断上下文检索 - LLM诊断前调用
        组合检索相关告警规则和SOP
        """
        query = f"{alert_description} {context or ''}"
        rules = self.semantic_search_rules(query, top_k=top_k)
        sops = self.semantic_search_sops(query, top_k=3)

        return {
            "relevant_rules": rules,
            "relevant_sops": sops,
            "query_used": query,
            "total_rules_found": len(rules),
            "total_sops_found": len(sops),
        }

    def get_stats(self) -> dict:
        """获取知识库统计"""
        return {
            "alert_rules_count": self._collection_alerts.count() if self._collection_alerts else 0,
            "sops_count": self._collection_sops.count() if self._collection_sops else 0,
            "embedding_model": self._embedding_model,
            "persist_dir": self._persist_dir,
        }


# 全局单例
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
