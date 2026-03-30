"""性能分析工具集 - V1.4 Round 1 新增
提供TopSQL提取、执行计划解读、参数调优建议工具
"""
import time
import random
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# TopSQL提取工具
# ============================================================================
class ExtractTopSQLTool(BaseTool):
    """TopSQL提取工具"""

    definition = ToolDefinition(
        name="extract_top_sql",
        description="从数据库性能视图中提取执行最频繁或耗时最长的SQL语句",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="limit", type="int", description="返回SQL数量", required=False, default=5, constraints={"min": 1, "max": 50}),
            ToolParam(name="sort_by", type="string", description="排序方式: exec_time/exec_count/io_time", required=False, default="exec_time"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="extract_top_sql(db_type='mysql', limit=5, sort_by='exec_time')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        limit = params.get("limit", 5)
        sort_by = params.get("sort_by", "exec_time")
        instance_id = params.get("instance_id", "INS-001")

        sqls = self._get_mock_top_sql(db_type, limit, sort_by)

        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "sort_by": sort_by,
                "sqls": sqls,
                "timestamp": time.time(),
            }
        )

    def _get_mock_top_sql(self, db_type: str, limit: int, sort_by: str) -> list[dict]:
        """生成模拟TopSQL数据"""
        if db_type == "mysql":
            templates = [
                ("SELECT * FROM orders WHERE status = %s AND create_time > %s", "critical"),
                ("UPDATE inventory SET stock = stock - 1 WHERE product_id = %s", "high"),
                ("SELECT o.*, u.name FROM orders o JOIN users u ON o.user_id = u.id", "high"),
                ("SELECT COUNT(*) FROM logs WHERE level = 'ERROR' AND created_at > %s", "medium"),
                ("INSERT INTO audit_log (action, user_id, timestamp) VALUES (%s, %s, NOW())", "medium"),
                ("SELECT * FROM products WHERE category_id = %s ORDER BY price DESC", "low"),
                ("DELETE FROM sessions WHERE expire_at < %s", "low"),
                ("SELECT user_id, SUM(amount) FROM payments GROUP BY user_id", "medium"),
            ]
        elif db_type == "postgresql":
            templates = [
                ("SELECT * FROM orders WHERE status = $1 AND created_at > $2", "critical"),
                ("UPDATE inventory SET stock = stock - 1 WHERE product_id = $1", "high"),
                ("SELECT o.*, u.name FROM orders o JOIN users u ON o.user_id = u.id", "high"),
                ("SELECT COUNT(*) FROM logs WHERE level = 'ERROR' AND created_at > $1", "medium"),
                ("SELECT pg_stat_activity.* FROM pg_stat_activity WHERE state = 'active'", "low"),
                ("SELECT * FROM products WHERE category_id = $1 ORDER BY price DESC", "low"),
                ("DELETE FROM sessions WHERE expire_at < $1", "low"),
                ("VACUUM ANALYZE orders", "medium"),
            ]
        else:  # oracle
            templates = [
                ("SELECT * FROM orders WHERE status = :1 AND create_time > :2", "critical"),
                ("UPDATE inventory SET stock = stock - 1 WHERE product_id = :1", "high"),
                ("SELECT o.*, u.name FROM orders o JOIN users u ON o.user_id = u.id", "high"),
                ("SELECT COUNT(*) FROM logs WHERE level = 'ERROR' AND created_at > :1", "medium"),
                ("SELECT * FROM products WHERE category_id = :1 ORDER BY price DESC", "low"),
                ("DELETE FROM sessions WHERE expire_at < :1", "low"),
                ("SELECT user_id, SUM(amount) FROM payments GROUP BY user_id", "medium"),
                ("SELECT * FROM v$session WHERE status = 'ACTIVE'", "low"),
            ]

        # 随机选择SQL并添加变化
        sqls = []
        used_templates = []
        for i in range(min(limit, len(templates))):
            template, risk = templates[i % len(templates)]
            # 添加轻微变化避免重复
            sql = template.replace("%s", f"'{i+1}'").replace("$1", f"'{i+1}'").replace(":1", f"'{i+1}'")

            exec_count = random.randint(100, 10000) * (limit - i)
            avg_time = random.uniform(10, 5000) / (i + 1)
            total_time = exec_count * avg_time
            rows = random.randint(1000, 1000000)

            suggestion = self._get_suggestion(risk, sql)

            sql_info = {
                "rank": i + 1,
                "sql": sql,
                "exec_count": exec_count,
                "avg_exec_time_ms": round(avg_time, 2),
                "total_exec_time_ms": round(total_time, 2),
                "rows_examined": rows,
                "risk_level": risk,
                "suggestion": suggestion,
            }
            sqls.append(sql_info)

        # 根据sort_by排序
        if sort_by == "exec_count":
            sqls.sort(key=lambda x: x["exec_count"], reverse=True)
        elif sort_by == "io_time":
            sqls.sort(key=lambda x: x["total_exec_time_ms"], reverse=True)
        else:  # exec_time
            sqls.sort(key=lambda x: x["avg_exec_time_ms"], reverse=True)

        for i, sql in enumerate(sqls):
            sql["rank"] = i + 1

        return sqls

    def _get_suggestion(self, risk: str, sql: str) -> str:
        """根据风险等级和SQL内容给出建议"""
        if "SELECT * FROM orders" in sql:
            return "避免SELECT *，使用具体列；添加复合索引(status, create_time)"
        elif "UPDATE inventory" in sql:
            return "建议使用批量更新，减少事务锁竞争"
        elif "JOIN users" in sql:
            return "确保JOIN列有索引；考虑添加covering index"
        elif "COUNT(*) FROM logs" in sql:
            return "添加 WHERE 条件索引；使用物化视图缓存"
        elif "INSERT INTO audit_log" in sql:
            return "批量插入替代单条插入；使用异步写入"
        elif "DELETE FROM sessions" in sql:
            return "使用分批删除；考虑定期归档而非实时删除"
        elif "GROUP BY" in sql:
            return "确保GROUP BY列有索引；考虑使用COUNT(*) OVER()窗口函数"
        elif "VACUUM" in sql or "ANALYZE" in sql:
            return "建议设置autovacuum；避免业务高峰期执行"
        else:
            return "建议使用EXPLAIN分析执行计划"


