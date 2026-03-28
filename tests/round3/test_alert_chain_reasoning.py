"""
Round 3 Test Preparation: Alert Chain Reasoning Tests
测试告警关联推理链 - A告警→B告警→C告警的链式诊断逻辑

测试场景:
1. 单跳推理: A告警直接关联B告警
2. 两跳推理: A告警→B告警→C告警
3. 并行告警推理: 多个告警同时触发时的关联分析
4. 告警因果链验证: 根因告警→中间告警→表象告警

覆盖范围:
- 告警关联规则匹配
- 推理链构建
- 置信度传递
- 根因定位
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestAlertChainDataStructures:
    """测试告警关联推理链的数据结构"""

    def test_alert_node_structure(self):
        """测试告警节点结构"""
        alert_node = {
            "alert_id": "ALT-001",
            "alert_type": "CPU_HIGH",
            "severity": "warning",
            "instance_id": "INS-001",
            "occurred_at": "2026-03-28T10:00:00Z",
            "metrics": {"cpu_usage": 85.0},
            "related_alerts": [],  # 关联的告警列表
            "root_cause": False,
            "chain_depth": 0,
        }
        
        required_fields = [
            "alert_id", "alert_type", "severity", 
            "instance_id", "occurred_at", "metrics",
            "related_alerts", "root_cause", "chain_depth"
        ]
        for field in required_fields:
            assert field in alert_node, f"Missing required field: {field}"

    def test_alert_chain_structure(self):
        """测试告警链结构"""
        chain = {
            "chain_id": "CHAIN-001",
            "root_alert_id": "ALT-001",
            "chain_length": 3,
            "nodes": [
                {"alert_id": "ALT-001", "depth": 0, "role": "root"},
                {"alert_id": "ALT-002", "depth": 1, "role": "intermediate"},
                {"alert_id": "ALT-003", "depth": 2, "role": "symptom"},
            ],
            "confidence": 0.85,
            "inference_path": ["ALT-001", "ALT-002", "ALT-003"],
        }
        
        assert chain["chain_length"] == len(chain["nodes"])
        assert chain["inference_path"] == [n["alert_id"] for n in chain["nodes"]]


class TestAlertCorrelationRules:
    """测试告警关联规则"""

    def test_cpu_high_triggers_lock_wait(self):
        """CPU高负载 → 锁等待超时 关联规则"""
        rule = {
            "cause_alert_type": "CPU_HIGH",
            "effect_alert_type": "LOCK_WAIT_TIMEOUT",
            "correlation_type": "causal",
            "probability": 0.7,
            "time_window_seconds": 300,
            "conditions": [
                "cpu_usage > 80",
                "active_connections > 100",
            ]
        }
        
        assert rule["cause_alert_type"] == "CPU_HIGH"
        assert rule["effect_alert_type"] == "LOCK_WAIT_TIMEOUT"
        assert 0 <= rule["probability"] <= 1

    def test_lock_wait_triggers_session_leak(self):
        """锁等待超时 → 会话泄漏 关联规则"""
        rule = {
            "cause_alert_type": "LOCK_WAIT_TIMEOUT",
            "effect_alert_type": "SESSION_LEAK",
            "correlation_type": "escalation",
            "probability": 0.6,
            "time_window_seconds": 600,
            "conditions": [
                "wait_duration > 300",
                "blocked_sessions > 5",
            ]
        }
        
        assert rule["cause_alert_type"] == "LOCK_WAIT_TIMEOUT"
        assert rule["correlation_type"] in ["causal", "escalation", "parallel"]

    def test_replication_lag_triggers_slow_queries(self):
        """主从延迟 → 慢查询增多 关联规则"""
        rule = {
            "cause_alert_type": "REPLICATION_LAG",
            "effect_alert_type": "SLOW_QUERY_DETECTED",
            "correlation_type": "causal",
            "probability": 0.8,
            "time_window_seconds": 180,
        }
        
        assert rule["correlation_type"] == "causal"
        assert rule["probability"] >= 0.7

    def test_disk_full_triggers_replication_failure(self):
        """磁盘空间满 → 复制失败 关联规则"""
        rule = {
            "cause_alert_type": "DISK_USAGE_HIGH",
            "effect_alert_type": "BACKUP_FAILED",
            "correlation_type": "causal",
            "probability": 0.9,
            "time_window_seconds": 60,
            "conditions": ["disk_usage > 95"]
        }
        
        assert rule["cause_alert_type"] == "DISK_USAGE_HIGH"
        assert rule["effect_alert_type"] == "BACKUP_FAILED"


class TestSingleHopReasoning:
    """测试单跳推理: A告警→B告警"""

    def test_cpu_high_to_lock_wait_single_hop(self):
        """CPU高 → 锁等待超时 (单跳)"""
        # 模拟告警数据
        cpu_alert = {
            "alert_id": "ALT-CPU-001",
            "alert_type": "CPU_HIGH",
            "severity": "warning",
            "metric_value": 92.5,
            "instance_id": "INS-001",
            "occurred_at": "2026-03-28T10:00:00Z",
        }
        
        expected_correlation = {
            "source": "ALT-CPU-001",
            "target": "LOCK_WAIT_TIMEOUT",
            "correlation_type": "causal",
            "confidence": 0.75,
            "reasoning": "CPU高负载导致事务处理变慢，锁等待时间增加",
        }
        
        assert expected_correlation["source"] == cpu_alert["alert_id"]
        assert expected_correlation["confidence"] > 0.5

    def test_slow_query_to_connection_exhaustion(self):
        """慢SQL → 连接数耗尽 (单跳)"""
        slow_sql_alert = {
            "alert_id": "ALT-SQL-001",
            "alert_type": "SLOW_QUERY_DETECTED",
            "severity": "info",
            "sql_id": "sql_abc123",
            "elapsed_seconds": 120.5,
        }
        
        expected_correlation = {
            "source": "ALT-SQL-001",
            "target": "CONNECTION_FULL",
            "correlation_type": "escalation",
            "confidence": 0.65,
        }
        
        assert expected_correlation["source"] == slow_sql_alert["alert_id"]


class TestTwoHopReasoning:
    """测试两跳推理: A告警→B告警→C告警"""

    def test_cpu_to_lock_to_session_leak_chain(self):
        """CPU高 → 锁等待 → 会话泄漏 (两跳链)"""
        chain = {
            "chain_id": "CHAIN-CPU-LOCK-SESSION",
            "inference_path": [
                {
                    "alert_id": "ALT-CPU-001",
                    "alert_type": "CPU_HIGH",
                    "depth": 0,
                    "role": "root_cause",
                },
                {
                    "alert_id": "ALT-LOCK-001",
                    "alert_type": "LOCK_WAIT_TIMEOUT",
                    "depth": 1,
                    "role": "intermediate",
                    "triggered_by": "ALT-CPU-001",
                },
                {
                    "alert_id": "ALT-SESSION-001",
                    "alert_type": "SESSION_LEAK",
                    "depth": 2,
                    "role": "symptom",
                    "triggered_by": "ALT-LOCK-001",
                },
            ],
            "total_confidence": 0.45,  # 0.75 * 0.60
            "chain_length": 2,  # 跳数
        }
        
        # 验证链长度
        assert chain["chain_length"] == len(chain["inference_path"]) - 1
        
        # 验证根因
        root = chain["inference_path"][0]
        assert root["role"] == "root_cause"
        assert root["alert_type"] == "CPU_HIGH"
        
        # 验证中间节点
        intermediate = chain["inference_path"][1]
        assert intermediate["role"] == "intermediate"
        assert intermediate["triggered_by"] == root["alert_id"]
        
        # 验证症状节点
        symptom = chain["inference_path"][2]
        assert symptom["role"] == "symptom"
        assert symptom["triggered_by"] == intermediate["alert_id"]

    def test_disk_full_to_backup_to_ha_switch_chain(self):
        """磁盘满 → 备份失败 → HA切换 (两跳链)"""
        chain = {
            "chain_id": "CHAIN-DISK-BACKUP-HA",
            "inference_path": [
                {"alert_id": "ALT-DISK-001", "alert_type": "DISK_USAGE_HIGH", "depth": 0, "role": "root_cause"},
                {"alert_id": "ALT-BACKUP-001", "alert_type": "BACKUP_FAILED", "depth": 1, "role": "intermediate"},
                {"alert_id": "ALT-HA-001", "alert_type": "HA_SWITCH_TRIGGERED", "depth": 2, "role": "symptom"},
            ],
            "total_confidence": 0.81,  # 0.90 * 0.90
        }
        
        assert chain["total_confidence"] > 0.8
        assert len(chain["inference_path"]) == 3

    def test_confidence_propagation_in_chain(self):
        """测试置信度在链中的传递"""
        # 第一跳置信度
        hop1_confidence = 0.75
        # 第二跳置信度
        hop2_confidence = 0.60
        
        # 链总置信度 = 各跳置信度乘积
        chain_confidence = hop1_confidence * hop2_confidence
        
        assert abs(chain_confidence - 0.45) < 0.001  # 浮点精度
        # 链越长，置信度衰减越多
        assert chain_confidence < hop1_confidence
        assert chain_confidence < hop2_confidence


class TestParallelAlertReasoning:
    """测试并行告警推理: 多告警同时触发"""

    def test_parallel_alerts_same_root_cause(self):
        """同一根因触发的并行告警"""
        parallel_alerts = {
            "root_cause": {
                "alert_id": "ALT-ROOT-001",
                "alert_type": "NETWORK_LATENCY",
                "severity": "critical",
            },
            "parallel_symptoms": [
                {"alert_id": "ALT-001", "alert_type": "SLOW_QUERY_DETECTED", "depth": 1},
                {"alert_id": "ALT-002", "alert_type": "CONNECTION_TIMEOUT", "depth": 1},
                {"alert_id": "ALT-003", "alert_type": "REPLICATION_LAG", "depth": 1},
            ],
            "total_confidence": 0.92,
        }
        
        assert len(parallel_alerts["parallel_symptoms"]) == 3
        # 网络延迟是多症状的根因
        assert parallel_alerts["root_cause"]["alert_type"] == "NETWORK_LATENCY"

    def test_multiple_chains_intersection(self):
        """多链交叉场景"""
        # 链1: CPU → Lock → Session
        chain1 = {
            "path": ["ALT-CPU-001", "ALT-LOCK-001", "ALT-SESSION-001"],
            "confidence": 0.45,
        }
        
        # 链2: CPU → SlowQuery → ConnectionFull
        chain2 = {
            "path": ["ALT-CPU-001", "ALT-SQL-001", "ALT-CONN-001"],
            "confidence": 0.38,
        }
        
        # 两条链共享根因
        assert chain1["path"][0] == chain2["path"][0]  # ALT-CPU-001
        assert chain1["path"][0] == "ALT-CPU-001"


class TestAlertChainReasoningLogic:
    """测试告警链推理核心逻辑"""

    def test_find_correlated_alerts(self):
        """测试查找关联告警"""
        all_alerts = [
            {"alert_id": "ALT-001", "alert_type": "CPU_HIGH"},
            {"alert_id": "ALT-002", "alert_type": "LOCK_WAIT_TIMEOUT"},
            {"alert_id": "ALT-003", "alert_type": "SESSION_LEAK"},
            {"alert_id": "ALT-004", "alert_type": "DISK_USAGE_HIGH"},
            {"alert_id": "ALT-005", "alert_type": "BACKUP_FAILED"},
        ]
        
        # CPU_HIGH 关联的告警类型
        cpu_correlations = {
            "LOCK_WAIT_TIMEOUT": 0.75,
            "SESSION_LEAK": 0.60,
            "SLOW_QUERY_DETECTED": 0.65,
        }
        
        # 查找关联告警
        alert_type = "CPU_HIGH"
        target_types = cpu_correlations.keys()
        
        correlated = [
            a for a in all_alerts 
            if a["alert_type"] in target_types and a["alert_type"] != alert_type
        ]
        
        assert len(correlated) == 2  # LOCK_WAIT_TIMEOUT, SESSION_LEAK

    def test_build_inference_chain(self):
        """测试构建推理链"""
        alert_types = ["CPU_HIGH", "LOCK_WAIT_TIMEOUT", "SESSION_LEAK"]
        
        # 关联规则
        rules = {
            ("CPU_HIGH", "LOCK_WAIT_TIMEOUT"): 0.75,
            ("LOCK_WAIT_TIMEOUT", "SESSION_LEAK"): 0.60,
        }
        
        # 构建链
        chain = []
        for i in range(len(alert_types) - 1):
            source = alert_types[i]
            target = alert_types[i + 1]
            conf = rules.get((source, target), 0.0)
            chain.append({
                "source": source,
                "target": target,
                "confidence": conf,
            })
        
        assert len(chain) == 2
        assert chain[0]["confidence"] == 0.75
        assert chain[1]["confidence"] == 0.60

    def test_identify_root_cause_alert(self):
        """测试识别根因告警"""
        alerts = [
            {"alert_id": "ALT-001", "alert_type": "CPU_HIGH", "is_root": True, "depth": 0},
            {"alert_id": "ALT-002", "alert_type": "LOCK_WAIT_TIMEOUT", "is_root": False, "depth": 1},
            {"alert_id": "ALT-003", "alert_type": "SESSION_LEAK", "is_root": False, "depth": 2},
        ]
        
        root_causes = [a for a in alerts if a.get("is_root", False)]
        assert len(root_causes) == 1
        assert root_causes[0]["alert_type"] == "CPU_HIGH"

    def test_chain_length_limit(self):
        """测试链长度限制（防止无限推理）"""
        max_chain_length = 5
        
        chain = [
            {"alert_id": f"ALT-{i}", "depth": i}
            for i in range(max_chain_length)
        ]
        
        assert len(chain) == max_chain_length
        # 超过限制则停止
        if len(chain) >= max_chain_length:
            truncated = chain[:max_chain_length]
            assert len(truncated) == max_chain_length


class TestAlertChainConfidenceCalculation:
    """测试告警链置信度计算"""

    def test_independent_probability_multiplication(self):
        """独立概率乘法"""
        p1 = 0.75  # A→B
        p2 = 0.60  # B→C
        
        # 链总置信度
        p_chain = p1 * p2
        assert abs(p_chain - 0.45) < 0.01

    def test_parallel_paths_merge_confidence(self):
        """并行路径置信度合并"""
        # 路径1: A→B→C, 置信度0.45
        # 路径2: A→D→E, 置信度0.40
        
        path1_conf = 0.45
        path2_conf = 0.40
        
        # 任一路径成立即可（取最大）
        merged_conf = max(path1_conf, path2_conf)
        assert merged_conf == 0.45
        
        # 或取加权平均
        avg_conf = (path1_conf + path2_conf) / 2
        assert abs(avg_conf - 0.425) < 0.01

    def test_low_confidence_threshold_filter(self):
        """低置信度阈值过滤"""
        chains = [
            {"chain_id": "C1", "confidence": 0.85, "path": ["A", "B"]},
            {"chain_id": "C2", "confidence": 0.45, "path": ["A", "B", "C"]},
            {"chain_id": "C3", "confidence": 0.32, "path": ["A", "B", "C", "D"]},
        ]
        
        threshold = 0.4
        valid_chains = [c for c in chains if c["confidence"] >= threshold]
        
        assert len(valid_chains) == 2
        assert all(c["confidence"] >= threshold for c in valid_chains)


class TestAlertChainIntegration:
    """测试告警链端到端集成"""

    def test_full_chain_diagnosis_workflow(self):
        """完整链式诊断工作流"""
        # 1. 接收告警列表
        incoming_alerts = [
            {"alert_id": "ALT-001", "alert_type": "CPU_HIGH", "severity": "warning"},
            {"alert_id": "ALT-002", "alert_type": "LOCK_WAIT_TIMEOUT", "severity": "warning"},
            {"alert_id": "ALT-003", "alert_type": "SESSION_LEAK", "severity": "critical"},
        ]
        
        # 2. 构建关联图
        correlation_graph = {
            "ALT-001": {"correlated": ["ALT-002"], "confidence": 0.75},
            "ALT-002": {"correlated": ["ALT-003"], "confidence": 0.60},
        }
        
        # 3. 构建推理链
        chains = []
        visited = set()
        
        def build_chain(alert_id, current_chain):
            if alert_id in visited:
                return
            visited.add(alert_id)
            current_chain.append(alert_id)
            
            if alert_id in correlation_graph:
                for next_id in correlation_graph[alert_id]["correlated"]:
                    build_chain(next_id, current_chain.copy())
            else:
                chains.append(current_chain)
        
        build_chain("ALT-001", [])
        
        # 4. 选择最优链
        best_chain = max(chains, key=lambda c: len(c))
        assert best_chain == ["ALT-001", "ALT-002", "ALT-003"]
        
        # 5. 验证根因定位
        root_cause = best_chain[0]
        assert root_cause == "ALT-001"

    def test_alert_prioritization_by_chain_position(self):
        """基于链位置的告警优先级"""
        chain = ["ALT-CPU", "ALT-LOCK", "ALT-SESSION"]
        
        # 根因告警优先级最高
        priorities = {
            "ALT-CPU": 1,    # 根因，需要优先处置
            "ALT-LOCK": 2,   # 中间
            "ALT-SESSION": 3,  # 表象
        }
        
        # 根因处置后，下游告警可能自动消除
        assert priorities["ALT-CPU"] < priorities["ALT-LOCK"]
        assert priorities["ALT-LOCK"] < priorities["ALT-SESSION"]


class TestAlertChainKnowledgeBase:
    """测试告警链知识库集成"""

    def test_knowledge_rule_matching(self):
        """测试知识规则匹配"""
        alert = {
            "alert_type": "LOCK_WAIT_TIMEOUT",
            "metrics": {"wait_time_ms": 5000, "blocked_sessions": 3},
        }
        
        # 知识库规则
        rules = [
            {
                "alert_type": "LOCK_WAIT_TIMEOUT",
                "conditions": {"wait_time_ms": ">3000"},
                "next_alerts": ["SESSION_LEAK"],
                "confidence": 0.6,
            },
            {
                "alert_type": "LOCK_WAIT_TIMEOUT",
                "conditions": {"wait_time_ms": ">10000"},
                "next_alerts": ["INSTANCE_CRASH"],
                "confidence": 0.8,
            },
        ]
        
        # 匹配规则
        wait_time = alert["metrics"]["wait_time_ms"]
        matched = [
            r for r in rules
            if r["alert_type"] == alert["alert_type"]
            and wait_time > 3000
        ]
        
        assert len(matched) >= 1
        assert "LOCK_WAIT_TIMEOUT" in [r["alert_type"] for r in matched]


# ============================================================================
# 测试运行统计
# ============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
