"""LLM层 - Ollama客户端封装（支持TLS加密）"""
import ssl
import httpx
import json
from typing import Optional, AsyncIterator
from src.config import get_settings
from src.security.tls import TLSConfig


class OllamaClient:
    """Ollama API客户端（支持TLS加密通信）"""
    
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.timeout = settings.ollama_timeout
        self._tls_config = TLSConfig.from_env()
        self._ssl_context: Optional[ssl.SSLContext] = None
        if not self._tls_config.ollama_verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
    
    def _get_client(self) -> httpx.AsyncClient:
        kwargs = {"base_url": self.base_url, "timeout": self.timeout}
        if self._ssl_context:
            kwargs["verify"] = self._ssl_context
        elif not self._tls_config.ollama_verify_ssl:
            kwargs["verify"] = False
        return httpx.AsyncClient(**kwargs)
    
    async def complete(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
        """同步补全（用于Agent推理）"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        async with self._get_client() as client:
            response = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    **kwargs
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]
    
    async def complete_stream(self, prompt: str, system: Optional[str] = None, **kwargs) -> AsyncIterator[str]:
        """流式补全"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        async with self._get_client() as client:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    **kwargs
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                # 优先使用 content，如果没有则使用 thinking（qwen3.5:35b等模型输出在thinking字段）
                                content = data["message"].get("content", "")
                                thinking = data["message"].get("thinking", "")
                                yield content or thinking or ""
                        except json.JSONDecodeError:
                            continue
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """generate接口（非chat）"""
        async with self._get_client() as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    **kwargs
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["response"]
    
    async def list_models(self) -> list:
        """列出可用模型"""
        async with self._get_client() as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with self._get_client() as client:
                response = await client.get("/")
                return response.status_code == 200
        except Exception:
            return False


# 全局单例
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client
