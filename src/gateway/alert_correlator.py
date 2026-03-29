"""告警关联推理引擎
实现告警链式诊断：A告警→B告警→C告警的关联分析
"""
import time
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# ==================== 数据模型 ====================

class AlertRole(Enum):
    """告警在关联链中的角色"""
    ROOT_CAUSE = "root_cause"      # 根因
    SYMPTOM = "symptom"            # 症状
    CONTRIBUTING = "contributing"  # 促成因素
    UNKNOWN = "unknown"


@dataclass
class AlertNode:
    """告警节点"""
    alert_id: str
    alert_name: str
    alert_type: str
    severity: str
    instance_id: str
    instance_name: str
    occurred_at: float
    metric_value: float
    threshold: float
    message: str
    status: str
    
    # 关联分析结果
    role: AlertRole = AlertRole.UNKNOWN
    confidence: float = 0.0
    related_alerts: list[str] = field(default_factory=list)
    
    def __hash__(self):
        return hash(self.alert_id)


@dataclass
class CorrelationLink:
    """关联链路"""
    from_alert: str
    to_alert: str
    link_type: str  # causal/time/instance/symptom
    confidence: float
    reason: str


@dataclass
class CorrelationResult:
    """关联分析结果"""
    primary_alert_id: str
    correlation_chain: list[AlertNode]
    diagnostic_path: list[str]
    root_cause: str
    confidence: float
    links: list[CorrelationLink]
    summary: str


# ==================== 关联规则 ====================

# 因果关联规则：告警类型 -> (导致因素, 引发结果)
CAUSAL_RULES = {
    "CPU_HIGH": {
        "causes": [],  # 没有上游因
        "leads_to": ["SLOW_QUERY", "RESPONSE_SLOW", "SESSION_BLOCK", "DB_HIGH_LOAD"],
    },
    "MEMORY_USAGE_HIGH": {
        "causes": [],
        "leads_to": ["SLOW_QUERY", "DB_HIGH_LOAD", "OOM_KILL"],
    },
    "DISK_USAGE_HIGH": {
        "causes": [],
        "leads_to": ["WRITE_SLOW", "BACKUP_FAILED", "DB_HIGH_LOAD"],
    },
    "DISK_IO_HIGH": {
        "causes": ["DISK_USAGE_HIGH"],
        "leads_to": ["SLOW_QUERY", "RESPONSE_SLOW", "WRITE_SLOW"],
    },
    "SLOW_QUERY": {
        "causes": ["CPU_HIGH", "DISK_IO_HIGH", "LOCK_WAIT", "MEMORY_USAGE_HIGH"],
        "leads_to": ["RESPONSE_SLOW", "USER_COMPLAIN", "SESSION_BLOCK"],
    },
    "LOCK_WAIT": {
        "causes": ["BIG_TRANSACTION", "MISSING_INDEX", "DEADLOCK_RETRY"],
        "leads_to": ["SESSION_BLOCK", "RESPONSE_SLOW", "USER_COMPLAIN"],
    },
    "LOCK_WAIT_TIMEOUT": {
        "causes": ["LOCK_WAIT"],
        "leads_to": ["SESSION_BLOCK", "TRANSACTION_FAIL", "USER_COMPLAIN"],
    },
    "CONNECTION_FULL": {
        "causes": ["SESSION_LEAK", "CONNECTION_SPREE"],
        "leads_to": ["SERVICE_UNAVAILABLE", "NEW_CONNECTION_FAIL"],
    },
    "SESSION_LEAK": {
        "causes": ["APP_BUG", "CONNECTION_NOT_CLOSED"],
        "leads_to": ["CONNECTION_FULL", "MEMORY_USAGE_HIGH"],
    },
    "REPLICATION_LAG": {
        "causes": ["NETWORK_LATENCY", "HEAVY_WRITE", "SLAVE_CATCHUP"],
        "leads_to": ["DATA_INCONSISTENCY", "READ_DELAY"],
    },
    "DB_HIGH_LOAD": {
        "causes": ["CPU_HIGH", "MEMORY_USAGE_HIGH", "DISK_IO_HIGH"],
        "leads_to": ["RESPONSE_SLOW", "SERVICE_UNAVAILABLE"],
    },
    "RESPONSE_SLOW": {
        "causes": ["CPU_HIGH", "SLOW_QUERY", "LOCK_WAIT", "DISK_IO_HIGH"],
        "leads_to": ["USER_COMPLAIN"],
    },
    "USER_COMPLAIN": {
        "causes": ["RESPONSE_SLOW", "SLOW_QUERY", "SERVICE_UNAVAILABLE"],
        "leads_to": [],
    },
    "HEALTH_CHECK_FAIL": {
        "causes": ["DB_HIGH_LOAD", "SERVICE_UNAVAILABLE"],
        "leads_to": ["HA_SWITCH_TRIGGERED"],
    },
    "HA_SWITCH_TRIGGERED": {
        "causes": ["HEALTH_CHECK_FAIL", "MANUAL_TRIGGER"],
        "leads_to": ["SERVICE_INTERRUPTION", "REPLICATION_REBUILD"],
    },
}

