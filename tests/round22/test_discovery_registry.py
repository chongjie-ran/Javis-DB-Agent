"""
LocalRegistry 单元测试
测试 upsert、查询、状态历史
"""

import pytest
import os
import tempfile
import time
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.discovery.registry import LocalRegistry, ManagedInstance
from src.discovery.identifier import IdentifiedInstance
from src.discovery.scanner import DBType, DiscoveredInstance


# ─────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────

_instance_counter = 0

def make_managed_instance(
    db_type: str = "postgresql",
    port: int = 5432,
    status: str = "discovered",
    version: str = "16.4",
) -> ManagedInstance:
    global _instance_counter
    _instance_counter += 1
    return ManagedInstance(
        id=f"test-id-{_instance_counter:03d}",
        db_type=db_type,
        host="localhost",
        port=port,
        version=version,
        version_major=16,
        version_minor=4,
        edition="",
        status=status,
        discovered_at="2026-03-31T10:00:00",
        onboarded_at=None,
        last_check_at="2026-03-31T10:00:00",
    )


def make_identified(
    db_type: DBType = DBType.POSTGRESQL,
    port: int = 5432,
    version: str = "16.4",
    major: int = 16,
    minor: int = 4,
) -> IdentifiedInstance:
    inst = DiscoveredInstance(db_type=db_type, host="localhost", port=port)
    return IdentifiedInstance(
        instance=inst,
        version=version,
        version_major=major,
        version_minor=minor,
    )


# ─────────────────────────────────────────────
# Fixture: 临时数据库
# ─────────────────────────────────────────────

