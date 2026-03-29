"""PG表膨胀分析API"""
import random
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional


router = APIRouter()


class BloatRow(BaseModel):
    """膨胀行"""
    schemaname: str
    tablename: str
    tuples_len: int
    wastedbytes: int
    wasted_truples: int
    wasted_percent: float
    iname_len: int
    wasted_ibytes: int
    wasted_iitems: int
    wasted_ipercent: float
    real_row_count: int
    extra: Optional[str] = None


_MOCK_BLOAT = [
    {
        "schemaname": "public",
        "tablename": "orders",
        "tuples_len": 5000000,
        "wastedbytes": 104857600,  # ~100MB
        "wasted_truples": 500000,
        "wasted_percent": 10.0,
        "iname_len": 8,
        "wasted_ibytes": 16777216,  # ~16MB
        "wasted_iitems": 50000,
        "wasted_ipercent": 8.0,
        "real_row_count": 4500000,
        "extra": "Table has 10% bloat, needs VACUUM",
    },
    {
        "schemaname": "public",
        "tablename": "order_items",
        "tuples_len": 25000000,
        "wastedbytes": 524288000,  # ~500MB
        "wasted_truples": 2500000,
        "wasted_percent": 10.0,
        "iname_len": 5,
        "wasted_ibytes": 83886080,  # ~80MB
        "wasted_iitems": 250000,
        "wasted_ipercent": 5.0,
        "real_row_count": 22500000,
        "extra": "Large table with significant bloat",
    },
    {
        "schemaname": "public",
        "tablename": "products",
        "tuples_len": 100000,
        "wastedbytes": 5242880,  # ~5MB
        "wasted_truples": 10000,
        "wasted_percent": 10.0,
        "iname_len": 3,
        "wasted_ibytes": 1048576,  # ~1MB
        "wasted_iitems": 1000,
        "wasted_ipercent": 3.3,
        "real_row_count": 90000,
        "extra": None,
    },
    {
        "schemaname": "public",
        "tablename": "users",
        "tuples_len": 2000000,
        "wastedbytes": 26214400,  # ~25MB
        "wasted_truples": 200000,
        "wasted_percent": 10.0,
        "iname_len": 4,
        "wasted_ibytes": 5242880,
        "wasted_iitems": 20000,
        "wasted_ipercent": 4.0,
        "real_row_count": 1800000,
        "extra": "Users table with moderate bloat",
    },
    {
        "schemaname": "public",
        "tablename": "audit_log",
        "tuples_len": 50000000,
        "wastedbytes": 2097152000,  # ~2GB
        "wasted_truples": 15000000,
        "wasted_percent": 30.0,
        "iname_len": 2,
        "wasted_ibytes": 104857600,
        "wasted_iitems": 500000,
        "wasted_ipercent": 10.0,
        "real_row_count": 35000000,
        "extra": "CRITICAL: 30% bloat detected, recommend VACUUM FULL or cluster",
    },
]


@router.get("/bloat")
async def get_bloat(
    min_wasted_percent: float = Query(0.0, ge=0, le=100, description="最小膨胀百分比过滤"),
    schema: str = Query("", description="Schema名称过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
):
    """获取表膨胀分析结果"""
    bloat = _MOCK_BLOAT.copy()
    
    if min_wasted_percent > 0:
        bloat = [b for b in bloat if b["wasted_percent"] >= min_wasted_percent]
    if schema:
        bloat = [b for b in bloat if b["schemaname"] == schema]
    
    bloat = sorted(bloat, key=lambda x: x["wastedbytes"], reverse=True)[:limit]
    
    # 添加一些随机变化
    for b in bloat:
        b["wastedbytes"] = int(b["wastedbytes"] * random.uniform(0.9, 1.1))
        b["wasted_percent"] = round(b["wastedbytes"] / (b["tuples_len"] * 100) * 100, 2)
    
    total_wasted_bytes = sum(b["wastedbytes"] for b in bloat)
    critical_count = len([b for b in bloat if b["wasted_percent"] > 20])
    
    return {
        "tables": bloat,
        "total_tables": len(bloat),
        "total_wasted_bytes": total_wasted_bytes,
        "total_wasted_gb": round(total_wasted_bytes / 1024 / 1024 / 1024, 2),
        "critical_count": critical_count,
        "warning_count": len([b for b in bloat if 10 < b["wasted_percent"] <= 20]),
    }


@router.get("/bloat/{schema}/{table}")
async def get_table_bloat(schema: str, table: str):
    """获取指定表的膨胀详情"""
    for b in _MOCK_BLOAT:
        if b["schemaname"] == schema and b["tablename"] == table:
            return {"bloat": b}
    return {"error": "Table not found", "schema": schema, "table": table}


@router.get("/bloat/summary")
async def get_bloat_summary():
    """获取膨胀总览"""
    total_bytes = sum(b["wastedbytes"] for b in _MOCK_BLOAT)
    total_rows = sum(b["tuples_len"] for b in _MOCK_BLOAT)
    avg_wasted_percent = sum(b["wasted_percent"] for b in _MOCK_BLOAT) / len(_MOCK_BLOAT)
    
    return {
        "total_tables": len(_MOCK_BLOAT),
        "total_wasted_bytes": total_bytes,
        "total_wasted_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
        "total_rows": total_rows,
        "average_wasted_percent": round(avg_wasted_percent, 2),
        "critical_tables": len([b for b in _MOCK_BLOAT if b["wasted_percent"] > 20]),
        "warning_tables": len([b for b in _MOCK_BLOAT if 10 < b["wasted_percent"] <= 20]),
        "healthy_tables": len([b for b in _MOCK_BLOAT if b["wasted_percent"] <= 10]),
        "recommendation": "Run VACUUM ANALYZE on critical tables",
    }
