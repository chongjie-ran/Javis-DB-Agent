"""TeamCoordinator 单元测试 (P0级)

覆盖 TC-001~003/006/007/010
设计参考: tasks/2026-04-12/mcp-teamcoordinator-test-design.md
"""
import pytest
import asyncio
from typing import Any

from src.team.coordinator import (
    AgentTeamCoordinator,
    AgentMessage,
    AgentMessageQueue,
    CollaborationRole,
    TaskDelegation,
    get_team_coordinator,
)
from src.subagent.subagent_spec import SubagentSpec, SubagentMode
from src.subagent.explore_spec import ExploreSpec


# ─── TC-001: 正常创建子任务 ────────────────────────────────────────────────

def test_delegate_creates_task_with_id():
    """TC-001: 正常创建子任务 - 应返回task_id且status=pending"""
    coord = get_team_coordinator("test-tc001")
    task_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="代码审查任务",
    )
    
    assert task_id is not None
    assert isinstance(task_id, str)
    assert len(task_id) == 12
    
    task = coord.get_task(task_id)
    assert task is not None
    assert task.status == "pending"
    assert task.task_id == task_id


def test_delegate_records_executor_role():
    """TC-001: 委派应记录执行者角色"""
    coord = get_team_coordinator("test-tc001b")
    task_id = coord.delegate(
        role=CollaborationRole.VERIFIER,
        task="验证任务",
    )
    
    task = coord.get_task(task_id)
    assert task.executor == CollaborationRole.VERIFIER.value


# ─── TC-002: 委派给指定Agent ───────────────────────────────────────────────

def test_delegate_with_subagent_spec():
    """TC-002: 委派给指定Agent - subagent_spec应被记录"""
    coord = get_team_coordinator("test-tc002")
    spec = ExploreSpec(
        task="探索代码库安全漏洞",
        timeout=60,
        max_cost=5000,
    )
    
    task_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="安全审查任务",
        subagent_spec=spec,
    )
    
    task = coord.get_task(task_id)
    assert task.subagent_spec is not None
    assert task.subagent_spec.task == "探索代码库安全漏洞"
    assert task.subagent_spec.mode == SubagentMode.EXPLORE


def test_delegate_records_delegation_chain():
    """TC-002: 委派链路应被正确记录"""
    coord = get_team_coordinator("test-tc002b")
    
    # Orchestrator创建父任务
    parent_id = coord.delegate(
        role=CollaborationRole.ORCHESTRATOR,
        task="分解任务",
    )
    
    # 委派给Executor
    child_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="执行子任务",
        parent_task_id=parent_id,
        delegation_chain=[CollaborationRole.ORCHESTRATOR.value],
    )
    
    child = coord.get_task(child_id)
    assert "orchestrator" in child.delegation_chain
    assert child.parent_task_id == parent_id


# ─── TC-003: 任务状态同步 ──────────────────────────────────────────────────

def test_mark_running_updates_status():
    """TC-003: mark_running应将status变为running"""
    coord = get_team_coordinator("test-tc003")
    task_id = coord.delegate(role=CollaborationRole.EXECUTOR, task="进行中任务")
    
    coord.mark_running(task_id)
    
    task = coord.get_task(task_id)
    assert task.status == "running"


def test_complete_task_with_result():
    """TC-003: complete_task应更新状态为completed并记录result"""
    coord = get_team_coordinator("test-tc003b")
    task_id = coord.delegate(role=CollaborationRole.REPORT, task="生成报告")
    
    coord.mark_running(task_id)
    coord.complete_task(task_id, result={"report": "完成"})
    
    task = coord.get_task(task_id)
    assert task.status == "completed"
    assert task.result is not None


def test_complete_task_with_error():
    """TC-003: 任务失败应记录error字段"""
    coord = get_team_coordinator("test-tc003c")
    task_id = coord.delegate(role=CollaborationRole.EXECUTOR, task="会失败的任务")
    
    coord.complete_task(task_id, result=None, error="资源不足")
    
    task = coord.get_task(task_id)
    assert task.status == "failed"
    assert task.error == "资源不足"


def test_parent_task_sees_child_in_children():
    """TC-003: 父任务children列表应包含子任务ID"""
    coord = get_team_coordinator("test-tc003d")
    
    parent_id = coord.delegate(role=CollaborationRole.ORCHESTRATOR, task="父任务")
    child_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="子任务",
        parent_task_id=parent_id,
    )
    
    # 完成子任务
    coord.complete_task(child_id, result="done")
    
    # 父任务children列表应包含child_id
    parent = coord.get_task(parent_id)
    assert child_id in parent.children


