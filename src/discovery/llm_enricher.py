"""
LLM语义增强模块

利用Ollama qwen3.5:35b实现自然语言运维。
R1: 预留接口，R4实现完整功能
"""

import logging
from typing import Optional, List, Dict
from dataclasses import dataclass

from .registry import ManagedInstance
from .knowledge_base import LocalKnowledgeBase

logger = logging.getLogger(__name__)

# Ollama可能未配置
try:
    from src.llm.ollama_client import OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("OllamaClient not available. LLM enrichment will be disabled.")


@dataclass
class NLQueryResult:
    """自然语言查询结果"""
    intent: str  # query_session / analyze_lock / check_replication
    entities: Dict  # 提取的实体（instance_id, time_range等）
    generated_sql: str = ""
    summary: str = ""
    confidence: float = 0.0


class LLMEnricher:
    """
    LLM语义增强器

    功能：
    1. 自然语言意图识别
    2. SQL查询生成
    3. schema语义摘要
    4. 诊断推理增强

    Note:
        R1预留接口，R4实现完整功能
    """

    INTENT_PROMPT = """你是一个数据库运维助手。请分析用户的自然语言查询，识别其运维意图。

支持的意图类型：
- query_session: 查询会话列表
- query_lock: 查询锁信息
- analyze_lock: 分析死锁
- check_replication: 检查复制状态
- query_capacity: 查询容量/磁盘
- query_performance: 查询性能指标
- diagnose: 诊断问题

输出格式（JSON）：
{{
  "intent": "意图类型",
  "entities": {{
    "instance_id": "实例ID（如果提到）",
    "time_range": "时间范围（如果提到）",
    "filters": "其他过滤条件"
  }},
  "generated_sql": "生成的SQL查询（如果适用）",
  "summary": "一句话总结",
  "confidence": 0.0-1.0置信度
}}

用户查询：{query}
"""

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        knowledge_base: Optional[LocalKnowledgeBase] = None,
    ):
        """
        初始化LLM增强器

        Args:
            ollama_client: Ollama客户端，默认创建新实例
            knowledge_base: 知识库，默认创建新实例
        """
        self._available = OLLAMA_AVAILABLE
        if self._available:
            self.ollama = ollama_client or OllamaClient()
        else:
            self.ollama = None
        self.kb = knowledge_base

    @property
    def is_available(self) -> bool:
        """LLM是否可用"""
        return self._available and self.ollama is not None

    async def understand_query(self, query: str) -> NLQueryResult:
        """
        理解自然语言查询
        返回意图、实体、生成的SQL

        Args:
            query: 自然语言查询

        Returns:
            NLQueryResult
        """
        if not self.is_available:
            logger.warning("LLM not available, returning empty result")
            return NLQueryResult(
                intent="unavailable",
                entities={},
                summary="LLM not available",
                confidence=0.0,
            )

        try:
            import json
            response = await self.ollama.complete(
                prompt=self.INTENT_PROMPT.format(query=query),
                system="你是一个数据库运维助手，输出JSON格式。"
            )

            # 解析JSON响应
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return NLQueryResult(
                    intent=data.get("intent", "unknown"),
                    entities=data.get("entities", {}),
                    generated_sql=data.get("generated_sql", ""),
                    summary=data.get("summary", ""),
                    confidence=data.get("confidence", 0.0),
                )
        except Exception as e:
            logger.warning(f"Failed to understand query: {e}")

        return NLQueryResult(
            intent="unknown",
            entities={},
            summary="无法理解查询",
            confidence=0.0,
        )

    async def summarize_schema(self, instance_id: str, query: str) -> str:
        """
        基于自然语言查询schema知识库
        返回相关的schema摘要

        Args:
            instance_id: 实例ID
            query: 自然语言查询

        Returns:
            schema摘要
        """
        if not self.kb:
            return "Knowledge base not available"

        results = self.kb.search_schemas(
            query=query,
            instance_id=instance_id,
            top_k=3,
        )

        if not results:
            return "未找到相关schema知识"

        summary_parts = ["找到以下相关表结构：\n"]
        for r in results:
            summary_parts.append(f"- {r['content'][:500]}")
        return "\n".join(summary_parts)

    async def diagnose_with_context(
        self,
        symptom: str,
        instance: ManagedInstance,
    ) -> str:
        """
        诊断推理：结合知识库和LLM进行诊断

        Args:
            symptom: 症状描述
            instance: 数据库实例

        Returns:
            诊断报告
        """
        if not self.is_available:
            return "LLM not available for diagnosis"

        # 检索相关故障案例
        cases = []
        if self.kb:
            cases = self.kb.search_cases(
                query=symptom,
                db_type=instance.db_type,
                top_k=3,
            )

        # 构建诊断上下文
        context = f"数据库类型: {instance.db_type} {instance.version}\n"
        context += f"症状: {symptom}\n\n"
        context += "相关故障案例：\n"
        for c in cases:
            context += f"- {c['content'][:300]}\n\n"

        prompt = f"""你是一个资深数据库管理员。请根据以下信息进行诊断推理。

{context}

请分析：
1. 可能的原因
2. 推荐的检查步骤
3. 可能的解决方案

输出格式：
## 可能原因
...

## 推荐检查
...

## 解决方案
...
"""
        try:
            return await self.ollama.complete(prompt=prompt)
        except Exception as e:
            logger.warning(f"Diagnosis failed: {e}")
            return f"诊断失败: {str(e)}"

    async def generate_sql(
        self,
        intent: str,
        instance: ManagedInstance,
        entities: Dict,
    ) -> str:
        """
        根据意图生成SQL查询

        Args:
            intent: 意图类型
            instance: 数据库实例
            entities: 提取的实体

        Returns:
            SQL查询
        """
        if not self.is_available:
            return ""

        # 为不同意图生成不同的SQL模板
        sql_templates = {
            "query_session": """
SELECT pid, usename, datname, state, query, query_start
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start NULLS LAST;
""",
            "query_lock": """
SELECT l.locktype, l.mode, l.granted, l.pid,
       l.relation::regclass AS relation, l.database
FROM pg_locks l
WHERE NOT l.granted;
""",
            "query_capacity": """
SELECT
    pg_database.datname,
    pg_database_size(pg_database.datname) as size_bytes
FROM pg_database
WHERE datname NOT IN ('postgres', 'template0', 'template1')
ORDER BY size_bytes DESC;
""",
        }

        return sql_templates.get(intent, "-- No SQL template available")
