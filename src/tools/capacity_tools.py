"""容量管理工具集 - Round 14 新增
提供存储分析、增长预测、容量报告、阈值告警工具
"""
import time
from typing import Any, Optional
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 存储分析工具
# ============================================================================
class StorageAnalysisTool(BaseTool):
    """存储容量分析工具"""

    definition = ToolDefinition(
        name="storage_analysis",
        description="分析数据库存储容量使用情况，返回各存储类型的使用率和风险等级",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="storage_analysis(db_type='mysql', instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        instance_id = params.get("instance_id", "INS-001")

        # 模拟存储数据
        storage_data = self._get_mock_storage(db_type)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "storage": storage_data,
                "timestamp": time.time(),
            }
        )

    def _get_mock_storage(self, db_type: str) -> list[dict]:
        """生成模拟存储数据"""
        if db_type == "mysql":
            return [
                {
                    "name": "数据文件 (InnoDB)",
                    "used_gb": 256.5,
                    "total_gb": 500.0,
                    "usage_percent": 51.3,
                    "risk_level": "low",
                    "mount_point": "/data/mysql",
                },
                {
                    "name": "日志文件 (Redo/Undo)",
                    "used_gb": 80.2,
                    "total_gb": 200.0,
                    "usage_percent": 40.1,
                    "risk_level": "low",
                    "mount_point": "/data/mysql_logs",
                },
                {
                    "name": "系统表空间",
                    "used_gb": 12.8,
                    "total_gb": 20.0,
                    "usage_percent": 64.0,
                    "risk_level": "medium",
                    "mount_point": "/data/mysql",
                },
                {
                    "name": "临时表空间",
                    "used_gb": 5.2,
                    "total_gb": 50.0,
                    "usage_percent": 10.4,
                    "risk_level": "low",
                    "mount_point": "/data/mysql_temp",
                },
                {
                    "name": "Binlog存储",
                    "used_gb": 180.0,
                    "total_gb": 200.0,
                    "usage_percent": 90.0,
                    "risk_level": "critical",
                    "mount_point": "/data/binlog",
                },
            ]
        elif db_type == "postgresql":
            return [
                {
                    "name": "数据目录 (PGDATA)",
                    "used_gb": 320.0,
                    "total_gb": 500.0,
                    "usage_percent": 64.0,
                    "risk_level": "medium",
                    "mount_point": "/var/lib/postgresql/data",
                },
                {
                    "name": "WAL日志",
                    "used_gb": 45.0,
                    "total_gb": 100.0,
                    "usage_percent": 45.0,
                    "risk_level": "low",
                    "mount_point": "/var/lib/postgresql/wal",
                },
                {
                    "name": "表空间 main",
                    "used_gb": 280.0,
                    "total_gb": 400.0,
                    "usage_percent": 70.0,
                    "risk_level": "medium",
                    "mount_point": "/var/lib/postgresql/tbs_main",
                },
                {
                    "name": "临时文件存储",
                    "used_gb": 8.5,
                    "total_gb": 50.0,
                    "usage_percent": 17.0,
                    "risk_level": "low",
                    "mount_point": "/var/lib/postgresql/temp",
                },
            ]
        else:  # oracle
            return [
                {
                    "name": "SYSTEM表空间",
                    "used_gb": 15.2,
                    "total_gb": 20.0,
                    "usage_percent": 76.0,
                    "risk_level": "medium",
                    "mount_point": "+DATA",
                },
                {
                    "name": "SYSAUX表空间",
                    "used_gb": 22.5,
                    "total_gb": 30.0,
                    "usage_percent": 75.0,
                    "risk_level": "medium",
                    "mount_point": "+DATA",
                },
                {
                    "name": "USERS表空间",
                    "used_gb": 8.0,
                    "total_gb": 10.0,
                    "usage_percent": 80.0,
                    "risk_level": "high",
                    "mount_point": "+DATA",
                },
                {
                    "name": "UNDOTBS1",
                    "used_gb": 35.0,
                    "total_gb": 100.0,
                    "usage_percent": 35.0,
                    "risk_level": "low",
                    "mount_point": "+DATA",
                },
                {
                    "name": "TEMP表空间",
                    "used_gb": 3.2,
                    "total_gb": 50.0,
                    "usage_percent": 6.4,
                    "risk_level": "low",
                    "mount_point": "+DATA",
                },
                {
                    "name": "ARCHIVELOG存储",
                    "used_gb": 95.0,
                    "total_gb": 100.0,
                    "usage_percent": 95.0,
                    "risk_level": "critical",
                    "mount_point": "+FRA",
                },
            ]


