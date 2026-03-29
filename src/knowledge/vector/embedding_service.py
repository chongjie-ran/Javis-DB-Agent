"""嵌入服务 - Ollama嵌入模型集成"""
import os
import httpx
from typing import List, Optional, Union
import numpy as np


class EmbeddingService:
    """
    嵌入服务 - 使用Ollama生成文本向量嵌入
    
    支持的模型:
    - nomic-embed-text (默认)
    - mxbai-embed-large
    - e5-mistral-7b-dual
    """
    
    DEFAULT_MODEL = "nomic-embed-text"
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    API_TIMEOUT = 60.0
    
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化嵌入服务
        
        Args:
            model: 嵌入模型名称，默认使用nomic-embed-text
            base_url: Ollama服务地址
        """
        self.model = model or self.DEFAULT_MODEL
        self.base_url = base_url or self.OLLAMA_BASE_URL
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.API_TIMEOUT
            )
        return self._client
    
    async def close(self):
        """关闭HTTP客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def embed_text(self, text: str) -> List[float]:
        """
        单条文本嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量 (List[float])
        """
        client = await self._get_client()
        
        response = await client.post("/api/embeddings", json={
            "model": self.model,
            "prompt": text
        })
        
        if response.status_code != 200:
            raise RuntimeError(f"Embedding API error: {response.status_code} - {response.text}")
        
        result = response.json()
        return result.get("embedding", [])
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        批量文本嵌入
        
        Args:
            texts: 输入文本列表
            
        Returns:
            嵌入向量列表
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        return embeddings
    
    async def compute_similarity(self, text1: str, text2: str) -> float:
        """
        计算两条文本的相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数 (0-1)
        """
        emb1 = await self.embed_text(text1)
        emb2 = await self.embed_text(text2)
        
        # 余弦相似度
        vec1 = np.array(emb1)
        vec2 = np.array(emb2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    async def health_check(self) -> bool:
        """
        检查Ollama服务健康状态
        
        Returns:
            服务是否可用
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    async def list_models(self) -> List[dict]:
        """
        列出可用的嵌入模型
        
        Returns:
            模型列表
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
            return []
        except Exception:
            return []
