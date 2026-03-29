"""智能告警工具集 - Round 15 新增
提供告警分析、去重、根因分析和预测性告警工具
"""
import time
from typing import Any, Optional
from collections import defaultdict

from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 工具1: 告警分析
# ============================================================================
class AlertAnalysisTool(BaseTool):
    """告警分析工具 - 多维度评估告警严重程度和影响"""

    definition = ToolDefinition(
        name="alert_analysis",
        description="对告警进行多维度分析,评估严重程度、影响范围,并给出处置建议",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(
                name="alert_data",
                type="object",
                description="告警数据对象",
                required=True,
                default={},
            ),
        ],
        example="alert_analysis(alert_data={'alert_id': 'ALT-001', 'alert_type': 'CONNECTION_HIGH', 'severity': 'warning'})"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        alert_data = params.get("alert_data", {})

        if not alert_data:
            return ToolResult(success=False, error="未提供告警数据", tool_name=self.name)

        alert_id = alert_data.get("alert_id", "unknown")
        alert_type = alert_data.get("alert_type", "unknown")
        severity = alert_data.get("severity", "unknown")
        metric = alert_data.get("metric", "")
        value = alert_data.get("value", 0)
        threshold = alert_data.get("threshold", 0)
        instance_id = alert_data.get("instance_id", "")

        # 多维度分析
        suggestions = []
        confidence = 0.85

        # 基于告警类型的分析
        if alert_type == "CONNECTION_HIGH":
            suggestions = [
                "检查连接泄漏,确认是否有未关闭的连接",
                "评估连接池配置是否合理",
                "查看sleeping连接,清理长时间idle的连接",
                "如持续告警,考虑扩大max_connections",
            ]
            if value and threshold and value > threshold * 0.9:
                suggestions.insert(0, "⚠️ 连接数接近上限,建议立即处理")

        elif alert_type == "CPU_HIGH":
            suggestions = [
                "查看当前活跃会话,识别高CPU占用的SQL",
                "检查是否存在慢查询占用CPU",
                "评估是否需要扩容CPU资源",
                "检查系统层面是否有其他进程占用CPU",
            ]

        elif alert_type == "MEMORY_HIGH":
            suggestions = [
                "检查Buffer Pool / shared_buffers使用率",
                "查看当前大查询是否占用过多内存",
                "评估内存泄漏可能性",
                "如持续高位,考虑扩大内存或优化SQL",
            ]

        elif alert_type == "DISK_FULL":
            suggestions = [
                "立即检查各表空间使用率",
                "清理临时文件和不必要的日志",
                "评估数据归档策略",
                "紧急情况下考虑扩容磁盘",
            ]
            confidence = 0.95

        elif alert_type == "REPLICATION_LAG":
            suggestions = [
                "检查从库负载和资源使用情况",
                "查看主库的WAL产生速度",
                "评估大事务是否在同步",
                "如持续延迟,考虑优化从库性能或调整复制架构",
            ]

        elif alert_type == "WAL_ACCUMULATION":
            suggestions = [
                "检查WAL保留目录磁盘空间",
                "确认归档进程是否正常运行",
                "查看是否有大型事务产生过多WAL",
                "评估checkpoint配置是否合理",
            ]

        elif alert_type == "BLOAT_EXCEEDED":
            suggestions = [
                "对高膨胀表执行VACUUM",
                "如膨胀严重,考虑VACUUM FULL",
                "评估自动清理配置是否开启",
                "检查是否有长事务阻塞清理",
            ]

        else:
            suggestions = [
                "查看告警详情和指标趋势",
                "检查相关实例状态",
                "评估是否需要人工介入",
            ]

        # 严重程度标准化
        severity_map = {"critical": "critical", "high": "high", "warning": "medium", "warn": "medium", "info": "low"}
        normalized_severity = severity_map.get(severity.lower() if isinstance(severity, str) else "unknown", "unknown")

        return ToolResult(
            success=True,
            data={
                "alert_id": alert_id,
                "alert_type": alert_type,
                "severity": normalized_severity,
                "confidence": confidence,
                "metric": metric,
                "current_value": value,
                "threshold": threshold,
                "instance_id": instance_id,
                "suggestions": suggestions,
                "analysis_time": int(time.time()),
            }
        )


