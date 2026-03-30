"""备份恢复专家Agent - V1.4 Round 1 新增
提供备份状态查询、策略建议、恢复演练、异常告警功能
"""
from typing import Optional, Any
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import ToolDefinition, ToolParam, RiskLevel


class BackupAgent(BaseAgent):
    """备份恢复专家Agent"""

    name = "backup"
    description = "备份恢复Agent:查询备份状态、管理备份策略、支持恢复演练、处理备份异常"

    system_prompt = """你是一个专业的数据库备份恢复专家。

角色定义:
- 你是 backup agent,负责数据库备份与恢复管理
- 你通过工具获取备份数据,不能直接访问数据库
- 你的职责是分析备份状态、制定备份策略、支持恢复演练、处理备份告警
- 你需要能够识别备份风险并给出改进建议

工作流程:
1. 接收备份管理请求
2. 调用备份状态查询工具获取当前备份情况
3. 调用备份历史工具分析备份趋势
4. 如需恢复演练,调用恢复时间估算工具
5. 如需触发备份,调用触发备份工具
6. 汇总分析,给出备份策略建议

输出格式要求:
- backup_status: 当前备份状态
- backup_history: 备份历史摘要
- risk_level: 风险等级 (critical/high/medium/low)
- recommendations: 备份策略建议
- alerts: 异常告警列表
"""

    available_tools = [
        "check_backup_status",
        "list_backup_history",
        "trigger_backup",
        "estimate_restore_time",
    ]

    def _build_system_prompt(self) -> str:
        return self.system_prompt

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """直接处理备份恢复请求"""
        goal_lower = goal.lower()

        if "状态" in goal or "status" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.check_status(db_type)
            return result
        elif "历史" in goal or "history" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            limit = self._extract_limit(goal)
            result = await self.list_history(db_type, limit)
            return result
        elif "触发" in goal or "启动" in goal or "backup" in goal_lower and ("trigger" in goal_lower or "start" in goal_lower):
            db_type = self._extract_db_type(goal, context)
            backup_type = self._extract_backup_type(goal)
            result = await self.trigger_backup(db_type, backup_type)
            return result
        elif "恢复" in goal or "restore" in goal_lower or "recover" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.estimate_restore(db_type)
            return result
        elif "策略" in goal or "strategy" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.suggest_strategy(db_type)
            return result
        elif "告警" in goal or "alert" in goal_lower:
            db_type = self._extract_db_type(goal, context)
            result = await self.check_alerts(db_type)
            return result
        else:
            # 通用备份查询
            db_type = self._extract_db_type(goal, context)
            result = await self.check_status(db_type)
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
        """提取历史记录数量"""
        import re
        match = re.search(r"(\d+)\s*条", goal)
        if match:
            return int(match.group(1))
        return 10

    def _extract_backup_type(self, goal: str) -> str:
        """提取备份类型"""
        goal_lower = goal.lower()
        if "全量" in goal or "full" in goal_lower:
            return "full"
        elif "增量" in goal or "incremental" in goal_lower:
            return "incremental"
        elif "差异" in goal or "differential" in goal_lower:
            return "differential"
        return "full"

    async def check_status(self, db_type: str) -> AgentResponse:
        """查询备份状态"""
        result = await self.call_tool(
            "check_backup_status",
            {"db_type": db_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_status_result(result.data),
                metadata={"agent": self.name, "tool": "check_backup_status"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def list_history(self, db_type: str, limit: int = 10) -> AgentResponse:
        """查询备份历史"""
        result = await self.call_tool(
            "list_backup_history",
            {"db_type": db_type, "limit": limit},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_history_result(result.data),
                metadata={"agent": self.name, "tool": "list_backup_history"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def trigger_backup(self, db_type: str, backup_type: str = "full") -> AgentResponse:
        """触发备份"""
        result = await self.call_tool(
            "trigger_backup",
            {"db_type": db_type, "backup_type": backup_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_trigger_result(result.data),
                metadata={"agent": self.name, "tool": "trigger_backup"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def estimate_restore(self, db_type: str) -> AgentResponse:
        """估算恢复时间"""
        result = await self.call_tool(
            "estimate_restore_time",
            {"db_type": db_type},
            {}
        )

        if result.success:
            return AgentResponse(
                success=True,
                content=self._format_restore_result(result.data),
                metadata={"agent": self.name, "tool": "estimate_restore_time"}
            )
        else:
            return AgentResponse(success=False, error=result.error)

    async def suggest_strategy(self, db_type: str) -> AgentResponse:
        """建议备份策略（联动CapacityAgent）"""
        # 先获取备份状态
        status_result = await self.call_tool(
            "check_backup_status",
            {"db_type": db_type},
            {}
        )

        if not status_result.success:
            return AgentResponse(success=False, error=status_result.error)

        data = status_result.data
        backup_enabled = data.get("backup_enabled", False)
        last_backup = data.get("last_backup_time", 0)
        current_size_gb = data.get("db_size_gb", 0)

        # 生成策略建议
        import time
        time_since_backup = time.time() - last_backup if last_backup else 0
        hours_since = time_since_backup / 3600

        recommendations = []
        risk_level = "low"

        if not backup_enabled:
            recommendations.append("⚠️ 备份未启用，建议立即配置自动备份策略")
            risk_level = "critical"
        elif hours_since > 48:
            recommendations.append(f"⚠️ 距离上次备份已超过{int(hours_since)}小时，建议尽快执行备份")
            risk_level = "high"
        elif hours_since > 24:
            recommendations.append(f"💡 距离上次备份已超过{int(hours_since)}小时，建议今日内执行备份")
            risk_level = "medium"

        if current_size_gb > 500:
            recommendations.append(f"📦 数据库较大({current_size_gb:.1f}GB)，建议使用增量备份减少备份窗口")
        elif current_size_gb > 100:
            recommendations.append(f"📦 数据库中等规模({current_size_gb:.1f}GB)，建议每日全量+每小时增量")

        # 默认策略
        recommendations.append("✅ 推荐策略: 每日全量备份 + 每6小时增量备份 + 保留7天")
        recommendations.append("✅ 推荐策略: 每周一全量，其余增量，保留30天")

        content = f"""## 💾 备份策略建议 - {db_type.upper()}

### 当前状态
- 备份状态: {'✅ 已启用' if backup_enabled else '❌ 未启用'}
- 上次备份: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_backup)) if last_backup else '从未备份'}
- 数据库大小: {current_size_gb:.2f} GB

### 风险等级: {risk_level.upper()}

### 策略建议
"""
        for rec in recommendations:
            content += f"{rec}\n"

        return AgentResponse(
            success=True,
            content=content,
            metadata={"agent": self.name, "tool": "check_backup_status + analysis"}
        )

    async def check_alerts(self, db_type: str) -> AgentResponse:
        """检查备份异常告警"""
        status_result = await self.call_tool(
            "check_backup_status",
            {"db_type": db_type},
            {}
        )
        history_result = await self.call_tool(
            "list_backup_history",
            {"db_type": db_type, "limit": 10},
            {}
        )

        if not status_result.success:
            return AgentResponse(success=False, error=status_result.error)

        alerts = []
        data = status_result.data
        import time

        # 检查备份启用状态
        if not data.get("backup_enabled", False):
            alerts.append(("critical", "备份功能未启用，存在数据丢失风险"))

        # 检查上次备份时间
        last_backup = data.get("last_backup_time", 0)
        if last_backup:
            hours_since = (time.time() - last_backup) / 3600
            if hours_since > 48:
                alerts.append(("high", f"超过{int(hours_since)}小时未备份，建议立即执行"))
            elif hours_since > 24:
                alerts.append(("medium", f"超过{int(hours_since)}小时未备份，请关注"))
        else:
            alerts.append(("critical", "从未执行过备份"))

        # 检查备份失败
        if history_result.success:
            failed_count = sum(1 for h in history_result.data.get("backups", []) if h.get("status") == "failed")
            if failed_count > 0:
                alerts.append(("high", f"最近10次备份中有{failed_count}次失败"))

        # 检查存储空间
        if data.get("backup_storage_percent", 0) > 80:
            alerts.append(("medium", f"备份存储使用率{data.get('backup_storage_percent')}%"))

        content = f"## 🔔 备份告警 - {db_type.upper()}\n\n"
        if alerts:
            for level, msg in alerts:
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(level, "⚪")
                content += f"{emoji} **{level.upper()}**: {msg}\n"
        else:
            content += "✅ **状态**: 无备份异常告警\n"

        return AgentResponse(success=True, content=content, metadata={"agent": self.name})

    def _format_status_result(self, data: Any) -> str:
        """格式化备份状态结果"""
        if not data:
            return "未获取到备份状态数据"

        import time
        db_type = data.get("db_type", "Unknown")
        backup_enabled = data.get("backup_enabled", False)
        last_backup = data.get("last_backup_time", 0)
        backup_method = data.get("backup_method", "unknown")
        db_size = data.get("db_size_gb", 0)
        backup_size = data.get("backup_size_gb", 0)
        storage_percent = data.get("backup_storage_percent", 0)
        retention_days = data.get("retention_days", 7)

        lines = [f"## 💾 备份状态 - {db_type.upper()}\n"]
        lines.append(f"- 备份状态: {'✅ 已启用' if backup_enabled else '❌ 未启用'}")
        lines.append(f"- 备份方式: {backup_method}")
        lines.append(f"- 上次备份: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_backup)) if last_backup else '从未备份'}")
        lines.append(f"- 数据库大小: {db_size:.2f} GB")
        lines.append(f"- 备份文件大小: {backup_size:.2f} GB")
        lines.append(f"- 备份存储使用: {storage_percent:.1f}%")
        lines.append(f"- 保留策略: {retention_days} 天")

        # 风险评估
        if not backup_enabled:
            lines.append("\n⚠️ **风险**: 备份未启用，数据存在丢失风险")
        elif last_backup and (time.time() - last_backup) > 86400:
            hours = int((time.time() - last_backup) / 3600)
            lines.append(f"\n⚠️ **风险**: 已超过{hours}小时未备份")
        elif storage_percent > 80:
            lines.append(f"\n⚠️ **风险**: 备份存储空间不足({storage_percent:.1f}%)")

        return "\n".join(lines)

    def _format_history_result(self, data: Any) -> str:
        """格式化备份历史结果"""
        if not data:
            return "未获取到备份历史数据"

        backups = data.get("backups", [])
        db_type = data.get("db_type", "Unknown")
        import time

        lines = [f"## 📜 备份历史 - {db_type.upper()}\n"]
        lines.append(f"共 {len(backups)} 条记录\n")

        for b in backups:
            status = b.get("status", "unknown")
            btype = b.get("backup_type", "unknown")
            ts = b.get("timestamp", 0)
            size = b.get("size_gb", 0)
            duration = b.get("duration_seconds", 0)

            emoji = {"completed": "✅", "failed": "❌", "running": "🔄", "unknown": "⚪"}.get(status, "⚪")
            time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "未知时间"

            lines.append(f"{emoji} [{time_str}] {btype.upper()} - {size:.2f}GB ({duration:.0f}s)")

        return "\n".join(lines)

    def _format_trigger_result(self, data: Any) -> str:
        """格式化触发备份结果"""
        if not data:
            return "未获取到触发结果"

        db_type = data.get("db_type", "Unknown")
        backup_id = data.get("backup_id", "N/A")
        status = data.get("status", "unknown")
        message = data.get("message", "")
        import time
        start_time = data.get("start_time", 0)

        lines = [f"## 🚀 备份触发结果 - {db_type.upper()}\n"]
        lines.append(f"- 备份ID: {backup_id}")
        lines.append(f"- 状态: {status.upper()}")
        lines.append(f"- 启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time)) if start_time else 'N/A'}")
        lines.append(f"- 消息: {message}")

        return "\n".join(lines)

    def _format_restore_result(self, data: Any) -> str:
        """格式化恢复时间估算结果"""
        if not data:
            return "未获取到恢复时间估算"

        db_type = data.get("db_type", "Unknown")
        total_time_seconds = data.get("total_time_seconds", 0)
        phases = data.get("phases", [])

        minutes = int(total_time_seconds // 60)
        seconds = int(total_time_seconds % 60)

        lines = [f"## ⏱️ 恢复时间估算 - {db_type.upper()}\n"]
        lines.append(f"**预计总时间: {minutes}分{seconds}秒**\n")
        lines.append("### 分阶段详情\n")

        for phase in phases:
            name = phase.get("name", "未知阶段")
            duration = phase.get("duration_seconds", 0)
            desc = phase.get("description", "")
            lines.append(f"- **{name}**: {duration:.0f}秒 - {desc}")

        return "\n".join(lines)
