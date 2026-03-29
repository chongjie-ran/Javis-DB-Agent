"""告警规则Repository测试"""
import pytest
import pytest_asyncio
import aiosqlite
import json
from pathlib import Path
from datetime import datetime


# 测试数据库路径
TEST_DB = "/tmp/test_knowledge.db"


# 配置pytest-asyncio
pytestmark = pytest.mark.asyncio(scope="function")


@pytest.fixture
def sample_alert_rule():
    """示例告警规则"""
    return {
        "id": "test-alert-001",
        "name": "锁等待超时",
        "entity_type": "database",
        "resource_type": "session",
        "observation_point": "lock_wait",
        "condition": "wait_time > 120",
        "severity": "warning",
        "recommendation": "检查长事务",
        "enabled": 1,
        "metadata": {"alert_code": "LOCK_WAIT_TIMEOUT", "risk_level": "L3"}
    }


@pytest_asyncio.fixture
async def db_conn():
    """测试数据库连接"""
    # 清理旧数据库
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    
    conn = await aiosqlite.connect(TEST_DB)
    conn.row_factory = aiosqlite.Row
    
    # 创建表
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT,
            resource_type TEXT,
            observation_point TEXT,
            condition TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
            recommendation TEXT,
            enabled INTEGER DEFAULT 1,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.commit()
    
    yield conn
    
    await conn.close()
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()


@pytest_asyncio.fixture
async def repo(db_conn):
    """创建Repository实例"""
    from src.knowledge.db.repositories.alert_rule_repo import AlertRuleRepository
    return AlertRuleRepository(db_conn)


class TestAlertRuleRepository:
    """AlertRuleRepository测试"""
    
    async def test_create_alert_rule(self, repo, sample_alert_rule):
        """测试创建告警规则"""
        result = await repo.create(sample_alert_rule)
        
        assert result is not None
        assert result["id"] == sample_alert_rule["id"]
        assert result["name"] == sample_alert_rule["name"]
        assert result["severity"] == "warning"
        assert result["enabled"] == 1
    
    async def test_get_by_id(self, repo, sample_alert_rule):
        """测试通过ID获取告警规则"""
        await repo.create(sample_alert_rule)
        
        result = await repo.get_by_id(sample_alert_rule["id"])
        
        assert result is not None
        assert result["id"] == sample_alert_rule["id"]
        assert result["name"] == "锁等待超时"
    
    async def test_get_nonexistent(self, repo):
        """测试获取不存在的记录"""
        result = await repo.get_by_id("nonexistent-id")
        assert result is None
    
    async def test_list_all(self, repo, sample_alert_rule):
        """测试列出所有告警规则"""
        await repo.create(sample_alert_rule)
        await repo.create({**sample_alert_rule, "id": "test-alert-002"})
        
        results = await repo.list_all()
        
        assert len(results) >= 2
    
    async def test_list_by_severity(self, repo, sample_alert_rule):
        """测试按严重程度筛选"""
        await repo.create(sample_alert_rule)
        await repo.create({**sample_alert_rule, "id": "test-alert-002", "severity": "critical"})
        
        results = await repo.list_by_severity("warning")
        
        assert all(r["severity"] == "warning" for r in results)
    
    async def test_update(self, repo, sample_alert_rule):
        """测试更新告警规则"""
        await repo.create(sample_alert_rule)
        
        update_data = {"name": "更新后的名称", "severity": "critical"}
        result = await repo.update(sample_alert_rule["id"], update_data)
        
        assert result["name"] == "更新后的名称"
        assert result["severity"] == "critical"
    
    async def test_delete(self, repo, sample_alert_rule):
        """测试删除告警规则"""
        await repo.create(sample_alert_rule)
        
        success = await repo.delete(sample_alert_rule["id"])
        assert success is True
        
        result = await repo.get_by_id(sample_alert_rule["id"])
        assert result is None
    
    async def test_search_by_keyword(self, repo, sample_alert_rule):
        """测试关键词搜索"""
        await repo.create(sample_alert_rule)
        await repo.create({
            **sample_alert_rule,
            "id": "test-alert-002",
            "name": "CPU使用率过高",
            "condition": "cpu_usage > 80"
        })
        
        results = await repo.search_by_keyword("锁")
        assert len(results) >= 1
        
        results = await repo.search_by_keyword("CPU")
        assert len(results) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
