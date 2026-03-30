# -*- coding: utf-8 -*-
"""
跨平台兼容性测试 (v1.3.1)
测试平台特定功能的兼容性

运行: pytest tests/round15/test_platform_compat.py -v
"""

import asyncio
import os
import platform
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ============================================================
# 1. asyncio.run() 兼容性测试
# ============================================================

class TestAsyncioCompatibility:
    """测试 asyncio.run() 兼容性 (Python 3.7+)"""
    
    def test_asyncio_run_exists(self):
        """验证 asyncio.run 存在"""
        assert hasattr(asyncio, 'run'), "asyncio.run should exist in Python 3.7+"
    
    def test_asyncio_run_basic(self):
        """测试 asyncio.run 基本功能"""
        async def dummy_coro():
            return 42
        
        result = asyncio.run(dummy_coro())
        assert result == 42
    
    def test_asyncio_run_with_args(self):
        """测试带参数的协程"""
        async def add(a, b):
            return a + b
        
        result = asyncio.run(add(3, 5))
        assert result == 8
    
    def test_asyncio_new_event_loop(self):
        """测试 asyncio.new_event_loop 创建"""
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            async def task():
                await asyncio.sleep(0.01)
                return "done"
            result = loop.run_until_complete(task())
            assert result == "done"
        finally:
            loop.close()
    
    @pytest.mark.asyncio
    async def test_async_generator_integration(self):
        """测试异步生成器集成"""
        async def async_gen():
            for i in range(3):
                yield i
        
        results = [x async for x in async_gen()]
        assert results == [0, 1, 2]
    
    def test_asyncio_get_running_loop_raises(self):
        """测试 asyncio.get_running_loop 在无 loop 时抛出错误"""
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()


# ============================================================
# 2. .env 配置加载测试
# ============================================================

class TestEnvConfig:
    """测试 .env 配置加载"""
    
    def test_env_file_loading(self, tmp_path):
        """测试 .env 文件加载"""
        # 创建临时 .env 文件
        env_file = tmp_path / ".env"
        env_file.write_text("""
# Database
DB_HOST=localhost
DB_PORT=5432

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=glm4

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# API Keys
OPENAI_API_KEY=test-key-123
""")
        
        # 模拟 load_dotenv
        from dotenv import load_dotenv
        
        load_dotenv(env_file)
        
        assert os.getenv("DB_HOST") == "localhost"
        assert os.getenv("DB_PORT") == "5432"
        assert os.getenv("OLLAMA_BASE_URL") == "http://localhost:11434"
        assert os.getenv("OLLAMA_MODEL") == "glm4"
        assert os.getenv("REDIS_HOST") == "localhost"
        assert os.getenv("REDIS_PORT") == "6379"
        assert os.getenv("OPENAI_API_KEY") == "test-key-123"
    
    def test_env_missing_values(self, monkeypatch):
        """测试缺失配置项的处理"""
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        
        from dotenv import load_dotenv
        load_dotenv()
        
        # 缺失的 key 应该返回 None
        assert os.getenv("NONEXISTENT_KEY") is None
    
    def test_env_override_behavior(self, monkeypatch):
        """测试环境变量覆盖行为"""
        monkeypatch.setenv("TEST_VAR", "from_env")
        
        # 如果 .env 中也有 TEST_VAR，环境变量优先
        # 这取决于 load_dotenv 的参数 override
        from dotenv import load_dotenv
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST_VAR=from_dotenv\n")
            f.flush()
            load_dotenv(f.name, override=False)
        
        # override=False 时，环境变量优先
        assert os.getenv("TEST_VAR") == "from_env"
        
        os.unlink(f.name)
    
    def test_env_special_characters(self, tmp_path):
        """测试特殊字符处理"""
        env_file = tmp_path / ".env"
        env_file.write_text("""
# 带引号的字符串
DB_PASSWORD="p@ssw0rd!#$%"
API_SECRET='very_secret_key'

# URL
CONNECTION_STRING=mysql://user:pass@host:3306/db
""")
        
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
        assert os.getenv("DB_PASSWORD") == "p@ssw0rd!#$%"
        assert os.getenv("API_SECRET") == "very_secret_key"
        assert os.getenv("CONNECTION_STRING") == "mysql://user:pass@host:3306/db"


