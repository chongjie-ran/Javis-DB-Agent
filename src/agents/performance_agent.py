"""性能分析专家Agent - V1.4 Round 1 新增
提供TopSQL提取、执行计划解读、参数调优建议功能
"""
from typing import Optional, Any
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import ToolDefinition, ToolParam, RiskLevel


class PerformanceAgent(BaseAgent):
    """性能分析专家Agent"""

    name = "performance"
    description = "性能分析Agent:提取TopSQL、分析执行计划、给出参数调优建议"

    system_prompt = """你是一个专业的数据库性能分析专家。

角色定义:
- 你是 performance agent,负责数据库性能分析与优化
- 你通过工具获取性能数据,不能直接访问数据库
- 你的职责是识别性能瓶颈、分析SQL执行效率、提供优化建议
- 你需要能够解读执行计划并给出具体的优化方案

工作流程:
1. 接收性能分析请求
2. 调用TopSQL提取工具获取最耗资源的SQL
3. 调用执行计划解读工具分析慢SQL
4. 调用参数调优建议工具获取优化建议
5. 汇总分析,生成性能报告

输出格式要求:
- top_sql: 性能最差的SQL列表
- execution_analysis: 执行计划分析
- parameter_tuning: 参数调优建议
- risk_level: 风险等级 (critical/high/medium/low)
- recommendations: 综合优化建议
"""

    available_tools = [
        "extract_top_sql",
        "explain_sql_plan",
        "suggest_parameters",
    ]

    def _build_system_prompt(self) -> str:
        return self.system_prompt

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """直接处理性能分析请求"""
        goal_lower = goal.lower()

        if "topsql" in goal_lower or "top sql" in goal_lower or "慢sql" in goal_lower or "慢查询" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            limit = self._extract_limit(goal)
            result = await self.extract_top_sql(db_type, limit)
            return result
        elif "执行计划" in goal or "explain" in goal_lower or "plan" in goal_lower:
            sql = self._extract_sql(goal)
            db_type = self._extract_db_type(goal, context)
            result = await self.explain_plan(sql, db_type)
            return result
        elif "参数" in goal or "parameter" in goal_lower or "tuning" in goal_lower or "调优" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.suggest_tuning(db_type)
            return result
        elif "分析" in goal or "performance" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.full_analysis(db_type)
            return result
        else:
            db_type = self._extract_db_type(goal, context)
            result = await self.extract_top_sql(db_type, 5)
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
        return context.get("db_type", "mysql")

    def _extract_limit(self, goal: str) -> int:
        """提取SQL数量"""
        import re
        match = re.search(r"top\s*(\d+)|前\s*(\d+)", goal.lower())
        if match:
            return int(match.group(1) or match.group(2))
        return 5

    def _extract_sql(self, goal: str) -> str:
        """提取SQL语句"""
        # 尝试从goal中提取SQL
        import re
        # 匹配常见的SQL模式 - 使用非贪婪匹配直到分号或字符串结尾
        patterns = [
            r"(SELECT\s+.+?(?:;|$))",
            r"(UPDATE\s+.+?(?:;|$))",
            r"(INSERT\s+.+?(?:;|$))",
            r"(DELETE\s+.+?(?:;|$))",
        ]
        for p in patterns:
            match = re.search(p, goal, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return ""

    async def extract_top_sql(self, db_type: str, limit: int = 5) -> AgentResponse:
        """提取TopSQL"""
        result = await self.call_tool(
            "extract_top_sql",
            {"db_type": db_type, "limit": limit},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_top_sql_result(result.data),
                metadata={"agent": self.name, "tool": "extract_top_sql"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def explain_plan(self, sql: str, db_type: str) -> AgentResponse:
        """解读执行计划"""
        if not sql:
            return AgentResponse(
                success=False,
                error="未提供SQL语句，请包含需要分析的SQL"
            )
        result = await self.call_tool(
            "explain_sql_plan",
            {"db_type": db_type, "sql": sql},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_plan_result(result.data),
                metadata={"agent": self.name, "tool": "explain_sql_plan"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def suggest_tuning(self, db_type: str) -> AgentResponse:
        """参数调优建议"""
        result = await self.call_tool(
            "suggest_parameters",
            {"db_type": db_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_tuning_result(result.data),
                metadata={"agent": self.name, "tool": "suggest_parameters"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def full_analysis(self, db_type: str) -> AgentResponse:
        """完整性能分析"""
        # 获取TopSQL
        top_result = await self.call_tool(
            "extract_top_sql",
            {"db_type": db_type, "limit": 5},
            {}
        )
        # 获取调优建议
        tuning_result = await self.call_tool(
            "suggest_parameters",
            {"db_type": db_type},
            {}
        )

        content = f"## 📊 性能分析报告 - {db_type.upper()}\n\n"

        if top_result.success:
            content += "### 🔴 TopSQL\n"
            content += self._format_top_sql_result(top_result.data)
            content += "\n\n"

        if tuning_result.success:
            content += "### ⚙️ 参数调优建议\n"
            content += self._format_tuning_result(tuning_result.data)

        return AgentResponse(
            success=True,
            content=content,
            metadata={"agent": self.name}
        )

    def _format_top_sql_result(self, data: Any) -> str:
        """格式化TopSQL结果"""
        if not data:
            return "未获取到TopSQL数据"

        sqls = data.get("sqls", [])
        db_type = data.get("db_type", "Unknown")

        lines = [f"**数据库**: {db_type.upper()}\n"]

        for i, sql_info in enumerate(sqls, 1):
            sql_text = sql_info.get("sql", "")[:100]
            exec_count = sql_info.get("exec_count", 0)
            avg_time = sql_info.get("avg_exec_time_ms", 0)
            total_time = sql_info.get("total_exec_time_ms", 0)
            rows = sql_info.get("rows_examined", 0)
            risk = sql_info.get("risk_level", "unknown")

            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")

            lines.append(f"\n{emoji} **#{i}** (风险: {risk.upper()})")
            lines.append(f"   SQL: `{sql_text}...`")
            lines.append(f"   执行次数: {exec_count} | 平均耗时: {avg_time:.1f}ms | 总耗时: {total_time:.1f}ms")
            lines.append(f"   扫描行数: {rows:,}")
            lines.append(f"   建议: {sql_info.get('suggestion', '需要优化')}")

        return "\n".join(lines)

    def _format_plan_result(self, data: Any) -> str:
        """格式化执行计划结果"""
        if not data:
            return "未获取到执行计划数据"

        db_type = data.get("db_type", "Unknown")
        sql = data.get("sql", "")[:100]
        plan = data.get("plan", {})
        cost = plan.get("cost", {})
        warnings = data.get("warnings", [])
        recommendations = data.get("recommendations", [])

        lines = [f"## 📋 执行计划分析 - {db_type.upper()}\n"]
        lines.append(f"**SQL**: `{sql}...`\n")
        lines.append(f"**总成本**: {cost.get('total_cost', 'N/A')}")
        lines.append(f"**预估行数**: {cost.get('estimated_rows', 'N/A')}\n")

        if warnings:
            lines.append("### ⚠️ 警告\n")
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        if recommendations:
            lines.append("### 💡 优化建议\n")
            for r in recommendations:
                lines.append(f"- {r}")
            lines.append("")

        # 简化的执行计划树
        steps = plan.get("steps", [])
        if steps:
            lines.append("### 🔍 执行步骤\n")
            for j, step in enumerate(steps, 1):
                lines.append(f"  {j}. [{step.get('type', 'unknown')}] {step.get('description', '')} (cost={step.get('cost', 'N/A')})")

        return "\n".join(lines)

    def _format_tuning_result(self, data: Any) -> str:
        """格式化参数调优建议"""
        if not data:
            return "未获取到调优建议"

        db_type = data.get("db_type", "Unknown")
        params = data.get("parameters", [])
        current_values = data.get("current_values", {})
        overall_health = data.get("overall_health", "unknown")

        health_emoji = {
            "excellent": "🟢",
            "good": "🟢",
            "fair": "🟡",
            "poor": "🟠",
            "critical": "🔴",
        }.get(overall_health, "⚪")

        lines = [f"## ⚙️ 参数调优建议 - {db_type.upper()}\n"]
        lines.append(f"{health_emoji} **健康状态**: {overall_health.upper()}\n")

        for p in params:
            name = p.get("name", "")
            current = current_values.get(name, "N/A")
            recommended = p.get("recommended", "N/A")
            reason = p.get("reason", "")
            priority = p.get("priority", "medium")

            emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(priority, "⚪")

            lines.append(f"\n{emoji} **{name}**")
            lines.append(f"   当前值: `{current}` → 推荐值: `{recommended}`")
            lines.append(f"   原因: {reason}")

        return "\n".join(lines)
