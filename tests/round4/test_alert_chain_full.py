"""
第四轮测试：告警诊断全链路测试

本模块测试告警诊断的完整链路：
1. 告警采集 → 2. 告警关联 → 3. 根因分析 → 4. 诊断建议
"""
import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.diagnostic import DiagnosticAgent
from src.gateway.alert_correlator import (
    AlertCorrelator,
    AlertNode,
    AlertRole,
    CorrelationLink,
    CorrelationResult,
    get_mock_alert_correlator,
)


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
    
    # 创建完整的告警链场景
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
    client.get_slow_queries = AsyncMock(return_value={
        "queries": [
            {
                "sql_id": "sql_blocking",
                "query": "UPDATE orders SET status='shipped' WHERE id>1000",
                "execution_time_ms": 15234,
            }
        ],
        "total": 1,
    })
    
    return client


# ============================================================================
# 全链路测试
# ============================================================================

class TestAlertChainFullPath:
    """告警诊断全链路测试"""
    
    @pytest.mark.asyncio
    async def test_full_diagnostic_chain(self, mock_zcloud_client):
        """
        测试完整诊断链路
        
        链路：告警采集 → 关联分析 → 根因识别 → 诊断输出
        """
        # Step 1: 告警采集
        all_alerts = await mock_zcloud_client.get_alerts(status="active")
        assert len(all_alerts) >= 3, "告警采集失败"
        
        # Step 2: 关联分析
        correlator = get_mock_alert_correlator()
        correlation_result = await correlator.correlate_alerts(
            primary_alert_id="ALT-004",  # LOCK_WAIT
            all_alerts=all_alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert correlation_result is not None, "关联分析失败"
        assert len(correlation_result.correlation_chain) >= 2, "关联链太短"
        
        # Step 3: 根因识别验证
        assert correlation_result.root_cause != "", "未识别出根因"
        assert 0.0 <= correlation_result.confidence <= 1.0, "置信度无效"
        
        # Step 4: 诊断路径验证
        assert len(correlation_result.diagnostic_path) >= 2, "诊断路径不完整"
        assert "ALT-004" in correlation_result.diagnostic_path, "主告警不在诊断路径中"
        
        print(f"\n=== 完整诊断链路结果 ===")
        print(f"关联告警数: {len(correlation_result.correlation_chain)}")
        print(f"诊断路径: {' → '.join(correlation_result.diagnostic_path)}")
        print(f"根因: {correlation_result.root_cause}")
        print(f"置信度: {correlation_result.confidence:.2f}")
    
    @pytest.mark.asyncio
    async def test_diagnostic_chain_with_context(self, mock_zcloud_client):
        """
        测试带上下文的诊断链路
        """
        agent = DiagnosticAgent()
        agent._correlator = get_mock_alert_correlator()
        
        # 模拟带有会话和锁信息的上下文
        sessions = await mock_zcloud_client.get_sessions()
        locks = await mock_zcloud_client.get_locks()
        slow_queries = await mock_zcloud_client.get_slow_queries()
        
        context = {
            "instance_id": "INS-PROD-001",
            "alert_id": "ALT-004",
            "sessions": sessions,
            "locks": locks,
            "slow_queries": slow_queries,
            "mock_client": mock_zcloud_client,
        }
        
        # 执行诊断
        result = await agent.diagnose_alert("ALT-004", context)
        
        assert result.success, f"带上下文诊断失败: {result.content}"
        assert "correlation_chain" in context, "未执行关联分析"
        
        # 验证上下文包含诊断结果
        assert context.get("root_cause") != "", "根因未填入上下文"
    
    @pytest.mark.asyncio
    async def test_multi_level_correlation(self, mock_zcloud_client):
        """
        测试多层级关联分析
        
        场景：CPU → DISK_IO → SLOW_QUERY → LOCK_WAIT → RESPONSE_SLOW
        """
        # 添加更多告警形成长链
        alerts = [
            create_mock_alert("ALT-A", "CPU_HIGH", "warning", minutes_ago=60),
            create_mock_alert("ALT-B", "DISK_IO_HIGH", "warning", minutes_ago=55),
            create_mock_alert("ALT-C", "SLOW_QUERY", "warning", minutes_ago=50),
            create_mock_alert("ALT-D", "LOCK_WAIT", "critical", minutes_ago=45),
            create_mock_alert("ALT-E", "RESPONSE_SLOW", "warning", minutes_ago=40),
            create_mock_alert("ALT-F", "USER_COMPLAIN", "warning", minutes_ago=35),
        ]
        
        correlator = get_mock_alert_correlator()
        
        # 以最终症状USER_COMPLAIN为主告警
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-F",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert len(result.correlation_chain) >= 3, "多层级关联失败"
        
        # 验证根因是最上游的告警
        root_alert = result.correlation_chain[0]
        assert root_alert.role == AlertRole.ROOT_CAUSE, \
            f"第一个告警应该是根因，实际角色: {root_alert.role}"
        
        print(f"\n=== 多层级关联 ===")
        for node in result.correlation_chain:
            print(f"  {node.alert_id} ({node.alert_type}): {node.role.value}, 置信度={node.confidence:.2f}")


# ============================================================================
# 根因分析测试
# ============================================================================

class TestRootCauseAnalysis:
    """根因分析测试"""
    
    @pytest.mark.asyncio
    async def test_root_cause_identification_lock_wait(self, mock_zcloud_client):
        """
        测试LOCK_WAIT场景的根因识别
        
        预期根因：长时间运行的慢SQL持有锁
        """
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-004",  # LOCK_WAIT
            all_alerts=await mock_zcloud_client.get_alerts(status="active"),
            mock_client=mock_zcloud_client,
        )
        
        # 验证根因包含关键信息
        root_cause_text = result.root_cause.lower()
        assert any(keyword in root_cause_text for keyword in ["lock", "sql", "transaction"]), \
            f"根因描述不准确: {result.root_cause}"
    
    @pytest.mark.asyncio
    async def test_root_cause_identification_cpu_high(self, mock_zcloud_client):
        """
        测试CPU_HIGH场景的根因识别
        
        预期根因：资源不足或高负载
        """
        alerts = [
            create_mock_alert("ALT-1", "CPU_HIGH", "warning", metric_value=95.0),
            create_mock_alert("ALT-2", "DB_HIGH_LOAD", "warning", metric_value=90.0),
        ]
        
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-1",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        assert result.root_cause != "", "未识别出根因"
        assert result.confidence > 0.5, f"置信度过低: {result.confidence}"
    
    @pytest.mark.asyncio
    async def test_confidence_calculation(self, mock_zcloud_client):
        """
        测试置信度计算逻辑
        """
        correlator = get_mock_alert_correlator()
        
        # 单告警 - 低置信度
        single_alert = [create_mock_alert("ALT-1", "CPU_HIGH", "warning")]
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-1",
            all_alerts=single_alert,
            mock_client=mock_zcloud_client,
        )
        assert result.confidence < 0.8, "单告警置信度不应太高"
        
        # 多告警关联 - 较高置信度
        multi_alerts = [
            create_mock_alert("ALT-1", "CPU_HIGH", "warning"),
            create_mock_alert("ALT-2", "SLOW_QUERY", "warning"),
            create_mock_alert("ALT-3", "RESPONSE_SLOW", "warning"),
        ]
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-3",
            all_alerts=multi_alerts,
            mock_client=mock_zcloud_client,
        )
        assert result.confidence > single_alert[0].get("confidence", 0), \
            "多告警关联置信度应更高"