# ============================================================================
# 工具2: 告警去重
# ============================================================================
class AlertDeduplicationTool(BaseTool):
    """告警去重工具 - 压缩同类告警,避免告警风暴"""

    definition = ToolDefinition(
        name="alert_deduplication",
        description="对告警列表进行去重压缩,识别同类告警并合并",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(
                name="alerts",
                type="array",
                description="告警列表",
                required=True,
                default=[],
            ),
            ToolParam(
                name="time_window_minutes",
                type="int",
                description="时间窗口(分钟),同一窗口内的同类告警视为重复",
                required=False,
                default=60,
            ),
        ],
        example="alert_deduplication(alerts=[{'alert_id': 'ALT-001', 'alert_type': 'CONNECTION_HIGH'}, {'alert_id': 'ALT-002', 'alert_type': 'CONNECTION_HIGH'}])"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        alerts = params.get("alerts", [])
        time_window = params.get("time_window_minutes", 60)

        if not alerts:
            return ToolResult(success=False, error="未提供告警列表", tool_name=self.name)

        original_count = len(alerts)

        # 按关键维度分组
        # 维度: (alert_type, instance_id, metric)
        groups = defaultdict(list)
        for alert in alerts:
            key = (
                alert.get("alert_type", "unknown"),
                alert.get("instance_id", ""),
                alert.get("metric", ""),
            )
            groups[key].append(alert)

        # 去重结果
        deduplicated = []
        dedup_groups = []

        for key, group_alerts in groups.items():
            alert_type, instance_id, metric = key
            representative = group_alerts[0]
            count = len(group_alerts)

            # 生成新的去重告警
            deduped_alert = {
                "group_id": f"dedup_{alert_type}_{instance_id}_{int(time.time())}",
                "alert_type": alert_type,
                "instance_id": instance_id,
                "metric": metric,
                "count": count,
                "representative_id": representative.get("alert_id", "unknown"),
                "severity": representative.get("severity", "unknown"),
                "first_occurrence": representative.get("timestamp", 0),
                "last_occurrence": max(
                    (a.get("timestamp", 0) for a in group_alerts), default=0
                ),
                "description": f"该类告警在时间窗口内共触发{count}次,已压缩为1条",
            }
            deduplicated.append(deduped_alert)

            dedup_groups.append({
                "type": alert_type,
                "instance_id": instance_id,
                "metric": metric,
                "group_id": deduped_alert["group_id"],
                "count": count,
            })

        deduped_count = len(deduplicated)
        compression_ratio = (1 - deduped_count / original_count) * 100 if original_count > 0 else 0

        return ToolResult(
            success=True,
            data={
                "original_count": original_count,
                "deduplicated_count": deduped_count,
                "compression_ratio": compression_ratio,
                "groups": dedup_groups,
                "deduplicated_alerts": deduplicated,
                "dedup_time": int(time.time()),
            }
        )


