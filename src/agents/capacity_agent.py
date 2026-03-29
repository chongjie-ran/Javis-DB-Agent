"""容量管理专家智能体 - Round 14 新增
提供存储容量分析、增长预测、容量报告和阈值告警功能
"""
from typing import Optional, Any
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import ToolDefinition, ToolParam, RiskLevel, ToolResult


class CapacityAgent(BaseAgent):
    """容量管理专家智能体"""

    name = "capacity"
    description = "容量管理Agent:分析存储容量、预测增长趋势、生成容量报告、处理容量告警"

    system_prompt = """你是一个专业的数据库容量管理专家。

角色定义:
- 你是 capacity agent,负责数据库存储容量管理
- 你通过工具获取容量数据,不能直接访问数据库
- 你的职责是分析存储使用、预测增长趋势、给出容量规划建议
- 你需要能够识别容量瓶颈 and 提供扩容建议

工作流程:
1. 接收容量分析请求
2. 调用存储分析工具获取当前容量数据
3. 调用增长预测工具预测未来趋势
4. 调用容量报告工具生成分析报告
5. 如有需要,调用告警工具检查阈值

输出格式要求:
- current_usage: 当前使用情况
- predicted_growth: 预测增长 (如: 90天后的预估)
- risk_level: 风险等级 (critical/high/medium/low)
- recommendations: 扩容建议
- threshold_alerts: 阈值告警列表
"""

    available_tools = [
        "storage_analysis",
        "growth_prediction",
        "capacity_report",
        "capacity_alert",
    ]

    def _build_system_prompt(self) -> str:
        return self.system_prompt

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """直接处理容量管理请求"""
        intent_lower = goal.lower()

        if "分析" in goal or "容量" in goal:
            # 容量分析
            db_type = self._extract_db_type(goal, context)
            result = await self.analyze_storage(db_type)
            return result
        elif "预测" in goal or "增长" in goal:
            # 增长预测
            db_type = self._extract_db_type(goal, context)
            days = self._extract_days(goal)
            result = await self.predict_growth(db_type, days)
            return result
        elif "报告" in goal:
            # 生成容量报告
            db_type = self._extract_db_type(goal, context)
            result = await self.generate_capacity_report(db_type)
            return result
        elif "告警" in goal or "阈值" in goal:
            # 阈值告警
            db_type = self._extract_db_type(goal, context)
            threshold = self._extract_threshold(goal)
            result = await self.alert_capacity_threshold(db_type, threshold)
            return result
        else:
            # 通用容量查询
            db_type = self._extract_db_type(goal, context)
            result = await self.analyze_storage(db_type)
            return result

    def _extract_db_type(self, goal: str, context: dict) -> str:
        """提取数据库类型"""
        goal_lower = goal.lower()
        if "mysql" in goal_lower:
            return "mysql"
        elif "postgresql" in goal_lower or "pg" in goal_lower:
            return "postgresql"
        elif "oracle" in goal_lower:
            return "oracle"
        # 从上下文获取
        return context.get("db_type", "mysql")

    def _extract_days(self, goal: str) -> int:
        """提取预测天数"""
        import re
        match = re.search(r"(\d+)\s*天", goal)
        if match:
            return int(match.group(1))
        return 90

    def _extract_threshold(self, goal: str) -> float:
        """提取阈值"""
        import re
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", goal)
        if match:
            return float(match.group(1))
        return 80.0

    async def analyze_storage(self, db_type: str) -> AgentResponse:
        """分析存储容量"""
        result = await self.call_tool(
            "storage_analysis",
            {"db_type": db_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_storage_result(result.data),
                metadata={"agent": self.name, "tool": "storage_analysis"}
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def predict_growth(self, db_type: str, days: int = 90) -> AgentResponse:
        """预测存储增长"""
        result = await self.call_tool(
            "growth_prediction",
            {"db_type": db_type, "days": days},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_growth_result(result.data, days),
                metadata={"agent": self.name, "tool": "growth_prediction"}
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def generate_capacity_report(self, db_type: str) -> AgentResponse:
        """生成容量报告"""
        result = await self.call_tool(
            "capacity_report",
            {"db_type": db_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_report_result(result.data),
                metadata={"agent": self.name, "tool": "capacity_report"}
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    async def alert_capacity_threshold(self, db_type: str, threshold: float) -> AgentResponse:
        """容量阈值告警"""
        result = await self.call_tool(
            "capacity_alert",
            {"db_type": db_type, "threshold": threshold},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_alert_result(result.data),
                metadata={"agent": self.name, "tool": "capacity_alert"}
            )
        else:
            return AgentResponse(
                success=False,
                error=result.error
            )

    def _format_storage_result(self, data: Any) -> str:
        """格式化存储分析结果"""
        if not data:
            return "未获取到存储数据"

        storage_items = data.get("storage", [])
        lines = ["## 📊 存储容量分析\n"]

        for item in storage_items:
            name = item.get("name", "Unknown")
            used = item.get("used_gb", 0)
            total = item.get("total_gb", 0)
            usage_pct = item.get("usage_percent", 0)
            risk = item.get("risk_level", "unknown")

            risk_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")

            lines.append(f"{risk_emoji} **{name}**")
            lines.append(f"   - 已用: {used:.2f} GB / {total:.2f} GB")
            lines.append(f"   - 使用率: {usage_pct:.1f}%")
            lines.append(f"   - 风险等级: {risk.upper()}")
            lines.append("")

        return "\n".join(lines)

    def _format_growth_result(self, data: Any, days: int) -> str:
        """格式化增长预测结果"""
        if not data:
            return "未获取到增长数据"

        current = data.get("current_size_gb", 0)
        predicted = data.get("predicted_size_gb", 0)
        daily_avg = data.get("daily_growth_gb", 0)
        trend = data.get("trend", "stable")
        confidence = data.get("confidence", 0) * 100

        trend_text = {
            "accelerating": "📈 加速增长",
            "decelerating": "📉 减速增长",
            "stable": "➡️ 稳定增长",
        }.get(trend, "❓ 未知趋势")

        lines = [f"## 📈 容量增长预测 ({days}天)\n"]
        lines.append(f"当前容量: **{current:.2f} GB**")
        lines.append(f"预测容量: **{predicted:.2f} GB**")
        lines.append(f"日均增长: **{daily_avg:.4f} GB/天**")
        lines.append(f"增长趋势: {trend_text}")
        lines.append(f"预测置信度: **{confidence:.0f}%**")

        # 风险评估
        growth_rate = (predicted - current) / current * 100 if current > 0 else 0
        if growth_rate > 50:
            lines.append(f"\n⚠️ 警告: 预测容量增长 **{growth_rate:.1f}%**，存在容量不足风险")
        elif growth_rate > 20:
            lines.append(f"\n💡 提示: 预测容量增长 **{growth_rate:.1f}%**，建议关注")
        else:
            lines.append(f"\n✅ 状态: 容量增长平稳，暂无风险")

        return "\n".join(lines)

    def _format_report_result(self, data: Any) -> str:
        """格式化容量报告"""
        if not data:
            return "未获取到报告数据"

        db_type = data.get("db_type", "Unknown")
        generated_at = data.get("generated_at", 0)
        import time
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(generated_at))

        storage_items = data.get("storage", [])
        predictions = data.get("predictions", {})
        alerts = data.get("alerts", [])

        lines = [f"## 📋 容量报告 - {db_type.upper()}\n"]
        lines.append(f"生成时间: {time_str}\n")
        lines.append("---")

        # 存储概览
        lines.append("\n### 📊 存储概览\n")
        for item in storage_items:
            name = item.get("name", "Unknown")
            used = item.get("used_gb", 0)
            total = item.get("total_gb", 0)
            usage_pct = item.get("usage_percent", 0)
            lines.append(f"- **{name}**: {used:.2f} GB / {total:.2f} GB ({usage_pct:.1f}%)")

        # 增长预测
        if predictions:
            lines.append("\n### 📈 增长预测\n")
            lines.append(f"- 90天后预测: **{predictions.get('predicted_90d_gb', 0):.2f} GB**")
            lines.append(f"- 日均增长: **{predictions.get('daily_growth_gb', 0):.4f} GB/天**")

        # 告警
        if alerts:
            lines.append("\n### 🔔 容量告警\n")
            for alert in alerts:
                lines.append(f"- {alert}")
        else:
            lines.append("\n### ✅ 状态: 无容量告警")

        # 建议
        lines.append("\n### 💡 扩容建议\n")
        for item in storage_items:
            usage_pct = item.get("usage_percent", 0)
            name = item.get("name", "Unknown")
            if usage_pct > 80:
                lines.append(f"- **{name}**: 使用率超过80%，建议尽快扩容")
            elif usage_pct > 60:
                lines.append(f"- **{name}**: 使用率偏高，建议关注")

        return "\n".join(lines)

    def _format_alert_result(self, data: Any) -> str:
        """格式化告警结果"""
        if not data:
            return "未获取到告警数据"

        threshold = data.get("threshold", 0)
        triggered = data.get("triggered", [])
        not_triggered = data.get("not_triggered", [])

        lines = [f"## 🔔 容量阈值告警 (阈值: {threshold}%)\n"]

        if triggered:
            lines.append(f"\n⚠️ **触发告警 ({len(triggered)}项)**:\n")
            for item in triggered:
                lines.append(f"- 🔴 **{item['name']}**: {item['usage_percent']:.1f}% (超过阈值)")
        else:
            lines.append("\n✅ **状态**: 所有存储均未超过阈值")

        if not_triggered:
            lines.append(f"\n✅ 正常存储 ({len(not_triggered)}项):\n")
            for item in not_triggered:
                lines.append(f"- {item['name']}: {item['usage_percent']:.1f}%")

        return "\n".join(lines)
