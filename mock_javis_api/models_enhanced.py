"""
Javis-DB-Agent API Mock Server - 增强版数据模型
接近真实 Javis-DB-Agent API 格式，添加了 custom_fields、annotations、nested_alerts 等嵌套结构
"""
import time
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional, Any

from pydantic import BaseModel, Field


# ============================================================================
# 增强版基础模型
# ============================================================================

class AlertAnnotation(BaseModel):
    """告警注解信息（annotations）"""
    first_occurrence: str
    last_evaluation: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    incident_id: Optional[str] = None
    runbook_url: Optional[str] = None
    dashboard_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class NestedAlert(BaseModel):
    """嵌套告警信息"""
    alert_id: str
    alert_code: str
    alert_name: str
    severity: str
    occurred_at: float


class AlertCustomFields(BaseModel):
    """告警自定义字段（custom_fields）"""
    host_ip: Optional[str] = None
    region: Optional[str] = None
    cluster: Optional[str] = None
    environment: Optional[str] = None
    business_line: Optional[str] = None
    on_call: Optional[str] = None
    # 额外扩展字段
    extra: dict[str, Any] = Field(default_factory=dict)


class EnhancedAlert(BaseModel):
    """增强版告警模型（接近真实 Javis-DB-Agent API）"""
    # 基础信息
    alert_id: str
    alert_code: str
    alert_name: str
    severity: str  # critical/warning/info
    instance_id: str
    instance_name: str
    message: str
    metric_value: float
    threshold: float
    unit: str = "%"
    
    # 时间信息
    occurred_at: float
    duration_seconds: int = 0
    
    # 状态
    status: str = "firing"  # firing/resolved
    acknowledged: bool = False
    
    # 嵌套结构（真实 Javis-DB-Agent API 特有）
    custom_fields: AlertCustomFields = Field(default_factory=AlertCustomFields)
    annotations: AlertAnnotation = Field(default_factory=AlertAnnotation)
    nested_alerts: list[NestedAlert] = Field(default_factory=list)
    
    # 关联资源
    related_instances: list[dict] = Field(default_factory=list)
    
    # 元数据
    timestamp: float = Field(default_factory=time.time)


class EnhancedInstance(BaseModel):
    """增强版实例模型"""
    # 基础信息
    instance_id: str
    instance_name: str
    db_type: str  # mysql/postgresql/oracle
    version: str
    status: str  # running/stopped/error
    role: str  # primary/standby
    
    # 连接信息
    host: str
    port: int
    region: Optional[str] = None
    cluster: Optional[str] = None
    
    # 指标
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    connections: int = 0
    max_connections: int = 500
    
    # 扩展指标
    buffer_cache_hit_ratio: float = 98.0
    transaction_per_second: float = 0.0
    
    # HA
    ha_enabled: bool = False
    ha_role: str = "primary"
    
    # 备份
    backup_enabled: bool = True
    last_backup_time: Optional[float] = None
    
    # 标签
    tags: list[str] = Field(default_factory=list)
    
    # 元数据
    uptime_seconds: int = 0
    created_at: str = "2025-01-01T00:00:00Z"
    timestamp: float = Field(default_factory=time.time)


class EnhancedSession(BaseModel):
    """增强版会话模型"""
    sid: int
    serial: int
    username: str
    status: str  # ACTIVE/INACTIVE
    program: str
    machine: str
    sql_id: Optional[str] = None
    sql_text: Optional[str] = None
    wait_event: Optional[str] = None
    wait_seconds: int = 0
    logon_time: float
    client_ip: Optional[str] = None
    background_process: bool = False
    osuser: Optional[str] = None
    process: Optional[str] = None