# ============================================================================
# 告警关联规则测试
# ============================================================================

class TestAlertCorrelationRules:
    """告警关联规则测试"""
    
    @pytest.mark.asyncio
    async def test_causal_chain_detection(self, mock_zcloud_client):
        """
        测试因果链检测
        
        验证：系统能正确识别 A→B→C 的因果关系
        """
        from src.gateway.alert_correlator import CAUSAL_RULES
        
        # CPU_HIGH → SLOW_QUERY → RESPONSE_SLOW
        alerts = [
            create_mock_alert("ALT-1", "CPU_HIGH", "warning", minutes_ago=20),
            create_mock_alert("ALT-2", "SLOW_QUERY", "warning", minutes_ago=15),
            create_mock_alert("ALT-3", "RESPONSE_SLOW", "warning", minutes_ago=10),
        ]
        
        correlator = get_mock_alert_correlator()
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-3",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 验证存在从ALT-1到ALT-3的链路
        alert_ids = [node.alert_id for node in result.correlation_chain]
        assert "ALT-1" in alert_ids, "未识别出因果链上游"
        assert "ALT-3" in alert_ids, "未包含主告警"
        
        # 验证规则库中的因果关系
        assert "SLOW_QUERY" in CAUSAL_RULES["CPU_HIGH"]["leads_to"], "规则库缺少因果关系"
    
    @pytest.mark.asyncio
    async def test_time_window_correlation(self, mock_zcloud_client):
        """
        测试时间窗口关联
        
        验证：短时间内发生的相关告警被正确关联
        """
        # 5分钟内发生的告警应关联
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
        
        # 所有告警都在时间窗口内，应该都被关联
        assert len(result.correlation_chain) >= 2, "时间窗口内告警未完全关联"
    
    @pytest.mark.asyncio
    async def test_cross_instance_correlation(self, mock_zcloud_client):
        """
        测试跨实例关联
        
        验证：不同实例的告警不会被错误关联
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
        
        # 应该只关联同实例的告警
        instance_ids = {node.instance_id for node in result.correlation_chain}
        assert len(instance_ids) == 1, f"不应跨实例关联: {instance_ids}"
        assert "INS-A" in instance_ids, "应只关联INS-A的告警"


# ============================================================================
# 诊断输出格式测试
# ============================================================================

class TestDiagnosticOutputFormat:
    """诊断输出格式测试"""
    
    @pytest.mark.asyncio
    async def test_diagnostic_path_format(self, mock_zcloud_client):
        """
        测试诊断路径格式
        
        验证：路径格式正确，告警ID顺序合理
        """
        correlator = get_mock_alert_correlator()
        
        alerts = [
            create_mock_alert("ALT-001", "CPU_HIGH", "warning", minutes_ago=30),
            create_mock_alert("ALT-002", "SLOW_QUERY", "warning", minutes_ago=20),
            create_mock_alert("ALT-003", "RESPONSE_SLOW", "warning", minutes_ago=10),
        ]
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-003",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 验证路径格式
        assert isinstance(result.diagnostic_path, list), "路径应为列表"
        assert all(isinstance(aid, str) for aid in result.diagnostic_path), "路径元素应为字符串"
        assert len(result.diagnostic_path) > 0, "路径不应为空"
    
    @pytest.mark.asyncio
    async def test_correlation_summary_format(self, mock_zcloud_client):
        """
        测试关联摘要格式
        
        验证：摘要内容完整、可读
        """
        correlator = get_mock_alert_correlator()
        
        alerts = [
            create_mock_alert("ALT-001", "CPU_HIGH", "warning", minutes_ago=20),
            create_mock_alert("ALT-002", "SLOW_QUERY", "warning", minutes_ago=15),
            create_mock_alert("ALT-003", "LOCK_WAIT", "critical", minutes_ago=10),
        ]
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-003",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 验证摘要格式
        assert isinstance(result.summary, str), "摘要应为字符串"
        assert len(result.summary) > 0, "摘要不应为空"
        assert len(result.summary) < 1000, "摘要不应过长"
    
    @pytest.mark.asyncio
    async def test_alert_node_details(self, mock_zcloud_client):
        """
        测试告警节点详情
        
        验证：节点包含所有必要信息
        """
        correlator = get_mock_alert_correlator()
        
        alerts = [
            create_mock_alert("ALT-001", "CPU_HIGH", "warning", metric_value=95.0),
        ]
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 验证节点详情
        node = result.correlation_chain[0]
        assert hasattr(node, "alert_id"), "缺少alert_id"
        assert hasattr(node, "alert_type"), "缺少alert_type"
        assert hasattr(node, "severity"), "缺少severity"
        assert hasattr(node, "role"), "缺少role"
        assert hasattr(node, "confidence"), "缺少confidence"


# ============================================================================
# 边界场景测试
# ============================================================================

class TestEdgeCases:
    """边界场景测试"""
    
    @pytest.mark.asyncio
    async def test_empty_alerts_list(self, mock_zcloud_client):
        """
        测试空告警列表
        
        验证：系统能正确处理空输入
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
    async def test_nonexistent_primary_alert(self, mock_zcloud_client):
        """
        测试不存在的主告警ID
        
        验证：系统能正确处理无效输入
        """
        alerts = [create_mock_alert("ALT-001", "CPU_HIGH", "warning")]
        
        correlator = get_mock_alert_correlator()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-NONEXISTENT",
            all_alerts=alerts,
            mock_client=mock_zcloud_client,
        )
        
        # 应返回以主告警为唯一节点的结果
        assert len(result.correlation_chain) >= 1
    
    @pytest.mark.asyncio
    async def test_single_alert_correlation(self, mock_zcloud_client):
        """
        测试单告警场景
        
        验证：单个告警也能生成有效结果
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


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
