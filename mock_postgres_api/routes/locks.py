"""PG锁API - pg_locks视图风格"""
import time
import random
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional


router = APIRouter()


class LockRow(BaseModel):
    """锁行"""
    locktype: str
    database: Optional[int]
    relation: Optional[int]
    page: Optional[int]
    tuple: Optional[int]
    virtualxid: Optional[str]
    transactionid: Optional[str]
    lock_class: int
    objid: Optional[int]
    objsubid: Optional[int]
    pid: int
    mode: str
    granted: bool
    fastpath: bool
    # Extended fields (not standard pg_locks)
    relname: Optional[str] = None
    schemaname: Optional[str] = None
    blocking_pid: Optional[int] = None


_MOCK_LOCKS = [
    {
        "locktype": "transactionid",
        "database": 16384,
        "relation": None,
        "page": None,
        "tuple": None,
        "virtualxid": None,
        "transactionid": "456789",
        "lock_class": 0,
        "objid": None,
        "objsubid": None,
        "pid": 1002,
        "mode": "ExclusiveLock",
        "granted": False,
        "fastpath": False,
        "blocking_pid": 1006,
    },
    {
        "locktype": "relation",
        "database": 16384,
        "relation": 123456,
        "page": None,
        "tuple": None,
        "virtualxid": None,
        "transactionid": None,
        "lock_class": 0,
        "objid": 123456,
        "objsubid": None,
        "pid": 1001,
        "mode": "ShareLock",
        "granted": True,
        "fastpath": True,
        "relname": "orders",
        "schemaname": "public",
        "blocking_pid": None,
    },
    {
        "locktype": "relation",
        "database": 16384,
        "relation": 123456,
        "page": None,
        "tuple": None,
        "virtualxid": None,
        "transactionid": None,
        "lock_class": 0,
        "objid": 123456,
        "objsubid": None,
        "pid": 1006,
        "mode": "RowExclusiveLock",
        "granted": False,
        "fastpath": False,
        "relname": "orders",
        "schemaname": "public",
        "blocking_pid": 1001,
    },
    {
        "locktype": "tuple",
        "database": 16384,
        "relation": 123456,
        "page": 5,
        "tuple": 10,
        "virtualxid": None,
        "transactionid": None,
        "lock_class": 0,
        "objid": None,
        "objsubid": None,
        "pid": 1003,
        "mode": "ShareLock",
        "granted": True,
        "fastpath": True,
        "relname": "order_items",
        "schemaname": "public",
        "blocking_pid": None,
    },
    {
        "locktype": "virtualxid",
        "database": None,
        "relation": None,
        "page": None,
        "tuple": None,
        "virtualxid": "1/145",
        "transactionid": None,
        "lock_class": 0,
        "objid": None,
        "objsubid": None,
        "pid": 1005,
        "mode": "ExclusiveLock",
        "granted": True,
        "fastpath": True,
        "blocking_pid": None,
    },
]


@router.get("/locks")
async def get_locks(
    locktype: str = "",
    granted: bool = None,
    pid: int = None,
):
    """获取PostgreSQL锁信息 - pg_locks视图风格"""
    locks = _MOCK_LOCKS.copy()
    
    if locktype:
        locks = [l for l in locks if l["locktype"] == locktype]
    if granted is not None:
        locks = [l for l in locks if l["granted"] == granted]
    if pid:
        locks = [l for l in locks if l["pid"] == pid]
    
    # 添加等待信息
    wait_seconds = {}
    for lock in locks:
        if not lock["granted"] and lock.get("blocking_pid"):
            wait_seconds[lock["pid"]] = random.randint(10, 120)
    
    return {
        "locks": locks,
        "total": len(locks),
        "granted_count": len([l for l in locks if l["granted"]]),
        "waiting_count": len([l for l in locks if not l["granted"]]),
        "wait_seconds": wait_seconds,
    }


@router.get("/locks/graph")
async def get_lock_graph():
    """获取锁等待图"""
    nodes = []
    edges = []
    
    for lock in _MOCK_LOCKS:
        if lock["pid"] not in [n["pid"] for n in nodes]:
            nodes.append({"pid": lock["pid"], "state": "waiting" if not lock["granted"] else "holding"})
        if lock.get("blocking_pid") and lock["blocking_pid"] not in [n["pid"] for n in nodes]:
            nodes.append({"pid": lock["blocking_pid"], "state": "holding"})
        if lock.get("blocking_pid"):
            edges.append({
                "from": lock["blocking_pid"],
                "to": lock["pid"],
                "lock_type": lock["locktype"],
                "mode": lock["mode"],
            })
    
    return {"nodes": nodes, "edges": edges}
