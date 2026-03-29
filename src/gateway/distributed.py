"""分布式多节点同步模块
支持Redis共享会话、审批状态同步、审计日志聚合
"""
import json
import time
import threading
import hashlib
from typing import Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import redis

from src.config import get_settings


# ==================== 分布式会话管理器 ====================

class DistributedSessionManager:
    """
    分布式会话管理器 - Redis共享存储
    
    在多节点环境下，所有实例共享同一份会话数据。
    会话同时写入本地SQLite（作为备份）和Redis（共享）。
    """

    def __init__(
        self,
        local_db_path: str = "data/sessions.db",
        ttl_seconds: int = 86400,
        max_sessions: int = 10000,
    ):
        """
        Args:
            local_db_path: 本地SQLite路径（备份）
            ttl_seconds: 会话TTL
            max_sessions: 最大会话数
        """
        self._local = None  # 延迟导入本地会话管理器
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._local_db_path = local_db_path
        
        settings = get_settings()
        try:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            self._redis.ping()
            self._redis_ok = True
        except Exception:
            self._redis = None
            self._redis_ok = False
        
        self._lock = threading.Lock()

    @property
    def local(self):
        """延迟加载本地会话管理器"""
        if self._local is None:
            from src.gateway.persistent_session import PersistentSessionManager
            self._local = PersistentSessionManager(
                db_path=self._local_db_path,
                ttl_seconds=self._ttl,
                max_sessions=self._max_sessions,
            )
        return self._local

    @property
    def is_distributed(self) -> bool:
        """是否启用了分布式模式"""
        return self._redis_ok

    def _redis_key(self, session_id: str) -> str:
        return f"zcloud:session:{session_id}"

    def _redis_user_key(self, user_id: str) -> str:
        return f"zcloud:user_sessions:{user_id}"

    # ==================== 会话操作（分布式） ====================

    def create_session(self, user_id: str, metadata: Optional[dict] = None) -> Any:
        """创建会话（同时写入本地和Redis）"""
        session = self.local.create_session(user_id, metadata)
        
        if self._redis_ok:
            try:
                session_data = session.to_dict()
                session_data["messages"] = [
                    {**m.to_dict(), "tool_calls": json.dumps(m.tool_calls) if m.tool_calls else ""}
                    for m in session.messages
                ]
                self._redis.setex(
                    self._redis_key(session.session_id),
                    self._ttl,
                    json.dumps(session_data, ensure_ascii=False),
                )
                # 更新用户会话索引
                self._redis.sadd(self._redis_user_key(user_id), session.session_id)
                self._redis.expire(self._redis_user_key(user_id), self._ttl)
            except Exception:
                pass
        
        return session

    def get_session(self, session_id: str) -> Optional[Any]:
        """获取会话（优先从Redis，fallback到本地）"""
        if self._redis_ok:
            try:
                data = self._redis.get(self._redis_key(session_id))
                if data:
                    return self._deserialize_session(json.loads(data))
            except Exception:
                pass
        
        return self.local.get_session(session_id)

    def save_session(self, session: Any):
        """保存会话（同时写入本地和Redis）"""
        self.local.save_session(session)
        
        if self._redis_ok:
            try:
                session_data = session.to_dict()
                session_data["messages"] = [
                    {**m.to_dict(), "tool_calls": json.dumps(m.tool_calls) if m.tool_calls else ""}
                    for m in session.messages
                ]
                self._redis.setex(
                    self._redis_key(session.session_id),
                    self._ttl,
                    json.dumps(session_data, ensure_ascii=False),
                )
            except Exception:
                pass

    def delete_session(self, session_id: str) -> bool:
        """删除会话（同时从本地和Redis删除）"""
        # 获取session先（用于清理用户索引）
        session = self.local.get_session(session_id)
        
        result = self.local.delete_session(session_id)
        
        if self._redis_ok:
            try:
                self._redis.delete(self._redis_key(session_id))
                if session:
                    self._redis.srem(self._redis_user_key(session.user_id), session_id)
            except Exception:
                pass
        
        return result

    def list_user_sessions(self, user_id: str) -> list:
        """列出用户所有会话"""
        if self._redis_ok:
            try:
                session_ids = self._redis.smembers(self._redis_user_key(user_id))
                sessions = []
                for sid in session_ids:
                    session = self.get_session(sid)
                    if session:
                        sessions.append(session)
                return sessions
            except Exception:
                pass
        
        return self.local.list_user_sessions(user_id)

    def _deserialize_session(self, data: dict) -> Any:
        """从Redis数据反序列化会话"""
        from src.gateway.persistent_session import Session, Message
        
        messages = []
        for m_data in data.get("messages", []):
            tool_calls = []
            if m_data.get("tool_calls") and m_data["tool_calls"]:
                try:
                    tool_calls = json.loads(m_data["tool_calls"])
                except Exception:
                    tool_calls = []
            messages.append(Message(
                role=m_data["role"],
                content=m_data["content"],
                tool_calls=tool_calls,
                tool_call_id=m_data.get("tool_call_id"),
                timestamp=m_data["timestamp"],
            ))
        
        return Session(
            session_id=data["session_id"],
            user_id=data["user_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            context=json.loads(data["context"]) if data.get("context") else {},
            metadata=json.loads(data["metadata"]) if data.get("metadata") else {},
            messages=messages,
        )

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self.local.get_stats()
        stats["distributed_mode"] = self._redis_ok
        if self._redis_ok:
            try:
                keys = self._redis.keys("zcloud:session:*")
                stats["redis_sessions"] = len(keys)
            except Exception:
                stats["redis_sessions"] = -1
        return stats

    def verify_consistency(self) -> dict:
        """
        验证多节点一致性
        
        Returns:
            包含以下信息的字典:
            - redis_available: Redis是否可用
            - session_count_local: 本地会话数
            - session_count_redis: Redis会话数
            - missing_in_redis: 本地有但Redis没有的会话
            - missing_in_local: Redis有但本地没有的会话
            - consistent: 是否一致
        """
        result = {
            "redis_available": self._redis_ok,
            "session_count_local": 0,
            "session_count_redis": 0,
            "missing_in_redis": [],
            "missing_in_local": [],
            "consistent": False,
            "checked_at": time.time(),
        }
        
        if not self._redis_ok:
            result["consistent"] = True  # 单节点模式认为一致
            return result
        
        try:
            # 统计本地
            local_stats = self.local.get_stats()
            result["session_count_local"] = local_stats["total_sessions"]
            
            # 统计Redis
            redis_keys = self._redis.keys("zcloud:session:*")
            result["session_count_redis"] = len(redis_keys)
            
            redis_sids = {k.replace("zcloud:session:", "") for k in redis_keys}
            
            # 获取本地所有会话ID
            with self.local._get_conn() as conn:
                local_rows = conn.execute("SELECT session_id FROM sessions").fetchall()
            local_sids = {row["session_id"] for row in local_rows}
            
            result["missing_in_redis"] = list(local_sids - redis_sids)
            result["missing_in_local"] = list(redis_sids - local_sids)
            result["consistent"] = (
                len(result["missing_in_redis"]) == 0 and
                len(result["missing_in_local"]) == 0
            )
        except Exception as e:
            result["error"] = str(e)
        
        return result


# ==================== 分布式审批管理器 ====================

class DistributedApprovalManager:
    """
    分布式审批管理器 - Redis共享审批状态
    
    多节点环境下，所有实例共享同一份审批状态。
    """

    def __init__(self, store_path: str = "data/approvals.jsonl"):
        self._store_path = store_path
        self._local = None  # 延迟加载本地审批存储
        
        settings = get_settings()
        try:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            self._redis.ping()
            self._redis_ok = True
        except Exception:
            self._redis = None
            self._redis_ok = False

    @property
    def local(self):
        """延迟加载本地审批存储"""
        if self._local is None:
            from src.models.approval import ApprovalStore
            self._local = ApprovalStore(self._store_path)
        return self._local

    @property
    def is_distributed(self) -> bool:
        return self._redis_ok

    def _redis_key(self, approval_id: str) -> str:
        return f"zcloud:approval:{approval_id}"

    def _redis_pending_key(self) -> str:
        return "zcloud:approvals:pending"

    def _submit_to_redis(self, record) -> bool:
        """将审批记录同步到Redis"""
        if not self._redis_ok:
            return False
        try:
            data = record.to_dict()
            self._redis.setex(
                self._redis_key(record.id),
                7200,  # 2小时TTL
                json.dumps(data, ensure_ascii=False),
            )
            if record.status.value in ("pending", "approved1"):
                self._redis.sadd(self._redis_pending_key(), record.id)
            return True
        except Exception:
            return False

    def get_from_redis(self, approval_id: str) -> Optional[dict]:
        """从Redis获取审批记录"""
        if not self._redis_ok:
            return None
        try:
            data = self._redis.get(self._redis_key(approval_id))
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None

    def submit(self, *args, **kwargs):
        """提交审批（同时写入本地和Redis）"""
        record = self.local.submit(*args, **kwargs)
        self._submit_to_redis(record)
        return record

    def approve1(self, *args, **kwargs):
        record = self.local.approve1(*args, **kwargs)
        self._submit_to_redis(record)
        return record

    def approve2(self, *args, **kwargs):
        record = self.local.approve2(*args, **kwargs)
        self._submit_to_redis(record)
        # 从pending集合移除
        if self._redis_ok:
            self._redis.srem(self._redis_pending_key(), record.id)
        return record

    def reject(self, *args, **kwargs):
        record = self.local.reject(*args, **kwargs)
        self._submit_to_redis(record)
        if self._redis_ok:
            self._redis.srem(self._redis_pending_key(), record.id)
        return record

    def get_approval(self, approval_id: str):
        """获取审批记录（优先Redis，fallback本地）"""
        if self._redis_ok:
            data = self.get_from_redis(approval_id)
            if data:
                from src.models.approval import ApprovalRecord
                return ApprovalRecord(**data)
        return self.local.get_approval(approval_id)

    def get_by_tool_call(self, tool_call_id: str):
        """通过tool_call_id获取审批记录"""
        if self._redis_ok:
            approval_id = self._redis.hget(f"zcloud:tool_call:{tool_call_id}", "approval_id")
            if approval_id:
                return self.get_approval(approval_id)
        return self.local.get_by_tool_call(tool_call_id)

    def list_pending(self, approver: Optional[str] = None) -> list:
        """列出待审批"""
        return self.local.list_pending(approver)

    def verify_consistency(self) -> dict:
        """验证审批状态一致性"""
        result = {
            "redis_available": self._redis_ok,
            "local_pending": len(self.local.list_pending()),
            "redis_pending": 0,
            "consistent": False,
            "checked_at": time.time(),
        }
        
        if not self._redis_ok:
            result["consistent"] = True
            return result
        
        try:
            result["redis_pending"] = self._redis.scard(self._redis_pending_key())
            result["consistent"] = abs(
                result["local_pending"] - result["redis_pending"]
            ) <= 1  # 允许1个的误差（因为状态转换时序）
        except Exception as e:
            result["error"] = str(e)
        
        return result


# ==================== 多节点健康检查 ====================

def check_multi_node_health() -> dict:
    """
    多节点健康检查
    
    检查:
    - Redis连接状态
    - 会话同步状态
    - 审批状态同步
    """
    from src.gateway.audit import get_audit_logger
    
    result = {
        "redis": {"available": False},
        "sessions": {"consistent": False},
        "approvals": {"consistent": False},
        "audit_chain_valid": False,
        "overall": "unknown",
        "checked_at": time.time(),
    }
    
    settings = get_settings()
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        result["redis"]["available"] = True
        info = r.info("server")
        result["redis"]["version"] = info.get("redis_version", "unknown")
        result["redis"]["mode"] = info.get("redis_mode", "unknown")
    except Exception as e:
        result["redis"]["error"] = str(e)
    
    # 检查会话一致性
    try:
        dist_session = DistributedSessionManager()
        session_check = dist_session.verify_consistency()
        result["sessions"] = session_check
    except Exception as e:
        result["sessions"]["error"] = str(e)
    
    # 检查审批一致性
    try:
        dist_approval = DistributedApprovalManager()
        approval_check = dist_approval.verify_consistency()
        result["approvals"] = approval_check
    except Exception as e:
        result["approvals"]["error"] = str(e)
    
    # 检查审计链完整性
    try:
        audit = get_audit_logger()
        chain_valid, _, _ = audit.verify_chain()
        result["audit_chain_valid"] = chain_valid
    except Exception as e:
        result["audit_error"] = str(e)
    
    # 综合状态
    all_ok = (
        result["redis"]["available"] and
        result["sessions"]["consistent"] and
        result["approvals"]["consistent"] and
        result["audit_chain_valid"]
    )
    result["overall"] = "healthy" if all_ok else "degraded"
    
    return result