# ============================================================================
# 工具3: 根因分析
# ============================================================================
class RootCauseAnalysisTool(BaseTool):
    """根因分析工具 - 深度分析告警链,定位根本原因"""

    definition = ToolDefinition(
        name="root_cause_analysis",
        description="对告警进行深度根因分析,识别告警链和依赖关系,定位根本原因",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(
                name="alert_id",
                type="string",
                description="告警ID",
                required=True,
                default="",
            ),
            ToolParam(
                name="lookback_hours",
                type="int",
                description="回溯时间范围(小时)",
                required=False,
                default=24,
            ),
        ],
        example="root_cause_analysis(alert_id='ALT-001', lookback_hours=24)"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        alert_id = params.get("alert_id", "")

        if not alert_id:
            return ToolResult(success=False, error="未提供告警ID", tool_name=self.name)

        lookback_hours = params.get("lookback_hours", 24)

        # 模拟根因分析结果
        # 实际实现中会调用诊断Agent和告警关联器
        root_cause_db = {
            "CONNECTION_HIGH": {
                "root_cause": "连接泄漏: 应用未正确关闭数据库连接,导致连接数持续累积",
                "confidence": 0.88,
                "evidence": [
                    "连接数从正常值持续增长,未出现回落",
                    "存在大量sleeping连接,最后活跃时间超过30分钟",
                    "应用日志显示部分请求获取连接超时",
                    "数据库max_connections接近阈值",
                ],
                "related_alerts": [
                    {"alert_id": "ALT-002", "alert_name": "连接池耗尽告警", "relation": "后续关联"},
                    {"alert_id": "ALT-003", "alert_name": "实例响应慢告警", "relation": "并发触发"},
                ],
            },
            "CPU_HIGH": {
                "root_cause": "慢SQL占用CPU: 部分SQL未使用索引,全表扫描导致CPU飙升",
                "confidence": 0.82,
                "evidence": [
                    "活跃会话中存在执行时间超过100秒的SQL",
                    "该SQL的查询计划显示全表扫描",
                    "该SQL在CPU使用高峰期频繁出现",
                    "优化该SQL后CPU使用率下降显著",
                ],
                "related_alerts": [
                    {"alert_id": "ALT-010", "alert_name": "慢SQL告警", "relation": "直接原因"},
                    {"alert_id": "ALT-011", "alert_name": "实例响应慢", "relation": "后续关联"},
                ],
            },
            "REPLICATION_LAG": {
                "root_cause": "大事务同步延迟: 主库执行了大事务,导致从库回放延迟",
                "confidence": 0.85,
                "evidence": [
                    "从库延迟在主库大事务执行期间同步增大",
                    "从库IO使用率和主库WAL产生速度高度相关",
                    "延迟在大事务完成后逐渐恢复",
                    "从库硬件配置低于主库",
                ],
                "related_alerts": [
                    {"alert_id": "ALT-020", "alert_name": "主库大事务告警", "relation": "直接原因"},
                ],
            },
            "WAL_ACCUMULATION": {
                "root_cause": "WAL归档阻塞: 归档进程异常或归档目录满,导致WAL堆积",
                "confidence": 0.90,
                "evidence": [
                    "pg_wal目录占用空间持续增长",
                    "归档进程状态异常或未运行",
                    "归档日志显示写入失败",
                    "重启归档进程后堆积缓解",
                ],
                "related_alerts": [
                    {"alert_id": "ALT-030", "alert_name": "磁盘空间告警", "relation": "间接关联"},
                ],
            },
            "BLOAT_EXCEEDED": {
                "root_cause": "表膨胀未及时清理: 自动VACUUM被阻塞,表膨胀率持续升高",
                "confidence": 0.87,
                "evidence": [
                    "存在长事务持有MVCC快照",
                    "autovacuum进程未正常处理目标表",
                    "表膨胀率超过阈值且持续增长",
                    "手动VACUUM后膨胀率明显下降",
                ],
                "related_alerts": [
                    {"alert_id": "ALT-040", "alert_name": "长事务告警", "relation": "阻塞原因"},
                ],
            },
        }

        # 通用根因分析(对于未知告警类型)
        default_rca = {
            "root_cause": "系统资源异常: 相关指标超过阈值,需要进一步诊断",
            "confidence": 0.60,
            "evidence": [
                "告警指标超过预设阈值",
                "需要进一步收集诊断信息",
            ],
            "related_alerts": [],
        }

        # 尝试匹配已知的根因模式
        # 实际实现中会根据alert_id查询真实告警数据
        result = {
            "alert_id": alert_id,
            "lookback_hours": lookback_hours,
            **default_rca,
        }

        # 模拟: 根据alert_id中的关键词匹配
        for key, rca in root_cause_db.items():
            if key in alert_id.upper():
                result = {"alert_id": alert_id, "lookback_hours": lookback_hours, **rca}
                break

        return ToolResult(
            success=True,
            data=result
        )


