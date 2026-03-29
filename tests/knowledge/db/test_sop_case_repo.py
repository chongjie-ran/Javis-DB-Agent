"""SOP和Case Repository测试"""
import pytest
import pytest_asyncio
import aiosqlite
import json
from pathlib import Path


# 测试数据库路径
TEST_DB = "/tmp/test_knowledge_sop_case.db"


# 配置pytest-asyncio
pytestmark = pytest.mark.asyncio(scope="function")


@pytest.fixture
def sample_sop():
    """示例SOP"""
    return {
        "id": "test-sop-001",
        "title": "锁等待排查流程",
        "alert_rule_id": "alert-LOCK_WAIT_TIMEOUT",
        "steps": [
            {"title": "确认告警", "done": False},
            {"title": "收集信息", "done": False},
            {"title": "分析根因", "done": False}
        ],
        "enabled": 1,
        "metadata": {"category": "lock", "priority": "high"}
    }


@pytest.fixture
def sample_case():
    """示例案例"""
    return {
        "id": "test-case-001",
        "title": "2026-01-15-锁等待故障",
        "alert_rule_id": "alert-LOCK_WAIT_TIMEOUT",
        "symptoms": ["等待时间超过阈值", "会话处于Waiting状态"],
        "root_cause": "长事务未提交，阻塞其他会话",
        "solution": "Kill阻塞会话",
        "outcome": "恢复正常",
        "metadata": {"date": "2026-01-15", "instance": "PROD-ORDER-DB"}
    }


@pytest_asyncio.fixture
async def db_conn():
    """测试数据库连接"""
    if Path(TEST_DB).exists():
        Path(TEST_DB).unlink()
    
    conn = await aiosqlite.connect(TEST_DB)
    conn.row_factory = aiosqlite.Row
    
    # 创建表
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS sops (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            alert_rule_id TEXT,
            steps JSON NOT NULL,
            enabled INTEGER DEFAULT 1,
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            alert_rule_id TEXT,
            symptoms JSON,
            root_cause TEXT,
            solution TEXT,
            outcome TEXT,
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
async def sop_repo(db_conn):
    """创建SOP Repository实例"""
    from src.knowledge.db.repositories.sop_repo import SOPRepository
    return SOPRepository(db_conn)


@pytest_asyncio.fixture
async def case_repo(db_conn):
    """创建Case Repository实例"""
    from src.knowledge.db.repositories.case_repo import CaseRepository
    return CaseRepository(db_conn)


class TestSOPRepository:
    """SOPRepository测试"""
    
    async def test_create_sop(self, sop_repo, sample_sop):
        """测试创建SOP"""
        result = await sop_repo.create(sample_sop)
        
        assert result is not None
        assert result["id"] == sample_sop["id"]
        assert result["title"] == "锁等待排查流程"
        assert isinstance(result["steps"], list)
    
    async def test_get_by_id(self, sop_repo, sample_sop):
        """测试通过ID获取SOP"""
        await sop_repo.create(sample_sop)
        
        result = await sop_repo.get_by_id(sample_sop["id"])
        
        assert result is not None
        assert result["id"] == sample_sop["id"]
    
    async def test_list_by_alert_rule(self, sop_repo, sample_sop):
        """测试通过告警规则获取SOP"""
        await sop_repo.create(sample_sop)
        await sop_repo.create({**sample_sop, "id": "test-sop-002"})
        
        results = await sop_repo.list_by_alert_rule("alert-LOCK_WAIT_TIMEOUT")
        
        assert len(results) == 2
    
    async def test_update(self, sop_repo, sample_sop):
        """测试更新SOP"""
        await sop_repo.create(sample_sop)
        
        update_data = {"title": "更新后的标题", "enabled": 0}
        result = await sop_repo.update(sample_sop["id"], update_data)
        
        assert result["title"] == "更新后的标题"
        assert result["enabled"] == 0
    
    async def test_delete(self, sop_repo, sample_sop):
        """测试删除SOP"""
        await sop_repo.create(sample_sop)
        
        success = await sop_repo.delete(sample_sop["id"])
        assert success is True
        
        result = await sop_repo.get_by_id(sample_sop["id"])
        assert result is None


class TestCaseRepository:
    """CaseRepository测试"""
    
    async def test_create_case(self, case_repo, sample_case):
        """测试创建案例"""
        result = await case_repo.create(sample_case)
        
        assert result is not None
        assert result["id"] == sample_case["id"]
        assert result["title"] == "2026-01-15-锁等待故障"
        assert isinstance(result["symptoms"], list)
    
    async def test_get_by_id(self, case_repo, sample_case):
        """测试通过ID获取案例"""
        await case_repo.create(sample_case)
        
        result = await case_repo.get_by_id(sample_case["id"])
        
        assert result is not None
        assert result["id"] == sample_case["id"]
    
    async def test_list_by_alert_rule(self, case_repo, sample_case):
        """测试通过告警规则获取案例"""
        await case_repo.create(sample_case)
        await case_repo.create({**sample_case, "id": "test-case-002"})
        
        results = await case_repo.list_by_alert_rule("alert-LOCK_WAIT_TIMEOUT")
        
        assert len(results) == 2
    
    async def test_update(self, case_repo, sample_case):
        """测试更新案例"""
        await case_repo.create(sample_case)
        
        update_data = {
            "root_cause": "更新的根因",
            "solution": "更新后的解决方案"
        }
        result = await case_repo.update(sample_case["id"], update_data)
        
        assert result["root_cause"] == "更新的根因"
        assert result["solution"] == "更新后的解决方案"
    
    async def test_delete(self, case_repo, sample_case):
        """测试删除案例"""
        await case_repo.create(sample_case)
        
        success = await case_repo.delete(sample_case["id"])
        assert success is True
        
        result = await case_repo.get_by_id(sample_case["id"])
        assert result is None
    
    async def test_search_by_keyword(self, case_repo, sample_case):
        """测试关键词搜索"""
        await case_repo.create(sample_case)
        await case_repo.create({
            **sample_case,
            "id": "test-case-002",
            "title": "CPU使用率过高",
            "root_cause": "大量并发请求"
        })
        
        results = await case_repo.search_by_keyword("锁")
        assert len(results) >= 1
        
        results = await case_repo.search_by_keyword("CPU")
        assert len(results) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