# ─── TC-006: 任务依赖链 ────────────────────────────────────────────────────

def test_parent_child_dependency():
    """TC-006: 子任务应正确记录父任务ID"""
    coord = get_team_coordinator("test-tc006")
    
    parent_id = coord.delegate(role=CollaborationRole.ORCHESTRATOR, task="父")
    child_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="子",
        parent_task_id=parent_id,
    )
    
    # 验证依赖关系
    parent = coord.get_task(parent_id)
    child = coord.get_task(child_id)
    
    assert child.parent_task_id == parent_id
    # delegation_chain记录角色链路，不记录task_id
    assert isinstance(child.delegation_chain, list)


def test_task_tree_builds_correctly():
    """TC-006: get_task_tree应正确构建依赖树"""
    coord = get_team_coordinator("test-tc006b")
    
    root = coord.delegate(role=CollaborationRole.ORCHESTRATOR, task="root")
    child1 = coord.delegate(
        role=CollaborationRole.EXECUTOR, task="child1", parent_task_id=root
    )
    child2 = coord.delegate(
        role=CollaborationRole.DIAGNOSTIC, task="child2", parent_task_id=root
    )
    
    tree = coord.get_task_tree(root)
    assert tree["task_id"] == root
    assert len(tree["children"]) == 2


# ─── TC-007: 循环依赖检测 ───────────────────────────────────────────────────

def test_allows_nested_delegation_by_design():
    """TC-007: 循环依赖由调用方保证，当前实现不自动检测"""
    coord = get_team_coordinator("test-tc007")
    task_a = coord.delegate(role=CollaborationRole.EXECUTOR, task="A")
    task_b = coord.delegate(
        role=CollaborationRole.EXECUTOR, task="B", parent_task_id=task_a
    )
    
    # 允许创建，不做自动检测（设计决策）
    task_b_obj = coord.get_task(task_b)
    assert task_b_obj.parent_task_id == task_a


# ─── TC-010: 子任务失败 ─────────────────────────────────────────────────────

def test_subtask_failure_recorded():
    """TC-010: 子任务失败应记录error字段"""
    coord = get_team_coordinator("test-tc010")
    
    parent_id = coord.delegate(role=CollaborationRole.ORCHESTRATOR, task="父")
    child_id = coord.delegate(
        role=CollaborationRole.EXECUTOR,
        task="子",
        parent_task_id=parent_id,
    )
    
    coord.complete_task(child_id, result=None, error="执行失败")
    
    child = coord.get_task(child_id)
    assert child.status == "failed"
    assert child.error == "执行失败"


# ─── 补充: get_pending_tasks / get_team_summary ────────────────────────────

def test_get_pending_tasks():
    """补充: get_pending_tasks返回待处理任务"""
    coord = get_team_coordinator("test-pending")
    id1 = coord.delegate(role=CollaborationRole.EXECUTOR, task="task1")
    id2 = coord.delegate(role=CollaborationRole.VERIFIER, task="task2")
    
    pending = coord.get_pending_tasks()
    assert id1 in pending
    assert id2 in pending


def test_get_team_summary():
    """补充: get_team_summary返回团队摘要"""
    coord = get_team_coordinator("test-summary-unique-%d" % id(object()))
    coord.delegate(role=CollaborationRole.ORCHESTRATOR, task="root")
    
    summary = coord.get_team_summary()
    assert "session_id" in summary
    assert "total_tasks" in summary
    assert summary["total_tasks"] == 1


# ─── 补充: 消息队列 ────────────────────────────────────────────────────────

def test_message_queue_put_get():
    """补充: 消息队列基本操作"""
    queue = AgentMessageQueue()
    msg = AgentMessage(from_agent="a", to_agent="b", content="hello")
    
    queue.put(msg)
    retrieved = queue.get("b", timeout=1.0)
    
    assert retrieved is not None
    assert retrieved.content == "hello"
    assert retrieved.from_agent == "a"


def test_message_queue_to_specific_agent():
    """补充: 消息队列定向投递"""
    queue = AgentMessageQueue()
    msg = AgentMessage(from_agent="orchestrator", to_agent="executor", content="task for executor")
    
    queue.put(msg)
    retrieved = queue.get("executor", timeout=1.0)
    assert retrieved is not None
    assert retrieved.content == "task for executor"
