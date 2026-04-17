"""持久化会话管理器
支持重启后恢复对话上下文
"""
import os
import json
import sqlite3
import uuid
import time
import threading
from typing import Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from contextlib import contextmanager


# ==================== 数据模型 ====================

@dataclass
class Message:
    """消息"""
    role: str  # user/assistant/system/tool
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        # Bug-1 fix: message_id 只生成一次，保证幂等性
        object.__setattr__(self, '_message_id', str(uuid.uuid4()))
    
    def to_dict(self) -> dict:
        return {
            "message_id": self._message_id,
            "role": self.role,
            "content": self.content,
            "tool_calls": json.dumps(self.tool_calls) if self.tool_calls else "",
            "tool_call_id": self.tool_call_id or "",
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        tool_calls = []
        if data.get("tool_calls"):
            try:
                tool_calls = json.loads(data["tool_calls"])
            except (json.JSONDecodeError, TypeError):
                tool_calls = []
        
        return cls(
            role=data["role"],
            content=data["content"],
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id") or None,
            timestamp=data["timestamp"],
        )


@dataclass
class Session:
    """会话"""
    session_id: str
    user_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)  # 运维上下文
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs) -> Message:
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg
    
    def get_history(self, limit: Optional[int] = None) -> list[Message]:
        """获取历史消息"""
        if limit:
            return self.messages[-limit:]
        return self.messages.copy()
    
    def get_context_value(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)
    
    def set_context_value(self, key: str, value: Any):
        self.context[key] = value
    
    def get_metadata_value(self, key: str, default: Any = None) -> Any:
        """获取 metadata 中的值"""
        return self.metadata.get(key, default)
    
    def set_metadata_value(self, key: str, value: Any):
        """设置 metadata 中的值（用于持久化存储）"""
        self.metadata[key] = value
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context": json.dumps(self.context),
            "metadata": json.dumps(self.metadata),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        context = {}
        metadata = {}
        
        if data.get("context"):
            try:
                context = json.loads(data["context"])
            except (json.JSONDecodeError, TypeError):
                context = {}
        
        if data.get("metadata"):
            try:
                metadata = json.loads(data["metadata"])
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        
        session = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            context=context,
            metadata=metadata,
            messages=[],
        )
        
        return session


# ==================== 持久化会话管理器 ====================

