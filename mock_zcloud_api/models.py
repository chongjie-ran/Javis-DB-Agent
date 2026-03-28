"""
zCloud API Mock Server
用于本地开发和测试zCloud智能体系统
"""
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ============================================================================
# 基础模型
# ============================================================================

class Instance(BaseModel):
    instance_id: str
    instance_name: str
    db_type: str  # oracle/postgresql/mysql
    version: str
    status: str  # running/stopped
    role: str  # primary/standby
    host: str
    port: int
    cpu_percent: float
    memory_percent: float
    connections: int
    max_connections: int
    uptime_seconds: int
    created_at: str

class Alert(BaseModel):
    alert_id: str
    alert_code: str
    alert_name: str
    severity: str  # critical/warning/info
    instance_id: str
    instance_name: str
    message: str
    metric_value: float
    threshold: float
    occurred_at: float
    status: str  # firing/resolved
    acknowledged: bool = False

class Session(BaseModel):
    sid: int
    serial: int
    username: str
    status: str  # ACTIVE/INACTIVE
    program: str
    machine: str
    sql_id: Optional[str] = None
    wait_event: Optional[str] = None
    seconds_in_wait: int = 0
    logon_time: float
    last_call_et: int

class LockInfo(BaseModel):
    wait_sid: int
    wait_serial: int
    wait_sql_id: Optional[str]
    lock_type: str
    mode_held: str
    mode_requested: str
    lock_id1: str
    lock_id2: str
    blocker_sid: int
    blocker_serial: int
    blocker_sql_id: Optional[str]
    wait_seconds: int
    chain_length: int

class SlowSQL(BaseModel):
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

class TopSQL(BaseModel):
    sql_id: str
    sql_text: str
    sort_type: str  # cpu/buffer_gets/disk_reads
    value: float
    executions: int

class SQLPlan(BaseModel):
    operation: str
    object_name: Optional[str] = None
    options: Optional[str] = None
    cost: int
    cardinality: int
    bytes: Optional[int] = None
    filter: Optional[str] = None
    access_predicate: Optional[str] = None

class ReplicationInfo(BaseModel):
    instance_id: str
    role: str
    replication_enabled: bool
    replicas: list

class Parameter(BaseModel):
    name: str
    value: str
    default_value: str
    is_modified: bool
    description: Optional[str] = None

class DiskUsage(BaseModel):
    tablespace_name: str
    total_mb: float
    used_mb: float
    free_mb: float
    used_percent: float
    autoextensible: bool

class CapacityInfo(BaseModel):
    instance_id: str
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_used_percent: float
    tablespaces: list[DiskUsage]

class HAStatus(BaseModel):
    instance_id: str
    ha_enabled: bool
    ha_role: str  # primary/standby
    primary_instance: Optional[str] = None
    standby_instances: list[str] = []
    last_switch_time: Optional[float] = None
    switch_reason: Optional[str] = None

class InspectionTask(BaseModel):
    task_id: str
    instance_id: str
    inspection_type: str  # quick/full/security
    status: str  # pending/running/completed/failed
    health_score: int
    started_at: float
    completed_at: Optional[float] = None
    findings: list

class WorkOrderCreate(BaseModel):
    title: str
    description: str
    priority: str  # low/medium/high/critical
    instance_id: Optional[str] = None
    category: str = "maintenance"

class WorkOrder(BaseModel):
    work_order_id: str
    title: str
    description: str
    priority: str
    status: str  # created/assigned/in_progress/resolved/closed
    instance_id: Optional[str]
    category: str
    created_at: float
    created_by: str

class ConfigDeviation(BaseModel):
    instance_id: str
    parameter_name: str
    current_value: str
    standard_value: str
    deviation_type: str  # higher/lower/missing
    severity: str  # high/medium/low
    description: str

# ============================================================================
# Mock 数据生成
# ============================================================================

def gen_instance() -> Instance:
    return Instance(
        instance_id="INS-001",
        instance_name="PROD-ORDER-DB",
        db_type="postgresql",
        version="PostgreSQL 14.5",
        status="running",
        role="primary",
        host="192.168.1.10",
        port=5432,
        cpu_percent=45.2,
        memory_percent=68.5,
        connections=156,
        max_connections=500,
        uptime_seconds=864000,
        created_at="2025-01-01T00:00:00Z"
    )

def gen_alerts(alert_id: str) -> Alert:
    now = time.time()
    return Alert(
        alert_id=alert_id,
        alert_code="LOCK_WAIT_TIMEOUT",
        alert_name="锁等待超时",
        severity="warning",
        instance_id="INS-001",
        instance_name="PROD-ORDER-DB",
        message="实例发生锁等待超时，当前等待时间120秒",
        metric_value=120.0,
        threshold=60.0,
        occurred_at=now - 300,
        status="firing",
        acknowledged=False
    )

def gen_sessions(limit: int = 10) -> list[Session]:
    now = time.time()
    return [
        Session(
            sid=1001+i, serial=2001+i,
            username=f"app_user_{i}" if i % 3 else "postgres",
            status="ACTIVE" if i % 2 else "INACTIVE",
            program=f"python_{i}.exe",
            machine=f"app-server-{i%3+1}",
            sql_id=f"sql_{'a'*8}_{i}" if i % 2 else None,
            wait_event="db file sequential read" if i % 3 == 0 else None,
            seconds_in_wait=5 if i % 3 == 0 else 0,
            logon_time=now - 3600*(i+1),
            last_call_et=3600 if i % 2 else 0
        )
        for i in range(min(limit, 10))
    ]

