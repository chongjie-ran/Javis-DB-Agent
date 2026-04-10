"""src/hooks - Agent生命周期Hook系统 (V3.0 Phase 0)

改进（V3.1 P0）：
- 新增AutoVerificationHook（自动验证Hook）

与 src/gateway/hooks/ 的区别：
- src/gateway/hooks/ : Tool层Hook（工具执行、SQL检查、审批）
- src/hooks/        : Agent层Hook（迭代、LLM、流式、验证）

6大机制对应的Hook点：
| 机制           | Hook点                 | 实现Phase |
|----------------|------------------------|-----------|
| 对抗性验证     | after_iteration        | Phase 3   |
| 自我合理化防护  | after_iteration        | Phase 4   |
| 指令自包含     | before_execute_tools   | Phase 1   |
| 记忆三防线     | after_iteration        | Phase 2   |
| 任务并发隔离    | before_execute_tools   | Phase 5   |
| 探索/执行分离   | before_iteration       | Phase 6   |
| 自动验证       | after_iteration        | Phase 3+  |
"""
from .hook import AgentHook
from .composite_hook import CompositeHook, get_composite_hook, reset_composite_hook
from .hook_events import AgentHookEvent
from .hook_context import AgentHookContext
from .auto_verification_hook import AutoVerificationHook
from .auto_memory_hook import AutoMemoryHook
from .self_justification_guard import SelfJustificationGuard

__all__ = [
    "AgentHook",
    "CompositeHook",
    "get_composite_hook",
    "reset_composite_hook",
    "AgentHookEvent",
    "AgentHookContext",
    "AutoVerificationHook",
    "SelfJustificationGuard",
    "AutoMemoryHook",
]