# 严重程度排序（数值越高越可能是根因）
SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "warning": 3,
    "info": 2,
}


# ==================== 告警关联引擎 ====================

class AlertCorrelator:
    """告警关联推理引擎"""
    
    def __init__(
        self,
        time_window_seconds: int = 600,  # 10分钟内告警关联
        same_instance_weight: float = 0.3,
        causal_weight: float = 0.5,
        time_proximity_weight: float = 0.2,
    ):
        """
        Args:
            time_window_seconds: 时间窗口，内的告警考虑关联
            same_instance_weight: 同一实例权重
            causal_weight: 因果关联权重
            time_proximity_weight: 时间接近权重
        """
        self.time_window = time_window_seconds
        self.weights = {
            "same_instance": same_instance_weight,
            "causal": causal_weight,
            "time_proximity": time_proximity_weight,
        }
    
    async def correlate_alerts(
        self,
        primary_alert_id: str,
        all_alerts: list[dict],
        mock_client=None,
    ) -> CorrelationResult:
        """
        关联分析一组告警
        
        Args:
            primary_alert_id: 主要告警ID
            all_alerts: 所有告警列表
            mock_client: Mock Javis客户端（可选）
        
        Returns:
            CorrelationResult: 关联分析结果
        """
        # 1. 转换为AlertNode
        alert_nodes = {}
        for alert in all_alerts:
            node = self._create_alert_node(alert)
            alert_nodes[node.alert_id] = node
        
        # 边界用例处理：如果primary_alert不在列表中，创建占位节点
        if primary_alert_id not in alert_nodes:
            # 创建占位节点用于边界场景
            placeholder_node = AlertNode(
                alert_id=primary_alert_id,
                alert_name=f"告警 {primary_alert_id}",
                alert_type="UNKNOWN",
                severity="unknown",
                instance_id="unknown",
                instance_name="未知实例",
                occurred_at=time.time(),
                metric_value=0,
                threshold=0,
                message=f"告警 {primary_alert_id} 未在告警列表中找到",
                status="unknown",
                role=AlertRole.UNKNOWN,
                confidence=0.0,
            )
            alert_nodes[primary_alert_id] = placeholder_node
        
        # 2. 构建关联图
        links = self._build_correlation_graph(
            primary_alert_id,
            alert_nodes,
            self._get_alert_detail if mock_client else None,
            mock_client,
        )
        
        # 3. 分析因果链
        chain = self._analyze_causal_chain(
            primary_alert_id,
            alert_nodes,
            links,
        )
        
        # 4. 生成诊断路径
        diagnostic_path = self._generate_diagnostic_path(chain)
        
        # 5. 确定根因
        root_cause_node = next(
            (n for n in chain if n.role == AlertRole.ROOT_CAUSE),
            chain[0] if chain else None,
        )
        root_cause = root_cause_node.alert_name if root_cause_node else "Unknown"
        confidence = self._calculate_overall_confidence(chain, links)
        
        # 6. 生成摘要
        summary = self._generate_summary(primary_alert_id, chain, root_cause)
        
        return CorrelationResult(
            primary_alert_id=primary_alert_id,
            correlation_chain=chain,
            diagnostic_path=diagnostic_path,
            root_cause=root_cause,
            confidence=confidence,
            links=links,
            summary=summary,
        )
    
    def _create_alert_node(self, alert: dict) -> AlertNode:
        """从字典创建AlertNode"""
        return AlertNode(
            alert_id=alert["alert_id"],
            alert_name=alert.get("alert_name", alert["alert_type"]),
            alert_type=alert["alert_type"],
            severity=alert["severity"],
            instance_id=alert["instance_id"],
            instance_name=alert.get("instance_name", ""),
            occurred_at=alert.get("occurred_at", time.time()),
            metric_value=alert.get("metric_value", 0),
            threshold=alert.get("threshold", 0),
            message=alert.get("message", f"{alert['alert_type']}告警"),
            status=alert.get("status", "unknown"),
        )
    
    async def _get_alert_detail(self, alert_id: str, mock_client) -> Optional[dict]:
        """获取告警详情"""
        try:
            return await mock_client.get_alert_detail(alert_id)
        except Exception:
            return None
    
    def _build_correlation_graph(
        self,
        primary_alert_id: str,
        alert_nodes: dict[str, AlertNode],
        get_detail_func=None,
        mock_client=None,
    ) -> list[CorrelationLink]:
        """构建告警关联图"""
        links = []
        primary_node = alert_nodes[primary_alert_id]
        
        for alert_id, node in alert_nodes.items():
            if alert_id == primary_alert_id:
                continue
            
            # 计算关联度
            correlation = self._calculate_correlation(
                primary_node, node, get_detail_func, mock_client
            )
            
            if correlation["score"] > 0.3:  # 阈值
                link = CorrelationLink(
                    from_alert=correlation["source"],
                    to_alert=correlation["target"],
                    link_type=correlation["type"],
                    confidence=correlation["score"],
                    reason=correlation["reason"],
                )
                links.append(link)
                
                # 更新节点的关联告警列表
                alert_nodes[correlation["source"]].related_alerts.append(correlation["target"])
        
        return links
    
    def _calculate_correlation(
        self,
        alert1: AlertNode,
        alert2: AlertNode,
        get_detail_func=None,
        mock_client=None,
    ) -> dict:
        """计算两个告警之间的关联度"""
        score = 0.0
        reasons = []
        link_type = "unknown"
        
        # 1. 同一实例关联 (权重: same_instance)
        if alert1.instance_id == alert2.instance_id:
            score += self.weights["same_instance"]
            reasons.append(f"同一实例 {alert1.instance_name}")
            link_type = "instance"
        
        # 2. 因果关联 (权重: causal)
        causal_result = self._check_causal_relation(alert1, alert2)
        if causal_result["is_related"]:
            score += self.weights["causal"] * causal_result["confidence"]
            reasons.append(causal_result["reason"])
            link_type = "causal"
        
        # 3. 时间接近关联 (权重: time_proximity)
        time_diff = abs(alert1.occurred_at - alert2.occurred_at)
        if time_diff < self.time_window:
            time_score = self.weights["time_proximity"] * (1 - time_diff / self.time_window)
            score += time_score
            if time_score > 0.05:
                reasons.append(f"时间接近 ({int(time_diff)}秒内)")
                if link_type == "unknown":
                    link_type = "time"
        
        # 4. 类型相似关联
        if alert1.alert_type == alert2.alert_type:
            score += 0.1
            reasons.append(f"相同类型 {alert1.alert_type}")
        
        # 确定source和target（更严重的在前）
        if SEVERITY_RANK.get(alert1.severity, 0) >= SEVERITY_RANK.get(alert2.severity, 0):
            source, target = alert1.alert_id, alert2.alert_id
        else:
            source, target = alert2.alert_id, alert1.alert_id
        
        return {
            "source": source,
            "target": target,
            "score": min(score, 1.0),
            "type": link_type,
            "reason": "; ".join(reasons) if reasons else "弱关联",
        }
    
    def _check_causal_relation(
        self,
        alert1: AlertNode,
        alert2: AlertNode,
    ) -> dict:
        """检查两个告警是否存在因果关系"""
        # 检查 alert1 是否导致 alert2
        type1_rules = CAUSAL_RULES.get(alert1.alert_type, {})
        leads_to = type1_rules.get("leads_to", [])
        
        if alert2.alert_type in leads_to:
            return {
                "is_related": True,
                "direction": "alert1_causes_alert2",
                "confidence": 0.9,
                "reason": f"{alert1.alert_type} 可能导致 {alert2.alert_type}",
            }
        
        # 检查 alert2 是否导致 alert1
        type2_rules = CAUSAL_RULES.get(alert2.alert_type, {})
        leads_to2 = type2_rules.get("leads_to", [])
        
        if alert1.alert_type in leads_to2:
            return {
                "is_related": True,
                "direction": "alert2_causes_alert1",
                "confidence": 0.9,
                "reason": f"{alert2.alert_type} 可能导致 {alert1.alert_type}",
            }
        
        return {"is_related": False, "confidence": 0.0, "reason": ""}
    
    def _analyze_causal_chain(
        self,
        primary_alert_id: str,
        alert_nodes: dict[str, AlertNode],
        links: list[CorrelationLink],
    ) -> list[AlertNode]:
        """分析因果链，确定每个告警的角色"""
        chain = []
        visited = set()
        
        # BFS遍历关联链
        queue = [primary_alert_id]
        while queue:
            alert_id = queue.pop(0)
            if alert_id in visited:
                continue
            visited.add(alert_id)
            
            node = alert_nodes[alert_id]
            
            # 确定角色
            self._assign_role(node, links, alert_nodes)
            
            chain.append(node)
            
            # 添加关联告警到队列
            for link in links:
                if link.from_alert == alert_id and link.to_alert not in visited:
                    queue.append(link.to_alert)
                elif link.to_alert == alert_id and link.from_alert not in visited:
                    queue.append(link.from_alert)
        
        # 按因果顺序排序（根因在前）
        return self._sort_by_causal_order(chain, links)
    
    def _assign_role(
        self,
        node: AlertNode,
        links: list[CorrelationLink],
        all_nodes: dict[str, AlertNode],
    ):
        """为告警节点分配角色"""
        # 查找作为target的链接（别人导致的）
        caused_by = [l for l in links if l.to_alert == node.alert_id]
        causes = [l for l in links if l.from_alert == node.alert_id]
        
        # 没有上游，也没有下游 -> 可能是根因
        if not caused_by and not causes:
            node.role = AlertRole.UNKNOWN
            node.confidence = 0.5
        elif not caused_by:
            node.role = AlertRole.ROOT_CAUSE
            node.confidence = 0.9
        elif not causes:
            node.role = AlertRole.SYMPTOM
            node.confidence = 0.7
        else:
            # 既有上游又有下游 -> 促成因素
            node.role = AlertRole.CONTRIBUTING
            node.confidence = 0.6
    
    def _sort_by_causal_order(
        self,
        chain: list[AlertNode],
        links: list[CorrelationLink],
    ) -> list[AlertNode]:
        """按因果顺序排序"""
        # 构建出度映射
        out_degree = {}
        for node in chain:
            out_degree[node.alert_id] = sum(
                1 for l in links if l.from_alert == node.alert_id
            )
        
        # 按严重程度和出度排序
        def sort_key(n: AlertNode):
            severity_rank = SEVERITY_RANK.get(n.severity, 0)
            return (-severity_rank, -out_degree.get(n.alert_id, 0))
        
        return sorted(chain, key=sort_key)
    
    def _generate_diagnostic_path(self, chain: list[AlertNode]) -> list[str]:
        """生成诊断路径"""
        # 按因果顺序生成路径
        path = []
        for node in chain:
            if node.role == AlertRole.ROOT_CAUSE:
                path.insert(0, node.alert_id)  # 根因放最前
            elif node.role == AlertRole.SYMPTOM:
                path.append(node.alert_id)  # 症状放最后
            else:
                # 插入到合适位置
                insert_pos = len(path) - 1
                for i, pid in enumerate(path):
                    if chain[i].role == AlertRole.ROOT_CAUSE:
                        insert_pos = i + 1
                path.insert(insert_pos, node.alert_id)
        
        return path if path else [chain[0].alert_id] if chain else []
    
    def _calculate_overall_confidence(
        self,
        chain: list[AlertNode],
        links: list[CorrelationLink],
    ) -> float:
        """计算整体置信度"""
        if not chain:
            return 0.0
        
        # 节点置信度平均
        node_confidence = sum(n.confidence for n in chain) / len(chain)
        
        # 链路置信度
        if links:
            link_confidence = sum(l.confidence for l in links) / len(links)
        else:
            link_confidence = 0.5
        
        # 加权平均
        return round(node_confidence * 0.6 + link_confidence * 0.4, 2)
    
    def _generate_summary(
        self,
        primary_alert_id: str,
        chain: list[AlertNode],
        root_cause: str,
    ) -> str:
        """生成关联分析摘要"""
        if not chain:
            return f"告警 {primary_alert_id} 无关联告警"
        
        root_causes = [n for n in chain if n.role == AlertRole.ROOT_CAUSE]
        symptoms = [n for n in chain if n.role == AlertRole.SYMPTOM]
        
        summary_parts = []
        
        if root_causes:
            rc_names = ", ".join(n.alert_name for n in root_causes)
            summary_parts.append(f"根因：{rc_names}")
        
        if symptoms:
            symptom_names = ", ".join(n.alert_name for n in symptoms)
            summary_parts.append(f"症状：{symptom_names}")
        
        if len(chain) > 1:
            summary_parts.append(f"共发现 {len(chain)} 个关联告警")
        
        return " | ".join(summary_parts) if summary_parts else f"告警 {primary_alert_id} 正在分析中"