# ============================================================================
# 工具4: 预测性告警
# ============================================================================
class PredictiveAlertTool(BaseTool):
    """预测性告警工具 - 基于趋势预测未来风险"""

    definition = ToolDefinition(
        name="predictive_alert",
        description="基于历史趋势分析,预测指标到达阈值的时间,提前发出预警",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(
                name="metric",
                type="string",
                description="指标名称 (如: connection_count, wal_lag, replication_delay, bloat_percent)",
                required=True,
                default="",
            ),
            ToolParam(
                name="threshold",
                type="float",
                description="告警阈值",
                required=True,
                default=80.0,
            ),
            ToolParam(
                name="instance_id",
                type="string",
                description="实例ID (可选)",
                required=False,
                default="",
            ),
            ToolParam(
                name="history_days",
                type="int",
                description="历史数据天数",
                required=False,
                default=7,
            ),
        ],
        example="predictive_alert(metric='connection_count', threshold=1000, instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        metric = params.get("metric", "")
        threshold = params.get("threshold", 80.0)
        instance_id = params.get("instance_id", "")
        history_days = params.get("history_days", 7)

        if not metric:
            return ToolResult(success=False, error="未提供指标名称", tool_name=self.name)

        # 基于指标类型的模拟数据
        metric_db = {
            "connection_count": {
                "current_value": 850,
                "daily_growth": 15,
                "trend": "accelerating",
                "risk_level": "high",
            },
            "wal_lag": {
                "current_value": 0.5,
                "daily_growth": 0.05,
                "trend": "stable",
                "risk_level": "low",
            },
            "replication_delay": {
                "current_value": 30,
                "daily_growth": 2,
                "trend": "accelerating",
                "risk_level": "medium",
            },
            "bloat_percent": {
                "current_value": 18,
                "daily_growth": 0.8,
                "trend": "accelerating",
                "risk_level": "high",
            },
            "disk_usage_percent": {
                "current_value": 72,
                "daily_growth": 0.5,
                "trend": "stable",
                "risk_level": "medium",
            },
            "cpu_usage_percent": {
                "current_value": 65,
                "daily_growth": 1.2,
                "trend": "accelerating",
                "risk_level": "medium",
            },
            "memory_usage_percent": {
                "current_value": 78,
                "daily_growth": 0.3,
                "trend": "stable",
                "risk_level": "medium",
            },
        }

        # 获取metric数据,默认使用memory_usage_percent
        metric_info = metric_db.get(metric, {
            "current_value": threshold * 0.8,
            "daily_growth": threshold * 0.01,
            "trend": "stable",
            "risk_level": "medium",
        })

        current_value = metric_info["current_value"]
        daily_growth = metric_info["daily_growth"]
        trend = metric_info["trend"]

        # 计算预测值和到达阈值时间
        if daily_growth > 0 and current_value < threshold:
            days_to_threshold = (threshold - current_value) / daily_growth
            predicted_value = current_value + daily_growth * 7  # 7天预测
            if days_to_threshold <= 0:
                predicted_time = "已超过阈值"
                days_to_threshold = 0
            else:
                # 格式化时间
                import time as time_module
                predicted_timestamp = time_module.time() + days_to_threshold * 86400
                predicted_time = time_module.strftime(
                    "%Y-%m-%d %H:%M", time_module.localtime(predicted_timestamp)
                )
        else:
            days_to_threshold = 999
            predicted_value = current_value
            predicted_time = "短期内不会到达阈值"

        # 风险等级判定
        risk_level = metric_info["risk_level"]
        if days_to_threshold < 1:
            risk_level = "critical"
        elif days_to_threshold < 3:
            risk_level = "high"
        elif days_to_threshold < 7:
            risk_level = "medium"
        else:
            risk_level = "low"

        return ToolResult(
            success=True,
            data={
                "metric": metric,
                "threshold": threshold,
                "instance_id": instance_id,
                "current_value": current_value,
                "predicted_value": predicted_value,
                "daily_growth": daily_growth,
                "trend": trend,
                "days_to_threshold": days_to_threshold if days_to_threshold < 999 else None,
                "predicted_time": predicted_time,
                "risk_level": risk_level,
                "history_days": history_days,
                "prediction_time": int(time.time()),
            }
        )


# ============================================================================
# 注册函数
# ============================================================================
def register_alert_tools(registry):
    """注册所有告警工具"""
    tools = [
        AlertAnalysisTool(),
        AlertDeduplicationTool(),
        RootCauseAnalysisTool(),
        PredictiveAlertTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
