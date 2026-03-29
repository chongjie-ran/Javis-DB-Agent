"""DB Adapter Layer 测试
验证 MySQL 和 PostgreSQL 双引擎适配层功能
"""
import pytest
import asyncio
from src.db.base import DBType, get_db_connector, DBConnector
from src.db.mysql_adapter import MySQLConnector
from src.db.postgres_adapter import PostgresConnector


class TestDBConnectorFactory:
    """测试连接器工厂函数"""
    
    def test_get_mysql_connector(self):
        """测试MySQL连接器创建"""
        conn = get_db_connector(
            db_type="mysql",
            host="192.168.1.10",
            port=3306,
            username="root",
            password="secret",
        )
        assert isinstance(conn, MySQLConnector)
        assert conn.db_type == DBType.MYSQL
        assert conn.host == "192.168.1.10"
        assert conn.port == 3306
    
    def test_get_postgres_connector(self):
        """测试PostgreSQL连接器创建"""
        conn = get_db_connector(
            db_type="postgresql",
            host="192.168.1.11",
            port=5432,
            username="postgres",
            password="secret",
        )
        assert isinstance(conn, PostgresConnector)
        assert conn.db_type == DBType.POSTGRES
        assert conn.host == "192.168.1.11"
        assert conn.port == 5432
    
    def test_unsupported_db_type(self):
        """测试不支持的数据库类型"""
        with pytest.raises(ValueError) as exc_info:
            get_db_connector(db_type="oracle", host="localhost", port=1521)
        assert "Unsupported db_type" in str(exc_info.value)


class TestMySQLConnector:
    """测试MySQL连接器"""
    
    @pytest.mark.asyncio
    async def test_get_sessions(self):
        """测试获取会话列表"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        sessions = await conn.get_sessions(limit=5)
        assert isinstance(sessions, list)
        # Mock数据至少有内容
        assert len(sessions) > 0
    
    @pytest.mark.asyncio
    async def test_get_locks(self):
        """测试获取锁信息"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        locks = await conn.get_locks()
        assert isinstance(locks, list)
        assert len(locks) > 0
    
    @pytest.mark.asyncio
    async def test_get_replication(self):
        """测试获取复制状态"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        rep_info = await conn.get_replication()
        assert rep_info.role == "primary"
        assert rep_info.replication_enabled is True
        assert len(rep_info.replicas) > 0
    
    @pytest.mark.asyncio
    async def test_get_capacity(self):
        """测试获取容量信息"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        cap = await conn.get_capacity()
        assert cap.disk_total_gb > 0
        assert cap.disk_used_percent > 0
        assert len(cap.tablespaces) > 0
    
    @pytest.mark.asyncio
    async def test_get_performance(self):
        """测试获取性能指标"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        perf = await conn.get_performance()
        assert perf.cpu_usage_percent > 0
        assert perf.memory_usage_percent > 0
        assert perf.active_connections >= 0
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        healthy = await conn.health_check()
        assert isinstance(healthy, bool)
    
    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        conn = MySQLConnector(host="localhost", port=18080, api_base="http://localhost:18080")
        await conn._get_client()  # 初始化客户端
        await conn.close()
        assert conn._client is None


class TestPostgresConnector:
    """测试PostgreSQL连接器"""
    
    @pytest.mark.asyncio
    async def test_get_sessions(self):
        """测试获取会话列表"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        sessions = await conn.get_sessions(limit=5)
        assert isinstance(sessions, list)
        assert len(sessions) > 0
        # PG特有字段
        assert all(hasattr(s, "pid") for s in sessions)
    
    @pytest.mark.asyncio
    async def test_get_locks(self):
        """测试获取锁信息"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        locks = await conn.get_locks()
        assert isinstance(locks, list)
        assert len(locks) > 0
        # PG特有字段
        assert all(hasattr(l, "pid") for l in locks)
    
    @pytest.mark.asyncio
    async def test_get_replication(self):
        """测试获取复制状态"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        rep_info = await conn.get_replication()
        assert rep_info.role == "primary"
        assert rep_info.replication_enabled is True
        # PG特有字段
        assert hasattr(rep_info, "wal_lag")
        assert hasattr(rep_info, "replay_lag")
    
    @pytest.mark.asyncio
    async def test_get_capacity(self):
        """测试获取容量信息"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        cap = await conn.get_capacity()
        assert cap.disk_total_gb > 0
        # PG特有字段
        assert cap.database_size != ""
    
    @pytest.mark.asyncio
    async def test_get_performance(self):
        """测试获取性能指标"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        perf = await conn.get_performance()
        assert perf.cpu_usage_percent > 0
        # PG特有字段
        assert hasattr(perf, "transactions_per_sec")
        assert hasattr(perf, "commits_per_sec")
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        healthy = await conn.health_check()
        assert isinstance(healthy, bool)
    
    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        conn = PostgresConnector(host="localhost", port=18081, api_base="http://localhost:18081")
        await conn._get_client()
        await conn.close()
        assert conn._client is None


class TestDualEngineSwitching:
    """测试双引擎切换"""
    
    def test_mysql_connector_type(self):
        """验证MySQL连接器类型"""
        conn = get_db_connector("mysql", host="h1", port=3306)
        assert conn.db_type == DBType.MYSQL
        assert isinstance(conn, MySQLConnector)
    
    def test_postgres_connector_type(self):
        """验证PostgreSQL连接器类型"""
        conn = get_db_connector("postgresql", host="h1", port=5432)
        assert conn.db_type == DBType.POSTGRES
        assert isinstance(conn, PostgresConnector)
    
    @pytest.mark.asyncio
    async def test_both_connectors_can_be_used(self):
        """验证可以同时使用两种连接器"""
        mysql_conn = get_db_connector("mysql", host="localhost", port=18080)
        pg_conn = get_db_connector("postgresql", host="localhost", port=18081)
        
        # 两种连接器可以独立获取数据
        mysql_sessions = await mysql_conn.get_sessions(limit=3)
        pg_sessions = await pg_conn.get_sessions(limit=3)
        
        assert isinstance(mysql_sessions, list)
        assert isinstance(pg_sessions, list)
        assert len(mysql_sessions) > 0
        assert len(pg_sessions) > 0
        
        # 字段差异：MySQL用sid，PG用pid
        assert hasattr(mysql_sessions[0], "sid") or hasattr(mysql_sessions[0], "pid")
        assert hasattr(pg_sessions[0], "pid")
    
    @pytest.mark.asyncio
    async def test_unified_interface(self):
        """验证统一接口可以返回不同类型的数据"""
        mysql_conn = get_db_connector("mysql", host="localhost", port=18080)
        pg_conn = get_db_connector("postgresql", host="localhost", port=18081)
        
        # 会话接口统一，但底层实现不同
        mysql_rep = await mysql_conn.get_replication()
        pg_rep = await pg_conn.get_replication()
        
        # 都有replicas属性
        assert hasattr(mysql_rep, "replicas")
        assert hasattr(pg_rep, "replicas")
        
        # PG特有lag字段
        assert hasattr(pg_rep, "wal_lag")
        assert hasattr(pg_rep, "replay_lag")
        assert hasattr(pg_rep, "flush_lag")
        
        # MySQL有lag_bytes
        assert hasattr(mysql_rep, "lag_bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
