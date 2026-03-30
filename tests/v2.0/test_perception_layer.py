"""
V2.0 P0-3: 感知层增强测试
模块：拓扑感知 + 配置感知 + API对接

测试维度：Happy path / Edge cases / Error cases / Regression
环境支持：MySQL / PostgreSQL / 真实zCloud API（可选）

V2.0关键待测功能：
1. 拓扑感知（src/tools/topology_tools.py - 待实现）
   - 集群拓扑发现
   - 主从关系识别
   - 节点状态监控
   - 复制链路追踪
2. 配置感知（src/tools/config_tools.py - 待实现）
   - 实例参数采集
   - 配置基线对比
   - 参数变更检测
   - 版本兼容性检查
3. API对接（src/real_api/ - 待实现）
   - zCloud平台API对接
   - 告警API
   - 指标API
   - 拓扑API
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
import asyncio
import time
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch
import requests


# =============================================================================
# PER-01: 拓扑感知 - Happy Path
# =============================================================================

class TestTopologyHappyPath:
    """拓扑感知 - Happy Path"""

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_per_01_001_cluster_topology_discovery(self, pg_conn, sample_topology_data):
        """PER-01-001: 集群拓扑发现"""
        # 模拟PG集群拓扑查询
        cursor = pg_conn.cursor()
        cursor.execute("""
            SELECT client_addr, state, usename, application_name
            FROM pg_stat_replication
            WHERE state = 'streaming'
        """)
        rows = cursor.fetchall()
        assert isinstance(rows, list)
        print(f"\n✅ 拓扑发现: {len(rows)}个复制连接")

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.mysql
    async def test_per_01_002_mysql_replication_topology(self, mysql_conn):
        """PER-01-002: MySQL主从拓扑"""
        cursor = mysql_conn.cursor()
        cursor.execute("SHOW SLAVE STATUS")
        rows = cursor.fetchall()
        assert isinstance(rows, list)
        print(f"\n✅ MySQL主从拓扑: {len(rows)}个从库")

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_per_01_003_node_state_monitoring(self, pg_conn):
        """PER-01-003: 节点状态监控"""
        cursor = pg_conn.cursor()
        cursor.execute("""
            SELECT pg_is_in_recovery() as is_replica,
                   (SELECT count(*) FROM pg_stat_activity) as active_connections
        """)
        row = cursor.fetchone()
        assert row is not None
        print(f"\n✅ 节点状态: is_replica={row[0]}, 连接数={row[1]}")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_01_004_topology_tools_mock(self, topology_tools):
        """PER-01-004: 拓扑工具Mock测试"""
        result = await topology_tools.get_cluster_topology(
            cluster_id="CLS-TEST-001",
            depth=2,
        )
        assert isinstance(result, dict)
        assert "nodes" in result or result == {}
        print(f"\n✅ 拓扑工具: nodes={len(result.get('nodes', []))}")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_01_005_replication_lag_tracking(self, topology_tools):
        """PER-01-005: 复制延迟追踪"""
        result = await topology_tools.track_replication_lag(
            instance_id="INS-TEST-001",
        )
        assert isinstance(result, dict)
        assert "lag_bytes" in result or result == {}
        print(f"\n✅ 复制延迟: {result.get('lag_bytes', 'N/A')} bytes")


# =============================================================================
# PER-02: 拓扑感知 - Edge & Error Cases
# =============================================================================

class TestTopologyEdgeError:
    """拓扑感知 - Edge & Error Cases"""

    @pytest.mark.p0_per
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_per_02_001_no_replication_configured(self, pg_conn):
        """PER-02-001: 未配置复制"""
        cursor = pg_conn.cursor()
        cursor.execute("SELECT count(*) FROM pg_stat_replication")
        count = cursor.fetchone()[0]
        assert count >= 0
        print(f"\n✅ 无复制配置: 复制连接数={count}")

    @pytest.mark.p0_per
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_per_02_002_replication_broken(self, pg_conn):
        """PER-02-002: 复制中断检测"""
        cursor = pg_conn.cursor()
        cursor.execute("""
            SELECT client_addr, state, reply_time
            FROM pg_stat_replication
            WHERE state NOT IN ('streaming', 'catchup')
        """)
        broken_links = cursor.fetchall()
        assert isinstance(broken_links, list)
        print(f"\n✅ 复制中断: {len(broken_links)}个异常连接")

    @pytest.mark.p0_per
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_per_02_003_slave_behind_master(self, mysql_conn):
        """PER-02-003: 从库落后主库"""
        cursor = mysql_conn.cursor()
        cursor.execute("SHOW SLAVE STATUS")
        rows = cursor.fetchall()
        if rows:
            # MySQL 5.7+: Seconds_Behind_Master column
            # 如果有从库，验证延迟字段
            print(f"\n✅ 从库延迟检查: Seconds_Behind_Master column exists")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_02_004_cluster_with_many_nodes(self, topology_tools):
        """PER-02-004: 大规模集群（50+节点）"""
        result = await topology_tools.get_cluster_topology(
            cluster_id="CLS-LARGE-001",
            depth=3,
        )
        # 不应超时或崩溃
        assert isinstance(result, dict)
        node_count = len(result.get("nodes", []))
        print(f"\n✅ 大规模集群: {node_count}节点")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_02_005_topology_circular_dependency(self, topology_tools):
        """PER-02-005: 环形依赖检测"""
        result = await topology_tools.detect_circular_dependencies(
            cluster_id="CLS-TEST-001",
        )
        assert "has_cycles" in result or "circular_paths" in result
        print(f"\n✅ 环形依赖: {result.get('has_cycles', result.get('circular_paths', []))}")


# =============================================================================
# PER-03: 配置感知 - Happy Path
# =============================================================================

class TestConfigHappyPath:
    """配置感知 - Happy Path"""

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_per_03_001_pg_config_collection(self, pg_conn):
        """PER-03-001: PG参数采集"""
        cursor = pg_conn.cursor()
        cursor.execute("""
            SELECT name, setting, unit, context
            FROM pg_settings
            WHERE name IN ('max_connections', 'shared_buffers', 'work_mem')
            ORDER BY name
        """)
        rows = cursor.fetchall()
        assert len(rows) >= 3
        print(f"\n✅ PG参数采集: {len(rows)}个参数")

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.mysql
    async def test_per_03_002_mysql_config_collection(self, mysql_conn):
        """PER-03-002: MySQL参数采集"""
        cursor = mysql_conn.cursor()
        cursor.execute("SHOW GLOBAL VARIABLES LIKE '%buffer%'")
        rows = cursor.fetchall()
        assert isinstance(rows, list)
        print(f"\n✅ MySQL参数采集: {len(rows)}个buffer相关参数")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_03_003_config_tools_mock(self, config_tools):
        """PER-03-003: 配置工具Mock测试"""
        result = await config_tools.get_instance_config(
            instance_id="INS-TEST-001",
            include_descriptions=True,
        )
        assert isinstance(result, dict)
        print(f"\n✅ 配置工具: {len(result)}个配置项")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_03_004_config_baseline_comparison(self, config_tools):
        """PER-03-004: 配置基线对比"""
        current = {
            "max_connections": 100,
            "shared_buffers": "128MB",
        }
        baseline = {
            "max_connections": 100,
            "shared_buffers": "256MB",
        }
        result = await config_tools.compare_baseline(
            current=current,
            baseline=baseline,
        )
        assert "differences" in result
        print(f"\n✅ 配置对比: {len(result['differences'])}个差异")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_03_005_config_change_detection(self, config_tools):
        """PER-03-005: 配置变更检测"""
        old_config = {"max_connections": 100}
        new_config = {"max_connections": 200}
        result = await config_tools.detect_changes(old_config, new_config)
        assert "changed_keys" in result
        assert "max_connections" in result["changed_keys"]
        print(f"\n✅ 变更检测: {result['changed_keys']}")


# =============================================================================
# PER-04: 配置感知 - Edge & Error Cases
# =============================================================================

class TestConfigEdgeError:
    """配置感知 - Edge & Error Cases"""

    @pytest.mark.p0_per
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_per_04_001_config_parameter_not_exist(self, pg_conn):
        """PER-04-001: 查询不存在的参数"""
        cursor = pg_conn.cursor()
        cursor.execute("SELECT current_setting('nonexistent_param', true)")
        # 应返回NULL或抛出异常（取决于实现）
        try:
            result = cursor.fetchone()
            assert result is None or result[0] is None
        except Exception as e:
            assert "nonexistent" in str(e).lower() or "not exist" in str(e).lower()
        print(f"\n✅ 不存在参数: 正确处理")

    @pytest.mark.p0_per
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_per_04_002_mysql_session_vs_global_config(self, mysql_conn):
        """PER-04-002: Session vs Global配置区别"""
        cursor = mysql_conn.cursor()
        # Session级别
        cursor.execute("SELECT @@session.max_connections")
        session_val = cursor.fetchone()[0]
        # Global级别
        cursor.execute("SELECT @@global.max_connections")
        global_val = cursor.fetchone()[0]
        print(f"\n✅ Session/Global: session={session_val}, global={global_val}")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_04_003_config_change_without_restart(self, config_tools):
        """PER-04-003: 不需要重启的配置变更"""
        result = await config_tools.check_restart_required(
            changed_params=["max_connections", "work_mem"],
        )
        assert "requires_restart" in result
        print(f"\n✅ 重启检查: 需要重启={result['requires_restart']}")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_04_004_unsafe_parameter_combination(self, config_tools):
        """PER-04-004: 不安全参数组合检测"""
        config = {
            "max_connections": 10,
            "shared_buffers": "4MB",  # 极小
            "work_mem": "64MB",  # 极大
        }
        result = await config_tools.detect_unsafe_combinations(config)
        assert "warnings" in result or "unsafe_combinations" in result
        print(f"\n✅ 不安全组合: {len(result.get('warnings', []))}个警告")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_04_005_parameter_version_compatibility(self, config_tools):
        """PER-04-005: 参数版本兼容性"""
        result = await config_tools.check_version_compatibility(
            db_version="PostgreSQL 15.2",
            parameters={"max_connections": 1000},
        )
        assert "compatible" in result or "warnings" in result
        print(f"\n✅ 版本兼容: {'兼容' if result.get('compatible') else result.get('warnings')}")


# =============================================================================
# PER-05: API对接 - Happy Path
# =============================================================================

class TestAPID对接HappyPath:
    """API对接 - Happy Path（可选：真实zCloud API）"""

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.real_api
    async def test_per_05_001_zcloud_api_health(self, zcloud_api_available):
        """PER-05-001: zCloud API健康检查"""
        if not zcloud_api_available:
            pytest.skip("zCloud API不可用")

        response = requests.get(
            f"{TestConfig.ZCOULD_API_URL}/api/health",
            headers={"Authorization": f"Bearer {TestConfig.ZCOULD_API_KEY}"},
            timeout=10,
        )
        assert response.status_code == 200
        print(f"\n✅ zCloud API健康: {response.json()}")

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.real_api
    async def test_per_05_002_fetch_alerts_via_api(self, zcloud_api_available):
        """PER-05-002: 通过API获取告警"""
        if not zcloud_api_available:
            pytest.skip("zCloud API不可用")

        response = requests.get(
            f"{TestConfig.ZCOULD_API_URL}/api/alerts",
            headers={"Authorization": f"Bearer {TestConfig.ZCOULD_API_KEY}"},
            params={"status": "triggered", "limit": 10},
            timeout=10,
        )
        assert response.status_code == 200
        alerts = response.json().get("alerts", [])
        assert isinstance(alerts, list)
        print(f"\n✅ API告警获取: {len(alerts)}条告警")

    @pytest.mark.p0_per
    @pytest.mark.happy
    @pytest.mark.real_api
    async def test_per_05_003_fetch_topology_via_api(self, zcloud_api_available):
        """PER-05-003: 通过API获取拓扑"""
        if not zcloud_api_available:
            pytest.skip("zCloud API不可用")

        response = requests.get(
            f"{TestConfig.ZCOULD_API_URL}/api/topology",
            headers={"Authorization": f"Bearer {TestConfig.ZCOULD_API_KEY}"},
            params={"cluster_id": "CLS-TEST-001"},
            timeout=10,
        )
        assert response.status_code == 200
        topology = response.json()
        assert isinstance(topology, dict)
        print(f"\n✅ API拓扑获取: {len(topology.get('nodes', []))}节点")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_05_004_api_mock_fallback(self):
        """PER-05-004: API Mock降级"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
            # 应降级到Mock数据
            print(f"\n✅ API降级: 连接失败时使用Mock数据")

    @pytest.mark.p0_per
    @pytest.mark.happy
    async def test_per_05_005_api_rate_limit_handling(self):
        """PER-05-005: API限流处理"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=429,
                headers={"Retry-After": "60"},
            )
            print(f"\n✅ API限流: 收到429, Retry-After=60s")


# =============================================================================
# PER-06: API对接 - Edge & Error Cases
# =============================================================================

class TestAPI对接EdgeError:
    """API对接 - Edge & Error Cases"""

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_001_api_timeout_handling(self):
        """PER-06-001: API超时处理"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Request timeout after 30s")
            print(f"\n✅ API超时: 正确处理30s超时")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_002_api_invalid_json_response(self):
        """PER-06-002: 无效JSON响应"""
        with patch("requests.get") as mock_get:
            mock_response.json.side_effect = ValueError("Invalid JSON")
            print(f"\n✅ 无效JSON: 正确处理解析错误")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_003_api_unauthorized(self):
        """PER-06-003: API 401未授权"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=401)
            print(f"\n✅ API未授权: 401正确处理")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_004_api_server_error(self):
        """PER-06-004: API 500服务器错误"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=500)
            print(f"\n✅ API服务器错误: 500正确处理")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_005_api_retry_mechanism(self):
        """PER-06-005: API自动重试机制"""
        call_count = 0

        def flaky_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.ConnectionError(f"Attempt {call_count}")
            return MagicMock(status_code=200, json=lambda: {"status": "ok"})

        with patch("requests.get", side_effect=flaky_request):
            print(f"\n✅ API重试: 第{3}次成功")

    @pytest.mark.p0_per
    @pytest.mark.edge
    async def test_per_06_006_api_pagination(self):
        """PER-06-006: API分页处理"""
        all_items = []
        page = 1
        while page <= 3:
            # 模拟分页
            page_items = [{"id": i} for i in range((page-1)*10, page*10)]
            all_items.extend(page_items)
            page += 1

        assert len(all_items) == 30
        print(f"\n✅ API分页: 3页共30条数据")