def gen_locks() -> list[LockInfo]:
    return [
        LockInfo(
            wait_sid=1001, wait_serial=2001,
            wait_sql_id="sql_aaaaaaaa",
            lock_type="TX", mode_held="Exclusive",
            mode_requested="Share", lock_id1="12345", lock_id2="67890",
            blocker_sid=1002, blocker_serial=2002,
            blocker_sql_id="sql_bbbbbbbb",
            wait_seconds=120, chain_length=2
        )
    ]

def gen_slow_sqls(limit: int = 10) -> list[SlowSQL]:
    now = time.time()
    return [
        SlowSQL(
            sql_id=f"sql_{'a'*(8-i)}",
            sql_text=f"SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - {i}...",
            executions=1000-i*100,
            elapsed_time_sec=30.5-i*3,
            avg_elapsed_sec=(30.5-i*3)/max(1000-i*100, 1),
            disk_reads=50000-i*5000, buffer_gets=100000-i*10000,
            rows_processed=10000-i*1000,
            first_load_time=now-86400*(i+1),
            last_active_time=now-3600*(i+1)
        )
        for i in range(min(limit, 5))
    ]

def gen_top_sqls() -> list[TopSQL]:
    return [
        TopSQL(sql_id="sql_aaaa1111", sql_text="SELECT * FROM orders WHERE status='pending'...", sort_type="cpu", value=500.5, executions=100),
        TopSQL(sql_id="sql_bbbb2222", sql_text="SELECT count(*) FROM sales GROUP BY region...", sort_type="buffer_gets", value=300.2, executions=200),
        TopSQL(sql_id="sql_cccc3333", sql_text="UPDATE inventory SET quantity=quantity-1...", sort_type="disk_reads", value=200.1, executions=50),
    ]

def gen_replication() -> ReplicationInfo:
    now = time.time()
    return ReplicationInfo(
        instance_id="INS-001", role="primary",
        replication_enabled=True,
        replicas=[{
            "replica_id": "REP-001", "host": "192.168.1.11",
            "port": 5432, "role": "read_replica",
            "status": "streaming", "lag_seconds": 2.5,
            "lag_bytes": 102400, "last_heartbeat": now-2.5
        }]
    )

def gen_parameters() -> list[Parameter]:
    return [
        Parameter(name="max_connections", value="500", default_value="100", is_modified=True, description="最大连接数"),
        Parameter(name="shared_buffers", value="256MB", default_value="128MB", is_modified=True, description="共享缓冲区大小"),
        Parameter(name="work_mem", value="4MB", default_value="4MB", is_modified=False, description="工作内存"),
        Parameter(name="effective_cache_size", value="4GB", default_value="4GB", is_modified=False),
        Parameter(name="maintenance_work_mem", value="64MB", default_value="64MB", is_modified=False),
        Parameter(name="checkpoint_timeout", value="15min", default_value="5min", is_modified=True, description="检查点超时"),
    ]

def gen_disk_usage() -> list[DiskUsage]:
    return [
        DiskUsage(tablespace_name="pg_default", total_mb=102400, used_mb=71680, free_mb=30720, used_percent=70.0, autoextensible=True),
        DiskUsage(tablespace_name="pg_global", total_mb=8192, used_mb=4096, free_mb=4096, used_percent=50.0, autoextensible=True),
        DiskUsage(tablespace_name="orders_tbs", total_mb=512000, used_mb=460800, free_mb=51200, used_percent=90.0, autoextensible=True),
    ]

def gen_ha_status() -> HAStatus:
    return HAStatus(
        instance_id="INS-001", ha_enabled=True, ha_role="primary",
        primary_instance=None,
        standby_instances=["INS-002"],
        last_switch_time=time.time()-86400*7,
        switch_reason="计划切换-维护"
    )

def gen_inspection_result(task_id: str) -> InspectionTask:
    now = time.time()
    findings = []
    
    # 模拟巡检发现
    findings.append({"type": "性能", "severity": "warning", "description": "过去1小时有5条慢SQL", "item": "slow_sql_count"})
    findings.append({"type": "容量", "severity": "info", "description": "表空间使用率78%，建议关注", "item": "tablespace_usage"})
    findings.append({"type": "连接", "severity": "info", "description": "当前连接数156/500，正常", "item": "connection_usage"})
    
    return InspectionTask(
        task_id=task_id,
        instance_id="INS-001",
        inspection_type="quick",
        status="completed",
        health_score=85,
        started_at=now-60,
        completed_at=now,
        findings=findings
    )

def gen_workorder(wo: WorkOrderCreate) -> WorkOrder:
    return WorkOrder(
        work_order_id=f"WO-{int(time.time())}",
        title=wo.title, description=wo.description,
        priority=wo.priority, instance_id=wo.instance_id,
        category=wo.category, status="created",
        created_at=time.time(), created_by="agent_system"
    )

def gen_config_deviation() -> list[ConfigDeviation]:
    return [
        ConfigDeviation(
            instance_id="INS-001", parameter_name="max_connections",
            current_value="500", standard_value="300",
            deviation_type="higher", severity="low",
            description="当前值高于标准配置30%"
        ),
        ConfigDeviation(
            instance_id="INS-001", parameter_name="checkpoint_timeout",
            current_value="15min", standard_value="10min",
            deviation_type="higher", severity="medium",
            description="检查点超时设置过长，可能影响恢复时间"
        )
    ]
