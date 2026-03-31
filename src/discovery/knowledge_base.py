"""
本地知识库 - ChromaDB扩展

存储数据库schema、配置参数、故障案例知识。
R1: 预留接口，R2+实现
"""

from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

# ChromaDB可能未安装
try:
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB not installed. Knowledge base will be disabled.")


@dataclass
class SchemaKnowledge:
    """数据库Schema知识"""
    instance_id: str
    db_name: str
    tables: List[Dict]  # [{table_name, columns, row_count, size_bytes}]
    indexes: List[Dict]
    version: str
    captured_at: str


@dataclass
class ConfigKnowledge:
    """配置参数知识"""
    instance_id: str
    db_type: str
    version: str
    parameters: Dict[str, str]  # key -> value
    captured_at: str


@dataclass
class CaseKnowledge:
    """故障案例知识"""
    id: str
    instance_id: str
    title: str
    symptoms: str
    root_cause: str
    solution: str
    db_type: str
    db_version: str
    created_at: str


class LocalKnowledgeBase:
    """
    本地知识库 - 基于ChromaDB

    集合：
    - schemas:     数据库Schema知识
    - configs:     配置参数知识
    - cases:       故障案例知识

    Note:
        R1预留，R3实现完整功能
    """

    PERSIST_DIR = "data/local_knowledge"

    def __init__(self, persist_dir: Optional[str] = None):
        """
        初始化知识库

        Args:
            persist_dir: 持久化目录

        Raises:
            RuntimeError: ChromaDB未安装
        """
        if not CHROMA_AVAILABLE:
            logger.warning("LocalKnowledgeBase: ChromaDB not available, using stub mode")
            self._stub_mode = True
            self._stub_data: Dict[str, List] = {"schemas": [], "configs": [], "cases": []}
            return

        self._stub_mode = False
        self.persist_dir = persist_dir or self.PERSIST_DIR
        self._client = None
        self._collections: Dict[str, any] = {}
        self._embedding_fn = DefaultEmbeddingFunction()
        self._connect()

    def _connect(self):
        """连接ChromaDB并初始化集合"""
        import os
        os.makedirs(self.persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.persist_dir)

        for name, desc in [
            ("schemas", "Database schema knowledge"),
            ("configs", "Database configuration knowledge"),
            ("cases", "Failure case knowledge"),
        ]:
            try:
                coll = self._client.get_or_create_collection(
                    name=name,
                    embedding_function=self._embedding_fn,
                    metadata={"description": desc},
                )
            except Exception:
                coll = self._client.get_collection(name)
            self._collections[name] = coll

    def add_schema(self, schema: SchemaKnowledge) -> str:
        """添加Schema知识"""
        if self._stub_mode:
            doc_id = f"schema_{schema.instance_id}_{schema.db_name}"
            self._stub_data["schemas"].append({
                "id": doc_id,
                "instance_id": schema.instance_id,
                "db_name": schema.db_name,
                "tables": schema.tables,
            })
            return doc_id

        content = self._format_schema_content(schema)
        doc_id = f"schema_{schema.instance_id}_{schema.db_name}"

        self._collections["schemas"].upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{
                "instance_id": schema.instance_id,
                "db_name": schema.db_name,
                "table_count": len(schema.tables),
                "captured_at": schema.captured_at,
                "version": schema.version,
            }]
        )
        return doc_id

    def search_schemas(
        self, query: str, instance_id: Optional[str] = None, top_k: int = 5
    ) -> List[Dict]:
        """语义搜索Schema"""
        if self._stub_mode:
            return self._stub_data["schemas"][:top_k]

        where = {"instance_id": instance_id} if instance_id else None
        results = self._collections["schemas"].query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_search_results(results)

    def add_config(self, config: ConfigKnowledge) -> str:
        """添加配置参数知识"""
        if self._stub_mode:
            doc_id = f"config_{config.instance_id}_{config.db_type}"
            self._stub_data["configs"].append({
                "id": doc_id,
                "instance_id": config.instance_id,
                "db_type": config.db_type,
                "parameters": config.parameters,
            })
            return doc_id

        content = self._format_config_content(config)
        doc_id = f"config_{config.instance_id}_{config.db_type}"

        self._collections["configs"].upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{
                "instance_id": config.instance_id,
                "db_type": config.db_type,
                "version": config.version,
                "captured_at": config.captured_at,
                "param_count": len(config.parameters),
            }]
        )
        return doc_id

    def search_configs(
        self, query: str, db_type: Optional[str] = None, top_k: int = 5
    ) -> List[Dict]:
        """语义搜索配置"""
        if self._stub_mode:
            return self._stub_data["configs"][:top_k]

        where = {"db_type": db_type} if db_type else None
        results = self._collections["configs"].query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_search_results(results)

    def add_case(self, case: CaseKnowledge) -> str:
        """添加故障案例"""
        if self._stub_mode:
            doc_id = case.id or f"case_{hashlib.md5(case.title.encode()).hexdigest()[:12]}"
            self._stub_data["cases"].append({
                "id": doc_id,
                "instance_id": case.instance_id,
                "title": case.title,
                "symptoms": case.symptoms,
            })
            return doc_id

        content = self._format_case_content(case)
        doc_id = case.id or f"case_{hashlib.md5(case.title.encode()).hexdigest()[:12]}"

        self._collections["cases"].upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{
                "instance_id": case.instance_id,
                "db_type": case.db_type,
                "db_version": case.db_version,
                "title": case.title,
                "created_at": case.created_at,
            }]
        )
        return doc_id

    def search_cases(
        self, query: str, db_type: Optional[str] = None, top_k: int = 5
    ) -> List[Dict]:
        """语义搜索故障案例"""
        if self._stub_mode:
            return self._stub_data["cases"][:top_k]

        where = {"db_type": db_type} if db_type else None
        results = self._collections["cases"].query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_search_results(results)

    def _format_schema_content(self, schema: SchemaKnowledge) -> str:
        tables_desc = "\n".join([
            f"表: {t['table_name']}, 行数: {t.get('row_count', 0)}, "
            f"大小: {t.get('size_bytes', 0)} bytes, "
            f"列: {', '.join(c.get('name', '') for c in t.get('columns', []))}"
            for t in schema.tables
        ])
        return f"""数据库: {schema.db_name}
版本: {schema.version}
采集时间: {schema.captured_at}

表结构:
{tables_desc}
"""

    def _format_config_content(self, config: ConfigKnowledge) -> str:
        params = "\n".join([f"  {k}: {v}" for k, v in list(config.parameters.items())[:50]])
        return f"""数据库类型: {config.db_type}
版本: {config.version}
采集时间: {config.captured_at}

配置参数:
{params}
"""

    def _format_case_content(self, case: CaseKnowledge) -> str:
        return f"""标题: {case.title}
数据库类型: {case.db_type} {case.db_version}
实例: {case.instance_id}

症状:
{case.symptoms}

根因:
{case.root_cause}

解决方案:
{case.solution}
"""

    def _format_search_results(self, results: dict) -> List[Dict]:
        items = []
        if results and results.get("ids"):
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                })
        return items

    def get_stats(self) -> Dict[str, int]:
        """获取知识库统计"""
        if self._stub_mode:
            return {name: len(data) for name, data in self._stub_data.items()}
        return {name: coll.count() for name, coll in self._collections.items()}
