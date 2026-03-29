"""测试 Pydantic V3 迁移 (第15轮 P0-1)

验证所有 Config 类已迁移至 model_config = ConfigDict(...)
"""
import pytest

from src.config import Settings
from src.real_api.config import RealAPIConfig
from src.channels.wecom.config import WecomChannelConfig


class TestPydanticV3Migration:
    """确保所有配置类使用 Pydantic V3 语法"""

    def test_settings_uses_model_config(self):
        """Settings 类应使用 model_config 而非 class Config"""
        assert hasattr(Settings, "model_config")
        # model_config 是一个 dict-like 对象
        cfg = dict(Settings.model_config)
        assert cfg.get("env_file") == ".env"
        assert cfg.get("env_file_encoding") == "utf-8"
        # 确保没有 class Config
        assert "Config" not in Settings.__dict__

    def test_real_api_config_uses_model_config(self):
        """RealAPIConfig 类应使用 model_config 而非 class Config"""
        assert hasattr(RealAPIConfig, "model_config")
        cfg = dict(RealAPIConfig.model_config)
        assert cfg.get("env_prefix") == "ZCLOUD_"
        assert "Config" not in RealAPIConfig.__dict__

    def test_wecom_channel_config_uses_model_config(self):
        """WecomChannelConfig 类应使用 model_config 而非 class Config"""
        assert hasattr(WecomChannelConfig, "model_config")
        cfg = dict(WecomChannelConfig.model_config)
        assert cfg.get("env_prefix") == "WECOM_"
        assert cfg.get("extra") == "allow"
        assert "Config" not in WecomChannelConfig.__dict__


class TestSettingsBehavior:
    """Settings 功能回归测试"""

    def test_settings_defaults(self):
        s = Settings()
        assert s.app_name == "Javis-DB-Agent"
        assert s.debug is False
        assert s.api_port == 8000

    def test_settings_env_override(self, monkeypatch):
        monkeypatch.setenv("APP_NAME", "TestApp")
        monkeypatch.setenv("DEBUG", "true")
        s = Settings()
        assert s.app_name == "TestApp"
        assert s.debug is True


class TestRealAPIConfigBehavior:
    """RealAPIConfig 功能回归测试"""

    def test_real_api_config_defaults(self):
        c = RealAPIConfig()
        assert c.auth_type == "api_key"
        assert c.timeout == 30
        assert c.use_mock is True

    def test_real_api_config_oauth2_env_prefix(self, monkeypatch):
        monkeypatch.setenv("ZCLOUD_AUTH_TYPE", "oauth2")
        monkeypatch.setenv("ZCLOUD_API_KEY", "test-key-123")
        c = RealAPIConfig()
        assert c.auth_type == "oauth2"
        assert c.api_key == "test-key-123"


class TestWecomChannelConfigBehavior:
    """WecomChannelConfig 功能回归测试"""

    def test_wecom_config_defaults(self):
        w = WecomChannelConfig()
        assert w.enabled is False
        assert w.session_enabled is True
        assert w.api_timeout == 30
        assert w.send_rate_limit == 10

    def test_wecom_config_env_override(self, monkeypatch):
        monkeypatch.setenv("WECOM_ENABLED", "true")
        monkeypatch.setenv("WECOM_CORP_ID", "test-corp-id")
        monkeypatch.setenv("WECOM_AGENT_ID", "123456")
        w = WecomChannelConfig()
        assert w.enabled is True
        assert w.corp_id == "test-corp-id"
        assert w.agent_id == 123456
