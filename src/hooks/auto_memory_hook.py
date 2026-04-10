"""AutoMemoryHook - on_complete时触发AutoMemory (V3.2 P0)"""
from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext
from src.memory.auto_memory import AutoMemory
from src.memory.memory_manager import MemoryManager
import logging

logger = logging.getLogger(__name__)

# Global auto_memory instance
_auto_memory: AutoMemory | None = None


def get_auto_memory() -> AutoMemory:
    global _auto_memory
    if _auto_memory is None:
        import os
        workspace = os.environ.get("DATA_DIR", "data") + "/memory"
        _auto_memory = AutoMemory(mm)
    return _auto_memory


class AutoMemoryHook(AgentHook):
    """on_complete时触发AutoMemory会话整合"""

    name: str = "auto_memory"
    priority: int = 50

    def on_complete(self, ctx: AgentHookContext) -> AgentHookContext:
        """会话完成时整合记忆"""
        try:
            auto_mem = get_auto_memory()
            count = auto_mem.consolidate_session()
            ctx.add_warning(f"AutoMemory: 写入{count}条记忆")
            logger.info(f"[AutoMemoryHook] 写入{count}条记忆")
        except Exception as e:
            logger.warning(f"[AutoMemoryHook] 失败: {e}")
        return ctx

    def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """检测纠正信号并记录"""
        response = ctx.llm_response or ctx.stream_chunk or ""
        # 简单纠正检测
        correction_keywords = ["不对", "错了", "重新", "不是", "应该"]
        for kw in correction_keywords:
            if kw in response and len(response) > 50:
                ctx.add_warning(f"AutoMemory: 检测到纠正信号({kw})")
                break
        return ctx
