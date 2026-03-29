"""
MySQL 实例状态查询测试

测试 MySQL 数据库实例状态查询功能
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.mysql.config import MYSQL_QUERIES


class TestMySQLInstanceStatus:
    """MySQL 实例状态查询测试"""

    def test_mysql_version_query(self, mysql_config):
        """测试 MySQL 版本查询"""
        query = MYSQL_QUERIES["version"]
        assert "SELECT @@version" in query
        assert "information_schema" not in query  # 版本是全局变量

    def test_mysql_connections_query(self, mysql_config):
        """测试 MySQL 连接数查询"""
        query = MYSQL_QUERIES["connections"]
        assert "information_schema.processlist" in query
        assert "total_connections" in query

    def test_mysql_max_connections_query(self, mysql_config):
        """测试 MySQL 最大连接数查询"""
        query = MYSQL_QUERIES["max_connections"]
        assert "SHOW VARIABLES" in query
        assert "max_connections" in query

    def test_mysql_buffer_pool_query(self, mysql_config):
        """测试 MySQL 缓冲池查询"""
        query = MYSQL_QUERIES["buffer_pool_size"]
        assert "SHOW VARIABLES" in query
        assert "innodb_buffer_pool_size" in query

    def test_instance_data_structure(self, mysql_instance_data):
        """测试实例数据结构"""
        assert mysql_instance_data["db_type"] == "mysql"
        assert mysql_instance_data["status"] == "running"
        assert mysql_instance_data["port"] == 3306
        assert "connections" in mysql_instance_data
        assert "max_connections" in mysql_instance_data

    def test_instance_metrics_calculation(self, mysql_instance_data):
        """测试实例指标计算"""
        data = mysql_instance_data
        conn_pct = (data["connections"] / data["max_connections"]) * 100
        assert 0 <= conn_pct <= 100
        assert conn_pct == pytest.approx(31.2, rel=0.1)


class TestMySQLInstanceQueries:
    """MySQL 实例查询语句验证"""

    def test_all_queries_defined(self):
        """验证所有查询语句已定义"""
        required_queries = [
            "version", "connections", "max_connections",
            "buffer_pool_size", "sessions", "lock_waits",
            "slow_sql", "table_stats"
        ]
        for query_name in required_queries:
            assert query_name in MYSQL_QUERIES, f"Query {query_name} not defined"

    def test_queries_use_information_schema(self):
        """验证查询使用 information_schema"""
        schema_queries = ["connections", "sessions", "lock_waits", "table_stats", "index_stats"]
        for query_name in schema_queries:
            assert "information_schema" in MYSQL_QUERIES[query_name]

    def test_queries_use_performance_schema(self):
        """验证查询使用 performance_schema（慢SQL）"""
        assert "performance_schema" in MYSQL_QUERIES["slow_sql"]

    def test_lock_query_uses_innodb_tables(self):
        """验证锁查询使用 InnoDB 表"""
        lock_query = MYSQL_QUERIES["lock_waits"]
        assert "INNODB_LOCK_WAITS" in lock_query
        assert "INNODB_TRX" in lock_query

    def test_slow_sql_query_grouping(self):
        """验证慢SQL查询包含分组和排序"""
        slow_sql_query = MYSQL_QUERIES["slow_sql"]
        assert "GROUP BY" in slow_sql_query
        assert "ORDER BY" in slow_sql_query
        assert "sum_timer_wait" in slow_sql_query
        assert "DESC" in slow_sql_query


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