@pytest.fixture
def temp_db():
    """创建临时SQLite数据库用于测试"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    registry = LocalRegistry(db_path=db_path)
    yield registry
    # 清理
    try:
        os.unlink(db_path)
    except Exception:
        pass


# ─────────────────────────────────────────────
# 测试：ManagedInstance
# ─────────────────────────────────────────────

class TestManagedInstance:
    def test_from_identified_discovered(self):
        """from_identified 创建 discovered 状态的实例"""
        identified = make_identified(DBType.POSTGRESQL, 5432, "16.4", 16, 4)
        managed = ManagedInstance.from_identified(identified, status="discovered")

        assert managed.db_type == "postgresql"
        assert managed.port == 5432
        assert managed.status == "discovered"
        assert managed.onboarded_at is None
        assert managed.discovered_at != ""

    def test_from_identified_onboarded(self):
        """from_identified 创建 onboarded 状态的实例"""
        identified = make_identified(DBType.POSTGRESQL, 5432)
        managed = ManagedInstance.from_identified(identified, status="onboarded")

        assert managed.status == "onboarded"
        assert managed.onboarded_at is not None

    def test_from_identified_mysql(self):
        """from_identified 支持 MySQL"""
        identified = make_identified(DBType.MYSQL, 3306, "8.0.36", 8, 0)
        managed = ManagedInstance.from_identified(identified)

        assert managed.db_type == "mysql"
        assert managed.port == 3306


# ─────────────────────────────────────────────
# 测试：LocalRegistry 初始化
# ─────────────────────────────────────────────

class TestRegistryInit:
    def test_init_creates_parent_dirs(self, temp_db):
        """初始化时自动创建父目录"""
        assert temp_db.db_path.parent.exists()

    def test_init_creates_schema(self, temp_db):
        """初始化时创建表结构"""
        with temp_db._conn() as conn:
            # 检查表是否存在
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r["name"] for r in tables}
            assert "managed_instances" in table_names
            assert "status_history" in table_names
            assert "scan_sessions" in table_names

    def test_init_creates_indexes(self, temp_db):
        """初始化时创建索引"""
        with temp_db._conn() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = {r["name"] for r in indexes}
            assert "idx_instance_key" in index_names
            assert "idx_status" in index_names


# ─────────────────────────────────────────────
# 测试：upsert / register
# ─────────────────────────────────────────────

class TestUpsert:
    def test_register_new_instance(self, temp_db):
        """注册新实例"""
        instance = make_managed_instance()
        instance_id = temp_db.register(instance)

        assert instance_id != ""
        # 再次查询验证
        retrieved = temp_db.get_by_id(instance_id)
        assert retrieved is not None
        assert retrieved.db_type == "postgresql"
        assert retrieved.port == 5432

    def test_register_upsert_updates_existing(self, temp_db):
        """同一(db_type, host, port)注册会更新而非重复创建"""
        inst1 = make_managed_instance()
        inst1.id = "id-001"
        inst2 = make_managed_instance()
        inst2.id = "id-002"  # 不同的id

        id1 = temp_db.register(inst1)
        id2 = temp_db.register(inst2)

        # 应该更新而非插入，返回的id相同（因为是同一个唯一键）
        assert id1 == id2

        # 验证只有一条记录
        all_instances = temp_db.get_all()
        assert len(all_instances) == 1

        # 验证版本等信息已更新（如果有变化）
        retrieved = temp_db.get_by_id(id1)
        assert retrieved is not None

    def test_upsert_alias_same_as_register(self, temp_db):
        """upsert() 与 register() 功能相同"""
        instance = make_managed_instance()
        id1 = temp_db.register(instance)
        id2 = temp_db.upsert(instance)
        assert id1 == id2


# ─────────────────────────────────────────────
# 测试：查询
# ─────────────────────────────────────────────

class TestQuery:
    def test_get_all_empty(self, temp_db):
        """空数据库返回空列表"""
        assert temp_db.get_all() == []

    def test_get_all_returns_all(self, temp_db):
        """get_all 返回所有实例"""
        inst1 = make_managed_instance(port=5432)
        inst2 = make_managed_instance(port=5433)
        temp_db.register(inst1)
        temp_db.register(inst2)

        results = temp_db.get_all()
        assert len(results) == 2
        ports = {r.port for r in results}
        assert ports == {5432, 5433}

    def test_get_all_with_status_filter(self, temp_db):
        """get_all 支持状态过滤"""
        inst1 = make_managed_instance(port=5432, status="discovered")
        inst2 = make_managed_instance(port=5433, status="onboarded")
        temp_db.register(inst1)
        temp_db.register(inst2)

        discovered = temp_db.get_all(status_filter="discovered")
        assert len(discovered) == 1
        assert discovered[0].status == "discovered"

        onboarded = temp_db.get_all(status_filter="onboarded")
        assert len(onboarded) == 1
        assert onboarded[0].status == "onboarded"

    def test_get_by_id_found(self, temp_db):
        """get_by_id 找到时返回实例"""
        instance = make_managed_instance()
        registered_id = temp_db.register(instance)

        retrieved = temp_db.get_by_id(registered_id)
        assert retrieved is not None
        assert retrieved.id == registered_id

    def test_get_by_id_not_found(self, temp_db):
        """get_by_id 找不到时返回None"""
        result = temp_db.get_by_id("non-existent-id")
        assert result is None

    def test_get_by_key_found(self, temp_db):
        """get_by_key 找到时返回实例"""
        instance = make_managed_instance(db_type="postgresql", port=5432)
        temp_db.register(instance)

        retrieved = temp_db.get_by_key("postgresql", "localhost", 5432)
        assert retrieved is not None
        assert retrieved.db_type == "postgresql"

    def test_get_by_key_not_found(self, temp_db):
        """get_by_key 找不到时返回None"""
        result = temp_db.get_by_key("postgresql", "localhost", 5432)
        assert result is None


# ─────────────────────────────────────────────
# 测试：状态更新与历史
# ─────────────────────────────────────────────

class TestStatusUpdate:
    def test_update_status_success(self, temp_db):
        """update_status 成功更新状态"""
        instance = make_managed_instance(status="discovered")
        instance_id = temp_db.register(instance)

        success = temp_db.update_status(instance_id, "onboarded", "test_reason")
        assert success is True

        retrieved = temp_db.get_by_id(instance_id)
        assert retrieved.status == "onboarded"

    def test_update_status_not_found(self, temp_db):
        """update_status 对不存在的实例返回False"""
        success = temp_db.update_status("non-existent-id", "onboarded")
        assert success is False

    def test_update_status_records_history(self, temp_db):
        """状态更新会记录到历史表"""
        instance = make_managed_instance(status="discovered")
        instance_id = temp_db.register(instance)

        temp_db.update_status(instance_id, "onboarded", "initial_onboard")

        history = temp_db.get_status_history(instance_id)
        assert len(history) == 1
        assert history[0]["old_status"] == "discovered"
        assert history[0]["new_status"] == "onboarded"
        assert history[0]["reason"] == "initial_onboard"

    def test_update_status_multiple_changes(self, temp_db):
        """多次状态变更产生多条历史记录"""
        instance = make_managed_instance(status="discovered")
        instance_id = temp_db.register(instance)

        temp_db.update_status(instance_id, "onboarded")
        temp_db.update_status(instance_id, "monitoring")
        temp_db.update_status(instance_id, "error")

        history = temp_db.get_status_history(instance_id)
        assert len(history) == 3
        statuses = [h["new_status"] for h in history]
        assert statuses == ["error", "monitoring", "onboarded"]  # 最新在前

    def test_update_status_empty_reason(self, temp_db):
        """状态更新允许空reason"""
        instance = make_managed_instance(status="discovered")
        instance_id = temp_db.register(instance)

        temp_db.update_status(instance_id, "onboarded", "")

        history = temp_db.get_status_history(instance_id)
        assert history[0]["reason"] == ""


# ─────────────────────────────────────────────
# 测试：remove（软删除）
# ─────────────────────────────────────────────

class TestRemove:
    def test_remove_sets_status_to_removed(self, temp_db):
        """remove 将状态标记为 removed"""
        instance = make_managed_instance(status="onboarded")
        instance_id = temp_db.register(instance)

        temp_db.remove(instance_id)

        retrieved = temp_db.get_by_id(instance_id)
        assert retrieved.status == "removed"

    def test_remove_records_history(self, temp_db):
        """remove 记录状态历史"""
        instance = make_managed_instance(status="onboarded")
        instance_id = temp_db.register(instance)

        temp_db.remove(instance_id)

        history = temp_db.get_status_history(instance_id)
        assert len(history) == 1
        assert history[0]["new_status"] == "removed"
        assert history[0]["reason"] == "user_requested"


# ─────────────────────────────────────────────
# 测试：连接数更新
# ─────────────────────────────────────────────

class TestConnectionUpdate:
    def test_update_connections_success(self, temp_db):
        """update_connections 成功更新连接数"""
        instance = make_managed_instance()
        instance_id = temp_db.register(instance)

        success = temp_db.update_connections(instance_id, 42)
        assert success is True

        retrieved = temp_db.get_by_id(instance_id)
        assert retrieved.current_connections == 42

    def test_update_connections_not_found(self, temp_db):
        """update_connections 对不存在的实例返回False"""
        success = temp_db.update_connections("non-existent-id", 42)
        assert success is False


# ─────────────────────────────────────────────
# 测试：统计
# ─────────────────────────────────────────────

class TestStats:
    def test_get_stats_empty(self, temp_db):
        """空数据库的统计"""
        stats = temp_db.get_stats()
        assert stats["total_instances"] == 0
        assert stats["by_status"] == {}
        assert stats["by_type"] == {}

    def test_get_stats_with_data(self, temp_db):
        """有数据时的统计（get_stats 排除 removed 状态）"""
        inst1 = make_managed_instance(db_type="postgresql", port=5432, status="onboarded")
        inst2 = make_managed_instance(db_type="mysql", port=3306, status="onboarded")
        inst3 = make_managed_instance(db_type="postgresql", port=5433, status="removed")
        temp_db.register(inst1)
        temp_db.register(inst2)
        temp_db.register(inst3)

        stats = temp_db.get_stats()
        # get_stats 排除 removed 状态
        assert stats["total_instances"] == 2  # 只统计非removed实例
        assert stats["by_status"]["onboarded"] == 2
        assert "removed" not in stats["by_status"]
        assert stats["by_type"]["postgresql"] == 1  # 只统计非removed
        assert stats["by_type"]["mysql"] == 1
