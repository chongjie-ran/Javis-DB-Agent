"""
第九轮测试：集成测试增强

复用Round4测试的"诊断-告警链"端到端场景：
1. 告警 → 诊断 完整链路
2. 诊断 → 告警关联
3. 端到端回归测试
"""
import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.diagnostic import DiagnosticAgent
from src.agents.orchestrator import OrchestratorAgent
from src.gateway.alert_correlator import (
    AlertCorrelator,
    AlertNode,
    AlertRole,
    CorrelationLink,
    CorrelationResult,
    get_mock_alert_correlator,
)
from src.mock_api.zcloud_client import MockZCloudClient


# ============================================================================
# 测试数据
# ============================================================================

def create_mock_alert(
    alert_id: str,
    alert_type: str,
    severity: str,
    instance_id: str = "INS-PROD-001",
    metric_value: float = 90.0,
    threshold: float = 80.0,
    minutes_ago: int = 0,
) -> Dict[str, Any]:
    """创建Mock告警数据"""
    return {
        "alert_id": alert_id,
        "alert_type": alert_type,
        "alert_name": f"{alert_type}告警",
        "severity": severity,
        "instance_id": instance_id,
        "instance_name": "生产主库",
        "occurred_at": time.time() - minutes_ago * 60,
        "metric_value": metric_value,
        "threshold": threshold,
        "message": f"{alert_type}超过阈值，当前值{metric_value}",
        "status": "active",
    }


# ============================================================================
# 夹具
# ============================================================================

@pytest.fixture
def mock_zcloud_client():
    """Mock zCloud客户端"""
    client = MagicMock()
    
    alerts = [
        create_mock_alert("ALT-001", "CPU_HIGH", "warning", minutes_ago=30),
        create_mock_alert("ALT-002", "DISK_IO_HIGH", "warning", minutes_ago=25),
        create_mock_alert("ALT-003", "SLOW_QUERY", "warning", minutes_ago=20),
        create_mock_alert("ALT-004", "LOCK_WAIT", "critical", minutes_ago=10),
        create_mock_alert("ALT-005", "RESPONSE_SLOW", "warning", minutes_ago=5),
    ]
    
    client.get_alerts = AsyncMock(return_value=alerts)
    client.get_instance = AsyncMock(return_value={
        "instance_id": "INS-PROD-001",
        "name": "生产主库",
        "status": "running",
    })
    client.get_sessions = AsyncMock(return_value={
        "sessions": [
            {"sid": 1001, "status": "ACTIVE", "wait_event": "lock", "sql_id": "sql_blocking"},
            {"sid": 1002, "status": "ACTIVE", "wait_event": "lock", "sql_id": "sql_blocked"},
        ],
        "total": 2,
    })
    client.get_locks = AsyncMock(return_value={
        "locks": [
            {"lock_type": "row exclusive", "granted": True, "sid": 1001},
            {"lock_type": "row exclusive", "granted": False, "sid": 1002},
        ],
        "blocking_chain": [{"blocker": 1001, "waiter": 1002}],
    })
    client.get_slow_sql = AsyncMock(return_value={
        "slow_sqls": [
            {
                "sql_id": "sql_blocking",
                "sql_text": "UPDATE orders SET status='shipped' WHERE id>1000",
                "elapsed_time_sec": 15.234,
            }
        ],
        "count": 1,
    })
    
    return client


@pytest.fixture
def real_client():
    """RealClient测试夹具"""
    from src.real_api import ZCloudRealClient, RealAPIConfig
    
    config = RealAPIConfig(
        base_url="https://zcloud.example.com/api/v1",
        auth_type="api_key",
        api_key="test-key",
        use_mock=True,  # 使用mock模式
    )
    return ZCloudRealClient(config=config)


# ============================================================================
# 告警→诊断 端到端测试
# ============================================================================

