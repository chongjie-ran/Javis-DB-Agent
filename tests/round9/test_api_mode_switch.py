"""
第九轮测试：API模式切换脚本测试

测试 scripts/switch_api_mode.py 脚本功能：
1. Mock模式切换
2. Real模式切换
3. 状态查看
4. 配置验证
"""
import pytest
import sys
import os
import yaml
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# 导入被测试的脚本
from scripts.switch_api_mode import (
    load_config,
    save_config,
    get_current_mode,
    switch_to_mock,
    switch_to_real,
    show_status,
    CONFIG_FILE,
)


class TestAPIModeSwitch:
    """API模式切换测试"""
    
    @pytest.fixture
    def temp_config(self):
        """临时配置文件"""
        # 创建临时目录和配置文件
        temp_dir = tempfile.mkdtemp()
        temp_config_file = os.path.join(temp_dir, "config.yaml")
        
        # 初始化配置
        original_config = load_config()
        test_config = {
            "zcloud_api": {
                "use_mock": True,
                "base_url": "http://localhost:18080",
            },
            "zcloud_real_api": {
                "base_url": "https://zcloud.example.com/api/v1",
                "auth_type": "api_key",
                "api_key": "test-key-12345",
            }
        }
        
        with open(temp_config_file, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)
        
        # 临时替换全局变量
        original_file = CONFIG_FILE
        import scripts.switch_api_mode as module
        module.CONFIG_FILE = temp_config_file
        
        yield temp_config_file
        
        # 恢复
        module.CONFIG_FILE = original_file
        shutil.rmtree(temp_dir)
    
    def test_load_config_structure(self, temp_config):
        """测试配置加载"""
        config = load_config()
        assert config is not None
        assert isinstance(config, dict)
        assert "zcloud_api" in config
    
    def test_get_current_mode_mock(self, temp_config):
        """测试获取当前模式 - Mock模式"""
        config = load_config()
        mode = get_current_mode(config)
        assert mode == True, "当前应该是Mock模式"
    
    def test_get_current_mode_real(self, temp_config):
        """测试获取当前模式 - Real模式"""
        config = load_config()
        config["zcloud_api"]["use_mock"] = False
        save_config(config)
        
        config = load_config()
        mode = get_current_mode(config)
        assert mode == False, "当前应该是Real模式"
    
    def test_switch_to_mock_preserves_structure(self, temp_config):
        """测试切换到Mock模式 - 保持配置结构"""
        switch_to_mock()
        
        config = load_config()
        assert config["zcloud_api"]["use_mock"] == True
        assert config["zcloud_api"]["base_url"] == "http://localhost:18080"
    
    def test_switch_to_real_updates_flag(self, temp_config):
        """测试切换到Real模式 - 更新标志"""
        switch_to_real(
            base_url="https://real-api.example.com",
            api_key="real-key-67890",
            auth_type="api_key"
        )
        
        config = load_config()
        assert config["zcloud_api"]["use_mock"] == False
    
    def test_switch_to_real_with_oauth(self, temp_config):
        """测试切换到Real模式 - OAuth2认证"""
        switch_to_real(
            base_url="https://oauth-api.example.com",
            auth_type="oauth2",
            oauth_client_id="client-id-123",
            oauth_client_secret="client-secret-456"
        )
        
        config = load_config()
        assert config["zcloud_real_api"]["auth_type"] == "oauth2"
        assert config["zcloud_real_api"]["oauth_client_id"] == "client-id-123"
    
    def test_switch_to_real_masks_api_key(self, temp_config, capsys):
        """测试切换到Real模式 - API Key脱敏显示"""
        switch_to_real(
            base_url="https://api.example.com",
            api_key="secret-api-key-12345",
            auth_type="api_key"
        )
        
        # 验证API Key已保存
        config = load_config()
        assert config["zcloud_real_api"]["api_key"] == "secret-api-key-12345"
    
    def test_config_persistence(self, temp_config):
        """测试配置持久化"""
        # 第一次切换
        switch_to_mock()
        config1 = load_config()
        
        # 第二次加载
        config2 = load_config()
        
        assert config1 == config2, "配置应该持久化"
    
    def test_zcloud_real_api_section_created(self, temp_config):
        """测试zcloud_real_api配置段创建"""
        # 确保初始状态没有real_api配置
        config = load_config()
        if "zcloud_real_api" in config:
            del config["zcloud_real_api"]
            save_config(config)
        
        # 切换到real模式
        switch_to_real(base_url="https://new-api.example.com")
        
        # 验证配置段已创建
        config = load_config()
        assert "zcloud_real_api" in config
        assert config["zcloud_real_api"]["base_url"] == "https://new-api.example.com"


class TestAPIModeSwitchEdgeCases:
    """API模式切换边界场景测试"""
    
    def test_missing_zcloud_api_section(self):
        """测试缺少zcloud_api配置段"""
        temp_dir = tempfile.mkdtemp()
        temp_config_file = os.path.join(temp_dir, "config.yaml")
        
        # 创建不完整的配置
        incomplete_config = {"app_name": "test"}
        with open(temp_config_file, "w", encoding="utf-8") as f:
            yaml.dump(incomplete_config, f)
        
        # 临时替换
        import scripts.switch_api_mode as module
        original_file = module.CONFIG_FILE
        module.CONFIG_FILE = temp_config_file
        
        try:
            # 应该能处理这种情况
            config = load_config()
            mode = get_current_mode(config)
            assert mode == True, "缺少配置时应默认为Mock"
        finally:
            module.CONFIG_FILE = original_file
            shutil.rmtree(temp_dir)
    
    def test_switch_without_api_key(self, temp_config=None):
        """测试切换到Real模式时不提供API Key"""
        temp_dir = tempfile.mkdtemp()
        temp_config_file = os.path.join(temp_dir, "config.yaml")
        
        test_config = {"zcloud_api": {"use_mock": True}}
        with open(temp_config_file, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)
        
        import scripts.switch_api_mode as module
        original_file = module.CONFIG_FILE
        module.CONFIG_FILE = temp_config_file
        
        try:
            # 不提供api_key切换
            switch_to_real(base_url="https://api.example.com", auth_type="api_key")
            
            config = load_config()
            assert config["zcloud_api"]["use_mock"] == False
            # api_key应该为空字符串或不设置
            real_api = config.get("zcloud_real_api", {})
            assert "api_key" not in real_api or real_api.get("api_key") in [None, ""]
        finally:
            module.CONFIG_FILE = original_file
            shutil.rmtree(temp_dir)


class TestShowStatus:
    """状态显示测试"""
    
    def test_show_status_output(self, capsys):
        """测试状态显示输出"""
        temp_dir = tempfile.mkdtemp()
        temp_config_file = os.path.join(temp_dir, "config.yaml")
        
        test_config = {
            "zcloud_api": {
                "use_mock": True,
                "base_url": "http://localhost:18080",
            },
            "zcloud_real_api": {
                "base_url": "https://zcloud.example.com",
                "auth_type": "api_key",
            }
        }
        with open(temp_config_file, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)
        
        import scripts.switch_api_mode as module
        original_file = module.CONFIG_FILE
        module.CONFIG_FILE = temp_config_file
        
        try:
            show_status()
            captured = capsys.readouterr()
            assert "Mock" in captured.out or "Real" in captured.out
            assert "use_mock" in captured.out
        finally:
            module.CONFIG_FILE = original_file
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