# ============================================================================
# 增长预测工具 (使用numpy)
# ============================================================================
class GrowthPredictionTool(BaseTool):
    """存储增长预测工具 - 使用线性回归预测"""

    definition = ToolDefinition(
        name="growth_prediction",
        description="基于历史增长数据，使用线性回归预测未来存储增长趋势",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="days", type="int", description="预测天数", required=False, default=90, constraints={"min": 1, "max": 365}),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="growth_prediction(db_type='mysql', days=90, instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        days = params.get("days", 90)
        instance_id = params.get("instance_id", "INS-001")

        try:
            import numpy as np
        except ImportError:
            return ToolResult(
                success=False,
                error="numpy未安装,请执行: pip install numpy"
            )

        # 获取历史增长数据
        history = self._get_mock_growth_history(db_type)

        # 线性回归预测
        x = np.array([h["day"] for h in history])
        y = np.array([h["size_gb"] for h in history])

        # 线性回归: y = slope * x + intercept
        n = len(x)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x * x) - np.sum(x) ** 2)
        intercept = (np.sum(y) - slope * np.sum(x)) / n

        # 预测
        current_day = history[-1]["day"]
        future_day = current_day + days
        predicted_size = slope * future_day + intercept

        # 当前大小
        current_size = history[-1]["size_gb"]

        # 日均增长
        daily_growth = slope

        # 计算R²决定系数 (拟合优度)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # 判断趋势
        if daily_growth > 0.1:
            trend = "accelerating"
        elif daily_growth < -0.1:
            trend = "decelerating"
        else:
            trend = "stable"

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "current_size_gb": round(current_size, 4),
                "predicted_size_gb": round(predicted_size, 4),
                "daily_growth_gb": round(daily_growth, 4),
                "trend": trend,
                "confidence": round(r_squared, 4),
                "prediction_days": days,
                "history": history,
                "timestamp": time.time(),
            }
        )

    def _get_mock_growth_history(self, db_type: str) -> list[dict]:
        """生成模拟历史增长数据"""
        # 最近30天的历史数据
        base_size = 200.0
        history = []

        for i in range(30):
            day = i - 29  # 从-29到0
            # 模拟每天增长约0.5-1.5GB，带随机波动
            import random
            size = base_size + (29 - day) * 1.0 + random.uniform(-0.3, 0.5)
            history.append({
                "day": day,
                "size_gb": round(size, 2)
            })

        return history


# ============================================================================
# 容量报告工具
# ============================================================================
class CapacityReportTool(BaseTool):
    """容量报告生成工具"""

    definition = ToolDefinition(
        name="capacity_report",
        description="生成综合容量分析报告，包含存储使用、增长预测、告警和建议",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="capacity_report(db_type='mysql', instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        instance_id = params.get("instance_id", "INS-001")

        # 获取存储数据
        storage_tool = StorageAnalysisTool()
        storage_result = await storage_tool.execute({"db_type": db_type, "instance_id": instance_id}, context)

        # 获取预测数据
        prediction_tool = GrowthPredictionTool()
        prediction_result = await prediction_tool.execute({"db_type": db_type, "days": 90, "instance_id": instance_id}, context)

        # 生成告警
        alerts = []
        if storage_result.success:
            for item in storage_result.data.get("storage", []):
                usage = item.get("usage_percent", 0)
                name = item.get("name", "")
                if usage >= 90:
                    alerts.append(f"🔴 [{name}] 使用率 {usage:.1f}%，严重告警，需立即扩容")
                elif usage >= 80:
                    alerts.append(f"🟠 [{name}] 使用率 {usage:.1f}%，告警，建议扩容")
                elif usage >= 70:
                    alerts.append(f"🟡 [{name}] 使用率 {usage:.1f}%，警告，关注中")

        # 预测数据
        predictions = {}
        if prediction_result.success:
            p_data = prediction_result.data
            predictions = {
                "predicted_90d_gb": p_data.get("predicted_size_gb", 0),
                "daily_growth_gb": p_data.get("daily_growth_gb", 0),
                "trend": p_data.get("trend", "unknown"),
            }

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "storage": storage_result.data.get("storage", []) if storage_result.success else [],
                "predictions": predictions,
                "alerts": alerts,
                "generated_at": time.time(),
            }
        )


# ============================================================================
# 容量告警工具
# ============================================================================
class CapacityAlertTool(BaseTool):
    """容量阈值告警工具"""

    definition = ToolDefinition(
        name="capacity_alert",
        description="检查存储容量是否超过指定阈值，返回触发告警的存储列表",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="threshold", type="float", description="告警阈值(百分比)", required=False, default=80.0, constraints={"min": 0, "max": 100}),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="capacity_alert(db_type='mysql', threshold=80.0, instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        threshold = params.get("threshold", 80.0)
        instance_id = params.get("instance_id", "INS-001")

        # 获取存储数据
        storage_tool = StorageAnalysisTool()
        storage_result = await storage_tool.execute({"db_type": db_type, "instance_id": instance_id}, context)

        if not storage_result.success:
            return ToolResult(
                success=False,
                error=f"获取存储数据失败: {storage_result.error}"
            )

        triggered = []
        not_triggered = []

        for item in storage_result.data.get("storage", []):
            usage = item.get("usage_percent", 0)
            name = item.get("name", "")
            storage_entry = {
                "name": name,
                "usage_percent": usage,
                "used_gb": item.get("used_gb", 0),
                "total_gb": item.get("total_gb", 0),
            }

            if usage >= threshold:
                triggered.append(storage_entry)
            else:
                not_triggered.append(storage_entry)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "threshold": threshold,
                "triggered": triggered,
                "not_triggered": not_triggered,
                "total": len(triggered) + len(not_triggered),
                "triggered_count": len(triggered),
                "timestamp": time.time(),
            }
        )


# ============================================================================
# 注册函数
# ============================================================================
def register_capacity_tools(registry) -> None:
    """注册容量管理工具到工具注册中心"""
    tools = [
        StorageAnalysisTool(),
        GrowthPredictionTool(),
        CapacityReportTool(),
        CapacityAlertTool(),
    ]
    for tool in tools:
        registry.register_tool(tool)


__all__ = [
    "StorageAnalysisTool",
    "GrowthPredictionTool",
    "CapacityReportTool",
    "CapacityAlertTool",
    "register_capacity_tools",
]
