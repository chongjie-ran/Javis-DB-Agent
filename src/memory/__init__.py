"""src/memory - 双层记忆系统 (V3.0 Phase 2)

双层记忆架构：
- 短期记忆：HISTORY.md（事件日志，可grep）
- 长期记忆：MEMORY.md（结构化事实）
- Token监控：超过阈值触发记忆整合

Hook集成点：
- after_iteration：追加事件到HISTORY.md
- on_complete：检查token是否需要整合
- on_error：记录错误到HISTORY.md
"""
from .dual_memory import DualMemory, MemoryType
from .history_manager import HistoryManager, HistoryEntry
from .memory_manager import MemoryManager, MemoryTypeEnum
from .token_monitor import TokenMonitor, TokenStatus
from .memory_optimizer import MemoryOptimizer

__all__ = [
    "DualMemory",
    "MemoryType",
    "HistoryManager",
    "HistoryEntry",
    "MemoryManager",
    "MemoryTypeEnum",
    "TokenMonitor",
    "TokenStatus",
    "MemoryOptimizer",
]