class EnhancedLock(BaseModel):
    """增强版锁信息模型"""
    wait_sid: int
    wait_serial: int
    wait_sql_id: Optional[str] = None
    wait_username: Optional[str] = None
    lock_type: str  # transaction/table/share
    mode_held: str
    mode_requested: str
    lock_id1: str
    lock_id2: str
    lock_table: Optional[str] = None
    blocker_sid: Optional[int] = None
    blocker_serial: Optional[int] = None
    blocker_sql_id: Optional[str] = None
    blocker_username: Optional[str] = None
    wait_seconds: int
    chain_length: int


class EnhancedSlowSQL(BaseModel):
    """增强版慢SQL模型"""
    sql_id: str
    sql_text: str
    executions: int
    elapsed_time_sec: float
    avg_elapsed_sec: float
    disk_reads: int
    buffer_gets: int
    rows_processed: int
    first_load_time: float
    last_active_time: float
    # 扩展字段
    module: Optional[str] = None
    parsing_schema: Optional[str] = None
    optimizer_mode: Optional[str] = None


class SQLPlanStep(BaseModel):
    """SQL执行计划步骤"""
    id: int
    operation: str
    options: Optional[str] = None
    object_name: Optional[str] = None
    object_type: Optional[str] = None
    optimizer: Optional[str] = None
    cost: int
    cardinality: int
    bytes: Optional[int] = None
    filter: Optional[str] = None
    access_predicate: Optional[str] = None


class EnhancedTablespace(BaseModel):
    """增强版表空间模型"""
    tablespace_name: str
    status: str = "ONLINE"
    total_size_mb: float
    used_size_mb: float
    free_size_mb: float
    usage_percent: float
    auto_extensible: bool = True
    max_size_mb: Optional[float] = None
    increment_mb: Optional[float] = None


class EnhancedWorkOrder(BaseModel):
    """增强版工单模型"""
    work_order_id: str
    title: str
    description: str
    priority: str  # low/medium/high/critical
    status: str  # created/assigned/in_progress/resolved/closed
    instance_id: Optional[str] = None
    category: str = "maintenance"
    created_at: float
    created_by: str
    assigned_to: Optional[str] = None
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    resolution: Optional[str] = None
    approval_required: bool = False
    approval_status: Optional[str] = None
    comments: list[dict] = Field(default_factory=list)


# ============================================================================
# 增强版数据生成器
# ============================================================================