class PersistentSessionManager:
    """
    持久化会话管理器
    使用SQLite存储会话数据，支持重启后恢复
    """
    
    _lock = threading.RLock()  # 类级别的可重入锁（支持同一线程重复获取）
    
    def __init__(
        self,
        db_path: str = "data/sessions.db",
        ttl_seconds: int = 86400,  # 24小时TTL
        max_sessions: int = 10000,
    ):
        """
        Args:
            db_path: SQLite数据库路径
            ttl_seconds: 会话TTL（秒）
            max_sessions: 最大会话数
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        
        # 确保数据库表存在
        self._ensure_db()
        
        # 内存缓存（用于快速访问）
        self._cache: dict[str, Session] = {}
        self._user_sessions: dict[str, list[str]] = defaultdict(list)
        
        # 后台自动清理机制
        self._cleanup_thread_running = False
        self._cleanup_thread = None
    
    def _start_cleanup_thread(self, interval_seconds: int = 300):
        """启动后台自动清理线程
        
        Args:
            interval_seconds: 清理间隔（秒），默认5分钟
        """
        if self._cleanup_thread_running:
            return
        
        def cleanup_loop():
            while self._cleanup_thread_running:
                time.sleep(interval_seconds)
                if self._cleanup_thread_running:
                    try:
                        self._cleanup_expired()
                    except Exception:
                        pass  # 静默处理清理中的异常
        
        self._cleanup_thread_running = True
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _stop_cleanup_thread(self):
        """停止后台自动清理线程"""
        self._cleanup_thread_running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=2)
            self._cleanup_thread = None
    
    def _ensure_db(self):
        """确保数据库和表存在"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    context TEXT DEFAULT '{}',
                    metadata TEXT DEFAULT '{}'
                );
                
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT DEFAULT '',
                    tool_call_id TEXT DEFAULT '',
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
            """)
            conn.commit()
    
    @contextmanager
    def _get_conn(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # ==================== 核心操作 ====================
    
    def create_session(self, user_id: str, metadata: Optional[dict] = None) -> Session:
        """
        创建新会话
        
        Args:
            user_id: 用户ID
            metadata: 元数据（可选）
        
        Returns:
            Session: 新建的会话
        """
        with self._lock:
            # 清理过期会话
            self._cleanup_expired()
            
            session_id = str(uuid.uuid4())
            now = time.time()
            
            session = Session(
                session_id=session_id,
                user_id=user_id,
                created_at=now,
                updated_at=now,
                metadata=metadata or {},
            )
            
            # 写入数据库
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO sessions 
                       (session_id, user_id, created_at, updated_at, context, metadata)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        session.session_id,
                        session.user_id,
                        session.created_at,
                        session.updated_at,
                        json.dumps(session.context),
                        json.dumps(session.metadata),
                    ),
                )
                conn.commit()
            
            # 更新内存索引
            self._cache[session_id] = session
            self._user_sessions[user_id].append(session_id)
            
            # 限制用户会话数
            if len(self._user_sessions[user_id]) > 10:
                old_sid = self._user_sessions[user_id].pop(0)
                self._cache.pop(old_sid, None)
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM sessions WHERE session_id = ?", (old_sid,))
                    conn.commit()
            
            # 限制总会话数（LRU淘汰）- 在添加新会话后执行
            while len(self._cache) > self.max_sessions:
                oldest_sid = min(
                    self._cache.keys(),
                    key=lambda s: self._cache[s].updated_at,
                )
                self.delete_session(oldest_sid)
            
            return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            Optional[Session]: 会话对象，不存在或过期返回None
        """
        # 先检查缓存
        if session_id in self._cache:
            session = self._cache[session_id]
            # 检查是否过期（基于缓存的 updated_at）
            if time.time() - session.updated_at < self.ttl_seconds:
                # 缓存未过期，验证 DB 中的 updated_at 是否更新（可能 DB 中已过期）
                with self._get_conn() as conn:
                    row = conn.execute(
                        "SELECT updated_at FROM sessions WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    
                    if row:
                        db_updated_at = row["updated_at"]
                        # 如果 DB 中的 updated_at 比缓存的旧，说明 DB 中已过期
                        if db_updated_at < session.updated_at:
                            # DB 中会话已过期，从缓存和 DB 删除
                            self._cache.pop(session_id, None)
                            self._user_sessions[session.user_id].remove(session_id)
                            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                            conn.commit()
                            return None
                return session
            else:
                # 缓存已过期，从缓存和数据库删除
                self._cache.pop(session_id, None)
                self._user_sessions[session.user_id].remove(session_id)
                # 直接从数据库删除，不调用 delete_session（避免不必要的缓存操作）
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                    conn.commit()
                return None
        
        # 从数据库加载
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        
        if not row:
            return None
        
        session = Session.from_dict(dict(row))
        
        # 检查是否过期
        if time.time() - session.updated_at >= self.ttl_seconds:
            # 直接从数据库删除，不调用 delete_session（避免不必要的缓存操作）
            with self._get_conn() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
            return None
        
        # 加载消息
        session.messages = self._load_messages(session_id)
        
        # 更新缓存
        self._cache[session_id] = session
        
        return session
    
    def save_session(self, session: Session):
        """
        保存会话（更新）
        
        Args:
            session: 会话对象
        """
        session.updated_at = time.time()
        
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """UPDATE sessions 
                       SET updated_at = ?, context = ?, metadata = ?
                       WHERE session_id = ?""",
                    (
                        session.updated_at,
                        json.dumps(session.context),
                        json.dumps(session.metadata),
                        session.session_id,
                    ),
                )
                conn.commit()
            
            # 更新缓存
            self._cache[session.session_id] = session
    
    def delete_session(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            session = self._cache.get(session_id)
            
            # 从数据库删除
            with self._get_conn() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
            
            # 从缓存删除
            if session:
                self._user_sessions[session.user_id].remove(session_id)
            self._cache.pop(session_id, None)
            
            return True
    
    def list_user_sessions(self, user_id: str) -> list[Session]:
        """
        列出用户所有会话
        
        Args:
            user_id: 用户ID
        
        Returns:
            list[Session]: 会话列表（按更新时间倒序）
        """
        sessions = []
        
        # 从数据库查询
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM sessions 
                   WHERE user_id = ? 
                   ORDER BY updated_at DESC""",
                (user_id,),
            ).fetchall()
        
        for row in rows:
            session = Session.from_dict(dict(row))
            # 检查是否过期
            if time.time() - session.updated_at < self.ttl_seconds:
                sessions.append(session)
        
        return sessions
    
    # ==================== 消息操作 ====================
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] = None,
        tool_call_id: str = None,
    ) -> Optional[Message]:
        """
        添加消息到会话
        
        Args:
            session_id: 会话ID
            role: 角色 (user/assistant/system/tool)
            content: 消息内容
            tool_calls: 工具调用列表
            tool_call_id: 工具调用ID
        
        Returns:
            Optional[Message]: 创建的消息对象
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        message = session.add_message(
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            tool_call_id=tool_call_id,
        )
        
        # 保存消息到数据库
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO messages 
                   (message_id, session_id, role, content, tool_calls, tool_call_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    session_id,
                    message.role,
                    message.content,
                    json.dumps(message.tool_calls) if message.tool_calls else "",
                    message.tool_call_id or "",
                    message.timestamp,
                ),
            )
            conn.commit()
        
        # 更新会话
        self.save_session(session)
        
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[Message]:
        """
        获取会话消息
        
        Args:
            session_id: 会话ID
            limit: 限制数量
        
        Returns:
            list[Message]: 消息列表
        """
        session = self.get_session(session_id)
        if not session:
            return []
        
        messages = session.messages
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    def _load_messages(self, session_id: str) -> list[Message]:
        """从数据库加载消息"""
        messages = []
        
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM messages 
                   WHERE session_id = ?
                   ORDER BY timestamp ASC""",
                (session_id,),
            ).fetchall()
        
        for row in rows:
            messages.append(Message.from_dict(dict(row)))
        
        return messages
    
    # ==================== 维护操作 ====================
    
    def _cleanup_expired(self):
        """清理过期会话"""
        now = time.time()
        expire_time = now - self.ttl_seconds
        
        with self._get_conn() as conn:
            # 查找过期会话
            rows = conn.execute(
                "SELECT session_id, user_id FROM sessions WHERE updated_at < ?",
                (expire_time,),
            ).fetchall()
            
            if rows:
                expired_ids = [r["session_id"] for r in rows]
                
                # 删除消息
                conn.execute(
                    "DELETE FROM messages WHERE session_id IN ({})".format(
                        ",".join("?" * len(expired_ids))
                    ),
                    expired_ids,
                )
                
                # 删除会话
                conn.execute(
                    "DELETE FROM sessions WHERE session_id IN ({})".format(
                        ",".join("?" * len(expired_ids))
                    ),
                    expired_ids,
                )
                
                conn.commit()
                
                # 清理缓存
                for row in rows:
                    self._cache.pop(row["session_id"], None)
                    if row["session_id"] in self._user_sessions[row["user_id"]]:
                        self._user_sessions[row["user_id"]].remove(row["session_id"])
        
        # 限制总会话数
        while len(self._cache) > self.max_sessions:
            oldest_sid = min(
                self._cache.keys(),
                key=lambda s: self._cache[s].updated_at,
            )
            self.delete_session(oldest_sid)
    
    def cleanup_all(self):
        """清理所有会话"""
        # 先停止后台清理线程
        self._stop_cleanup_thread()
        
        with self._lock:
            with self._get_conn() as conn:
                # 安全删除，只在表存在时删除
                try:
                    conn.execute("DELETE FROM messages")
                except sqlite3.OperationalError:
                    pass  # 表不存在，跳过
                try:
                    conn.execute("DELETE FROM sessions")
                except sqlite3.OperationalError:
                    pass  # 表不存在，跳过
                try:
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
            
            self._cache.clear()
            self._user_sessions.clear()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._get_conn() as conn:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            user_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM sessions").fetchone()[0]
        
        return {
            "total_sessions": session_count,
            "total_messages": message_count,
            "total_users": user_count,
            "cached_sessions": len(self._cache),
            "db_path": self.db_path,
        }


# ==================== 兼容层 ====================

class SessionManager(PersistentSessionManager):
    """
    兼容层：兼容原有的 SessionManager 接口
    直接继承 PersistentSessionManager，使用相同的接口
    """
    pass


# ==================== 单例 ====================

_session_manager: Optional[PersistentSessionManager] = None


def get_session_manager(
    db_path: str = "data/sessions.db",
    ttl_seconds: int = 86400,
) -> PersistentSessionManager:
    """
    获取会话管理器单例
    
    Args:
        db_path: 数据库路径
        ttl_seconds: 会话TTL
    
    Returns:
        PersistentSessionManager: 会话管理器实例
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = PersistentSessionManager(
            db_path=db_path,
            ttl_seconds=ttl_seconds,
        )
    return _session_manager


def reset_session_manager():
    """重置会话管理器单例（用于测试）"""
    global _session_manager
    if _session_manager:
        _session_manager.cleanup_all()
    _session_manager = None
