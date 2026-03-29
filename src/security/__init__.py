"""安全模块 - TLS/SSL、敏感数据脱敏、API鉴权、限速"""
from src.security.tls import TLSConfig, TLSMiddleware, enforce_https
from src.security.sensitive import SensitiveDataMask, mask_sensitive_data
from src.security.rate_limit import (
    RateLimitMiddleware,
    RateLimitDependency,
    RateLimitConfig,
    RateLimitExceeded,
    rate_limit,
    configure_rate_limits,
    get_rate_limit_status,
    get_rate_store,
    extract_client_ip,
    DEFAULT_LIMITS,
)

__all__ = [
    # TLS
    "TLSConfig",
    "TLSMiddleware",
    "enforce_https",
    # 敏感数据
    "SensitiveDataMask",
    "mask_sensitive_data",
    # 限速
    "RateLimitMiddleware",
    "RateLimitDependency",
    "RateLimitConfig",
    "RateLimitExceeded",
    "rate_limit",
    "configure_rate_limits",
    "get_rate_limit_status",
    "get_rate_store",
    "extract_client_ip",
    "DEFAULT_LIMITS",
]
