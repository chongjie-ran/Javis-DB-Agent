"""StructuredLogger - 结构化日志 / Hook 事件日志 / Agent 决策日志
输出 JSON Lines 格式，便于日志聚合和检索
"""
import json
import logging
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Any


# ── 日志数据模型 ─────────────────────────────────────────────────────────────

@dataclass
class HookEventLog:
    """
    Hook 事件日志

    Attributes:
        timestamp: 事件时间（ISO 8601）
        event: 事件类型（HookEvent.value）
        session_id: 会话 ID
        user_id: 用户 ID
        blocked: 是否被阻止
        message: 阻止/警告消息
        warnings: 警告列表
        matched_rules: 匹配的规则名称
        duration_ms: Hook 处理耗时（毫秒）
        payload: 事件负载数据（脱敏后）
    """
    timestamp: str
    event: str
    session_id: str
    user_id: str
    blocked: bool
    message: str
    warnings: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


@dataclass
class AgentDecisionLog:
    """
    Agent 决策日志

    Attributes:
        timestamp: 决策时间（ISO 8601）
        agent_name: Agent 名称
        session_id: 会话 ID
        user_id: 用户 ID
        decision_type: 决策类型（select_tool / llm_response / route / fallback）
        decision_data: 决策数据（工具选择原因 / LLM 输出摘要 / 路由目标 / 降级原因）
        goal: 用户目标（截断至 200 字符）
        success: 是否成功
        execution_time_ms: 执行耗时
        trace_id: 关联的 Trace ID
    """
    timestamp: str
    agent_name: str
    session_id: str
    user_id: str
    decision_type: str  # select_tool / llm_response / route / fallback
    decision_data: dict[str, Any] = field(default_factory=dict)
    goal: str = ""
    success: bool = True
    execution_time_ms: int = 0
    trace_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


# ── 结构化日志器 ─────────────────────────────────────────────────────────────

class StructuredLogger:
    """
    结构化日志器

    特性：
    - JSON Lines 格式输出（每行一条日志，便于 ELK / Loki 聚合）
    - 支持 Hook 事件日志和 Agent 决策日志
    - 自动注入 timestamp / trace_id / service_name 等公共字段
    - 支持标准 logging 模块输出（设置 handler 即可）
    - 内存缓冲 + 批量输出（避免频繁 IO）
    """

    def __init__(
        self,
        service_name: str = "javis-db-agent",
        output_file: Optional[str] = None,
        batch_size: int = 100,
    ):
        self._service_name = service_name
        self._output_file = output_file
        self._batch_size = batch_size
        self._buffer: list[dict] = []
        self._lock = threading.Lock()

        # 绑定标准 logging
        self._logger = logging.getLogger(f"observability.{service_name}")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat() + "Z"

    def _base_fields(self) -> dict:
        return {
            "service": self._service_name,
            "timestamp": self._now_iso(),
        }

    # ── Hook 事件日志 ────────────────────────────────────────────────────────

    def log_hook_event(
        self,
        event: str,
        session_id: str,
        user_id: str,
        blocked: bool = False,
        message: str = "",
        warnings: Optional[list[str]] = None,
        matched_rules: Optional[list[str]] = None,
        duration_ms: float = 0.0,
        payload: Optional[dict] = None,
    ):
        """记录 Hook 事件"""
        log_entry = {
            **self._base_fields(),
            "log_type": "hook_event",
            "event": event,
            "session_id": session_id,
            "user_id": user_id,
            "blocked": blocked,
            "message": message,
            "warnings": warnings or [],
            "matched_rules": matched_rules or [],
            "duration_ms": duration_ms,
            "payload": self._sanitize_payload(payload or {}),
        }
        self._emit(log_entry)

    def _sanitize_payload(self, payload: dict) -> dict:
        """脱敏敏感字段"""
        sensitive_keys = {"password", "token", "secret", "api_key", "credential"}
        result = {}
        for k, v in payload.items():
            if k.lower() in sensitive_keys:
                result[k] = "[REDACTED]"
            elif isinstance(v, dict):
                result[k] = self._sanitize_payload(v)
            else:
                result[k] = v
        return result

    # ── Agent 决策日志 ────────────────────────────────────────────────────────

    def log_agent_decision(
        self,
        agent_name: str,
        session_id: str,
        user_id: str,
        decision_type: str,
        decision_data: dict,
        goal: str = "",
        success: bool = True,
        execution_time_ms: int = 0,
        trace_id: str = "",
    ):
        """记录 Agent 决策"""
        log_entry = {
            **self._base_fields(),
            "log_type": "agent_decision",
            "agent_name": agent_name,
            "session_id": session_id,
            "user_id": user_id,
            "decision_type": decision_type,
            "decision_data": decision_data,
            "goal": goal[:200] if goal else "",
            "success": success,
            "execution_time_ms": execution_time_ms,
            "trace_id": trace_id,
        }
        self._emit(log_entry)

    # ── 通用结构化日志 ───────────────────────────────────────────────────────

    def log(
        self,
        level: str,
        message: str,
        **kwargs,
    ):
        """通用结构化日志"""
        log_entry = {
            **self._base_fields(),
            "log_type": "generic",
            "level": level.upper(),
            "message": message,
            **kwargs,
        }
        self._emit(log_entry)

    def info(self, message: str, **kwargs):
        self.log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self.log("DEBUG", message, **kwargs)

    # ── 内部输出 ─────────────────────────────────────────────────────────────

    def _emit(self, entry: dict):
        """输出日志条目"""
        line = json.dumps(entry, ensure_ascii=False, default=str)

        # 写入文件（如配置）
        if self._output_file:
            with self._lock:
                self._buffer.append(line)
                if len(self._buffer) >= self._batch_size:
                    self._flush()
        else:
            # 通过标准 logging 输出
            self._logger.info(line)

    def _flush(self):
        """强制刷新缓冲区"""
        if not self._buffer or not self._output_file:
            return
        try:
            with open(self._output_file, "a", encoding="utf-8") as f:
                f.write("\n".join(self._buffer) + "\n")
            self._buffer.clear()
        except Exception:
            pass

    def flush(self):
        """手动刷新"""
        if self._output_file:
            with self._lock:
                self._flush()

    def get_recent_logs(self, log_type: Optional[str] = None, limit: int = 100) -> list[dict]:
        """获取最近的日志（仅文件模式）"""
        if not self._output_file:
            return []
        try:
            with open(self._output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            logs = []
            for line in reversed(lines[-limit:]):
                try:
                    entry = json.loads(line.strip())
                    if log_type is None or entry.get("log_type") == log_type:
                        logs.append(entry)
                except Exception:
                    continue
            return logs
        except Exception:
            return []


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_structured_logger: Optional[StructuredLogger] = None


def get_structured_logger(
    service_name: str = "javis-db-agent",
    output_file: Optional[str] = None,
) -> StructuredLogger:
    global _structured_logger
    if _structured_logger is None:
        _structured_logger = StructuredLogger(service_name=service_name, output_file=output_file)
    return _structured_logger
