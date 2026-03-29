"""TLS/SSL配置与HTTPS强制启用"""
import ssl
import os
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse


@dataclass
class TLSConfig:
    """
    TLS/SSL配置
    
    HTTPS强制策略：
    - enabled: 启用HTTPS强制（所有HTTP请求重定向到HTTPS）
    - hsts_enabled: 启用HSTS（HTTP严格传输安全）
    - hsts_max_age: HSTS有效期（秒），默认1年
    - hsts_include_subdomains: 是否包含子域名
    - cert_file: SSL证书文件路径
    - key_file: SSL私钥文件路径
    - verify_ssl: 是否验证SSL证书（Ollama等内部服务可关闭）
    """
    enabled: bool = False
    hsts_enabled: bool = False
    hsts_max_age: int = 31536000  # 1年
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    verify_ssl: bool = True
    
    # Ollama TLS配置
    ollama_verify_ssl: bool = True
    ollama_client_cert_file: Optional[str] = None
    ollama_client_key_file: Optional[str] = None
    ollama_ca_file: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "TLSConfig":
        """从环境变量加载配置"""
        return cls(
            enabled=os.environ.get("ZLOUD_HTTPS_ENABLED", "false").lower() == "true",
            hsts_enabled=os.environ.get("ZLOUD_HSTS_ENABLED", "false").lower() == "true",
            hsts_max_age=int(os.environ.get("ZLOUD_HSTS_MAX_AGE", "31536000")),
            hsts_include_subdomains=os.environ.get("ZLOUD_HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true",
            hsts_preload=os.environ.get("ZLOUD_HSTS_PRELOAD", "false").lower() == "true",
            cert_file=os.environ.get("ZLOUD_SSL_CERT_FILE") or None,
            key_file=os.environ.get("ZLOUD_SSL_KEY_FILE") or None,
            verify_ssl=os.environ.get("ZLOUD_VERIFY_SSL", "true").lower() == "true",
            ollama_verify_ssl=os.environ.get("ZLOUD_OLLAMA_VERIFY_SSL", "true").lower() == "true",
            ollama_client_cert_file=os.environ.get("ZLOUD_OLLAMA_CLIENT_CERT_FILE") or None,
            ollama_client_key_file=os.environ.get("ZLOUD_OLLAMA_CLIENT_KEY_FILE") or None,
            ollama_ca_file=os.environ.get("ZLOUD_OLLAMA_CA_FILE") or None,
        )
    
    def validate(self) -> list[str]:
        """验证配置合法性，返回错误列表"""
        errors = []
        if self.enabled:
            if not self.cert_file:
                errors.append("ZLOUD_SSL_CERT_FILE 未配置")
            elif not Path(self.cert_file).exists():
                errors.append(f"SSL证书文件不存在: {self.cert_file}")
            if not self.key_file:
                errors.append("ZLOUD_SSL_KEY_FILE 未配置")
            elif not Path(self.key_file).exists():
                errors.append(f"SSL私钥文件不存在: {self.key_file}")
            # 检查私钥权限
            if self.key_file and Path(self.key_file).exists():
                mode = Path(self.key_file).stat().st_mode & 0o777
                if mode & 0o077:
                    errors.append(f"SSL私钥权限过宽({oct(mode)})，建议设置为0o600")
        return errors
    
    def get_hsts_header(self) -> Optional[str]:
        """生成HSTS响应头"""
        if not self.enabled or not self.hsts_enabled:
            return None
        directives = [f"max-age={self.hsts_max_age}"]
        if self.hsts_include_subdomains:
            directives.append("includeSubDomains")
        if self.hsts_preload:
            directives.append("preload")
        return "; ".join(directives)
    
    def get_ssl_context(self) -> Optional[ssl.SSLContext]:
        """创建SSL上下文（用于uvicorn）"""
        if not self.enabled:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert_file, self.key_file)
        return ctx
    
    def get_ollama_ssl_context(self) -> Optional[ssl.SSLContext]:
        """创建Ollama客户端SSL上下文"""
        if not self.ollama_verify_ssl:
            return None  # 跳过验证
        ctx = ssl.create_default_context()
        if self.ollama_ca_file:
            ctx.load_verify_locations(self.ollama_ca_file)
        if self.ollama_client_cert_file and self.ollama_client_key_file:
            ctx.load_cert_chain(self.ollama_client_cert_file, self.ollama_client_key_file)
        return ctx


class TLSMiddleware(BaseHTTPMiddleware):
    """
    HTTPS强制中间件
    
    功能：
    1. HTTP → HTTPS 重定向（生产环境）
    2. HSTS响应头注入
    3. 安全响应头（X-Frame-Options, X-Content-Type-Options等）
    """
    
    def __init__(self, app, config: Optional[TLSConfig] = None):
        super().__init__(app)
        self.config = config or TLSConfig.from_env()
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # 仅在HTTPS启用时处理
        if self.config.enabled:
            # 检查是否为HTTP请求
            if request.url.scheme == "http":
                # 获取原始host
                host = request.headers.get("host", "")
                # 构建HTTPS URL
                https_url = str(request.url.replace(scheme="https"))
                response = RedirectResponse(https_url, status_code=307)
                # 添加HSTS头
                hsts = self.config.get_hsts_header()
                if hsts:
                    response.headers["Strict-Transport-Security"] = hsts
                return response
        
        # 处理请求
        response = await call_next(request)
        
        # 添加安全响应头
        if self.config.enabled:
            # HSTS
            hsts = self.config.get_hsts_header()
            if hsts:
                response.headers["Strict-Transport-Security"] = hsts
            # 其他安全头
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-XSS-Protection", "1; mode=block")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            # 防止缓存敏感数据
            response.headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, private")
            response.headers.setdefault("Pragma", "no-cache")
        
        return response


def enforce_https(app, config: Optional[TLSConfig] = None) -> None:
    """
    为FastAPI应用启用HTTPS强制
    
    Usage:
        from src.security.tls import enforce_https
        enforce_https(app)  # 自动从环境变量加载配置
    """
    tls_config = config or TLSConfig.from_env()
    tls_config.enabled = True  # 强制启用
    app.add_middleware(TLSMiddleware, config=tls_config)
