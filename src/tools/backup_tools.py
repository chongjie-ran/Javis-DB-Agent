"""备份恢复工具集 - V1.4 Round 1 新增 V1.5 Round 2 - PG真实连接
提供备份状态查询、历史记录、触发备份、恢复时间估算工具
"""
import time
import random
import uuid
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult

# PG连接配置（V1.5 Round 2）
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "javis_test",
    "password": "javis_test123",
    "database": "javis_test_db",
}


# ============================================================================
# 备份状态查询工具
# ============================================================================
class CheckBackupStatusTool(BaseTool):
    """备份状态查询工具"""

    definition = ToolDefinition(
        name="check_backup_status",
        description="查询数据库备份状态，返回备份启用状态、上次备份时间、备份方式、存储使用率等信息",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="check_backup_status(db_type='mysql', instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        instance_id = params.get("instance_id", "INS-001")

        # PostgreSQL使用真实查询，MySQL/Oracle保持mock
        if db_type == "postgresql":
            backup_data = self._get_backup_status_pg(instance_id)
        else:
            backup_data = self._get_mock_backup_status(db_type, instance_id)

        return ToolResult(
            success=True,
            data=backup_data
        )

    def _get_backup_status_pg(self, instance_id: str) -> dict:
        """从真实PG数据库查询备份状态（V1.5 Round 2）"""
        import psycopg2
        now = time.time()
        
        try:
            conn = psycopg2.connect(**PG_CONFIG)
            cursor = conn.cursor()
            
            # 查询数据库大小
            cursor.execute("""
                SELECT 
                    datname,
                    pg_size_pretty(pg_database_size(datname)) as size,
                    pg_database_size(datname) as size_bytes
                FROM pg_database
                WHERE datname NOT IN ('postgres', 'template0', 'template1')
                ORDER BY pg_database_size(datname) DESC
                LIMIT 1
            """)
            db_row = cursor.fetchone()
            
            # 查询备份历史（最新的成功备份）
            cursor.execute("""
                SELECT backup_type, end_time, size_bytes
                FROM backup_history
                WHERE db_type = 'postgresql' AND status = 'success'
                ORDER BY end_time DESC
                LIMIT 1
            """)
            backup_row = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if db_row:
                db_name, size_pretty, size_bytes = db_row
                db_size_gb = size_bytes / (1024**3)
            else:
                db_name = "javis_test_db"
                size_pretty = "unknown"
                db_size_gb = 0
            
            if backup_row:
                backup_type, end_time, backup_size = backup_row
                last_backup_ts = end_time.timestamp() if hasattr(end_time, 'timestamp') else time.mktime(end_time.timetuple())
                backup_size_gb = backup_size / (1024**3) if backup_size else 0
            else:
                backup_type = "none"
                last_backup_ts = 0
                backup_size_gb = 0
            
            return {
                "db_type": "postgresql",
                "instance_id": instance_id,
                "backup_enabled": backup_row is not None,
                "last_backup_time": last_backup_ts,
                "backup_method": "pg_basebackup + WAL" if backup_type == "full" else "WAL",
                "backup_schedule": "daily_full + continuous_WAL",
                "db_size_gb": round(db_size_gb, 2),
                "backup_size_gb": round(backup_size_gb, 2),
                "backup_storage_percent": round((backup_size_gb / db_size_gb * 100), 1) if db_size_gb > 0 else 0,
                "retention_days": 14,
                "compression_ratio": 0.30,
                "source": "real_pg",  # 标记数据来源
                "timestamp": now,
            }
            
        except Exception as e:
            # PG连接失败时降级到mock但标注来源
            print(f"[WARN] PG查询失败，降级到mock: {e}")
            mock = self._get_mock_backup_status("postgresql", instance_id)
            mock["source"] = "mock_fallback"
            return mock

    def _get_mock_backup_status(self, db_type: str, instance_id: str) -> dict:
        """生成模拟备份状态数据（MySQL/Oracle使用）"""
        now = time.time()
        if db_type == "mysql":
            return {
                "db_type": db_type,
                "instance_id": instance_id,
                "backup_enabled": True,
                "last_backup_time": now - 3600 * 12,  # 12小时前
                "backup_method": "xtrabackup",
                "backup_schedule": "daily_full + 6h_incremental",
                "db_size_gb": 256.5,
                "backup_size_gb": 85.2,
                "backup_storage_percent": 68.5,
                "retention_days": 7,
                "compression_ratio": 0.33,
                "source": "mock",
                "timestamp": now,
            }
        elif db_type == "postgresql":
            return {
                "db_type": db_type,
                "instance_id": instance_id,
                "backup_enabled": True,
                "last_backup_time": now - 3600 * 6,  # 6小时前
                "backup_method": "pg_basebackup + WAL",
                "backup_schedule": "daily_full + continuous_WAL",
                "db_size_gb": 320.0,
                "backup_size_gb": 95.8,
                "backup_storage_percent": 72.0,
                "retention_days": 14,
                "compression_ratio": 0.30,
                "source": "mock",
                "timestamp": now,
            }
        else:  # oracle
            return {
                "db_type": db_type,
                "instance_id": instance_id,
                "backup_enabled": True,
                "last_backup_time": now - 3600 * 48,  # 48小时前（超过建议）
                "backup_method": "RMAN",
                "backup_schedule": "weekly_full + daily_inc",
                "db_size_gb": 450.0,
                "backup_size_gb": 180.0,
                "backup_storage_percent": 85.0,  # 存储告警
                "retention_days": 30,
                "compression_ratio": 0.40,
                "source": "mock",
                "timestamp": now,
            }


# ============================================================================
# 备份历史查询工具
# ============================================================================
class ListBackupHistoryTool(BaseTool):
    """备份历史查询工具"""

    definition = ToolDefinition(
        name="list_backup_history",
        description="查询数据库备份历史记录，返回最近N次备份的执行情况",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="limit", type="int", description="返回记录数量", required=False, default=10, constraints={"min": 1, "max": 100}),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="list_backup_history(db_type='mysql', limit=10, instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        limit = params.get("limit", 10)
        instance_id = params.get("instance_id", "INS-001")

        # PostgreSQL使用真实查询，MySQL/Oracle保持mock
        if db_type == "postgresql":
            backups = self._list_history_pg(limit)
        else:
            backups = self._get_mock_backup_history(db_type, limit)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "backups": backups,
                "total_count": len(backups),
                "timestamp": time.time(),
            }
        )

    def _list_history_pg(self, limit: int) -> list[dict]:
        """从PG查询备份历史（V1.5 Round 2 - 真实PG查询）"""
        import psycopg2
        
        try:
            conn = psycopg2.connect(**PG_CONFIG)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    id,
                    backup_type,
                    status,
                    start_time,
                    end_time,
                    size_bytes
                FROM backup_history
                WHERE db_type = 'postgresql'
                ORDER BY end_time DESC
                LIMIT %s
            """, (limit,))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            backups = []
            for row in rows:
                bid, btype, status, start_time, end_time, size_bytes = row
                
                # 计算时长
                if start_time and end_time:
                    if hasattr(start_time, 'timestamp') and hasattr(end_time, 'timestamp'):
                        duration = end_time.timestamp() - start_time.timestamp()
                    else:
                        duration = 0
                else:
                    duration = 0
                
                size_gb = (size_bytes or 0) / (1024**3)
                
                backup = {
                    "backup_id": f"BK-{bid}",
                    "timestamp": end_time.timestamp() if hasattr(end_time, 'timestamp') else time.time(),
                    "backup_type": btype,
                    "status": status,
                    "size_gb": round(size_gb, 2),
                    "duration_seconds": round(duration, 0),
                    "compression_ratio": 0.30,
                    "destination": "local",
                    "source": "real_pg",
                }
                backups.append(backup)
            
            return backups
            
        except Exception as e:
            print(f"[WARN] PG查询备份历史失败，降级到mock: {e}")
            return self._get_mock_backup_history("postgresql", limit)

    def _get_mock_backup_history(self, db_type: str, limit: int) -> list[dict]:
        """生成模拟备份历史（MySQL/Oracle使用）"""
        now = time.time()
        backups = []
        backup_types = ["full", "incremental", "differential"]
        statuses = ["completed", "completed", "completed", "failed", "completed"]

        for i in range(limit):
            # 越近的记录越新
            ts = now - i * 86400 - random.randint(0, 3600)
            btype = backup_types[i % len(backup_types)]
            status = statuses[i % len(statuses)]

            if btype == "full":
                size_gb = random.uniform(80, 120)
                duration = random.uniform(600, 1800)
            elif btype == "incremental":
                size_gb = random.uniform(5, 30)
                duration = random.uniform(60, 300)
            else:
                size_gb = random.uniform(20, 60)
                duration = random.uniform(180, 600)

            backup = {
                "backup_id": f"BK-{int(ts)}",
                "timestamp": ts,
                "backup_type": btype,
                "status": status,
                "size_gb": round(size_gb, 2),
                "duration_seconds": round(duration, 0),
                "compression_ratio": round(random.uniform(0.25, 0.40), 2),
                "destination": "local" if i % 3 == 0 else "remote",
                "source": "mock",
            }
            backups.append(backup)

        return backups


# ============================================================================
# 触发备份工具
# ============================================================================
class TriggerBackupTool(BaseTool):
    """触发备份工具"""

    definition = ToolDefinition(
        name="trigger_backup",
        description="触发一次数据库备份，支持全量备份、增量备份、差异备份三种类型",
        category="action",
        risk_level=RiskLevel.L3_LOW_RISK,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="backup_type", type="string", description="备份类型: full/incremental/differential", required=False, default="full"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        pre_check="检查备份存储空间是否充足（预留20%空间）",
        post_check="验证备份文件完整性",
        example="trigger_backup(db_type='mysql', backup_type='full', instance_id='INS-001')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        backup_type = params.get("backup_type", "full")
        instance_id = params.get("instance_id", "INS-001")

        # 模拟备份触发
        backup_id = f"BK-{uuid.uuid4().hex[:12].upper()}"
        start_time = time.time()

        # 估算备份时间
        if backup_type == "full":
            est_duration = random.uniform(600, 1800)
            est_size_gb = random.uniform(80, 120)
        elif backup_type == "incremental":
            est_duration = random.uniform(60, 300)
            est_size_gb = random.uniform(5, 30)
        else:  # differential
            est_duration = random.uniform(180, 600)
            est_size_gb = random.uniform(20, 60)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "backup_id": backup_id,
                "backup_type": backup_type,
                "status": "running",
                "start_time": start_time,
                "estimated_duration_seconds": round(est_duration, 0),
                "estimated_size_gb": round(est_size_gb, 2),
                "message": f"备份任务已提交，预计耗时{int(est_duration)}秒",
                "timestamp": start_time,
            }
        )


# ============================================================================
# 恢复时间估算工具
# ============================================================================
class EstimateRestoreTimeTool(BaseTool):
    """恢复时间估算工具"""

    definition = ToolDefinition(
        name="estimate_restore_time",
        description="估算数据库恢复所需时间，基于备份文件大小、数据量、恢复方式等因素",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
            ToolParam(name="restore_type", type="string", description="恢复类型: point_in_time/latest/full", required=False, default="latest"),
        ],
        example="estimate_restore_time(db_type='mysql', instance_id='INS-001', restore_type='latest')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        instance_id = params.get("instance_id", "INS-001")
        restore_type = params.get("restore_type", "latest")

        phases = self._build_restore_phases(db_type, restore_type)
        total_time = sum(p["duration_seconds"] for p in phases)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "restore_type": restore_type,
                "total_time_seconds": round(total_time, 1),
                "phases": phases,
                "timestamp": time.time(),
            }
        )

    def _build_restore_phases(self, db_type: str, restore_type: str) -> list[dict]:
        """构建恢复阶段及耗时"""
        phases = []

        if db_type == "mysql":
            phases = [
                {
                    "name": "停止服务",
                    "duration_seconds": 5,
                    "description": "暂停数据库写入服务",
                },
                {
                    "name": "文件传输",
                    "duration_seconds": 300,
                    "description": "备份文件从备份存储传输到目标服务器",
                },
                {
                    "name": "全量恢复",
                    "duration_seconds": 600,
                    "description": "解压并恢复全量备份文件",
                },
                {
                    "name": "增量应用",
                    "duration_seconds": 120,
                    "description": "应用增量备份/WAL日志到指定时间点",
                },
                {
                    "name": "完整性校验",
                    "duration_seconds": 60,
                    "description": "校验数据完整性",
                },
                {
                    "name": "启动服务",
                    "duration_seconds": 10,
                    "description": "启动数据库服务",
                },
            ]
        elif db_type == "postgresql":
            phases = [
                {
                    "name": "停止服务",
                    "duration_seconds": 5,
                    "description": "暂停数据库写入服务",
                },
                {
                    "name": "文件清理",
                    "duration_seconds": 30,
                    "description": "清理现有数据文件",
                },
                {
                    "name": "基础备份恢复",
                    "duration_seconds": 480,
                    "description": "恢复pg_basebackup全量备份",
                },
                {
                    "name": "WAL重放",
                    "duration_seconds": 180,
                    "description": "重放WAL日志到目标时间点",
                },
                {
                    "name": "恢复校验",
                    "duration_seconds": 60,
                    "description": "执行pg_verifybackup校验",
                },
                {
                    "name": "启动服务",
                    "duration_seconds": 10,
                    "description": "启动PostgreSQL服务",
                },
            ]
        else:  # oracle
            phases = [
                {
                    "name": "实例关闭",
                    "duration_seconds": 30,
                    "description": "关闭Oracle实例(Nomount模式)",
                },
                {
                    "name": "控制文件恢复",
                    "duration_seconds": 60,
                    "description": "恢复控制文件",
                },
                {
                    "name": "数据文件恢复",
                    "duration_seconds": 900,
                    "description": "RMAN restore datafile",
                },
                {
                    "name": "介质恢复",
                    "duration_seconds": 300,
                    "description": "RMAN recover database",
                },
                {
                    "name": "Resetlogs打开",
                    "duration_seconds": 30,
                    "description": "以resetlogs方式打开数据库",
                },
            ]

        # point_in_time 额外增加时间
        if restore_type == "point_in_time":
            for phase in phases:
                phase["duration_seconds"] = int(phase["duration_seconds"] * 1.3)

        return phases


# ============================================================================
# 注册函数
# ============================================================================
def register_backup_tools(registry) -> None:
    """注册备份恢复工具到工具注册中心"""
    tools = [
        CheckBackupStatusTool(),
        ListBackupHistoryTool(),
        TriggerBackupTool(),
        EstimateRestoreTimeTool(),
    ]
    for tool in tools:
        registry.register(tool)


__all__ = [
    "CheckBackupStatusTool",
    "ListBackupHistoryTool",
    "TriggerBackupTool",
    "EstimateRestoreTimeTool",
    "register_backup_tools",
]
