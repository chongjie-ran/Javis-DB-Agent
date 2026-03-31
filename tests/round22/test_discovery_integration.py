"""
数据库发现集成测试
测试扫描 localhost:5432 PostgreSQL，验证发现结果
"""

import pytest
import asyncio
import tempfile
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.discovery.scanner import DatabaseScanner, DiscoveredInstance, DBType
from src.discovery.identifier import DatabaseIdentifier
from src.discovery.registry import LocalRegistry, ManagedInstance


# ─────────────────────────────────────────────
# Fixture: 临时注册表
# ─────────────────────────────────────────────

@pytest.fixture
def temp_registry():
    """创建临时注册表"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    registry = LocalRegistry(db_path=db_path)
    yield registry
    try:
        os.unlink(db_path)
    except Exception:
        pass


# ─────────────────────────────────────────────
# 测试：端口扫描发现 PostgreSQL
# ─────────────────────────────────────────────

class TestPortScanDiscovery:
    @pytest.mark.asyncio
    async def test_scan_finds_localhost_postgres(self):
        """扫描 localhost:5432 能发现 PostgreSQL"""
        scanner = DatabaseScanner(
            ports=[5432],
            scan_timeout=5.0,
        )
        results = await scanner.scan_ports("localhost")

        assert len(results) >= 1, "应该至少发现一个数据库实例"
        pg_instances = [r for r in results if r.port == 5432]
        assert len(pg_instances) == 1
        assert pg_instances[0].db_type == DBType.POSTGRESQL
        assert pg_instances[0].status == "reachable"

    @pytest.mark.asyncio
    async def test_scan_postgres_unreachable_on_wrong_port(self):
        """5433端口没有数据库时返回空"""
        scanner = DatabaseScanner(
            ports=[5433],
            scan_timeout=2.0,
        )
        results = await scanner.scan_ports("localhost")
        # 5433可能关闭或无数据库
        pg_5433 = [r for r in results if r.port == 5433]
        assert len(pg_5433) == 0


# ─────────────────────────────────────────────
# 测试：PostgreSQL 识别与版本获取
# ─────────────────────────────────────────────

class TestPostgresIdentification:
    @pytest.mark.asyncio
    async def test_identify_postgres_version(self):
        """能成功识别 localhost:5432 PostgreSQL 并获取版本"""
        inst = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            status="reachable",
        )
        identifier = DatabaseIdentifier()
        result = await identifier.identify(inst)

        assert result is not None, "应该能成功识别 PostgreSQL"
        assert "PostgreSQL" in result.version
        assert result.version_major >= 10, f"版本号应 >= 10，实际: {result.version_major}"
        assert result.instance.status == "identified"
        assert result.current_connections >= 0
        assert result.max_connections > 0

    @pytest.mark.asyncio
    async def test_identify_updates_instance_version(self):
        """识别后 instance.version 被正确填充"""
        inst = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            status="reachable",
        )
        identifier = DatabaseIdentifier()
        result = await identifier.identify(inst)

        assert result is not None
        assert result.instance.version != ""
        assert "PostgreSQL" in result.instance.version


# ─────────────────────────────────────────────
# 测试：端到端扫描+识别流程
# ─────────────────────────────────────────────

class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_scan_and_identify_postgres(self):
        """完整流程：扫描 → 识别"""
        scanner = DatabaseScanner(ports=[5432], scan_timeout=5.0)
        identifier = DatabaseIdentifier()

        # Step 1: 扫描
        discovered = await scanner.scan_ports("localhost")
        assert len(discovered) >= 1
        pg = next((d for d in discovered if d.port == 5432), None)
        assert pg is not None
        assert pg.db_type == DBType.POSTGRESQL

        # Step 2: 识别
        identified = await identifier.identify(pg)
        assert identified is not None
        assert identified.version_major >= 10
        assert identified.instance.status == "identified"

    @pytest.mark.asyncio
    async def test_scan_identify_and_register(self, temp_registry):
        """完整流程：扫描 → 识别 → 注册"""
        scanner = DatabaseScanner(ports=[5432], scan_timeout=5.0)
        identifier = DatabaseIdentifier()

        # Step 1: 扫描
        discovered = await scanner.scan_ports("localhost")
        pg = next((d for d in discovered if d.port == 5432), None)
        assert pg is not None

        # Step 2: 识别
        identified = await identifier.identify(pg)
        assert identified is not None

        # Step 3: 注册
        managed = ManagedInstance.from_identified(identified, status="onboarded")
        instance_id = temp_registry.register(managed)

        assert instance_id != ""

        # 验证查询
        retrieved = temp_registry.get_by_id(instance_id)
        assert retrieved is not None
        assert retrieved.db_type == "postgresql"
        assert retrieved.port == 5432
        assert retrieved.status == "onboarded"
        assert retrieved.version_major >= 10

    @pytest.mark.asyncio
    async def test_batch_identify_all(self):
        """批量识别多个实例"""
        scanner = DatabaseScanner(ports=[5432], scan_timeout=5.0)
        identifier = DatabaseIdentifier()

        discovered = await scanner.scan_ports("localhost")
        results = await identifier.identify_all(discovered)

        # 至少要能识别出5432
        pg_results = [r for r in results if r.instance.port == 5432]
        assert len(pg_results) >= 1


# ─────────────────────────────────────────────
# 测试：本地注册表持久化
# ─────────────────────────────────────────────

class TestRegistryPersistence:
    def test_register_and_retrieve(self, temp_registry):
        """注册后能正确查询"""
        managed = ManagedInstance(
            id="test-pg-local",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.4",
            version_major=16,
            version_minor=4,
            edition="",
            status="onboarded",
            discovered_at="2026-03-31T10:00:00",
            onboarded_at="2026-03-31T10:00:00",
            last_check_at="2026-03-31T10:00:00",
        )
        instance_id = temp_registry.register(managed)

        # 查询验证
        retrieved = temp_registry.get_by_id(instance_id)
        assert retrieved is not None
        assert retrieved.db_type == "postgresql"
        assert retrieved.version_major == 16

        # 按键查询
        by_key = temp_registry.get_by_key("postgresql", "localhost", 5432)
        assert by_key is not None
        assert by_key.id == instance_id

    def test_upsert_updates_existing(self, temp_registry):
        """upsert 同一实例会更新而非重复插入"""
        managed1 = ManagedInstance(
            id="id-1",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.4",
            version_major=16,
            version_minor=4,
            edition="",
            status="discovered",
            discovered_at="2026-03-31T10:00:00",
        )
        managed2 = ManagedInstance(
            id="id-2",  # 不同的id，但同一键
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.5",  # 新版本
            version_major=16,
            version_minor=5,
            edition="",
            status="onboarded",
            discovered_at="2026-03-31T11:00:00",
        )

        temp_registry.register(managed1)
        temp_registry.register(managed2)

        all_instances = temp_registry.get_all()
        assert len(all_instances) == 1
        assert all_instances[0].version == "16.5"
        assert all_instances[0].status == "onboarded"

    def test_status_history_on_state_change(self, temp_registry):
        """状态变更正确记录历史"""
        managed = ManagedInstance(
            id="hist-test",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.4",
            version_major=16,
            version_minor=4,
            edition="",
            status="discovered",
            discovered_at="2026-03-31T10:00:00",
        )
        instance_id = temp_registry.register(managed)

        temp_registry.update_status(instance_id, "onboarded", "ready for use")
        temp_registry.update_status(instance_id, "monitoring", "health check ok")
        temp_registry.remove(instance_id)

        history = temp_registry.get_status_history(instance_id)
        assert len(history) == 3

        # 最新状态在最前
        assert history[0]["new_status"] == "removed"
        assert history[1]["new_status"] == "monitoring"
        assert history[2]["new_status"] == "onboarded"

    def test_stats_reflects_data(self, temp_registry):
        """统计数据正确反映注册情况"""
        pg = ManagedInstance(
            id="pg-stat",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.4",
            version_major=16,
            version_minor=4,
            edition="",
            status="onboarded",
            discovered_at="2026-03-31T10:00:00",
        )
        mysql = ManagedInstance(
            id="mysql-stat",
            db_type="mysql",
            host="localhost",
            port=3306,
            version="8.0.36",
            version_major=8,
            version_minor=0,
            edition="",
            status="discovered",
            discovered_at="2026-03-31T10:00:00",
        )

        temp_registry.register(pg)
        temp_registry.register(mysql)

        stats = temp_registry.get_stats()
        assert stats["total_instances"] == 2
        assert stats["by_type"]["postgresql"] == 1
        assert stats["by_type"]["mysql"] == 1
        assert stats["by_status"]["onboarded"] == 1
        assert stats["by_status"]["discovered"] == 1


# ─────────────────────────────────────────────
# 测试：进程扫描（仅在有真实数据库进程时运行）
# ─────────────────────────────────────────────

class TestProcessScanIntegration:
    def test_scan_processes_finds_postgres_if_running(self):
        """如果有 postgres 进程在运行，能被发现"""
        scanner = DatabaseScanner()
        results = scanner.scan_processes()

        # 如果本地有运行中的PG，会被发现
        pg_results = [r for r in results if r.db_type == DBType.POSTGRESQL]
        if len(pg_results) > 0:
            assert pg_results[0].port == 5432
            assert pg_results[0].pid is not None
            assert pg_results[0].status == "process_found"


# ─────────────────────────────────────────────
# 测试：综合扫描（端口+进程合并）
# ─────────────────────────────────────────────

class TestCombinedScan:
    @pytest.mark.asyncio
    async def test_scan_local_combines_both_channels(self):
        """scan_local 合并端口和进程扫描结果"""
        scanner = DatabaseScanner(ports=[5432], scan_timeout=5.0)
        results = await scanner.scan_local()

        assert len(results) >= 1
        # 5432 肯定会被发现
        pg_5432 = [r for r in results if r.port == 5432]
        assert len(pg_5432) == 1
        assert pg_5432[0].db_type == DBType.POSTGRESQL