# ============================================================================
# 执行计划解读工具
# ============================================================================
class ExplainSQLPlanTool(BaseTool):
    """执行计划解读工具"""

    definition = ToolDefinition(
        name="explain_sql_plan",
        description="解析SQL执行计划，分析查询成本、索引使用情况、连接方式等，给出优化建议",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="sql", type="string", description="待分析的SQL语句", required=True),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
        ],
        example="explain_sql_plan(db_type='mysql', sql='SELECT * FROM orders WHERE status = 1')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        sql = params.get("sql", "")
        instance_id = params.get("instance_id", "INS-001")

        if not sql:
            return ToolResult(success=False, error="未提供SQL语句")

        plan = self._get_mock_plan(db_type, sql)
        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "sql": sql,
                "plan": plan,
                "timestamp": time.time(),
            }
        )

    def _get_mock_plan(self, db_type: str, sql: str) -> dict:
        """生成模拟执行计划"""
        sql_upper = sql.upper()

        # 基于SQL类型生成不同计划
        if "JOIN" in sql_upper:
            plan = {
                "cost": {"total_cost": 1250.50, "estimated_rows": 50000},
                "warnings": [],
                "recommendations": [
                    "确保JOIN列(user_id)两边都有索引",
                    "考虑将小表放在JOIN左边(MySQL优化器行为)",
                    "添加covering index: (user_id, name) 避免回表",
                ],
                "steps": [
                    {"type": "SIMPLE", "description": "orders表 - 全表扫描", "cost": "850.00"},
                    {"type": "SIMPLE", "description": "users表 - 主键索引", "cost": "0.35"},
                    {"type": "JOIN", "description": "Hash Join (user_id)", "cost": "400.15"},
                    {"type": "SORT", "description": "排序(order_date DESC)", "cost": "50.00"},
                ],
            }
        elif "SELECT * FROM ORDERS WHERE" in sql_upper:
            plan = {
                "cost": {"total_cost": 125.30, "estimated_rows": 1500},
                "warnings": ["使用了SELECT *，返回了不必要的列"],
                "recommendations": [
                    "避免使用SELECT *，明确指定需要的列",
                    "为WHERE条件列(status, create_time)添加复合索引",
                    "如果status选择性低，考虑其他过滤条件",
                ],
                "steps": [
                    {"type": "INDEX_RANGE", "description": "idx_orders_status_date (status = 1)", "cost": "80.00"},
                    {"type": "FILTER", "description": "WHERE create_time > '2024-01-01'", "cost": "35.30"},
                    {"type": "SELECT", "description": "返回结果集", "cost": "10.00"},
                ],
            }
        elif "UPDATE" in sql_upper:
            plan = {
                "cost": {"total_cost": 250.00, "estimated_rows": 1},
                "warnings": ["UPDATE语句会获取排他锁，注意事务大小"],
                "recommendations": [
                    "确保WHERE条件有索引支撑，避免锁全表",
                    "批量更新时分开提交，减少锁持有时间",
                ],
                "steps": [
                    {"type": "INDEX_RANGE", "description": "idx_inventory_product (product_id = 1)", "cost": "5.00"},
                    {"type": "UPDATE", "description": "UPDATE inventory SET stock", "cost": "245.00"},
                ],
            }
        elif "INSERT" in sql_upper:
            plan = {
                "cost": {"total_cost": 15.50, "estimated_rows": 1},
                "warnings": [],
                "recommendations": [
                    "批量INSERT比单条INSERT性能好(5-10倍)",
                    "使用INSERT INTO ... VALUES (...), (...), (...)",
                ],
                "steps": [
                    {"type": "INSERT", "description": "INSERT INTO audit_log", "cost": "15.50"},
                ],
            }
        elif "DELETE" in sql_upper:
            plan = {
                "cost": {"total_cost": 500.00, "estimated_rows": 1000},
                "warnings": ["DELETE可能产生大量binlog/redo日志"],
                "recommendations": [
                    "分批DELETE，避免长事务锁阻塞",
                    "考虑使用分区表按时间自动清理",
                    "可以先SELECT确认影响行数",
                ],
                "steps": [
                    {"type": "INDEX_RANGE", "description": "idx_sessions_expire (expire_at < now())", "cost": "200.00"},
                    {"type": "DELETE", "description": "DELETE 1000 rows", "cost": "300.00"},
                ],
            }
        elif "GROUP BY" in sql_upper:
            plan = {
                "cost": {"total_cost": 850.00, "estimated_rows": 500},
                "warnings": [],
                "recommendations": [
                    "确保GROUP BY列有索引",
                    "考虑使用索引覆盖避免回表",
                    "如需排序，添加ORDER BY NULL禁用排序",
                ],
                "steps": [
                    {"type": "INDEX_SCAN", "description": "idx_payments_user (user_id)", "cost": "400.00"},
                    {"type": "GROUP", "description": "Hash Group (user_id)", "cost": "300.00"},
                    {"type": "SORT", "description": "ORDER BY SUM(amount)", "cost": "150.00"},
                ],
            }
        else:
            plan = {
                "cost": {"total_cost": 100.00, "estimated_rows": 100},
                "warnings": [],
                "recommendations": ["建议使用EXPLAIN ANALYZE获取实际执行时间"],
                "steps": [
                    {"type": "SCAN", "description": "表扫描", "cost": "100.00"},
                ],
            }

        return plan