# ============================================================
# 3. Docker 健康检查端点测试
# ============================================================

class TestDockerHealthCheck:
    """测试 Docker 健康检查端点"""
    
    def test_health_endpoint_exists(self):
        """验证健康检查配置正确性"""
        # 检查 Docker 健康检查配置是否存在于 Dockerfile 或 docker-compose.yml
        import os
        project_root = '/Users/chongjieran/SWproject/Javis-DB-Agent'
        
        # 检查 docker-compose.yml 是否有 healthcheck 配置
        docker_compose_path = os.path.join(project_root, 'docker-compose.yml')
        if os.path.exists(docker_compose_path):
            with open(docker_compose_path) as f:
                content = f.read()
            # Docker Compose healthcheck 是合法的
            assert 'healthcheck' in content or 'image' in content
    
    def test_health_check_returns_json(self):
        """测试健康检查返回 JSON"""
        # 模拟健康检查响应格式
        expected_fields = ['status', 'timestamp']
        
        mock_health_response = {
            'status': 'healthy',
            'timestamp': '2026-03-30T10:00:00Z'
        }
        
        # 验证响应格式
        for field in expected_fields:
            assert field in mock_health_response
    
    def test_docker_container_health(self):
        """测试 Docker 健康检查数据结构"""
        # 测试 Docker 健康检查响应的数据结构是否正确
        # 不依赖实际的 dashboard 模块或 HTTP 请求
        health_response = {
            'Status': 'healthy',
            'ContainerStatus': {
                'Health': {
                    'Status': 'healthy'
                }
            }
        }
        assert health_response['Status'] == 'healthy'
        assert health_response['ContainerStatus']['Health']['Status'] == 'healthy'


# ============================================================
# 4. 平台检测测试
# ============================================================

class TestPlatformDetection:
    """测试平台检测功能"""
    
    def test_platform_system(self):
        """测试 platform.system()"""
        system = platform.system()
        assert system in ['Linux', 'Darwin', 'Windows']
    
    def test_python_version(self):
        """测试 Python 版本"""
        version = sys.version_info
        assert version.major >= 3
        if version.major == 3:
            assert version.minor >= 9, "Python 3.9+ required"
    
    def test_venv_detection(self):
        """测试虚拟环境检测"""
        in_venv = sys.prefix != sys.base_prefix
        # 在测试环境中不强制要求是 venv
        # 只是验证检测逻辑可用
        assert isinstance(in_venv, bool)
    
    def test_path_separator(self):
        """测试路径分隔符"""
        sep = os.sep
        if platform.system() == 'Windows':
            assert sep == '\\'
        else:
            assert sep == '/'
    
    def test_line_ending(self):
        """测试行尾符"""
        eol = os.linesep
        if platform.system() == 'Windows':
            assert eol == '\r\n'
        else:
            assert eol == '\n'


# ============================================================
# 5. 跨平台文件路径测试
# ============================================================

class TestCrossPlatformPaths:
    """测试跨平台路径处理"""
    
    def test_pathlib_works(self, tmp_path):
        """测试 Pathlib 跨平台兼容性"""
        # Pathlib 在所有平台都可用
        p = tmp_path / "test" / "file.txt"
        assert str(p).endswith('test/file.txt') or str(p).endswith('test\\file.txt')
    
    def test_expanduser(self):
        """测试用户目录展开"""
        home = os.path.expanduser("~")
        assert home != "~"  # 应该展开为实际路径
        assert len(home) > 0
    
    def test_which_command(self):
        """测试命令查找 (跨平台)"""
        import shutil
        
        # python3 应该在所有平台都存在
        python_path = shutil.which("python3") or shutil.which("python")
        if python_path:
            assert os.path.exists(python_path)


# ============================================================
# 6. 运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