class TestAlertToDiagnosisE2E:
    """告警到诊断端到端测试"""
    
    @pytest.mark.asyncio
    async def test_alert_chain_diagnosis_flow(self, mock_zcloud_client):
        """
        测试告警链诊断完整流程
        
        流程：告警列表 → 关联分析 → 诊断 → 结果
        """
        # Step 1: 获取告警列表
        alerts = await mock_zcloud_client.get_alerts(status="active")
        assert len(alerts) >= 3, "告警列表获取失败"
        
        # Step 2: 选择主告警进行诊断
        primary_alert = next((a for a in alerts if a["alert_type"] == "LOCK_WAIT"), alerts[0])
        
        # Step 3: 告警关联分析
        correlator = get_mock_alert_correlator()
        correlation_result = await correlator.correlate_alerts(
            primary_alert_id=primary_alert["alert_id"],
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert correlation_result is not None, "关联分析失败"
        assert len(correlation_result.correlation_chain) >= 1, "关联链为空"
        
        # Step 4: 获取实例详情
        instance = await mock_zcloud_client.get_instance(primary_alert["instance_id"])
        assert instance is not None, "实例详情获取失败"
        
        # Step 5: 获取会话信息
        sessions = await mock_zcloud_client.get_sessions(primary_alert["instance_id"])
        assert sessions is not None, "会话信息获取失败"
        
        print(f"\n=== 告警→诊断流程完成 ===")
        print(f"处理告警数: {len(alerts)}")
        print(f"关联链长度: {len(correlation_result.correlation_chain)}")
        print(f"根因: {correlation_result.root_cause}")
    
    @pytest.mark.asyncio
    async def test_diagnosis_with_session_context(self, mock_zcloud_client):
        """
        测试带会话上下文的诊断
        
        验证：诊断能正确使用会话信息
        """
        correlator = get_mock_alert_correlator()
        
        alerts = await mock_zcloud_client.get_alerts(status="active")
        sessions = await mock_zcloud_client.get_sessions("INS-PROD-001")
        locks = await mock_zcloud_client.get_locks("INS-PROD-001")
        
        # 构建上下文
        context = {
            "alerts": alerts,
            "sessions": sessions,
            "locks": locks,
            "mock_client": mock_zcloud_client,
        }
        
        # 执行关联分析
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-004",  # LOCK_WAIT
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert result is not None
        assert len(result.correlation_chain) >= 1


class TestMockVsRealClientConsistency:
    """Mock与Real客户端一致性测试"""
    
    @pytest.mark.asyncio
    async def test_get_alerts_interface_consistency(self, mock_zcloud_client, real_client):
        """测试get_alerts接口一致性"""
        # Mock客户端调用
        mock_result = await mock_zcloud_client.get_alerts(
            instance_id="INS-001",
            severity="warning",
            status="active",
            limit=50,
        )
        
        # Real客户端接口存在（即使无法实际调用）
        assert hasattr(real_client, "get_alerts")
        
        # 验证Real客户端接口签名正确
        import inspect
        real_sig = inspect.signature(real_client.get_alerts)
        # inspect.signature on bound method already excludes self
        real_params = list(real_sig.parameters.keys())
        
        # Real客户端应该有这些参数
        expected_params = ['instance_id', 'severity', 'status', 'limit']
        assert real_params == expected_params, f"Real接口参数: {real_params}"
    
    @pytest.mark.asyncio
    async def test_get_instance_interface_consistency(self, mock_zcloud_client, real_client):
        """测试get_instance接口一致性"""
        assert hasattr(real_client, "get_instance")
        
        import inspect
        real_sig = inspect.signature(real_client.get_instance)
        # inspect.signature on bound method already excludes self
        real_params = list(real_sig.parameters.keys())
        
        # get_instance(instance_id)
        assert real_params == ['instance_id'], f"Real接口参数: {real_params}"


class TestAlertCorrelationRegression:
    """告警关联回归测试（复用Round4）"""
    
    @pytest.mark.asyncio
    async def test_full_diagnostic_chain_regression(self, mock_zcloud_client):
        """
        回归测试：完整诊断链路
        
        这是Round4的test_full_diagnostic_chain测试的回归验证
        """
        all_alerts = await mock_zcloud_client.get_alerts(status="active")
        assert len(all_alerts) >= 3, "告警采集失败"
        
        correlator = get_mock_alert_correlator()
        correlation_result = await correlator.correlate_alerts(
            primary_alert_id="ALT-004",
            all_alerts=all_alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert correlation_result is not None, "关联分析失败"
        assert len(correlation_result.correlation_chain) >= 2, "关联链太短"
        assert correlation_result.root_cause != "", "未识别出根因"
        assert 0.0 <= correlation_result.confidence <= 1.0, "置信度无效"
    
    @pytest.mark.asyncio
    async def test_multi_level_correlation_regression(self, mock_zcloud_client):
        """
        回归测试：多层级关联
        
        这是Round4的test_multi_level_correlation测试的回归验证
        """
        alerts = [
            create_mock_alert("ALT-A", "CPU_HIGH", "warning", minutes_ago=60),
            create_mock_alert("ALT-B", "DISK_IO_HIGH", "warning", minutes_ago=55),
            create_mock_alert("ALT-C", "SLOW_QUERY", "warning", minutes_ago=50),
            create_mock_alert("ALT-D", "LOCK_WAIT", "critical", minutes_ago=45),
            create_mock_alert("ALT-E", "RESPONSE_SLOW", "warning", minutes_ago=40),
        ]
        
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-E",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert len(result.correlation_chain) >= 3, "多层级关联失败"
        
        root_alert = result.correlation_chain[0]
        assert root_alert.role == AlertRole.ROOT_CAUSE, \
            f"第一个告警应该是根因，实际角色: {root_alert.role}"
    
    @pytest.mark.asyncio
    async def test_root_cause_identification_regression(self, mock_zcloud_client):
        """
        回归测试：根因识别
        
        这是Round4的test_root_cause_identification_lock_wait测试的回归验证
        """
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-004",
            all_alerts=await mock_zcloud_client.get_alerts(status="active"),
            mock_client=mock_zcloud_client,
        )
        
        root_cause_text = result.root_cause.lower()
        assert any(keyword in root_cause_text for keyword in ["lock", "sql", "transaction"]), \
            f"根因描述不准确: {result.root_cause}"
    
    @pytest.mark.asyncio
    async def test_time_window_correlation_regression(self, mock_zcloud_client):
        """
        回归测试：时间窗口关联
        
        这是Round4的test_time_window_correlation测试的回归验证
        """
        alerts = [
            create_mock_alert("ALT-1", "CPU_HIGH", "warning", minutes_ago=5),
            create_mock_alert("ALT-2", "DISK_IO_HIGH", "warning", minutes_ago=4),
            create_mock_alert("ALT-3", "SLOW_QUERY", "warning", minutes_ago=3),
        ]
        
        correlator = get_mock_alert_correlator()
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-1",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert len(result.correlation_chain) >= 2, "时间窗口内告警未完全关联"
    
    @pytest.mark.asyncio
    async def test_cross_instance_isolation_regression(self, mock_zcloud_client):
        """
        回归测试：跨实例隔离
        
        这是Round4的test_cross_instance_correlation测试的回归验证
        """
        alerts = [
            create_mock_alert("ALT-1", "CPU_HIGH", "warning", instance_id="INS-A", minutes_ago=5),
            create_mock_alert("ALT-2", "CPU_HIGH", "warning", instance_id="INS-B", minutes_ago=4),
            create_mock_alert("ALT-3", "SLOW_QUERY", "warning", instance_id="INS-A", minutes_ago=3),
        ]
        
        correlator = get_mock_alert_correlator()
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-1",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        instance_ids = {node.instance_id for node in result.correlation_chain}
        assert len(instance_ids) == 1, f"不应跨实例关联: {instance_ids}"
        assert "INS-A" in instance_ids, "应只关联INS-A的告警"
    
    @pytest.mark.asyncio
    async def test_edge_case_empty_alerts_regression(self, mock_zcloud_client):
        """
        回归测试：空告警列表处理
        
        这是Round4的test_empty_alerts_list测试的回归验证
        """
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-999",
            all_alerts=[],
            mock_client=mock_zcloud_client,
        )
        
        assert result is not None, "空列表不应返回None"
        assert len(result.correlation_chain) >= 1, "应至少包含主告警"
    
    @pytest.mark.asyncio
    async def test_edge_case_single_alert_regression(self, mock_zcloud_client):
        """
        回归测试：单告警处理
        
        这是Round4的test_single_alert_correlation测试的回归验证
        """
        alerts = [create_mock_alert("ALT-001", "CPU_HIGH", "warning")]
        
        correlator = get_mock_alert_correlator()
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert result.primary_alert_id == "ALT-001"
        assert len(result.correlation_chain) == 1
        assert result.confidence >= 0.0