# ============================================================================
# 参数调优建议工具
# ============================================================================
class SuggestParametersTool(BaseTool):
    """参数调优建议工具"""

    definition = ToolDefinition(
        name="suggest_parameters",
        description="根据当前数据库负载和配置，给出数据库参数调优建议",
        category="analysis",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False, default="INS-001"),
            ToolParam(name="workload_type", type="string", description="负载类型: oltp/ap/mixed/batch", required=False, default="mixed"),
        ],
        example="suggest_parameters(db_type='mysql', workload_type='oltp')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        db_type = params.get("db_type", "mysql")
        instance_id = params.get("instance_id", "INS-001")
        workload_type = params.get("workload_type", "mixed")

        result = self._get_mock_tuning_params(db_type, workload_type)
        return ToolResult(
            success=True,
            data={
                "db_type": db_type,
                "instance_id": instance_id,
                "workload_type": workload_type,
                **result,
                "timestamp": time.time(),
            }
        )

    def _get_mock_tuning_params(self, db_type: str, workload_type: str) -> dict:
        """生成模拟调优参数建议"""
        if db_type == "mysql":
            current = {
                "innodb_buffer_pool_size": "2G",
                "max_connections": "151",
                "innodb_log_file_size": "256M",
                "innodb_flush_log_at_trx_commit": "1",
                "query_cache_size": "128M",
                "slow_query_log": "OFF",
            }
            params = [
                {"name": "innodb_buffer_pool_size", "recommended": "4G", "reason": "建议设为可用内存的70%，当前2G偏小", "priority": "high"},
                {"name": "max_connections", "recommended": "500", "reason": "当前151在高并发时可能不足", "priority": "medium"},
                {"name": "innodb_flush_log_at_trx_commit", "recommended": "2", "reason": "OLTP场景可设为2提升写入性能", "priority": "medium"},
                {"name": "slow_query_log", "recommended": "ON", "reason": "开启慢查询日志用于分析", "priority": "high"},
                {"name": "query_cache_size", "recommended": "0", "reason": "MySQL8.0已移除Query Cache，建议禁用", "priority": "low"},
            ]
            overall_health = "fair"
        elif db_type == "postgresql":
            current = {
                "shared_buffers": "256MB",
                "max_connections": "100",
                "work_mem": "4MB",
                "maintenance_work_mem": "64MB",
                "effective_cache_size": "1GB",
                "random_page_cost": "4.0",
            }
            params = [
                {"name": "shared_buffers", "recommended": "1GB", "reason": "建议设为系统内存的25%", "priority": "high"},
                {"name": "work_mem", "recommended": "64MB", "reason": "当前4MB对于复杂查询太小", "priority": "high"},
                {"name": "maintenance_work_mem", "recommended": "256MB", "reason": "VACUUM和索引创建需要更多内存", "priority": "medium"},
                {"name": "effective_cache_size", "recommended": "3GB", "reason": "建议设为系统内存的75%", "priority": "medium"},
                {"name": "random_page_cost", "recommended": "1.1", "reason": "SSD存储应设为接近1的值", "priority": "medium"},
            ]
            overall_health = "poor"
        else:  # oracle
            current = {
                "sga_target": "2G",
                "pga_aggregate_target": "1G",
                "db_file_multiblock_read_count": "16",
                "optimizer_mode": "ALL_ROWS",
                "statistics_level": "TYPICAL",
            }
            params = [
                {"name": "sga_target", "recommended": "4G", "reason": "建议根据SGA命中率调整", "priority": "high"},
                {"name": "pga_aggregate_target", "recommended": "2G", "reason": "PGA不足会导致频繁磁盘排序", "priority": "high"},
                {"name": "db_file_multiblock_read_count", "recommended": "128", "reason": "全表扫描时一次读取更多块", "priority": "medium"},
                {"name": "optimizer_mode", "recommended": "FIRST_ROWS_10", "reason": "OLTP优先返回前几行", "priority": "low"},
            ]
            overall_health = "fair"

        return {
            "current_values": current,
            "parameters": params,
            "overall_health": overall_health,
        }


# ============================================================================
# 注册函数
# ============================================================================
def register_performance_tools(registry) -> None:
    """注册性能分析工具到工具注册中心"""
    tools = [
        ExtractTopSQLTool(),
        ExplainSQLPlanTool(),
        SuggestParametersTool(),
    ]
    for tool in tools:
        registry.register(tool)


__all__ = [
    "ExtractTopSQLTool",
    "ExplainSQLPlanTool",
    "SuggestParametersTool",
    "register_performance_tools",
]
