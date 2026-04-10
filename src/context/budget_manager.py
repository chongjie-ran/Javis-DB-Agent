"""ContextBudgetManager - Token预算与压缩触发管理 (V3.2 P2)

职责：
1. 管理所有会话的token预算状态
2. 追踪压缩历史（次数、时间）
3. 触发压缩的阈值判断
4. 与AutoMemory联动
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompressionRecord:
    """压缩记录"""
    session_id: str
    timestamp: float
    tokens_before: int
    tokens_after: int
    messages_removed: int
    reason: str  # "manual" | "threshold" | "auto_memory"


class ContextBudgetManager:
    """
    上下文预算管理器

    功能：
    - per-session token预算（默认100k）
    - 压缩阈值配置（默认60%/80%/90%）
    - 压缩历史记录
    - 与AutoMemory联动接口
    """

    DEFAULT_BUDGET = 100_000
    DEFAULT_THRESHOLDS = [60.0, 80.0, 90.0, 100.0]

    def __init__(
        self,
        default_budget: int = DEFAULT_BUDGET,
        thresholds: Optional[list[float]] = None,
    ):
        self._default_budget = default_budget
        self._thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self._lock = threading.Lock()
        # session_id -> session state
        self._sessions: dict[str, dict] = {}
        # 全局压缩记录
        self._compression_history: list[CompressionRecord] = []
        # 回调：超预算时触发AutoMemory
        self._auto_memory_callback: Optional[callable] = None

    def set_auto_memory_callback(self, fn: callable) -> None:
        """设置AutoMemory联动回调"""
        self._auto_memory_callback = fn

    def get_or_create_session(self, session_id: str, budget: Optional[int] = None) -> dict:
        """获取或创建会话状态"""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "budget": budget or self._default_budget,
                    "token_count": 0,
                    "compression_count": 0,
                    "last_compression_at": 0.0,
                    "thresholds_triggered": set(),
                }
            return self._sessions[session_id]

    def update_token_count(self, session_id: str, token_count: int) -> list[str]:
        """
        更新会话token计数，返回触发的阈值列表

        Returns:
            list of triggered threshold percentages, e.g. ["80.0", "90.0"]
        """
        sess = self.get_or_create_session(session_id)
        with self._lock:
            sess["token_count"] = token_count
            triggered = []
            budget = sess["budget"]
            pct = (token_count / budget * 100) if budget > 0 else 0
            for t in self._thresholds:
                if pct >= t and t not in sess["thresholds_triggered"]:
                    triggered.append(str(t))
                    sess["thresholds_triggered"].add(t)
                    # 超100%时触发AutoMemory联动
                    if t >= 100.0 and self._auto_memory_callback:
                        try:
                            self._auto_memory_callback(session_id)
                        except Exception:
                            pass
            return triggered

    def record_compression(
        self,
        session_id: str,
        tokens_before: int,
        tokens_after: int,
        messages_removed: int,
        reason: str = "threshold",
    ) -> None:
        """记录一次压缩操作"""
        record = CompressionRecord(
            session_id=session_id,
            timestamp=time.time(),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_removed=messages_removed,
            reason=reason,
        )
        with self._lock:
            self._compression_history.append(record)
            if session_id in self._sessions:
                self._sessions[session_id]["compression_count"] += 1
                self._sessions[session_id]["last_compression_at"] = time.time()
                # 重置阈值触发状态（压缩后重新开始）
                self._sessions[session_id]["thresholds_triggered"] = set()

    def get_session_status(self, session_id: str) -> dict:
        """获取会话状态摘要"""
        sess = self.get_or_create_session(session_id)
        with self._lock:
            budget = sess["budget"]
            tokens = sess["token_count"]
            return {
                "session_id": session_id,
                "token_count": tokens,
                "budget": budget,
                "usage_percent": round((tokens / budget * 100), 2) if budget > 0 else 0,
                "compression_count": sess["compression_count"],
                "last_compression_at": sess["last_compression_at"],
                "thresholds": {
                    str(t): (t <= (tokens / budget * 100)) if budget > 0 else False
                    for t in self._thresholds
                },
            }

    def should_compress(self, session_id: str) -> tuple[bool, str]:
        """
        判断是否应该触发压缩

        Returns:
            (should_compress, reason)
        """
        status = self.get_session_status(session_id)
        pct = status["usage_percent"]
        if pct >= 80.0:
            return True, f"token_usage_{pct:.1f}%"
        if status["compression_count"] > 0 and pct >= 60.0:
            return True, "recurrent_after_compression"
        return False, ""

    def get_compression_history(self, session_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        """获取压缩历史"""
        with self._lock:
            records = self._compression_history
            if session_id:
                records = [r for r in records if r.session_id == session_id]
            records = records[-limit:]
            return [
                {
                    "session_id": r.session_id,
                    "timestamp": r.timestamp,
                    "tokens_before": r.tokens_before,
                    "tokens_after": r.tokens_after,
                    "reduction_percent": round((1 - r.tokens_after / r.tokens_before) * 100, 1) if r.tokens_before > 0 else 0,
                    "messages_removed": r.messages_removed,
                    "reason": r.reason,
                }
                for r in records
            ]

    def set_budget(self, session_id: str, budget: int) -> None:
        """设置会话预算"""
        sess = self.get_or_create_session(session_id)
        with self._lock:
            sess["budget"] = budget

    def reset_session(self, session_id: str) -> None:
        """重置会话状态"""
        with self._lock:
            self._sessions.pop(session_id, None)


# 全局单例
_budget_manager: Optional[ContextBudgetManager] = None


def get_budget_manager() -> ContextBudgetManager:
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = ContextBudgetManager()
    return _budget_manager