def gen_enhanced_alert(
    alert_id: str,
    alert_code: str = "CPU_HIGH",
    severity: str = "warning",
    instance_id: str = "INS-001",
    instance_name: str = "PROD-ORDER-DB",
    metric_value: float = 85.5,
    threshold: float = 80.0,
    custom_override: Optional[dict] = None
) -> EnhancedAlert:
    """生成增强版告警"""
    now = time.time()
    occurred_at = now - random.randint(60, 3600)
    
    alert_types = {
        "CPU_HIGH": ("CPU使用率过高", "CPU使用率达到{mvalue}%，超过阈值{threshold}%"),
        "MEMORY_HIGH": ("内存使用率过高", "内存使用率达到{mvalue}%，超过阈值{threshold}%"),
        "DISK_HIGH": ("磁盘使用率过高", "磁盘使用率达到{mvalue}%，超过阈值{threshold}%"),
        "LOCK_WAIT_TIMEOUT": ("锁等待超时", "实例发生锁等待超时，当前等待时间{mvalue}秒"),
        "CONNECTION_HIGH": ("连接数过高", "当前连接数{mvalue}，超过阈值{threshold}"),
        "SLOW_QUERY": ("慢查询检测", "检测到执行时间超过{threshold}秒的查询，当前{mvalue}秒"),
        "REPLICATION_LAG": ("复制延迟", "主从复制延迟达到{mvalue}秒，超过阈值{threshold}秒"),
        "BACKUP_FAILED": ("备份失败", "数据库备份任务执行失败"),
    }
    
    alert_name, message_template = alert_types.get(
        alert_code,
        ("未知告警", "发生未知类型的告警")
    )
    
    message = message_template.format(mvalue=metric_value, threshold=threshold)
    
    # 生成自定义字段
    custom_fields = AlertCustomFields(
        host_ip=f"192.168.1.{random.randint(10, 250)}",
        region=random.choice(["华东-上海", "华北-北京", "华南-广州", "西南-成都"]),
        cluster=f"prod-cluster-{random.randint(1, 5):02d}",
        environment="production",
        business_line=random.choice(["订单系统", "用户中心", "支付系统", "分析平台"]),
        on_call=random.choice(["张三", "李四", "王五", "赵六"]),
        extra={"priority_group": random.choice(["P1", "P2", "P3"])}
    )
    
    # 生成注解
    annotations = AlertAnnotation(
        first_occurrence=datetime.fromtimestamp(occurred_at).isoformat() + "Z",
        last_evaluation=datetime.fromtimestamp(now).isoformat() + "Z",
        incident_id=f"INC-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}",
        runbook_url=f"https://wiki.example.com/runbooks/{alert_code.lower()}",
        dashboard_url=f"https://grafana.example.com/d/{instance_id.lower()}",
        tags=[alert_code, severity, instance_id]
    )
    
    # 生成嵌套告警（部分告警有）
    nested_alerts = []
    if alert_code == "CPU_HIGH" and random.random() > 0.5:
        nested_alerts.append(NestedAlert(
            alert_id=f"ALT-{uuid.uuid4().hex[:8].upper()}",
            alert_code="LOAD_HIGH",
            alert_name="系统负载过高",
            severity="info",
            occurred_at=occurred_at + 30
        ))
    
    # 关联实例
    related_instances = []
    if random.random() > 0.7:
        related_instances.append({
            "instance_id": f"INS-{random.randint(2, 5):03d}",
            "instance_name": f"PROD-SUB-DB-{random.randint(1, 5)}",
            "relationship": "same_cluster"
        })
    
    alert_data = {
        "alert_id": alert_id,
        "alert_code": alert_code,
        "alert_name": alert_name,
        "severity": severity,
        "instance_id": instance_id,
        "instance_name": instance_name,
        "message": message,
        "metric_value": metric_value,
        "threshold": threshold,
        "unit": "%" if "%" in alert_name else ("秒" if "秒" in alert_name else ""),
        "occurred_at": occurred_at,
        "duration_seconds": int(now - occurred_at),
        "status": "firing",
        "acknowledged": False,
        "custom_fields": custom_fields,
        "annotations": annotations,
        "nested_alerts": nested_alerts,
        "related_instances": related_instances,
        "timestamp": now
    }
    
    # 应用覆盖
    if custom_override:
        alert_data.update(custom_override)
    
    return EnhancedAlert(**alert_data)


def gen_enhanced_instance(
    instance_id: str = "INS-001",
    db_type: str = "postgresql",
    instance_name: str = "PROD-ORDER-DB",
    role: str = "primary",
    custom_override: Optional[dict] = None
) -> EnhancedInstance:
    """生成增强版实例"""
    now = time.time()
    
    instance_data = {
        "instance_id": instance_id,
        "instance_name": instance_name,
        "db_type": db_type,
        "version": f"{db_type.capitalize()} {random.choice(['14.5', '14.7', '15.2', '8.0.32', '19c'])}",
        "status": "running",
        "role": role,
        "host": f"192.168.1.{random.randint(10, 250)}",
        "port": random.choice([3306, 5432, 1521]),
        "region": random.choice(["华东-上海", "华北-北京", "华南-广州"]),
        "cluster": f"prod-cluster-{random.randint(1, 5):02d}",
        "cpu_percent": round(random.uniform(20, 90), 1),
        "memory_percent": round(random.uniform(40, 85), 1),
        "disk_percent": round(random.uniform(30, 75), 1),
        "connections": random.randint(50, 400),
        "max_connections": 500,
        "buffer_cache_hit_ratio": round(random.uniform(95, 99.9), 2),
        "transaction_per_second": round(random.uniform(100, 2000), 2),
        "ha_enabled": random.random() > 0.3,
        "ha_role": role,
        "backup_enabled": random.random() > 0.2,
        "last_backup_time": now - random.randint(3600, 86400) if random.random() > 0.2 else None,
        "tags": ["production", instance_id.lower().replace("-", "_"), "core"],
        "uptime_seconds": random.randint(86400, 2592000),
        "created_at": (datetime.now() - timedelta(days=random.randint(30, 365))).isoformat() + "Z",
        "timestamp": now
    }
    
    if custom_override:
        instance_data.update(custom_override)
    
    return EnhancedInstance(**instance_data)


