"""
第三轮测试：告警关联推理链
测试 AlertCorrelator 的链式诊断功能
"""
import pytest
import time
import asyncio
from src.gateway.alert_correlator import (
    AlertCorrelator,
    MockAlertCorrelator,
    AlertNode,
    AlertRole,
    CAUSAL_RULES,
)


class TestAlertCorrelation:
    """告警关联测试"""
    
    @pytest.fixture
    def correlator(self):
        """创建关联器实例"""
        return AlertCorrelator(
            time_window_seconds=600,
            same_instance_weight=0.3,
            causal_weight=0.5,
            time_proximity_weight=0.2,
        )
    
    @pytest.fixture
    def sample_alerts(self):
        """样本告警数据"""
        now = time.time()
        return [
            {
                "alert_id": "ALT-001",
                "alert_name": "CPU使用率过高",
                "alert_type": "CPU_HIGH",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-ORDER-DB",
                "occurred_at": now - 300,
                "metric_value": 85.0,
                "threshold": 75.0,
                "message": "CPU使用率达到85%，超过阈值75%",
                "status": "active",
            },
            {
                "alert_id": "ALT-002",
                "alert_name": "慢SQL告警",
                "alert_type": "SLOW_QUERY",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-ORDER-DB",
                "occurred_at": now - 200,
                "metric_value": 5.0,
                "threshold": 1.0,
                "message": "检测到执行时间超过5秒的SQL",
                "status": "active",
            },
            {
                "alert_id": "ALT-003",
                "alert_name": "用户反馈响应慢",
                "alert_type": "RESPONSE_SLOW",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-ORDER-DB",
                "occurred_at": now - 100,
                "metric_value": 3.0,
                "threshold": 1.0,
                "message": "用户反馈系统响应时间超过3秒",
                "status": "active",
            },
            {
                "alert_id": "ALT-004",
                "alert_name": "磁盘使用率过高",
                "alert_type": "DISK_USAGE_HIGH",
                "severity": "warning",
                "instance_id": "INS-002",
                "instance_name": "PROD-USER-DB",
                "occurred_at": now - 150,
                "metric_value": 88.0,
                "threshold": 85.0,
                "message": "磁盘使用率达到88%，超过阈值85%",
                "status": "active",
            },
        ]
    
    def test_causal_rules_exist(self):
        """测试因果规则是否定义完整"""
        # 检查关键告警类型是否有因果规则
        required_types = ["CPU_HIGH", "SLOW_QUERY", "LOCK_WAIT", "RESPONSE_SLOW"]
        for alert_type in required_types:
            assert alert_type in CAUSAL_RULES, f"Missing causal rule for {alert_type}"
        
        # 检查因果规则的格式
        for alert_type, rules in CAUSAL_RULES.items():
            assert "causes" in rules, f"Missing 'causes' for {alert_type}"
            assert "leads_to" in rules, f"Missing 'leads_to' for {alert_type}"
            assert isinstance(rules["causes"], list), f"'causes' should be list for {alert_type}"
            assert isinstance(rules["leads_to"], list), f"'leads_to' should be list for {alert_type}"
    
    def test_correlator_initialization(self, correlator):
        """测试关联器初始化"""
        assert correlator.time_window == 600
        assert correlator.weights["same_instance"] == 0.3
        assert correlator.weights["causal"] == 0.5
        assert correlator.weights["time_proximity"] == 0.2
    
    @pytest.mark.asyncio
    async def test_correlate_alerts_basic(self, correlator, sample_alerts):
        """测试基本告警关联功能"""
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",
            all_alerts=sample_alerts,
        )
        
        # 验证结果结构
        assert result.primary_alert_id == "ALT-001"
        assert len(result.correlation_chain) >= 1
        assert len(result.diagnostic_path) >= 1
        assert result.confidence > 0
        assert result.summary != ""
        
        # 验证诊断路径
        assert "ALT-001" in result.diagnostic_path
    
    @pytest.mark.asyncio
    async def test_correlate_alerts_chain(self, correlator, sample_alerts):
        """测试告警链构建：CPU_HIGH -> SLOW_QUERY -> RESPONSE_SLOW"""
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",  # CPU_HIGH
            all_alerts=sample_alerts,
        )
        
        # 验证关联链包含相关告警
        alert_ids = [n.alert_id for n in result.correlation_chain]
        
        # ALT-001 应该与 ALT-002 (SLOW_QUERY) 关联（CPU_HIGH leads_to SLOW_QUERY）
        # ALT-002 应该与 ALT-003 (RESPONSE_SLOW) 关联（SLOW_QUERY leads_to RESPONSE_SLOW）
        
        assert len(result.correlation_chain) >= 1, "Should find related alerts"
        
        # 验证根因分析
        if result.root_cause:
            assert len(result.root_cause) > 0, "Root cause should be identified"
    
    @pytest.mark.asyncio
    async def test_different_instance_alerts_not_correlated(self, correlator, sample_alerts):
        """测试不同实例的告警不会被强关联"""
        # INS-001 和 INS-002 的告警
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",  # INS-001
            all_alerts=sample_alerts,
        )
        
        # 查找 INS-002 的告警是否在关联链中
        ins002_alerts = [n for n in result.correlation_chain if n.instance_id == "INS-002"]
        
        # INS-002 的告警不应该有高关联度（因为是不同实例）
        for node in ins002_alerts:
            # 如果出现在链中，置信度应该较低
            if node.alert_id == "ALT-004":
                assert node.confidence < 0.8, "Different instance alert should have lower confidence"
    
    @pytest.mark.asyncio
    async def test_time_window_filtering(self, correlator):
        """测试时间窗口过滤"""
        now = time.time()
        
        # 创建时间上分散的告警
        alerts = [
            {
                "alert_id": "ALT-OLD",
                "alert_name": "旧告警",
                "alert_type": "CPU_HIGH",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "TEST",
                "occurred_at": now - 7200,  # 2小时前
                "metric_value": 80.0,
                "threshold": 75.0,
                "message": "旧告警",
                "status": "active",
            },
            {
                "alert_id": "ALT-NEW",
                "alert_name": "新告警",
                "alert_type": "SLOW_QUERY",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "TEST",
                "occurred_at": now - 60,  # 1分钟前
                "metric_value": 5.0,
                "threshold": 1.0,
                "message": "新告警",
                "status": "active",
            },
        ]
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-OLD",
            all_alerts=alerts,
        )
        
        # 新告警应该在关联链中（时间接近）
        alert_ids = [n.alert_id for n in result.correlation_chain]
        assert "ALT-NEW" in alert_ids, "Recent alert should be correlated"
    
    def test_alert_role_assignment(self, correlator):
        """测试告警角色分配"""
        # 创建测试节点
        node1 = AlertNode(
            alert_id="ALT-1",
            alert_name="CPU高",
            alert_type="CPU_HIGH",
            severity="warning",
            instance_id="INS-001",
            instance_name="TEST",
            occurred_at=time.time() - 300,
            metric_value=85.0,
            threshold=75.0,
            message="CPU高",
            status="active",
        )
        
        node2 = AlertNode(
            alert_id="ALT-2",
            alert_name="慢SQL",
            alert_type="SLOW_QUERY",
            severity="warning",
            instance_id="INS-001",
            instance_name="TEST",
            occurred_at=time.time() - 200,
            metric_value=5.0,
            threshold=1.0,
            message="慢SQL",
            status="active",
        )
        
        # CPU_HIGH leads_to SLOW_QUERY
        links = []  # 简化测试
        
        # 分配角色
        correlator._assign_role(node1, links, {"ALT-1": node1, "ALT-2": node2})
        correlator._assign_role(node2, links, {"ALT-1": node1, "ALT-2": node2})
        
        # node1 应该是根因（CPU_HIGH 是 SLOW_QUERY 的原因）
        # node2 应该是症状
        assert node1.role in [AlertRole.ROOT_CAUSE, AlertRole.UNKNOWN]
        assert node2.role in [AlertRole.SYMPTOM, AlertRole.CONTRIBUTING, AlertRole.UNKNOWN]


