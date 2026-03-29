"""PG复制API - 流复制状态风格"""
import time
import random
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List


router = APIRouter()


class ReplicationSlot(BaseModel):
    slot_name: str
    plugin: str
    slot_type: str
    active: bool
    restart_lsn: str
    confirmed_flush_lsn: str


class WALReceiver(BaseModel):
    pid: int
    status: str
    receive_start_lsn: str
    receive_start_tli: int
    written_lsn: str
    flushed_lsn: str
    received_tli: int
    last_msg_send_time: float
    last_msg_receipt_time: float
    latest_end_lsn: str
    latest_end_time: float


class ReplicationInfo(BaseModel):
    role: str
    replication_enabled: bool
    wal_level: str
    max_replication_slots: int
    max_wal_senders: int
    wal_sender_halt: bool
    replication_slots: List[ReplicationSlot]
    wal_receivers: List[WALReceiver]
    wal_lag: float
    replay_lag: float
    flush_lag: float
    write_lag: float


_MOCK_REPLICATION = {
    "role": "primary",
    "replication_enabled": True,
    "wal_level": "logical",
    "max_replication_slots": 10,
    "max_wal_senders": 10,
    "wal_sender_halt": False,
    "replication_slots": [
        {
            "slot_name": "replica_slot_1",
            "plugin": "pgoutput",
            "slot_type": "logical",
            "active": True,
            "restart_lsn": "0/7000000",
            "confirmed_flush_lsn": "0/7000100",
        },
        {
            "slot_name": "replica_slot_2",
            "plugin": "pgoutput",
            "slot_type": "logical",
            "active": False,
            "restart_lsn": "0/5000000",
            "confirmed_flush_lsn": "0/5000100",
        },
    ],
    "wal_receivers": [
        {
            "pid": 12345,
            "status": "streaming",
            "receive_start_lsn": "0/3000000",
            "receive_start_tli": 1,
            "written_lsn": "0/7000058",
            "flushed_lsn": "0/7000058",
            "received_tli": 1,
            "last_msg_send_time": time.time() - 0.1,
            "last_msg_receipt_time": time.time() - 0.1,
            "latest_end_lsn": "0/7000058",
            "latest_end_time": time.time() - 0.1,
        }
    ],
    "wal_lag": 0.3,
    "replay_lag": 0.5,
    "flush_lag": 0.4,
    "write_lag": 0.2,
}


@router.get("/replication")
async def get_replication():
    """获取PostgreSQL流复制状态"""
    data = _MOCK_REPLICATION.copy()
    
    # 添加随机延迟变化
    data["wal_lag"] = round(random.uniform(0.1, 2.0), 2)
    data["replay_lag"] = round(random.uniform(0.1, 3.0), 2)
    data["flush_lag"] = round(random.uniform(0.1, 2.5), 2)
    data["write_lag"] = round(random.uniform(0.05, 1.5), 2)
    
    return data


@router.get("/replication/slots")
async def get_replication_slots():
    """获取复制槽信息"""
    return {
        "slots": _MOCK_REPLICATION["replication_slots"],
        "total": len(_MOCK_REPLICATION["replication_slots"]),
        "active": len([s for s in _MOCK_REPLICATION["replication_slots"] if s["active"]]),
    }


@router.get("/replication/lag")
async def get_replication_lag():
    """获取复制延迟详情"""
    return {
        "wal_lag_mb": round(random.uniform(0.1, 2.0), 3),
        "replay_lag_mb": round(random.uniform(0.1, 3.0), 3),
        "flush_lag_mb": round(random.uniform(0.1, 2.5), 3),
        "write_lag_mb": round(random.uniform(0.05, 1.5), 3),
        "wal_lag_seconds": round(random.uniform(0.01, 1.0), 3),
        "replay_lag_seconds": round(random.uniform(0.01, 1.5), 3),
    }


@router.get("/replication/wal_senders")
async def get_wal_senders():
    """获取WAL发送者信息"""
    return {
        "wal_senders": [
            {
                "pid": 12345,
                "usesysid": 10,
                "usename": "replicator",
                "application_name": "walreceiver",
                "client_addr": "192.168.1.102",
                "client_hostname": "",
                "client_port": 54328,
                "backend_start": time.time() - 86400,
                "backend_xmin": 1845,
                "state": "streaming",
                "sent_lsn": "0/7000060",
                "write_lsn": "0/7000058",
                "flush_lsn": "0/7000058",
                "replay_lsn": "0/7000058",
                "write_lag": "0.2 s",
                "flush_lag": "0.4 s",
                "replay_lag": "0.5 s",
                "sync_priority": 1,
                "sync_state": "sync",
            }
        ]
    }
