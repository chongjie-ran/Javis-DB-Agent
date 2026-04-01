"""配置管理"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator
from typing import Optional
import os
import threading
from pathlib import Path


def _get_data_dir() -> str:
    """获取数据目录路径，默认为 ./data"""
    return os.environ.get("DATA_DIR", "data")


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用
    app_name: str = "Javis-DB-Agent"
    app_version: str = "2.1.0"
    debug: bool = False
    
    # LLM - Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:35b"
    ollama_timeout: int = 60
    
    # 数据库
    db_path: str = "data/javis_db_agent.db"
    audit_db_path: str = "data/audit.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # ChromaDB
    chroma_db_path: str = "data/chroma"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # 安全
    policy_require_approval_l4: bool = True  # L4及以上需要审批
    policy_require_dual_approval_l5: bool = True  # L5需要双人审批
    
    # 审批令牌TTL
    approval_l4_ttl_seconds: int = 600  # L4令牌有效期10分钟
    approval_l5_ttl_seconds: int = 300  # L5令牌有效期5分钟
    
    # TLS/SSL配置
    https_enabled: bool = False  # 强制HTTPS
    hsts_enabled: bool = False  # HSTS头
    ssl_cert_file: Optional[str] = None  # SSL证书路径
    ssl_key_file: Optional[str] = None  # SSL私钥路径
    verify_ssl: bool = True  # 验证SSL证书
    ollama_verify_ssl: bool = True  # Ollama SSL验证
    
    # 知识库
    knowledge_base_path: str = "knowledge/"
    alert_rules_path: str = "knowledge/alert_rules.yaml"
    sop_path: str = "knowledge/sop/"
    cases_path: str = "knowledge/cases/"
    
    @field_validator("db_path", "audit_db_path", "chroma_db_path", mode="before")
    @classmethod
    def resolve_data_dir(cls, v: str) -> str:
        """将相对路径转换为基于 DATA_DIR 的绝对路径"""
        if v.startswith("/"):
            return v  # 已经是绝对路径
        data_dir = _get_data_dir()
        # 如果 v 是 "data/xxx" 形式，替换为 DATA_DIR/xxx
        if v.startswith("data/"):
            return str(Path(data_dir) / v[5:])
        return str(Path(data_dir) / v)
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# 全局单例（线程安全）
_settings: Optional[Settings] = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        with _settings_lock:
            if _settings is None:  # 二次检查
                _settings = Settings()
    return _settings


def reload_settings():
    global _settings
    with _settings_lock:
        _settings = Settings()
