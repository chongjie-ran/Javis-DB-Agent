"""
pytest配置
V1.5真实环境测试配置
"""
import pytest
import os


def pytest_configure(config):
    """pytest配置钩子 - DFX测试标记注册"""
    # ---- DFX 核心维度标记 ----
    config.addinivalue_line("markers", "dfx: 全维度DFX测试（包含所有6个维度）")
    config.addinivalue_line("markers", "functionality: 功能测试 - 验证核心业务功能正确性")
    config.addinivalue_line("markers", "performance: 性能测试 - 验证系统性能指标")
    config.addinivalue_line("markers", "reliability: 可靠性测试 - 验证异常情况稳定性")
    config.addinivalue_line("markers", "maintainability: 可维护性测试 - 验证代码可维护性")
    config.addinivalue_line("markers", "security: 安全测试 - 验证系统安全防护")
    config.addinivalue_line("markers", "audit: 审计测试 - 验证系统审计能力")
    config.addinivalue_line("markers", "integration: 集成测试 - 验证端到端流程")
    # ---- 环境标记 ----
    config.addinivalue_line("markers", "mysql: MySQL环境测试")
    config.addinivalue_line("markers", "pg: PostgreSQL环境测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试 (>5s)")
    config.addinivalue_line("markers", "real_db: 真实数据库测试")


def pytest_collection_modifyitems(config, items):
    """修改测试收集行为"""
    for item in items:
        # 自动为真实数据库测试添加超时标记
        if "real" in item.nodeid.lower():
            item.add_marker(pytest.mark.timeout(120))
