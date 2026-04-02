"""dual_memory.py - 双层记忆核心 (V3.0 Phase 2)

整合短期记忆和长期记忆，提供统一的记忆接口。
"""

import asyncio
from enum import Enum
from typing import Optional

from .history_manager import HistoryManager, HistoryEntry
from .memory_manager import MemoryManager, MemoryTypeEnum
from .token_monitor import TokenMonitor, TokenStatus
from .memory_optimizer import MemoryOptimizer


class MemoryType(str, Enum):
    """记忆类型枚举"""
    SHORT_TERM = "short_term"   # 短期记忆 -> HISTORY.md
    LONG_TERM = "long_term"     # 长期记忆 -> MEMORY.md


class DualMemory:
    """双层记忆系统核心

    整合短期记忆（HISTORY.md）和长期记忆（MEMORY.md），
    提供统一的记忆存取接口和自动整合机制。

    核心功能：
    - save: 保存记忆（自动选择短期/长期）
    - get_short_term: 获取短期记忆
    - get_long_term: 获取长期记忆
    - consolidate: 触发记忆整合
    - check_token_status: 检查Token状态

    Hook集成点：
    - after_iteration: 追加事件到HISTORY.md
    - on_complete: 检查token是否需要整合
    - on_error: 记录错误到HISTORY.md

    使用示例：
        memory = DualMemory("/path/to/workspace")

        # 保存短期记忆
        await memory.save("完成SQL优化", MemoryType.SHORT_TERM)

        # 保存长期记忆
        await memory.save("用户偏好简洁SQL", MemoryType.LONG_TERM,
                         memory_subtype="user")

        # 检查Token状态
        status = memory.check_token_status(85000)

        # 触发整合（如Token超80%）
        if status.should_consolidate:
            await memory.consolidate(85000)
    """

    def __init__(
        self,
        workspace: str,
        token_warning_threshold: int = 80000,
        token_danger_threshold: int = 95000,
        token_total: int = 100000,
    ):
        """初始化双层记忆系统

        Args:
            workspace: 工作区路径
            token_warning_threshold: Token警告阈值（默认80%）
            token_danger_threshold: Token危险阈值（默认95%）
            token_total: Token总量（默认100000）
        """
        self.workspace = workspace

        # 初始化各组件
        self.history = HistoryManager(workspace)
        self.memory = MemoryManager(workspace)
        self.token_monitor = TokenMonitor(
            warning_threshold=token_warning_threshold,
            danger_threshold=token_danger_threshold,
            threshold=token_total,
        )
        self.optimizer = MemoryOptimizer()

    async def save(
        self,
        content: str,
        memory_type: MemoryType,
        **kwargs,
    ) -> str:
        """保存记忆

        根据记忆类型自动选择存储位置：
        - SHORT_TERM -> HISTORY.md（事件日志）
        - LONG_TERM -> MEMORY.md（结构化事实）

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            **kwargs: 额外参数
                - category: 短期记忆的类别
                - subtype: 长期记忆的子类型（MemoryTypeEnum值）
                - tags: 长期记忆的标签

        Returns:
            str: 保存的内容
        """
        if memory_type == MemoryType.SHORT_TERM:
            category = kwargs.get('category', 'general')
            entry = HistoryEntry(event=content, category=category)
            return await self.history.append(entry)
        else:
            subtype = kwargs.get('subtype', MemoryTypeEnum.PROJECT.value)
            tags = kwargs.get('tags', [])
            record = await self.memory.save(content, subtype, tags)
            return record.content

    async def save_iteration(self, iteration: int, action: str, result: str):
        """保存迭代记录（便捷方法）

        Args:
            iteration: 迭代编号
            action: 执行的操作
            result: 操作结果
        """
        event = f"Iteration {iteration}: {action} -> {result}"
        await self.save(event, MemoryType.SHORT_TERM, category="iteration")

    async def save_error(self, error: str, context: Optional[str] = None):
        """保存错误记录（便捷方法）

        Args:
            error: 错误信息
            context: 错误上下文
        """
        event = f"ERROR: {error}"
        if context:
            event += f" (context: {context})"
        await self.save(event, MemoryType.SHORT_TERM, category="error")

    async def save_tool_execution(
        self,
        tool_name: str,
        args: dict,
        result: str,
    ):
        """保存工具执行记录（便捷方法）

        Args:
            tool_name: 工具名
            args: 工具参数
            result: 执行结果
        """
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        event = f"Tool: {tool_name}({args_str}) -> {result[:50]}..."
        await self.save(event, MemoryType.SHORT_TERM, category="tool")

    def get_recent_events(self, count: int = 10) -> list[str]:
        """获取最近的事件

        Args:
            count: 获取数量

        Returns:
            list[str]: 最近的事件列表
        """
        return self.history.get_recent(count)

    def grep_events(self, pattern: str) -> list[str]:
        """搜索事件

        Args:
            pattern: 正则表达式模式

        Returns:
            list[str]: 匹配的事件
        """
        return self.history.grep(pattern)

    def get_memories(
        self,
        memory_type: Optional[str] = None,
    ) -> list:
        """获取长期记忆

        Args:
            memory_type: 记忆类型过滤

        Returns:
            list: 记忆记录列表
        """
        return self.memory.get(memory_type)

    def check_token_status(self, token_count: int) -> TokenStatusResult:
        """检查Token状态并返回详细信息

        Args:
            token_count: 当前token数量

        Returns:
            TokenStatusResult: 包含状态和是否应整合的详细信息
        """
        status = self.token_monitor.check(token_count)
        should_consolidate = self.token_monitor.should_consolidate(token_count)
        budget = self.token_monitor.get_budget(token_count)

        return TokenStatusResult(
            status=status,
            should_consolidate=should_consolidate,
            current_tokens=token_count,
            percentage=budget.percentage,
            remaining_tokens=budget.remaining,
        )

    async def consolidate(self, token_count: int) -> dict:
        """触发记忆整合

        当token超阈值时，将近期事件整合为长期事实。

        整合策略：
        1. 获取最近20条历史事件
        2. 提取关键信息（任务进度、错误、工具使用）
        3. 保存到长期记忆的project类型

        Args:
            token_count: 当前token数量

        Returns:
            dict: 整合结果
        """
        if not self.token_monitor.should_consolidate(token_count):
            return {
                'status': 'skipped',
                'reason': 'threshold_not_reached',
                'token_count': token_count,
            }

        # 获取最近事件
        recent = self.history.get_recent(20)

        if not recent:
            return {
                'status': 'skipped',
                'reason': 'no_history',
                'token_count': token_count,
            }

        # 执行整合
        records = await self.memory.consolidate(recent)

        # 清理过期短期记忆（可选）
        cleanup_result = self.optimizer.cleanup_old(
            os.path.join(self.workspace, "HISTORY.md"),
            older_than_days=30,
            dry_run=True,
        )

        return {
            'status': 'success',
            'token_count': token_count,
            'consolidated_count': len(records),
            'history_entries_processed': len(recent),
            'cleanup_preview': cleanup_result,
        }

    async def auto_consolidate_if_needed(self, token_count: int) -> bool:
        """如果需要则自动整合

        这是一个便捷方法，在Hook点调用。

        Args:
            token_count: 当前token数量

        Returns:
            bool: 是否执行了整合
        """
        if self.token_monitor.should_consolidate(token_count):
            result = await self.consolidate(token_count)
            return result['status'] == 'success'
        return False

    def compress_large_memory(self, content: str) -> str:
        """压缩过大的记忆

        Args:
            content: 原始内容

        Returns:
            str: 压缩后的内容
        """
        return self.optimizer.compress(content)

    def get_statistics(self) -> dict:
        """获取记忆统计信息

        Returns:
            dict: 统计信息
        """
        history_count = self.history.count()
        memory_counts = self.memory.count()

        return {
            'short_term_entries': history_count,
            'long_term_by_type': memory_counts,
            'long_term_total': sum(memory_counts.values()),
            'token_thresholds': {
                'warning': self.token_monitor.warning_threshold,
                'danger': self.token_monitor.danger_threshold,
                'total': self.token_monitor.threshold,
            },
        }


# 向后兼容的别名
class TokenStatusResult:
    """Token状态检查结果"""

    def __init__(
        self,
        status: TokenStatus,
        should_consolidate: bool,
        current_tokens: int,
        percentage: float,
        remaining_tokens: int,
    ):
        self.status = status
        self.should_consolidate = should_consolidate
        self.current_tokens = current_tokens
        self.percentage = percentage
        self.remaining_tokens = remaining_tokens


import os  # for consolidate method
