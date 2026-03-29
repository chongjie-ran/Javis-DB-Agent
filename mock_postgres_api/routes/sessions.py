"""PG会话API - pg_stat_activity风格"""
import time
import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel


router = APIRouter()


class SessionRow(BaseModel):
    """会话行"""
    pid: int
    usename: str
    datname: str
    state: str
    query: str
    query_start: Optional[float] = None
    backend_start: float
    xact_start: Optional[float] = None
    wait_event_type: Optional[str] = None
    wait_event: Optional[str] = None
    client_addr: str
    client_port: int
    application_name: str
    command: str


# 模拟会话数据
_MOCK_SESSIONS = [
    {"pid": 1001, "usename": "app_user", "datname": "orders_db", "state": "active", "query": "SELECT * FROM orders WHERE status = 'pending';", "query_start": time.time() - 5, "backend_start": time.time() - 3600, "xact_start": time.time() - 5, "wait_event_type": None, "wait_event": None, "client_addr": "192.168.1.10", "client_port": 54321, "application_name": "psql", "command": "SELECT"},
    {"pid": 1002, "usename": "app_user", "datname": "orders_db", "state": "idle", "query": "<idle in transaction>", "query_start": time.time() - 120, "backend_start": time.time() - 7200, "xact_start": time.time() - 120, "wait_event_type": "Lock", "wait_event": "transactionid", "client_addr": "192.168.1.11", "client_port": 54322, "application_name": "python", "command": "UPDATE"},
    {"pid": 1003, "usename": "app_user", "datname": "orders_db", "state": "active", "query": "INSERT INTO order_items (order_id, product_id, quantity) VALUES (1, 100, 5);", "query_start": time.time() - 1, "backend_start": time.time() - 1800, "xact_start": time.time() - 1, "wait_event_type": None, "wait_event": None, "client_addr": "192.168.1.12", "client_port": 54323, "application_name": "python", "command": "INSERT"},
    {"pid": 1004, "usename": "postgres", "datname": "postgres", "state": "active", "query": "SELECT datname, numbackends, xact_commit, xact_rollback FROM pg_stat_database;", "query_start": time.time() - 0.5, "backend_start": time.time() - 1728000, "xact_start": time.time() - 0.5, "wait_event_type": None, "wait_event": None, "client_addr": "127.0.0.1", "client_port": 54324, "application_name": "pg_monitor", "command": "SELECT"},
    {"pid": 1005, "usename": "app_user", "datname": "orders_db", "state": "idle", "query": "<idle>", "query_start": None, "backend_start": time.time() - 600, "xact_start": None, "wait_event_type": None, "wait_event": None, "client_addr": "192.168.1.13", "client_port": 54325, "application_name": "python", "command": ""},
    {"pid": 1006, "usename": "app_user", "datname": "orders_db", "state": "active", "query": "BEGIN; SELECT * FROM products FOR UPDATE; UPDATE products SET stock = stock - 1 WHERE id = 100; COMMIT;", "query_start": time.time() - 3, "backend_start": time.time() - 300, "xact_start": time.time() - 3, "wait_event_type": "Lock", "wait_event": "relation", "client_addr": "192.168.1.14", "client_port": 54326, "application_name": "python", "command": "SELECT"},
    {"pid": 1007, "usename": "replicator", "datname": "orders_db", "state": "streaming", "query": "COPY (SELECT * FROM orders) TO STDOUT;", "query_start": time.time() - 0.1, "backend_start": time.time() - 86400, "xact_start": time.time() - 0.1, "wait_event_type": None, "wait_event": None, "client_addr": "192.168.1.102", "client_port": 54327, "application_name": "pg_basebackup", "command": "COPY"},
]


@router.get("/sessions")
async def get_sessions(
    limit: int = Query(100, ge=1, le=500),
    datname: str = Query("", description="数据库名过滤"),
    state: str = Query("", description="状态过滤: active/idle/idle in transaction"),
    username: str = Query("", description="用户名过滤"),
):
    """获取PostgreSQL会话列表 - pg_stat_activity风格"""
    sessions = _MOCK_SESSIONS.copy()
    
    if datname:
        sessions = [s for s in sessions if s["datname"] == datname]
    if state:
        sessions = [s for s in sessions if s["state"] == state]
    if username:
        sessions = [s for s in sessions if s["usename"] == username]
    
    sessions = sessions[:limit]
    
    # 添加一些随机变化
    if len(sessions) < limit:
        for i in range(min(limit - len(sessions), 5)):
            pid = 2000 + i
            sessions.append({
                "pid": pid,
                "usename": random.choice(["app_user", "app_user", "postgres"]),
                "datname": random.choice(["orders_db", "orders_db", "postgres"]),
                "state": random.choice(["active", "idle", "idle in transaction"]),
                "query": random.choice(["SELECT 1;", "<idle>", "<idle in transaction>"]),
                "query_start": time.time() - random.randint(1, 300) if random.random() > 0.3 else None,
                "backend_start": time.time() - random.randint(60, 3600),
                "xact_start": time.time() - random.randint(1, 100) if random.random() > 0.5 else None,
                "wait_event_type": random.choice([None, "Lock", "IO"]) if random.random() > 0.7 else None,
                "wait_event": random.choice(["transactionid", "relation", "DataFileRead"]) if random.random() > 0.7 else None,
                "client_addr": f"192.168.1.{random.randint(10, 20)}",
                "client_port": random.randint(50000, 60000),
                "application_name": random.choice(["python", "psql", "node"]),
                "command": random.choice(["SELECT", "INSERT", "UPDATE", "DELETE"]),
            })
    
    return {
        "sessions": sessions,
        "total": len(sessions),
        "active_count": len([s for s in sessions if s["state"] == "active"]),
        "idle_count": len([s for s in sessions if s["state"] == "idle"]),
        "idle_in_transaction_count": len([s for s in sessions if s["state"] == "idle in transaction"]),
    }


@router.get("/sessions/{pid}")
async def get_session_by_pid(pid: int):
    """获取指定PID的会话详情"""
    for s in _MOCK_SESSIONS:
        if s["pid"] == pid:
            return {"session": s}
    return {"error": "Session not found", "pid": pid}
