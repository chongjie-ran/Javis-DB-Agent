"""PostgreSQL直连适配器

不依赖18081 API，直接使用asyncpg连接PostgreSQL。
环境变量配置：
  JAVIS_PG_HOST      - 数据库主机（默认localhost）
  JAVIS_PG_PORT      - 端口（默认5432）
  JAVIS_PG_USER      - 用户名（默认postgres）
  JAVIS_PG_PASSWORD  - 密码（默认空）
  JAVIS_PG_DATABASE  - 数据库名（默认postgres）
"""
import os
import asyncpg
from typing import Optional, Any


class DirectPostgresConnector:
    """直连PostgreSQL，不依赖18081 API"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        database: str = "postgres",
    ):
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "min_size": 1,
            "max_size": 10,
        }
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(**self.config)
        return self._pool

    async def get_sessions(self, limit: int = 100) -> list[dict]:
        """获取PostgreSQL会话列表（pg_stat_activity风格）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT pid, usename AS username, datname AS db,
                       state, query, query_start,
                       wait_event_type AS wait_event,
                       client_addr AS machine,
                       application_name
                FROM pg_stat_activity
                WHERE datname IS NOT NULL
                ORDER BY query_start NULLS LAST
                LIMIT $1
                """,
                limit,
            )
            return [dict(row) for row in rows]

    async def get_locks(self) -> list[dict]:
        """获取PostgreSQL锁信息（pg_locks风格）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    l.locktype,
                    l.mode,
                    l.granted,
                    l.pid,
                    l.relation::regclass AS relation,
                    l.database,
                    l.page,
                    l.tuple,
                    l.virtualxid,
                    l.transactionid,
                    l.classid,
                    l.objid,
                    l.objsubid,
                    b.pid AS blocker_pid
                FROM pg_locks l
                LEFT JOIN pg_locks b ON
                    l.locktype = b.locktype
                    AND l.database IS NOT DISTINCT FROM b.database
                    AND l.relation IS NOT DISTINCT FROM b.relation
                    AND l.page IS NOT DISTINCT FROM b.page
                    AND l.tuple IS NOT DISTINCT FROM b.tuple
                    AND l.virtualxid IS NOT DISTINCT FROM b.virtualxid
                    AND l.transactionid IS NOT DISTINCT FROM b.transactionid
                    AND l.classid IS NOT DISTINCT FROM b.classid
                    AND l.objid IS NOT DISTINCT FROM b.objid
                    AND l.objsubid IS NOT DISTINCT FROM b.objsubid
                    AND l.pid != b.pid
                    AND b.granted
                WHERE NOT l.granted
                """
            )
            return [dict(row) for row in rows]

    async def get_replication(self) -> dict:
        """获取PostgreSQL流复制状态"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # 获取当前节点角色
            role_row = await conn.fetchrow("SELECT pg_is_in_recovery() AS is_recovery, current_setting('max_wal_senders')::int AS max_wal_senders")
            is_recovery = role_row["is_recovery"]

            replicas = []
            if not is_recovery:
                # 主库：查询wal_sender
                rows = await conn.fetch(
                    """
                    SELECT pid, client_addr, state,
                           sent_lsn, write_lsn, flush_lsn, replay_lsn,
                           sync_state
                    FROM pg_stat_replication
                    """
                )
                for r in rows:
                    replicas.append({
                        "pid": r["pid"],
                        "client_addr": str(r["client_addr"]) if r["client_addr"] else None,
                        "state": r["state"],
                        "sent_lsn": str(r["sent_lsn"]),
                        "write_lsn": str(r["write_lsn"]),
                        "flush_lsn": str(r["flush_lsn"]),
                        "replay_lsn": str(r["replay_lsn"]),
                        "sync_state": r["sync_state"],
                        "lag_mb": 0.0,
                    })
            else:
                # 从库：查询wal_receiver
                rows = await conn.fetch(
                    """
                    SELECT pid, received_lsn, last_msg_send_time,
                           last_msg_receipt_time, latest_end_lsn, latest_end_time
                    FROM pg_stat_wal_receiver
                    """
                )
                for r in rows:
                    replicas.append({
                        "pid": r["pid"],
                        "state": "streaming",
                        "received_lsn": str(r["received_lsn"]),
                        "lag_mb": 0.0,
                    })

            return {
                "role": "standby" if is_recovery else "primary",
                "replication_enabled": len(replicas) > 0,
                "replicas": replicas,
                "wal_lag": 0.0,
                "replay_lag": 0.0,
                "flush_lag": 0.0,
            }

    async def execute_sql(self, sql: str, params: tuple = None) -> list[dict]:
        """执行SQL查询并返回结果"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if params:
                rows = await conn.fetch(sql, *params)
            else:
                rows = await conn.fetch(sql)
            return [dict(row) for row in rows]

    async def kill_backend(self, pid: int, kill_type: str = "terminate") -> dict:
        """
        终止PostgreSQL后端进程。

        Args:
            pid: 进程PID
            kill_type: terminate (SIGTERM) 或 cancel (SIGINT)
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(f"SELECT pg_{kill_type}_backend({pid})")
            return {"pid": pid, "kill_type": kill_type, "result": result}

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None


def get_default_postgres_connector() -> DirectPostgresConnector:
    """从环境变量创建默认的DirectPostgresConnector"""
    host = os.environ.get("JAVIS_PG_HOST", "localhost")
    port = int(os.environ.get("JAVIS_PG_PORT", "5432"))
    user = os.environ.get("JAVIS_PG_USER", "postgres")
    password = os.environ.get("JAVIS_PG_PASSWORD", "")
    database = os.environ.get("JAVIS_PG_DATABASE", "postgres")
    return DirectPostgresConnector(host, port, user, password, database)