def gen_enhanced_sessions(limit: int = 10) -> list[EnhancedSession]:
    """生成增强版会话列表"""
    now = time.time()
    sessions = []
    
    statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "INACTIVE", "INACTIVE"]
    wait_events = [None, None, "db file sequential read", "buffer busy", "log file sync"]
    
    for i in range(min(limit, 50)):
        logon = now - random.randint(60, 86400)
        sessions.append(EnhancedSession(
            sid=1001 + i,
            serial=2001 + i,
            username=random.choice(["app_user_0", "app_user_1", "app_user_2", "postgres", "system"]),
            status=random.choice(statuses),
            program=f"python-{i}.exe",
            machine=f"app-server-{i % 3 + 1}",
            sql_id=f"sql_{uuid.uuid4().hex[:8]}" if i % 2 == 0 else None,
            sql_text=f"SELECT * FROM table_{i} WHERE id = {i}..." if i % 2 == 0 else None,
            wait_event=random.choice(wait_events),
            wait_seconds=random.randint(0, 300) if random.random() > 0.7 else 0,
            logon_time=logon,
            client_ip=f"192.168.1.{random.randint(100, 200)}",
            background_process=False,
            osuser=f"appuser_{i % 3}",
            process=str(random.randint(1000, 9999))
        ))
    
    return sessions


def gen_enhanced_locks(limit: int = 5) -> list[EnhancedLock]:
    """生成增强版锁信息"""
    locks = []
    for i in range(min(limit, 10)):
        wait_sid = 1001 + i
        blocker_sid = 1001 + i + 1
        locks.append(EnhancedLock(
            wait_sid=wait_sid,
            wait_serial=2001 + i,
            wait_sql_id=f"sql_{uuid.uuid4().hex[:8]}",
            wait_username=f"app_user_{i}",
            lock_type=random.choice(["transaction", "table", "share"]),
            mode_held="Exclusive",
            mode_requested="Share",
            lock_id1=str(random.randint(10000, 99999)),
            lock_id2=str(random.randint(10000, 99999)),
            lock_table=random.choice(["orders", "users", "products", "inventory"]),
            blocker_sid=blocker_sid,
            blocker_serial=2001 + i + 1,
            blocker_sql_id=f"sql_{uuid.uuid4().hex[:8]}",
            blocker_username=f"app_user_{i+1}",
            wait_seconds=random.randint(10, 600),
            chain_length=random.randint(1, 3)
        ))
    return locks


def gen_enhanced_slow_sqls(limit: int = 10) -> list[EnhancedSlowSQL]:
    """生成增强版慢SQL列表"""
    now = time.time()
    sqls = []
    
    sql_templates = [
        "SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - {d}",
        "UPDATE inventory SET quantity = quantity - 1 WHERE product_id = {id}",
        "SELECT count(*) FROM sales GROUP BY region HAVING sum(amount) > 10000",
        "SELECT u.*, o.* FROM users u LEFT JOIN orders o ON u.id = o.user_id",
        "DELETE FROM logs WHERE created_at < SYSDATE - {d}",
    ]
    
    for i in range(min(limit, 20)):
        elapsed = random.uniform(1.0, 60.0)
        executions = random.randint(10, 5000)
        sqls.append(EnhancedSlowSQL(
            sql_id=f"sql_{uuid.uuid4().hex[:8]}",
            sql_text=random.choice(sql_templates).format(d=random.randint(1, 30), id=i),
            executions=executions,
            elapsed_time_sec=round(elapsed, 3),
            avg_elapsed_sec=round(elapsed / executions, 6) if executions > 0 else 0,
            disk_reads=random.randint(1000, 100000),
            buffer_gets=random.randint(5000, 500000),
            rows_processed=random.randint(100, 50000),
            first_load_time=now - random.randint(86400, 604800),
            last_active_time=now - random.randint(60, 86400),
            module=f"app_module_{i % 3}",
            parsing_schema="public",
            optimizer_mode="ALL_ROWS"
        ))
    
    return sqls


