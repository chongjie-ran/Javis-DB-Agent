"""tests/memory/test_dual_memory.py - 双层记忆系统测试"""

import pytest
import os
import tempfile
import shutil
from datetime import datetime

# 导入被测试模块
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from memory.dual_memory import DualMemory, MemoryType
from memory.history_manager import HistoryManager, HistoryEntry
from memory.memory_manager import MemoryManager, MemoryTypeEnum
from memory.token_monitor import TokenMonitor, TokenStatus
from memory.memory_optimizer import MemoryOptimizer


class TestTokenMonitor:
    """TokenMonitor测试"""

    def test_normal_status(self):
        monitor = TokenMonitor()
        assert monitor.check(50000) == TokenStatus.NORMAL

    def test_warning_status(self):
        monitor = TokenMonitor()
        assert monitor.check(85000) == TokenStatus.WARNING

    def test_danger_status(self):
        monitor = TokenMonitor()
        assert monitor.check(96000) == TokenStatus.DANGER

    def test_exhausted_status(self):
        monitor = TokenMonitor()
        assert monitor.check(100000) == TokenStatus.EXHAUSTED

    def test_should_consolidate(self):
        monitor = TokenMonitor()
        assert monitor.should_consolidate(90000) is True
        assert monitor.should_consolidate(70000) is False

    def test_get_budget(self):
        monitor = TokenMonitor()
        budget = monitor.get_budget(50000)
        assert budget.status == TokenStatus.NORMAL
        assert budget.percentage == 50.0
        assert budget.remaining == 50000


class TestHistoryManager:
    """HistoryManager测试"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作区"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def manager(self, temp_workspace):
        return HistoryManager(temp_workspace)

    @pytest.mark.asyncio
    async def test_append(self, manager):
        entry = HistoryEntry(event="测试事件", category="test")
        result = await manager.append(entry)
        assert "测试事件" in result

    @pytest.mark.asyncio
    async def test_get_recent(self, manager):
        entry = HistoryEntry(event="事件1", category="test")
        await manager.append(entry)
        entry2 = HistoryEntry(event="事件2", category="test")
        await manager.append(entry2)

        recent = manager.get_recent(2)
        assert len(recent) == 2

    @pytest.mark.asyncio
    async def test_grep(self, manager):
        entry = HistoryEntry(event="error occurred", category="error")
        await manager.append(entry)

        matches = manager.grep("error")
        assert len(matches) >= 1

    def test_count(self, manager):
        assert manager.count() == 0


class TestMemoryManager:
    """MemoryManager测试"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作区"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def manager(self, temp_workspace):
        return MemoryManager(temp_workspace)

    @pytest.mark.asyncio
    async def test_save(self, manager):
        record = await manager.save(
            "测试记忆内容",
            MemoryTypeEnum.USER.value
        )
        assert record.memory_type == "user"
        assert record.content == "测试记忆内容"

    @pytest.mark.asyncio
    async def test_get(self, manager):
        await manager.save("内容1", MemoryTypeEnum.PROJECT.value)
        await manager.save("内容2", MemoryTypeEnum.USER.value)

        all_records = manager.get()
        assert len(all_records) == 2

        user_records = manager.get("user")
        assert len(user_records) == 1
        assert user_records[0].content == "内容2"

    @pytest.mark.asyncio
    async def test_search(self, manager):
        await manager.save("Python代码规范", MemoryTypeEnum.PATTERN.value)
        await manager.save("用户偏好", MemoryTypeEnum.USER.value)

        results = manager.search("Python")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_consolidate(self, manager):
        recent_history = [
            "- [iteration] 完成SQL优化",
            "- [tool] 执行查询",
        ]
        records = await manager.consolidate(recent_history)
        assert len(records) == 1
        assert records[0].memory_type == "project"


class TestMemoryOptimizer:
    """MemoryOptimizer测试"""

    def test_compress_small_content(self):
        optimizer = MemoryOptimizer(max_size_kb=5)
        small_content = "这是小内容"
        result = optimizer.compress(small_content)
        assert result == small_content

    def test_compress_large_content(self):
        optimizer = MemoryOptimizer(max_size_kb=1)  # 1KB
        # 创建超过1KB的内容
        large_content = "x" * 3000
        result = optimizer.compress(large_content)
        assert len(result.encode('utf-8')) < len(large_content.encode('utf-8'))
        assert "[... 内容已压缩" in result


class TestDualMemory:
    """DualMemory测试"""

    @pytest.fixture
    def temp_workspace(self):
        """创建临时工作区"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def memory(self, temp_workspace):
        return DualMemory(temp_workspace)

    @pytest.mark.asyncio
    async def test_save_short_term(self, memory):
        await memory.save("测试短期记忆", MemoryType.SHORT_TERM)
        events = memory.get_recent_events(1)
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_save_long_term(self, memory):
        await memory.save(
            "用户偏好简洁代码",
            MemoryType.LONG_TERM,
            subtype="user"
        )
        records = memory.get_memories("user")
        assert len(records) == 1

    @pytest.mark.asyncio
    async def test_save_iteration(self, memory):
        await memory.save_iteration(1, "SQL优化", "完成")
        events = memory.get_recent_events(1)
        assert any("Iteration 1" in e for e in events)

    @pytest.mark.asyncio
    async def test_save_error(self, memory):
        await memory.save_error("连接失败", "DB连接")
        events = memory.get_recent_events(1)
        assert any("ERROR" in e for e in events)

    def test_check_token_status(self, memory):
        result = memory.check_token_status(90000)
        assert result.should_consolidate is True
        assert result.percentage == 90.0

    @pytest.mark.asyncio
    async def test_consolidate(self, memory):
        # 先添加一些历史
        await memory.save("事件1", MemoryType.SHORT_TERM)
        await memory.save("事件2", MemoryType.SHORT_TERM)

        result = await memory.consolidate(90000)
        assert result['status'] == 'success'
        assert result['consolidated_count'] == 1

    def test_get_statistics(self, memory):
        stats = memory.get_statistics()
        assert 'short_term_entries' in stats
        assert 'long_term_by_type' in stats
        assert 'token_thresholds' in stats

    def test_compress_large_memory(self, memory):
        # DualMemory uses MemoryOptimizer with default max_size_kb=5
        # So we need content > 5KB to trigger compression
        large_content = "x" * 6000
        result = memory.compress_large_memory(large_content)
        assert len(result.encode('utf-8')) < len(large_content.encode('utf-8'))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
