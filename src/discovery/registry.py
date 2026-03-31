"""
本地SQLite注册表 - 纳管实例存储

提供数据库实例的持久化存储、状态管理和历史追踪。
"""

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .scanner import DBType
from .identifier import IdentifiedInstance


@dataclass
class ManagedInstance:
    """已纳管的数据库实例"""
    id: str
    db_type: str
    host: str
    port: int
    version: str
    version_major: int
    version_minor: int
    edition: str
    status: str  # discovered / onboarded / monitoring / error / removed
    discovered_at: str  # ISO8601
    onboarded_at: Optional[str] = None
    last_check_at: Optional[str] = None
    max_connections: int = 100
    current_connections: int = 0
    process_path: str = ""
    pid: Optional[int] = None
    metadata_: str = "{}"  # JSON扩展字段

    @classmethod
    def from_identified(
        cls, identified: IdentifiedInstance, status: str = "discovered"
    ) -> "ManagedInstance":
        """
        从IdentifiedInstance创建ManagedInstance

        Args:
            identified: 识别后的实例
            status: 初始状态

        Returns:
            ManagedInstance
        """
        inst = identified.instance
        now = datetime.utcnow().isoformat()
        return cls(
            id=str(uuid.uuid4()),
            db_type=inst.db_type.value,
            host=inst.host,
            port=inst.port,
            version=identified.version,
            version_major=identified.version_major,
            version_minor=identified.version_minor,
            edition=identified.edition,
            status=status,
            discovered_at=now,
            onboarded_at=now if status == "onboarded" else None,
            last_check_at=now,
            max_connections=identified.max_connections,
            current_connections=identified.current_connections,
            process_path=inst.process_path,
            pid=inst.pid,
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ManagedInstance":
        """
        从数据库行创建ManagedInstance

        Args:
            row: sqlite3.Row

        Returns:
            ManagedInstance
        """
        return cls(**dict(row))


class LocalRegistry:
    """
    本地SQLite注册表

    表结构：
    - managed_instances: 已纳管实例
    - status_history:    状态变更历史
    - scan_sessions:     扫描会话记录

    Attributes:
        db_path: 数据库文件路径
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS managed_instances (
        id              TEXT PRIMARY KEY,
        db_type         TEXT NOT NULL,
        host            TEXT NOT NULL DEFAULT 'localhost',
        port            INTEGER NOT NULL,
        version         TEXT DEFAULT '',
        version_major   INTEGER DEFAULT 0,
        version_minor   INTEGER DEFAULT 0,
        edition         TEXT DEFAULT '',
        status          TEXT NOT NULL DEFAULT 'discovered',
        discovered_at   TEXT NOT NULL,
        onboarded_at    TEXT,
        last_check_at   TEXT,
        max_connections INTEGER DEFAULT 100,
        current_connections INTEGER DEFAULT 0,
        process_path    TEXT DEFAULT '',
        pid             INTEGER,
        metadata_       TEXT DEFAULT '{}'
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_instance_key
        ON managed_instances(db_type, host, port);

    CREATE INDEX IF NOT EXISTS idx_status
        ON managed_instances(status);

    CREATE TABLE IF NOT EXISTS status_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        instance_id     TEXT NOT NULL,
        old_status      TEXT,
        new_status      TEXT NOT NULL,
        changed_at      TEXT NOT NULL,
        reason          TEXT DEFAULT '',
        FOREIGN KEY (instance_id) REFERENCES managed_instances(id)
    );

    CREATE TABLE IF NOT EXISTS scan_sessions (
        id              TEXT PRIMARY KEY,
        started_at      TEXT NOT NULL,
        finished_at     TEXT,
        instances_found INTEGER DEFAULT 0,
        instances_new   INTEGER DEFAULT 0,
        instances_changed INTEGER DEFAULT 0,
        error_message   TEXT DEFAULT ''
    );
    """

    def __init__(self, db_path: str = "data/managed_db.db"):
        """
        初始化注册表

        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """上下文管理器：自动提交/回滚"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """初始化数据库schema"""
        with self._conn() as conn:
            conn.executescript(self.SCHEMA_SQL)

    def register(self, instance: ManagedInstance) -> str:
        """
        注册新实例（upsert），已存在则更新，返回instance_id

        Args:
            instance: 待注册的实例

        Returns:
            instance_id
        """
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO managed_instances (
                    id, db_type, host, port, version, version_major, version_minor,
                    edition, status, discovered_at, onboarded_at, last_check_at,
                    max_connections, current_connections, process_path, pid, metadata_
                ) VALUES (
                    :id, :db_type, :host, :port, :version, :version_major, :version_minor,
                    :edition, :status, :discovered_at, :onboarded_at, :last_check_at,
                    :max_connections, :current_connections, :process_path, :pid, :metadata_
                )
                ON CONFLICT(db_type, host, port) DO UPDATE SET
                    version = excluded.version,
                    version_major = excluded.version_major,
                    version_minor = excluded.version_minor,
                    edition = excluded.edition,
                    status = excluded.status,
                    last_check_at = excluded.last_check_at,
                    max_connections = excluded.max_connections,
                    current_connections = excluded.current_connections,
                    pid = excluded.pid
            """, asdict(instance))

            row = conn.execute(
                "SELECT id FROM managed_instances WHERE db_type=? AND host=? AND port=?",
                (instance.db_type, instance.host, instance.port)
            ).fetchone()
            return row["id"]

    def get_all(self, status_filter: Optional[str] = None) -> List[ManagedInstance]:
        """
        查询所有实例

        Args:
            status_filter: 可选的status过滤条件

        Returns:
            ManagedInstance列表
        """
        with self._conn() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM managed_instances WHERE status=? ORDER BY discovered_at DESC",
                    (status_filter,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM managed_instances ORDER BY discovered_at DESC"
                ).fetchall()
            return [ManagedInstance.from_row(row) for row in rows]

    def get_by_id(self, instance_id: str) -> Optional[ManagedInstance]:
        """
        按ID查询

        Args:
            instance_id: 实例ID

        Returns:
            ManagedInstance或None
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM managed_instances WHERE id=?",
                (instance_id,)
            ).fetchone()
            return ManagedInstance.from_row(row) if row else None

    def get_by_key(self, db_type: str, host: str, port: int) -> Optional[ManagedInstance]:
        """
        按(db_type, host, port)唯一键查询

        Args:
            db_type: 数据库类型
            host: 主机
            port: 端口

        Returns:
            ManagedInstance或None
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM managed_instances WHERE db_type=? AND host=? AND port=?",
                (db_type, host, port)
            ).fetchone()
            return ManagedInstance.from_row(row) if row else None

    def update_status(
        self, instance_id: str, new_status: str, reason: str = ""
    ) -> bool:
        """
        更新实例状态并记录历史

        Args:
            instance_id: 实例ID
            new_status: 新状态
            reason: 变更原因

        Returns:
            是否成功
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT status FROM managed_instances WHERE id=?",
                (instance_id,)
            ).fetchone()
            if not row:
                return False

            old_status = row["status"]
            now = datetime.utcnow().isoformat()

            conn.execute(
                "UPDATE managed_instances SET status=?, last_check_at=? WHERE id=?",
                (new_status, now, instance_id)
            )
            conn.execute(
                "INSERT INTO status_history (instance_id, old_status, new_status, changed_at, reason) VALUES (?, ?, ?, ?, ?)",
                (instance_id, old_status, new_status, now, reason)
            )
            return True

    def update_connections(self, instance_id: str, current: int) -> bool:
        """
        更新连接数

        Args:
            instance_id: 实例ID
            current: 当前连接数

        Returns:
            是否成功
        """
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE managed_instances SET current_connections=?, last_check_at=? WHERE id=?",
                (current, datetime.utcnow().isoformat(), instance_id)
            )
            return result.rowcount > 0

    def remove(self, instance_id: str) -> bool:
        """
        移除实例（软删除，标记为removed）

        Args:
            instance_id: 实例ID

        Returns:
            是否成功
        """
        return self.update_status(instance_id, "removed", "user_requested")

    def get_status_history(
        self, instance_id: str, limit: int = 50
    ) -> List[dict]:
        """
        获取实例的状态变更历史

        Args:
            instance_id: 实例ID
            limit: 返回记录数限制

        Returns:
            历史记录列表
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM status_history
                WHERE instance_id=?
                ORDER BY changed_at DESC
                LIMIT ?
                """,
                (instance_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """
        获取注册统计

        Returns:
            统计信息字典
        """
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM managed_instances WHERE status != 'removed'"
            ).fetchone()[0]

            by_status = {
                row["status"]: row["cnt"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM managed_instances WHERE status != 'removed' GROUP BY status"
                )
            }

            by_type = {
                row["db_type"]: row["cnt"]
                for row in conn.execute(
                    "SELECT db_type, COUNT(*) as cnt FROM managed_instances WHERE status != 'removed' GROUP BY db_type"
                )
            }

            return {
                "total_instances": total,
                "by_status": by_status,
                "by_type": by_type,
            }

    def create_scan_session(self, session_id: str) -> None:
        """
        创建扫描会话记录

        Args:
            session_id: 会话ID
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scan_sessions (id, started_at)
                VALUES (?, ?)
                """,
                (session_id, datetime.utcnow().isoformat())
            )

    def finish_scan_session(
        self,
        session_id: str,
        instances_found: int = 0,
        instances_new: int = 0,
        instances_changed: int = 0,
        error_message: str = "",
    ) -> None:
        """
        完成扫描会话记录

        Args:
            session_id: 会话ID
            instances_found: 发现的实例数
            instances_new: 新增实例数
            instances_changed: 变更实例数
            error_message: 错误信息
        """
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE scan_sessions SET
                    finished_at = ?,
                    instances_found = ?,
                    instances_new = ?,
                    instances_changed = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    datetime.utcnow().isoformat(),
                    instances_found,
                    instances_new,
                    instances_changed,
                    error_message,
                    session_id,
                )
            )
