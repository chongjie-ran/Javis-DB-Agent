"""AgentTeamCoordinator - 多Agent动态协作编排器 (V3.2 P2)

架构：
- 编排Agent(Orchestrator) 负责任务分解和委派
- 执行Agent(Dynamic) 按需创建/销毁
- 消息队列驱动异步通信
- 审计日志记录全流程

协作模式：
1. 直线链 (Linear): Orchestrator → Subagent1 → Subagent2 → Result
2. 树形分支 (Parallel): Orchestrator → [SubagentA, SubagentB] → Merge → Result
3. 验证环 (Verify): Executor → Verifier → [Retry? → Executor] → Result
"""
import asyncio
import threading
import uuid
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

from src.subagent.subagent_spec import SubagentSpec, SubagentMode
from src.team.audit import CollaborationAuditLogger, get_audit_logger

logger = logging.getLogger(__name__)


class CollaborationRole(str, Enum):
    """Agent角色类型"""
    ORCHESTRATOR = "orchestrator"    # 编排者：分解任务、委派、汇总
    EXECUTOR = "executor"            # 执行者：具体任务执行
    VERIFIER = "verifier"            # 验证者：结果验证
    REPORT = "report"                # 报告者：生成报告
    DIAGNOSTIC = "diagnostic"        # 诊断者：问题诊断


@dataclass
class AgentMessage:
    """Agent间消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent: str = ""
    to_agent: str = ""              # "" 表示广播
    content: Any = ""
    type: str = "task"              # task | result | error | approval | signal
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    reply_to: str = ""              # 回复的消息ID

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "content": str(self.content)[:200],
            "type": self.type,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
        }


@dataclass
class TaskDelegation:
    """任务委派记录"""
    task_id: str
    parent_task_id: str = ""         # 父任务ID（树形结构）
    orchestrator: str = ""           # 编排者名称
    executor: str = ""               # 执行者名称
    subagent_spec: Optional[SubagentSpec] = None
    status: str = "pending"          # pending | running | completed | failed | delegated
    result: Any = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    children: list[str] = field(default_factory=list)  # 子任务ID列表
    delegation_chain: list[str] = field(default_factory=list)  # 委派链

    def duration_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        if self.started_at:
            return (time.time() - self.started_at) * 1000
        return 0.0


class AgentMessageQueue:
    """
    Agent间异步消息队列
    
    支持：
    - 点对点消息
    - 广播消息
    - 消息订阅/投递
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queues: dict[str, list[AgentMessage]] = defaultdict(list)
        self._subscriptions: dict[str, asyncio.Queue] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def put(self, msg: AgentMessage) -> None:
        """投递消息"""
        with self._lock:
            if msg.to_agent:
                self._queues[msg.to_agent].append(msg)
            else:
                # 广播给所有队列
                for q in self._queues.values():
                    q.append(msg)

            # 通知订阅者
            if msg.to_agent in self._subscriptions:
                try:
                    asyncio.create_task(self._notify(msg.to_agent))
                except RuntimeError:
                    pass

    def get(self, agent_id: str, timeout: float = 5.0) -> Optional[AgentMessage]:
        """同步获取消息（带超时）"""
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if self._queues[agent_id]:
                    return self._queues[agent_id].pop(0)
            time.sleep(0.05)
        return None

    async def get_async(self, agent_id: str) -> AgentMessage:
        """异步获取消息"""
        if agent_id not in self._subscriptions:
            self._subscriptions[agent_id] = asyncio.Queue()
        q = self._subscriptions[agent_id]
        try:
            return await asyncio.wait_for(q.get(), timeout=30.0)
        except asyncio.TimeoutError:
            raise TimeoutError(f"No message for {agent_id} within timeout")

    async def _notify(self, agent_id: str) -> None:
        if agent_id in self._subscriptions:
            await self._subscriptions[agent_id].put(msg)


