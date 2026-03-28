"""配置管理"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用
    app_name: str = "zCloudNewAgentProject"
    app_version: str = "v1.0"
    debug: bool = False
    
    # LLM - Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "glm4:latest"
    ollama_timeout: int = 60
    
    # 数据库
    db_path: str = "data/zcloud_agent.db"
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
    
    # 知识库
    knowledge_base_path: str = "knowledge/"
    alert_rules_path: str = "knowledge/alert_rules.yaml"
    sop_path: str = "knowledge/sop/"
    cases_path: str = "knowledge/cases/"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局单例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings():
    global _settings
    _settings = Settings()
