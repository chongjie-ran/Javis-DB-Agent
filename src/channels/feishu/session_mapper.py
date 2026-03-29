"""飞书会话与Javis会话ID映射管理

负责维护 Feishu chat_id/user_id -> Javis-DB-Agent session_id 的映射关系，
支持多用户并发场景下的会话隔离。
"""
import time
import threading
import uuid
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FeishuSessionRef:
    """飞书会话引用"""
    feishu_chat_id: str
    feishu_user_id: str
    feishu_message_id: str
    zcloud_session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_thread: bool = False
    thread_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class FeishuSessionMapper:
    """
    飞书会话映射器

    管理 Feishu 会话（chat_id + user_id）与 Javis-DB-Agent session_id 的映射。
    线程安全，支持多用户并发。
    """

    def __init__(self, ttl_seconds: int = 86400, max_per_user: int = 10):
        """
        Args:
            ttl_seconds: 会话TTL（秒）
            max_per_user: 单用户最大会话数
        """
        self.ttl_seconds = ttl_seconds
        self.max_per_user = max_per_user

        # chat_id -> user_id -> session_id
        self._chat_user_to_session: dict[str, dict[str, str]] = defaultdict(dict)
        # session_id -> FeishuSessionRef
        self._session_refs: dict[str, FeishuSessionRef] = {}
        # user_id -> list of session_ids (for cleanup)
        self._user_sessions: dict[str, list[str]] = defaultdict(list)
        # lock
        self._lock = threading.Lock()

    # ==================== 核心映射操作 ====================

    def get_or_create_session(
        self,
        feishu_chat_id: str,
        feishu_user_id: str,
        feishu_message_id: str,
        is_thread: bool = False,
        thread_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        获取或创建 Javis-DB-Agent session_id

        Args:
            feishu_chat_id: 飞书会话ID
            feishu_user_id: 飞书用户ID
            feishu_message_id: 飞书消息ID（用于去重）
            is_thread: 是否为线程消息
            thread_id: 线程ID
            metadata: 额外元数据

        Returns:
            Javis-DB-Agent session_id
        """
        with self._lock:
            # 先尝试查找已存在的会话
            existing = self._find_session_locked(
                feishu_chat_id, feishu_user_id, is_thread, thread_id
            )
            if existing:
                # 更新访问时间
                ref = self._session_refs[existing]
                ref.updated_at = time.time()
                ref.feishu_message_id = feishu_message_id
                return existing

            # 创建新会话
            session_id = str(uuid.uuid4())
            ref = FeishuSessionRef(
                feishu_chat_id=feishu_chat_id,
                feishu_user_id=feishu_user_id,
                feishu_message_id=feishu_message_id,
                zcloud_session_id=session_id,
                is_thread=is_thread,
                thread_id=thread_id,
                metadata=metadata or {},
            )
            self._session_refs[session_id] = ref
            self._chat_user_to_session[feishu_chat_id][feishu_user_id] = session_id
            self._user_sessions[feishu_user_id].append(session_id)

            # 限制用户会话数
            self._enforce_user_limit_locked(feishu_user_id)

            return session_id

    def get_session(
        self,
        feishu_chat_id: str,
        feishu_user_id: str,
        is_thread: bool = False,
        thread_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取已存在的 session_id"""
        with self._lock:
            return self._find_session_locked(
                feishu_chat_id, feishu_user_id, is_thread, thread_id
            )

    def _find_session_locked(
        self,
        feishu_chat_id: str,
        feishu_user_id: str,
        is_thread: bool,
        thread_id: Optional[str],
    ) -> Optional[str]:
        """查找会话（内部加锁版本）"""
        # 线程模式下使用 thread_id 作为 key
        if is_thread and thread_id:
            for session_id, ref in self._session_refs.items():
                if (
                    ref.feishu_chat_id == feishu_chat_id
                    and ref.feishu_user_id == feishu_user_id
                    and ref.is_thread
                    and ref.thread_id == thread_id
                    and not self._is_expired(ref)
                ):
                    return session_id
        else:
            for session_id, ref in self._session_refs.items():
                if (
                    ref.feishu_chat_id == feishu_chat_id
                    and ref.feishu_user_id == feishu_user_id
                    and not ref.is_thread
                    and not self._is_expired(ref)
                ):
                    return session_id
        return None

    def get_ref(self, zcloud_session_id: str) -> Optional[FeishuSessionRef]:
        """获取会话引用"""
        with self._lock:
            return self._session_refs.get(zcloud_session_id)

    def get_zcloud_session_id(
        self,
        feishu_chat_id: str,
        feishu_user_id: str,
        is_thread: bool = False,
        thread_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取 Javis-DB-Agent session_id（公开接口）"""
        return self.get_session(feishu_chat_id, feishu_user_id, is_thread, thread_id)

    def clear_session(self, zcloud_session_id: str) -> bool:
        """清除会话映射"""
        with self._lock:
            ref = self._session_refs.pop(zcloud_session_id, None)
            if ref:
                self._chat_user_to_session[ref.feishu_chat_id].pop(
                    ref.feishu_user_id, None
                )
                if ref.feishu_user_id in self._user_sessions:
                    try:
                        self._user_sessions[ref.feishu_user_id].remove(
                            zcloud_session_id
                        )
                    except ValueError:
                        pass
                return True
            return False

    def clear_user_sessions(self, feishu_user_id: str) -> int:
        """清除用户所有会话"""
        with self._lock:
            session_ids = self._user_sessions.pop(feishu_user_id, [])
            for session_id in session_ids:
                ref = self._session_refs.pop(session_id, None)
                if ref:
                    self._chat_user_to_session[ref.feishu_chat_id].pop(
                        ref.feishu_user_id, None
                    )
            return len(session_ids)

    def _is_expired(self, ref: FeishuSessionRef) -> bool:
        """检查会话是否过期"""
        return time.time() - ref.updated_at > self.ttl_seconds

    def _enforce_user_limit_locked(self, feishu_user_id: str):
        """强制用户会话数限制（内部加锁版本）"""
        sessions = self._user_sessions.get(feishu_user_id, [])
        while len(sessions) > self.max_per_user:
            oldest_id = sessions.pop(0)
            ref = self._session_refs.pop(oldest_id, None)
            if ref:
                self._chat_user_to_session[ref.feishu_chat_id].pop(
                    ref.feishu_user_id, None
                )

    # ==================== 统计与维护 ====================

    def cleanup_expired(self) -> int:
        """清理过期会话，返回清理数量"""
        with self._lock:
            expired_ids = [
                sid
                for sid, ref in self._session_refs.items()
                if self._is_expired(ref)
            ]
            for sid in expired_ids:
                ref = self._session_refs.pop(sid, None)
                if ref:
                    self._chat_user_to_session[ref.feishu_chat_id].pop(
                        ref.feishu_user_id, None
                    )
                    try:
                        self._user_sessions[ref.feishu_user_id].remove(sid)
                    except ValueError:
                        pass
            return len(expired_ids)

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total = len(self._session_refs)
            expired = sum(1 for ref in self._session_refs.values() if self._is_expired(ref))
            users = len(self._user_sessions)
            chats = len(self._chat_user_to_session)
            threads = sum(1 for ref in self._session_refs.values() if ref.is_thread)
            return {
                "total_sessions": total,
                "expired_sessions": expired,
                "active_users": users,
                "active_chats": chats,
                "thread_sessions": threads,
                "ttl_seconds": self.ttl_seconds,
            }

    def list_user_sessions(self, feishu_user_id: str) -> list[FeishuSessionRef]:
        """列出用户的所有会话"""
        with self._lock:
            session_ids = self._user_sessions.get(feishu_user_id, [])
            return [
                ref
                for sid in session_ids
                if (ref := self._session_refs.get(sid)) and not self._is_expired(ref)
            ]


# ==================== 单例 ====================

_mapper: Optional[FeishuSessionMapper] = None
_mapper_lock = threading.Lock()


def get_feishu_session_mapper(
    ttl_seconds: int = 86400, max_per_user: int = 10
) -> FeishuSessionMapper:
    """获取飞书会话映射器单例"""
    global _mapper
    if _mapper is None:
        with _mapper_lock:
            if _mapper is None:
                _mapper = FeishuSessionMapper(ttl_seconds=ttl_seconds, max_per_user=max_per_user)
    return _mapper


def reset_feishu_session_mapper():
    """重置飞书会话映射器（用于测试）"""
    global _mapper
    with _mapper_lock:
        _mapper = None
