"""向量索引 - Chroma向量数据库集成"""
import os
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False


@dataclass
class VectorRecord:
    """向量记录"""
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]


class VectorIndex:
    """
    向量索引 - 基于Chroma的向量存储和检索
    
    功能:
    - 添加向量记录
    - 相似度搜索
    - 记录更新和删除
    """
    
    COLLECTION_NAME = "knowledge_base"
    DEFAULT_PERSIST_DIR = "data/chroma"
    
    def __init__(self, persist_dir: Optional[str] = None):
        """
        初始化向量索引
        
        Args:
            persist_dir: Chroma持久化目录
        """
        if not CHROMA_AVAILABLE:
            raise RuntimeError("ChromaDB not installed. Install with: pip install chromadb")
        
        self.persist_dir = persist_dir or self.DEFAULT_PERSIST_DIR
        os.makedirs(self.persist_dir, exist_ok=True)
        
        self._client: Optional[chromadb.Client] = None
        self._collection = None
    
    def _get_client(self) -> chromadb.Client:
        """获取Chroma客户端"""
        if self._client is None:
            self._client = chromadb.Client(Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                persist_directory=self.persist_dir
            ))
        return self._client
    
    @property
    def collection(self):
        """获取集合"""
        if self._collection is None:
            client = self._get_client()
            try:
                self._collection = client.get_collection(name=self.COLLECTION_NAME)
            except Exception:
                self._collection = client.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "Knowledge base vector index"}
                )
        return self._collection
    
    def add_record(self, record: VectorRecord) -> bool:
        """
        添加向量记录
        
        Args:
            record: 向量记录
            
        Returns:
            是否成功
        """
        try:
            self.collection.add(
                ids=[record.id],
                documents=[record.content],
                embeddings=[record.embedding],
                metadatas=[record.metadata]
            )
            return True
        except Exception as e:
            print(f"Error adding record: {e}")
            return False
    
    def add_records(self, records: List[VectorRecord]) -> bool:
        """
        批量添加向量记录
        
        Args:
            records: 向量记录列表
            
        Returns:
            是否成功
        """
        try:
            self.collection.add(
                ids=[r.id for r in records],
                documents=[r.content for r in records],
                embeddings=[r.embedding for r in records],
                metadatas=[r.metadata for r in records]
            )
            return True
        except Exception as e:
            print(f"Error adding records: {e}")
            return False
    
    def search(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict] = None,
        where_document: Optional[Dict] = None
    ) -> List[Dict]:
        """
        向量相似度搜索
        
        Args:
            query_embedding: 查询向量
            n_results: 返回结果数量
            where: 元数据过滤条件
            where_document: 文档内容过滤条件
            
        Returns:
            搜索结果列表
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                where_document=where_document
            )
            
            formatted_results = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    formatted_results.append({
                        "id": doc_id,
                        "content": results["documents"][0][i] if results["documents"] else "",
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                    })
            
            return formatted_results
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def search_by_text(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict]:
        """
        通过文本搜索（需要外部嵌入）
        
        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            where: 元数据过滤条件
            
        Returns:
            搜索结果列表
        """
        # 注意：实际使用中需要先调用embedding_service获取向量
        # 这里只是占位，需要外部传入query_embedding
        raise NotImplementedError("Use search() with pre-computed embedding")
    
    def get_record(self, record_id: str) -> Optional[Dict]:
        """
        获取单条记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            记录或None
        """
        try:
            result = self.collection.get(ids=[record_id])
            if result["ids"]:
                return {
                    "id": result["ids"][0],
                    "content": result["documents"][0] if result["documents"] else "",
                    "metadata": result["metadatas"][0] if result["metadatas"] else {}
                }
            return None
        except Exception:
            return None
    
    def update_record(self, record: VectorRecord) -> bool:
        """
        更新向量记录
        
        Args:
            record: 向量记录
            
        Returns:
            是否成功
        """
        try:
            self.collection.update(
                ids=[record.id],
                documents=[record.content],
                embeddings=[record.embedding],
                metadatas=[record.metadata]
            )
            return True
        except Exception as e:
            print(f"Error updating record: {e}")
            return False
    
    def delete_record(self, record_id: str) -> bool:
        """
        删除向量记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        try:
            self.collection.delete(ids=[record_id])
            return True
        except Exception as e:
            print(f"Error deleting record: {e}")
            return False
    
    def count(self) -> int:
        """获取记录总数"""
        try:
            return self.collection.count()
        except Exception:
            return 0
    
    def reset(self) -> bool:
        """
        重置索引（删除所有记录）
        
        Returns:
            是否成功
        """
        try:
            client = self._get_client()
            client.delete_collection(name=self.COLLECTION_NAME)
            self._collection = None
            return True
        except Exception as e:
            print(f"Error resetting index: {e}")
            return False