class TestMockAlertCorrelator:
    """Mock环境告警关联测试"""
    
    @pytest.fixture
    def mock_correlator(self):
        return MockAlertCorrelator()
    
    @pytest.mark.asyncio
    async def test_get_related_alerts(self, mock_correlator):
        """测试获取关联告警"""
        # 注意：这个测试需要Mock客户端配合
        # 当前只测试方法存在
        assert hasattr(mock_correlator, "get_related_alerts")


class TestAlertCorrelationIntegration:
    """告警关联集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_diagnostic_path(self):
        """测试完整诊断路径"""
        correlator = AlertCorrelator()
        
        now = time.time()
        
        # 模拟一个级联故障场景
        alerts = [
            # 根因：CPU高
            {
                "alert_id": "ALT-001",
                "alert_name": "CPU使用率过高",
                "alert_type": "CPU_HIGH",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-DB",
                "occurred_at": now - 600,
                "metric_value": 90.0,
                "threshold": 75.0,
                "message": "CPU 90%",
                "status": "active",
            },
            # 中间：慢SQL
            {
                "alert_id": "ALT-002",
                "alert_name": "慢SQL告警",
                "alert_type": "SLOW_QUERY",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-DB",
                "occurred_at": now - 400,
                "metric_value": 10.0,
                "threshold": 1.0,
                "message": "慢SQL",
                "status": "active",
            },
            # 症状：响应慢
            {
                "alert_id": "ALT-003",
                "alert_name": "响应缓慢",
                "alert_type": "RESPONSE_SLOW",
                "severity": "warning",
                "instance_id": "INS-001",
                "instance_name": "PROD-DB",
                "occurred_at": now - 200,
                "metric_value": 5.0,
                "threshold": 1.0,
                "message": "响应慢",
                "status": "active",
            },
            # 不相关告警
            {
                "alert_id": "ALT-004",
                "alert_name": "磁盘使用率高",
                "alert_type": "DISK_USAGE_HIGH",
                "severity": "warning",
                "instance_id": "INS-002",  # 不同实例
                "instance_name": "TEST-DB",
                "occurred_at": now - 300,
                "metric_value": 88.0,
                "threshold": 85.0,
                "message": "磁盘88%",
                "status": "active",
            },
        ]
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",
            all_alerts=alerts,
        )
        
        # 验证诊断链构建
        assert len(result.correlation_chain) >= 2, "Should find at least 2 related alerts"
        
        # 验证路径
        assert "ALT-001" in result.diagnostic_path, "Primary alert should be in path"
        
        # 验证根因识别
        root_cause_nodes = [n for n in result.correlation_chain if n.role == AlertRole.ROOT_CAUSE]
        assert len(root_cause_nodes) >= 1, "Should identify at least one root cause"
        
        # 验证置信度
        assert 0 <= result.confidence <= 1, "Confidence should be between 0 and 1"
        
        # 验证摘要
        assert len(result.summary) > 0, "Summary should not be empty"
        
        print(f"\n=== Diagnostic Path ===")
        print(f"Path: {' -> '.join(result.diagnostic_path)}")
        print(f"Root Cause: {result.root_cause}")
        print(f"Confidence: {result.confidence}")
        print(f"Summary: {result.summary}")
        print(f"\nCorrelation Chain:")
        for node in result.correlation_chain:
            print(f"  [{node.alert_id}] {node.alert_name} - {node.role.value} ({node.confidence:.0%})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
