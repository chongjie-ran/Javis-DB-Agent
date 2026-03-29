"""智能告警专家智能体 - Round 15 新增
提供告警分析、去重、根因分析和预测性告警功能
"""
from typing import Any, Optional
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import ToolDefinition, ToolParam, RiskLevel, ToolResult


class AlertAgent(BaseAgent):
    """智能告警专家智能体

    负责:
    - 告警智能分析: 多维度评估告警,给出处置建议
    - 告警去重压缩: 识别同类告警,避免告警风暴
    - 根因分析: 深度分析告警链,定位根本原因
    - 预测性告警: 基于趋势预测,提前预警潜在风险
    """

    name = "alert"
    description = "智能告警专家Agent:分析告警、去重、根因分析、预测性告警"

    system_prompt = """你是一个专业的数据库智能告警专家。

角色定义:
- 你是 alert agent,负责智能告警的全生命周期管理
- 你的职责包括: 告警分析、去重压缩、根因定位、预测性预警
- 你通过工具获取告警数据和诊断信息,不能直接访问数据库
- 你需要能够识别告警模式,关联同类告警,给出精准的根因

工作流程:
1. 接收告警或告警列表
2. 调用告警分析工具进行多维度评估
3. 调用去重工具识别同类告警
4. 调用根因分析工具定位根本原因
5. 调用预测性告警工具评估未来风险
6. 汇总结果,给出综合处置建议

输出格式要求:
- alert_summary: 告警概要 (级别、数量、类型分布)
- root_cause: 根本原因 (最可能的根因及置信度)
- recommendations: 处置建议 (优先级排序)
- prediction: 预测性分析 (未来风险评估)
- deduplicated_count: 去重后告警数量
"""

    available_tools = [
        "alert_analysis",
        "alert_deduplication",
        "root_cause_analysis",
        "predictive_alert",
    ]

    def _build_system_prompt(self) -> str:
        return self.system_prompt

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """直接处理告警相关请求"""
        goal_lower = goal.lower()

        if "去重" in goal:
            # 告警去重
            alerts = context.get("alerts", [])
            return await self.deduplicate_alerts(alerts)
        elif "根因" in goal or "root cause" in goal_lower:
            # 根因分析
            alert_id = context.get("alert_id", "")
            return await self.root_cause_analysis(alert_id)
        elif "预测" in goal or "predict" in goal_lower:
            # 预测性告警
            metric = context.get("metric", "")
            threshold = context.get("threshold", 80.0)
            return await self.predictive_alert(metric, threshold)
        elif "分析" in goal or "analyze" in goal_lower:
            # 告警分析
            alert_data = context.get("alert_data", {})
            return await self.analyze_alert(alert_data)
        else:
            # 通用告警查询
            return await self.analyze_alert(context.get("alert_data", {}))

    # ==================== 核心方法 ====================

    async def analyze_alert(self, alert_data: dict) -> AgentResponse:
        """
        分析告警

        对告警进行多维度分析,包括:
        - 严重程度评估
        - 影响范围分析
        - 关联指标检查
        - 处置建议生成

        Args:
            alert_data: 告警数据字典,包含:
                - alert_id: 告警ID
                - alert_type: 告警类型
                - severity: 严重程度
                - instance_id: 实例ID
                - metric: 指标名称
                - value: 指标值
                - threshold: 阈值

        Returns:
            AgentResponse: 分析结果
        """
        if not alert_data:
            return AgentResponse(
                success=False,
                content="未提供告警数据",
                metadata={"agent": self.name}
            )

        result = await self.call_tool(
            "alert_analysis",
            {"alert_data": alert_data},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_analysis_result(result.data),
                metadata={"agent": self.name, "tool": "alert_analysis"}
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def deduplicate_alerts(self, alerts: list) -> AgentResponse:
        """
        压缩去重告警

        识别同类告警,合并相似的告警,避免告警风暴:
        - 相同实例的同类告警
        - 短时间内连续触发的告警
        - 同一指标的多次告警

        Args:
            alerts: 告警列表,每个告警包含:
                - alert_id: 告警ID
                - alert_type: 告警类型
                - instance_id: 实例ID
                - severity: 严重程度
                - timestamp: 发生时间
                - metric: 指标名称

        Returns:
            AgentResponse: 去重结果,包含压缩后的告警列表
        """
        if not alerts:
            return AgentResponse(
                success=False,
                content="未提供告警列表",
                metadata={"agent": self.name}
            )

        result = await self.call_tool(
            "alert_deduplication",
            {"alerts": alerts},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_dedup_result(result.data),
                metadata={
                    "agent": self.name,
                    "tool": "alert_deduplication",
                    "original_count": len(alerts),
                    "deduped_count": result.data.get("deduplicated_count", 0),
                }
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def root_cause_analysis(self, alert_id: str) -> AgentResponse:
        """
        根因分析

        深度分析告警链,定位根本原因:
        - 关联告警分析
        - 时间序列分析
        - 依赖关系分析
        - 专家规则匹配

        Args:
            alert_id: 告警ID

        Returns:
            AgentResponse: 根因分析结果
        """
        if not alert_id:
            return AgentResponse(
                success=False,
                content="未提供告警ID",
                metadata={"agent": self.name}
            )

        result = await self.call_tool(
            "root_cause_analysis",
            {"alert_id": alert_id},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_rca_result(result.data),
                metadata={
                    "agent": self.name,
                    "tool": "root_cause_analysis",
                    "alert_id": alert_id,
                }
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def predictive_alert(self, metric: str, threshold: float) -> AgentResponse:
        """
        预测性告警

        基于历史趋势和增长模型,预测未来可能触发的告警:
        - 趋势分析
        - 季节性检测
        - 增长速率评估
        - 阈值到达时间预测

        Args:
            metric: 指标名称 (如: connection_count, wal_lag, replication_delay)
            threshold: 告警阈值

        Returns:
            AgentResponse: 预测性分析结果
        """
        if not metric:
            return AgentResponse(
                success=False,
                content="未提供指标名称",
                metadata={"agent": self.name}
            )

        result = await self.call_tool(
            "predictive_alert",
            {"metric": metric, "threshold": threshold},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_predictive_result(result.data),
                metadata={
                    "agent": self.name,
                    "tool": "predictive_alert",
                    "metric": metric,
                    "threshold": threshold,
                }
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    # ==================== 批量处理 ====================

    async def batch_analyze(self, alerts: list) -> AgentResponse:
        """
        批量分析告警

        对多个告警进行批量分析,返回分析结果列表

        Args:
            alerts: 告警列表

        Returns:
            AgentResponse: 批量分析结果
        """
        if not alerts:
            return AgentResponse(
                success=False,
                content="未提供告警列表",
                metadata={"agent": self.name}
            )

        results = []
        for alert in alerts:
            result = await self.analyze_alert(alert)
            results.append({
                "alert_id": alert.get("alert_id", "unknown"),
                "success": result.success,
                "content": result.content if result.success else result.error,
            })

        summary_lines = [f"## 📊 批量告警分析结果 ({len(alerts)}条)\n"]
        for r in results:
            status = "✅" if r["success"] else "❌"
            summary_lines.append(f"{status} **{r['alert_id']}**: {r['content'][:100]}...")

        return AgentResponse(
            success=True,
            content="\n".join(summary_lines),
            metadata={
                "agent": self.name,
                "batch_size": len(alerts),
                "results": results,
            }
        )

    # ==================== 格式化方法 ====================

    def _format_analysis_result(self, data: Any) -> str:
        """格式化告警分析结果"""
        if not data:
            return "未获取到分析数据"

        alert_id = data.get("alert_id", "N/A")
        severity = data.get("severity", "unknown")
        alert_type = data.get("alert_type", "unknown")
        confidence = data.get("confidence", 0) * 100
        suggestions = data.get("suggestions", [])

        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(severity, "⚪")

        lines = [f"## 🔍 告警分析结果\n"]
        lines.append(f"**告警ID**: {alert_id}")
        lines.append(f"**类型**: {alert_type}")
        lines.append(f"**严重程度**: {severity_emoji} {severity.upper()}")
        lines.append(f"**分析置信度**: {confidence:.0f}%")

        if suggestions:
            lines.append("\n### 💡 处置建议\n")
            for i, suggestion in enumerate(suggestions, 1):
                lines.append(f"{i}. {suggestion}")

        return "\n".join(lines)

    def _format_dedup_result(self, data: Any) -> str:
        """格式化告警去重结果"""
        if not data:
            return "未获取到去重数据"

        original_count = data.get("original_count", 0)
        deduped_count = data.get("deduplicated_count", 0)
        groups = data.get("groups", [])

        lines = [f"## 🔄 告警去重结果\n"]
        lines.append(f"**原始告警数**: {original_count}")
        lines.append(f"**去重后数量**: {deduped_count}")
        if original_count > 0 and deduped_count > 0:
            compression = (1 - deduped_count / original_count) * 100
            lines.append(f"**压缩比例**: {compression:.1f}%")

        if groups:
            lines.append("\n### 📦 告警分组\n")
            for i, group in enumerate(groups, 1):
                group_type = group.get("type", "unknown")
                count = group.get("count", 0)
                group_id = group.get("group_id", f"group_{i}")
                lines.append(f"- **{group_type}** ({count}条) - 压缩为1条, ID: {group_id}")

        if original_count > 0:
            compression = (1 - deduped_count / original_count) * 100
            lines.append(f"**压缩比例**: {compression:.1f}%")

        return "\n".join([l for l in lines if l])

    def _format_rca_result(self, data: Any) -> str:
        """格式化根因分析结果"""
        if not data:
            return "未获取到根因分析数据"

        alert_id = data.get("alert_id", "N/A")
        root_cause = data.get("root_cause", "未知")
        confidence = data.get("confidence", 0) * 100
        evidence = data.get("evidence", [])
        related_alerts = data.get("related_alerts", [])

        lines = [f"## 🎯 根因分析结果\n"]
        lines.append(f"**分析对象**: {alert_id}")
        lines.append(f"**根本原因**: {root_cause}")
        lines.append(f"**置信度**: {confidence:.0f}%")

        if evidence:
            lines.append("\n### 📋 证据链\n")
            for e in evidence:
                lines.append(f"- {e}")

        if related_alerts:
            lines.append("\n### 🔗 关联告警\n")
            for ra in related_alerts:
                lines.append(f"- [{ra['alert_id']}] {ra['alert_name']} ({ra['relation']})")

        return "\n".join(lines)

    def _format_predictive_result(self, data: Any) -> str:
        """格式化预测性告警结果"""
        if not data:
            return "未获取到预测数据"

        metric = data.get("metric", "unknown")
        threshold = data.get("threshold", 0)
        current_value = data.get("current_value", 0)
        predicted_value = data.get("predicted_value", 0)
        predicted_time = data.get("predicted_time", "N/A")
        trend = data.get("trend", "stable")
        risk_level = data.get("risk_level", "unknown")

        trend_emoji = {
            "accelerating": "📈",
            "decelerating": "📉",
            "stable": "➡️",
        }.get(trend, "❓")

        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(risk_level, "⚪")

        lines = [f"## 🔮 预测性告警分析\n"]
        lines.append(f"**指标**: {metric}")
        lines.append(f"**阈值**: {threshold}")
        lines.append(f"**当前值**: {current_value}")
        lines.append(f"**预测值**: {predicted_value}")
        lines.append(f"**增长趋势**: {trend_emoji} {trend}")
        lines.append(f"**风险等级**: {risk_emoji} {risk_level.upper()}")

        if predicted_time != "N/A":
            lines.append(f"**预计到达阈值时间**: {predicted_time}")

        return "\n".join(lines)