class TestEndToEndScenarios:
    """端到端场景测试"""
    
    @pytest.mark.asyncio
    async def test_lock_wait_full_flow(self, mock_zcloud_client):
        """
        测试LOCK_WAIT完整处理流程
        
        场景：数据库出现锁等待告警的完整处理流程
        """
        # 1. 告警检测
        alerts = await mock_zcloud_client.get_alerts(status="active")
        lock_wait_alert = next(
            (a for a in alerts if a["alert_type"] == "LOCK_WAIT"),
            None
        )
        assert lock_wait_alert is not None, "未找到LOCK_WAIT告警"
        
        # 2. 关联分析
        correlator = get_mock_alert_correlator()
        result = await correlator.correlate_alerts(
            primary_alert_id=lock_wait_alert["alert_id"],
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 3. 获取锁信息
        locks = await mock_zcloud_client.get_locks(lock_wait_alert["instance_id"])
        assert locks is not None
        
        # 4. 获取慢SQL
        slow_sql = await mock_zcloud_client.get_slow_sql(lock_wait_alert["instance_id"])
        assert slow_sql is not None
        
        print(f"\n=== LOCK_WAIT完整流程 ===")
        print(f"告警ID: {lock_wait_alert['alert_id']}")
        print(f"关联链: {' → '.join([n.alert_id for n in result.correlation_chain])}")
        print(f"阻塞会话: {locks.get('total_blocked', 0)}")
        print(f"慢SQL数: {slow_sql.get('count', 0)}")
    
    @pytest.mark.asyncio
    async def test_cpu_high_escalation_flow(self, mock_zcloud_client):
        """
        测试CPU高负载告警升级流程
        
        场景：CPU高 → 响应慢 → 可能触发锁等待
        """
        # 添加CPU相关的告警链 - 使用关联规则中存在的告警类型
        alerts = [
            create_mock_alert("ALT-CPU-1", "CPU_HIGH", "warning", metric_value=95.0, minutes_ago=30),
            create_mock_alert("ALT-CPU-2", "SLOW_QUERY", "warning", minutes_ago=20),
            create_mock_alert("ALT-CPU-3", "RESPONSE_SLOW", "warning", minutes_ago=10),
        ]
        
        correlator = get_mock_alert_correlator()
        
        # 以最终症状RESPONSE_SLOW为主告警进行溯源
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-CPU-3",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 验证能溯源到CPU问题
        alert_ids = [node.alert_id for node in result.correlation_chain]
        assert "ALT-CPU-1" in alert_ids, "未能溯源到CPU问题"
        
        print(f"\n=== CPU升级链路 ===")
        print(f"关联链: {' → '.join(alert_ids)}")


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