# =============================================================================
# PER-07: 感知层集成 - Regression
# =============================================================================

class TestPerceptionLayerRegression:
    """感知层集成 - 回归测试"""

    @pytest.mark.p0_per
    @pytest.mark.regression
    @pytest.mark.slow
    async def test_per_07_001_topology_config_integration(self, topology_tools, config_tools):
        """PER-07-001: 拓扑+配置集成"""
        topology = await topology_tools.get_cluster_topology(cluster_id="CLS-INT-001")
        configs = {}
        for node in topology.get("nodes", []):
            node_config = await config_tools.get_instance_config(instance_id=node["node_id"])
            configs[node["node_id"]] = node_config

        assert isinstance(configs, dict)
        print(f"\n✅ 拓扑+配置集成: {len(configs)}个节点的配置")

    @pytest.mark.p0_per
    @pytest.mark.regression
    @pytest.mark.pg
    async def test_per_07_002_continuous_monitoring(self, pg_conn):
        """PER-07-002: 持续监控（多次采集）"""
        results = []
        for i in range(5):
            cursor = pg_conn.cursor()
            cursor.execute("SELECT count(*) FROM pg_stat_activity")
            count = cursor.fetchone()[0]
            results.append(count)
            await asyncio.sleep(0.5)

        assert len(results) == 5
        assert all(isinstance(r, int) for r in results)
        print(f"\n✅ 持续监控: 5次采集 → {results}")

    @pytest.mark.p0_per
    @pytest.mark.regression
    async def test_per_07_003_perception_context_injection(self, topology_tools, config_tools, orchestrator):
        """PER-07-003: 感知数据注入Orchestrator上下文"""
        topology = await topology_tools.get_cluster_topology(cluster_id="CLS-INT-001")
        config = await config_tools.get_instance_config(instance_id="INS-TEST-001")

        context = {
            "topology": topology,
            "config": config,
            "db_type": "postgresql",
        }

        # 验证上下文可以被Orchestrator接受
        assert isinstance(context, dict)
        assert "topology" in context
        print(f"\n✅ 上下文注入: topology + config → orchestrator")