class AgentTeamCoordinator:
    """
    多Agent团队协作编排器

    使用示例:
        coordinator = AgentTeamCoordinator(session_id="s1")
        
        # 定义协作流程
        task_id = coordinator.delegate(
            role=CollaborationRole.ORCHESTRATOR,
            task="分析数据库性能问题",
            parent_task_id="",
        )
        
        # 诊断Agent处理
        diag_id = coordinator.delegate(
            role=CollaborationRole.DIAGNOSTIC,
            task="诊断CPU飙升原因",
            parent_task_id=task_id,
            delegation_chain=["orchestrator"],
        )
        
        # 等待结果
        result = await coordinator.wait_for_result(diag_id, timeout=60)
    """

    def __init__(self, session_id: str = ""):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._tasks: dict[str, TaskDelegation] = {}
        self._lock = threading.Lock()
        self._message_queue = AgentMessageQueue()
        self._audit = get_audit_logger()
        self._event_handlers: dict[str, list[callable]] = defaultdict(list)
        self._pending_results: dict[str, asyncio.Future] = {}

    # ── 任务委派 ─────────────────────────────────────────────────────────────

    def delegate(
        self,
        role: CollaborationRole,
        task: str,
        parent_task_id: str = "",
        subagent_spec: Optional[SubagentSpec] = None,
        delegation_chain: Optional[list[str]] = None,
    ) -> str:
        """
        创建任务委派

        Args:
            role: Agent角色
            task: 任务描述
            parent_task_id: 父任务ID（用于树形结构）
            subagent_spec: 子Agent规格
            delegation_chain: 委派链路

        Returns:
            task_id
        """
        task_id = str(uuid.uuid4())[:12]
        chain = list(delegation_chain or [])
        chain.append(role.value)

        with self._lock:
            td = TaskDelegation(
                task_id=task_id,
                parent_task_id=parent_task_id,
                orchestrator=chain[0] if chain else role.value,
                executor=role.value,
                subagent_spec=subagent_spec,
                status="pending",
                delegation_chain=chain,
            )
            self._tasks[task_id] = td

            # 更新父任务的子任务列表
            if parent_task_id and parent_task_id in self._tasks:
                self._tasks[parent_task_id].children.append(task_id)

        # 记录审计日志
        self._audit.log_delegation(
            session_id=self.session_id,
            task_id=task_id,
            parent_task_id=parent_task_id,
            from_role=chain[-2] if len(chain) > 1 else "user",
            to_role=role.value,
            task_preview=task[:100],
        )

        # 发送任务消息
        msg = AgentMessage(
            from_agent=chain[-2] if len(chain) > 1 else "orchestrator",
            to_agent=role.value,
            content=task,
            type="task",
            metadata={"task_id": task_id, "parent_task_id": parent_task_id},
        )
        self._message_queue.put(msg)

        logger.info(
            f"[AgentTeam] Delegated {task_id}: {role.value} "
            f"(chain={' -> '.join(chain)})"
        )
        return task_id

    def mark_running(self, task_id: str) -> None:
        """标记任务开始执行"""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = "running"
                self._tasks[task_id].started_at = time.time()

    def complete_task(
        self,
        task_id: str,
        result: Any,
        error: str = "",
    ) -> None:
        """标记任务完成"""
        with self._lock:
            if task_id not in self._tasks:
                return
            td = self._tasks[task_id]
            td.completed_at = time.time()
            if error:
                td.status = "failed"
                td.error = error
            else:
                td.status = "completed"
                td.result = result

        self._audit.log_completion(
            session_id=self.session_id,
            task_id=task_id,
            status=td.status,
            duration_ms=td.duration_ms(),
            error=error,
        )

        # 通知等待者
        if task_id in self._pending_results:
            future = self._pending_results.pop(task_id)
            if error:
                future.set_exception(Exception(error))
            else:
                future.set_result(result)

        # 如果有父任务，发送结果消息
        if td.parent_task_id:
            msg = AgentMessage(
                from_agent=td.executor,
                to_agent=self._tasks[td.parent_task_id].executor if td.parent_task_id in self._tasks else "",
                content=result,
                type="result",
                metadata={"task_id": task_id, "parent_task_id": td.parent_task_id},
            )
            self._message_queue.put(msg)

        logger.info(
            f"[AgentTeam] Task {task_id} {td.status} "
            f"({td.duration_ms():.0f}ms)"
        )

    # ── 结果查询 ────────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[TaskDelegation]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_task_tree(self, root_task_id: str) -> dict:
        """获取任务树结构"""
        def build_tree(tid: str) -> dict:
            td = self._tasks.get(tid)
            if not td:
                return {}
            return {
                "task_id": tid,
                "role": td.executor,
                "status": td.status,
                "duration_ms": td.duration_ms(),
                "children": [build_tree(cid) for cid in td.children],
            }
        return build_tree(root_task_id)

    async def wait_for_result(self, task_id: str, timeout: float = 60) -> Any:
        """异步等待任务结果"""
        with self._lock:
            td = self._tasks.get(task_id)
            if td and td.status in ("completed", "failed"):
                if td.error:
                    raise Exception(td.error)
                return td.result

            if task_id not in self._pending_results:
                self._pending_results[task_id] = asyncio.Future()

        try:
            return await asyncio.wait_for(
                self._pending_results[task_id],
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._pending_results.pop(task_id, None)
            raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    def get_pending_tasks(self) -> list[str]:
        """获取所有进行中的任务ID"""
        with self._lock:
            return [
                tid for tid, td in self._tasks.items()
                if td.status in ("pending", "running")
            ]

    def get_team_summary(self) -> dict:
        """获取团队协作摘要"""
        with self._lock:
            total = len(self._tasks)
            by_status = defaultdict(int)
            by_role = defaultdict(int)
            for td in self._tasks.values():
                by_status[td.status] += 1
                by_role[td.executor] += 1
            return {
                "session_id": self.session_id,
                "total_tasks": total,
                "by_status": dict(by_status),
                "by_role": dict(by_role),
                "pending": [
                    tid for tid, td in self._tasks.items()
                    if td.status in ("pending", "running")
                ],
            }


# 全局单例（per-session）
_coordinators: dict[str, AgentTeamCoordinator] = {}
_coordinators_lock = threading.Lock()


def get_team_coordinator(session_id: str = "") -> AgentTeamCoordinator:
    sid = session_id or "default"
    with _coordinators_lock:
        if sid not in _coordinators:
            _coordinators[sid] = AgentTeamCoordinator(session_id=sid)
        return _coordinators[sid]