# ==================== Mock Javis-DB-Agent 告警关联客户端 ====================

class MockAlertCorrelator(AlertCorrelator):
    """Mock环境的告警关联器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_alerts_cache = {}
    
    async def get_related_alerts(
        self,
        alert_id: str,
        mock_client,
        instance_id: str = None,
        time_range_seconds: int = 600,
    ) -> list[dict]:
        """
        获取与指定告警关联的其他告警
        
        Args:
            alert_id: 告警ID
            mock_client: Mock Javis客户端
            instance_id: 实例ID（可选，用于过滤）
            time_range_seconds: 时间范围（秒）
        
        Returns:
            关联告警列表
        """
        # 获取该实例的所有告警
        alerts = await mock_client.get_alerts(
            instance_id=instance_id,
            status="active",
        )
        
        if not alerts:
            return []
        
        # 执行关联分析
        result = await self.correlate_alerts(alert_id, alerts, mock_client)
        
        # 返回关联链中的其他告警
        related = []
        for node in result.correlation_chain:
            if node.alert_id != alert_id:
                related.append({
                    "alert_id": node.alert_id,
                    "alert_name": node.alert_name,
                    "role": node.role.value,
                    "confidence": node.confidence,
                    "reason": next(
                        (l.reason for l in result.links 
                         if l.from_alert == alert_id and l.to_alert == node.alert_id),
                        ""
                    ),
                })
        
        return related


# ==================== 单例 ====================

_alert_correlator: Optional[AlertCorrelator] = None
_mock_correlator: Optional[MockAlertCorrelator] = None


def get_alert_correlator() -> AlertCorrelator:
    """获取告警关联器单例"""
    global _alert_correlator
    if _alert_correlator is None:
        _alert_correlator = AlertCorrelator()
    return _alert_correlator


def get_mock_alert_correlator() -> MockAlertCorrelator:
    """获取Mock告警关联器单例"""
    global _mock_correlator
    if _mock_correlator is None:
        _mock_correlator = MockAlertCorrelator()
    return _mock_correlator