def gen_sql_plan(sql_id: str) -> list[SQLPlanStep]:
    """生成SQL执行计划"""
    return [
        SQLPlanStep(
            id=0,
            operation="SELECT",
            options=None,
            object_name=None,
            optimizer="ALL_ROWS",
            cost=100,
            cardinality=1000,
            bytes=50000
        ),
        SQLPlanStep(
            id=1,
            operation="HASH JOIN",
            options=None,
            object_name=None,
            optimizer="ALL_ROWS",
            cost=80,
            cardinality=1000,
            bytes=40000
        ),
        SQLPlanStep(
            id=2,
            operation="TABLE ACCESS FULL",
            options=None,
            object_name="ORDERS",
            object_type="TABLE",
            optimizer="ALL_ROWS",
            cost=50,
            cardinality=800,
            bytes=32000,
            filter="STATUS='pending'",
            access_predicate="CREATED_AT>SYSDATE-7"
        ),
        SQLPlanStep(
            id=3,
            operation="TABLE ACCESS FULL",
            options=None,
            object_name="USERS",
            object_type="TABLE",
            optimizer="ALL_ROWS",
            cost=30,
            cardinality=200,
            bytes=8000
        )
    ]


def gen_enhanced_tablespaces() -> list[EnhancedTablespace]:
    """生成增强版表空间列表"""
    return [
        EnhancedTablespace(
            tablespace_name="SYSTEM",
            status="ONLINE",
            total_size_mb=10240,
            used_size_mb=8192,
            free_size_mb=2048,
            usage_percent=80.0,
            auto_extensible=True,
            max_size_mb=32768,
            increment_mb=1024
        ),
        EnhancedTablespace(
            tablespace_name="USERS",
            status="ONLINE",
            total_size_mb=5120,
            used_size_mb=3072,
            free_size_mb=2048,
            usage_percent=60.0,
            auto_extensible=True,
            max_size_mb=20480,
            increment_mb=512
        ),
        EnhancedTablespace(
            tablespace_name="UNDO_TBS",
            status="ONLINE",
            total_size_mb=8192,
            used_size_mb=4096,
            free_size_mb=4096,
            usage_percent=50.0,
            auto_extensible=True,
            max_size_mb=32768,
            increment_mb=1024
        ),
        EnhancedTablespace(
            tablespace_name="TEMP_TBS",
            status="ONLINE",
            total_size_mb=4096,
            used_size_mb=512,
            free_size_mb=3584,
            usage_percent=12.5,
            auto_extensible=True,
            max_size_mb=16384,
            increment_mb=256
        ),
    ]


def gen_enhanced_workorder(
    title: str,
    description: str,
    priority: str = "medium",
    instance_id: Optional[str] = None,
    category: str = "maintenance"
) -> EnhancedWorkOrder:
    """生成增强版工单"""
    now = time.time()
    return EnhancedWorkOrder(
        work_order_id=f"WO-{int(now)}-{random.randint(100, 999)}",
        title=title,
        description=description,
        priority=priority,
        status="created",
        instance_id=instance_id,
        category=category,
        created_at=now,
        created_by="agent_system",
        assigned_to=None,
        resolved_at=None,
        resolved_by=None,
        resolution=None,
        approval_required=priority in ["high", "critical"],
        approval_status="pending" if priority in ["high", "critical"] else None,
        comments=[]
    )
