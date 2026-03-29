"""混合搜索 - 结合向量搜索和关键词搜索"""
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

try:
    from src.knowledge.vector.embedding_service import EmbeddingService
    from src.knowledge.vector.vector_index import VectorIndex, VectorRecord
    VECTOR_COMPONENTS_AVAILABLE = True
except ImportError:
    VECTOR_COMPONENTS_AVAILABLE = False


@dataclass
class HybridSearchResult:
    """混合搜索结果"""
    id: str
    content_type: str
    content_id: str
    title: str
    content: str
    vector_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class HybridSearch:
    """
    混合搜索引擎
    
    结合:
    - 向量相似度搜索 (语义理解)
    - 关键词搜索 (精确匹配)
    
    评分公式: combined_score = alpha * vector_score + (1-alpha) * keyword_score
    """
    
    DEFAULT_ALPHA = 0.7  # 向量搜索权重
    
    def __init__(
        self,
        db_conn: Any,
        embedding_service: Optional["EmbeddingService"] = None,
        vector_index: Optional["VectorIndex"] = None,
        alpha: float = DEFAULT_ALPHA
    ):
        """
        初始化混合搜索
        
        Args:
            db_conn: 数据库连接
            embedding_service: 嵌入服务
            vector_index: 向量索引
            alpha: 向量搜索权重 (0-1)
        """
        self.db = db_conn
        self.embedding_service = embedding_service
        self.vector_index = vector_index
        self.alpha = alpha
        
        self._kb_service = None
    
    @property
    def kb_service(self):
        """获取知识库服务"""
        if self._kb_service is None:
            from src.knowledge.services.knowledge_base_service import KnowledgeBaseService
            self._kb_service = KnowledgeBaseService(self.db)
        return self._kb_service
    
    async def search(
        self,
        query: str,
        content_types: Optional[List[str]] = None,
        limit: int = 10,
        enable_vector: bool = True,
        enable_keyword: bool = True
    ) -> List[HybridSearchResult]:
        """
        执行混合搜索
        
        Args:
            query: 搜索查询
            content_types: 限定的内容类型
            limit: 返回结果数量
            enable_vector: 启用向量搜索
            enable_keyword: 启用关键词搜索
            
        Returns:
            搜索结果列表
        """
        results: Dict[str, HybridSearchResult] = {}
        
        # 1. 关键词搜索
        if enable_keyword:
            keyword_results = await self._keyword_search(query, content_types)
            for result in keyword_results:
                results[result.content_id] = result
        
        # 2. 向量搜索
        if enable_vector and self.embedding_service and self.vector_index:
            vector_results = await self._vector_search(query, content_types, limit)
            for result in vector_results:
                if result.content_id in results:
                    # 合并评分
                    existing = results[result.content_id]
                    existing.vector_score = result.vector_score
                    existing.combined_score = (
                        self.alpha * result.vector_score +
                        (1 - self.alpha) * existing.keyword_score
                    )
                else:
                    results[result.content_id] = result
        
        # 按综合评分排序
        sorted_results = sorted(
            results.values(),
            key=lambda x: x.combined_score,
            reverse=True
        )
        
        return sorted_results[:limit]
    
    async def _keyword_search(
        self,
        query: str,
        content_types: Optional[List[str]] = None
    ) -> List[HybridSearchResult]:
        """关键词搜索"""
        results = []
        types_to_search = content_types or ["alert_rule", "sop", "case"]
        
        # 搜索告警规则
        if "alert_rule" in types_to_search:
            rules = await self.kb_service.search_alert_rules(query)
            for rule in rules:
                # 计算关键词匹配分数
                keyword_score = self._calc_keyword_score(query, rule)
                results.append(HybridSearchResult(
                    id=f"alert_rule_{rule['id']}",
                    content_type="alert_rule",
                    content_id=rule["id"],
                    title=rule["name"],
                    content=f"{rule.get('condition', '')} {rule.get('recommendation', '')}",
                    keyword_score=keyword_score,
                    combined_score=keyword_score,
                    metadata={"severity": rule.get("severity")}
                ))
        
        # 搜索SOP
        if "sop" in types_to_search:
            sops = await self.kb_service.search_sops(query)
            for sop in sops:
                steps_str = json.dumps(sop.get("steps", []), ensure_ascii=False)
                keyword_score = self._calc_keyword_score(query, sop)
                results.append(HybridSearchResult(
                    id=f"sop_{sop['id']}",
                    content_type="sop",
                    content_id=sop["id"],
                    title=sop["title"],
                    content=steps_str,
                    keyword_score=keyword_score,
                    combined_score=keyword_score,
                    metadata={}
                ))
        
        # 搜索案例
        if "case" in types_to_search:
            cases = await self.kb_service.search_cases(query)
            for case in cases:
                content = f"{case.get('root_cause', '')} {case.get('solution', '')}"
                keyword_score = self._calc_keyword_score(query, case)
                results.append(HybridSearchResult(
                    id=f"case_{case['id']}",
                    content_type="case",
                    content_id=case["id"],
                    title=case["title"],
                    content=content,
                    keyword_score=keyword_score,
                    combined_score=keyword_score,
                    metadata={}
                ))
        
        return results
    
    async def _vector_search(
        self,
        query: str,
        content_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[HybridSearchResult]:
        """向量搜索"""
        results = []
        
        try:
            # 获取查询向量
            query_embedding = await self.embedding_service.embed_text(query)
            
            # 构建过滤条件
            where = None
            if content_types:
                where = {"content_type": {"$in": content_types}}
            
            # 执行搜索
            search_results = self.vector_index.search(
                query_embedding=query_embedding,
                n_results=limit,
                where=where
            )
            
            for r in search_results:
                metadata = r.get("metadata", {})
                # 将距离转换为相似度分数 (Chroma用L2距离)
                distance = r.get("distance", 0)
                vector_score = 1.0 / (1.0 + distance)
                
                results.append(HybridSearchResult(
                    id=r["id"],
                    content_type=metadata.get("content_type", ""),
                    content_id=r["id"],
                    title=metadata.get("title", ""),
                    content=r.get("content", ""),
                    vector_score=vector_score,
                    combined_score=vector_score,
                    metadata=metadata
                ))
        except Exception as e:
            print(f"Vector search error: {e}")
        
        return results
    
    def _calc_keyword_score(self, query: str, record: Dict) -> float:
        """计算关键词匹配分数"""
        query_lower = query.lower()
        
        # 检查标题匹配
        title = record.get("title", record.get("name", "")).lower()
        if query_lower in title:
            return 1.0
        
        # 检查内容匹配
        content = ""
        if "condition" in record:
            content += record["condition"].lower()
        if "recommendation" in record:
            content += record["recommendation"].lower()
        if "root_cause" in record:
            content += record["root_cause"].lower()
        if "solution" in record:
            content += record["solution"].lower()
        
        if query_lower in content:
            return 0.8
        
        # 简单的词重叠计算
        query_words = set(query_lower.split())
        content_words = set(content.split())
        overlap = len(query_words & content_words)
        
        if overlap > 0:
            return 0.5 * (overlap / len(query_words))
        
        return 0.0
    
    async def index_content(
        self,
        content_type: str,
        content_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        将内容添加到向量索引
        
        Args:
            content_type: 内容类型
            content_id: 内容ID
            title: 标题
            content: 内容文本
            metadata: 元数据
            
        Returns:
            是否成功
        """
        if not self.embedding_service or not self.vector_index:
            return False
        
        try:
            # 生成嵌入
            full_content = f"{title}\n{content}"
            embedding = await self.embedding_service.embed_text(full_content)
            
            # 创建记录
            record = VectorRecord(
                id=f"{content_type}_{content_id}",
                content=full_content,
                embedding=embedding,
                metadata={
                    "content_type": content_type,
                    "content_id": content_id,
                    "title": title,
                    **(metadata or {})
                }
            )
            
            return self.vector_index.add_record(record)
        except Exception as e:
            print(f"Error indexing content: {e}")
            return False
