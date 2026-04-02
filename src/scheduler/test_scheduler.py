"""TaskScheduler 测试"""

import asyncio
import pytest

import sys
sys.path.insert(0, '.')

from task_classifier import TaskType, Task, TaskClassifier
from file_lock import FileLockManager
from task_scheduler import TaskScheduler


class TestTaskClassifier:
    """任务分类器测试"""
    
    def setup_method(self):
        self.classifier = TaskClassifier()
    
    def test_read_only_patterns(self):
        """测试读操作分类"""
        read_tasks = [
            "read file.py",
            "search for pattern",
            "grep 'hello'",
            "find files",
            "analyze code",
            "inspect object",
            "query database",
            "fetch data",
            "get content",
            "list files",
        ]
        
        for task in read_tasks:
            result = self.classifier.classify(task)
            assert result == TaskType.READ_ONLY, f"Failed for: {task}"
    
    def test_write_patterns(self):
        """测试写操作分类"""
        write_tasks = [
            "write content to file",
            "edit file.py",
            "create new file",
            "delete file",
            "modify config",
            "update settings",
            "patch code",
            "append to file",
        ]
        
        for task in write_tasks:
            result = self.classifier.classify(task)
            assert result == TaskType.WRITE_SAME_FILE, f"Failed for: {task}"
    
    def test_verify_patterns(self):
        """测试验证操作分类"""
        verify_tasks = [
            "test function",
            "verify result",
            "validate input",
            "check output",
            "assert condition",
            "pytest tests/",
            "unittest TestClass",
            "coverage run",
        ]
        
        for task in verify_tasks:
            result = self.classifier.classify(task)
            assert result == TaskType.VERIFY, f"Failed for: {task}"
    
    def test_unknown_defaults_to_read(self):
        """测试未知操作默认为读"""
        unknown_tasks = [
            "unknown command",
            "some random text",
            "",
        ]
        
        for task in unknown_tasks:
            result = self.classifier.classify(task)
            assert result == TaskType.READ_ONLY, f"Failed for: {task}"


class TestFileLockManager:
    """文件锁管理器测试"""
    
    @pytest.mark.asyncio
    async def test_single_lock(self):
        """测试单个文件锁"""
        manager = FileLockManager()
        lock_acquired = False
        
        async with manager.acquire("test.txt"):
            lock_acquired = True
        
        assert lock_acquired
    
    @pytest.mark.asyncio
    async def test_same_file_sequential(self):
        """测试同一文件的顺序锁"""
        manager = FileLockManager()
        results = []
        
        async def task1():
            async with manager.acquire("file.txt"):
                results.append("task1_start")
                await asyncio.sleep(0.1)
                results.append("task1_end")
        
        async def task2():
            await asyncio.sleep(0.05)  # 稍微延迟启动
            async with manager.acquire("file.txt"):
                results.append("task2_start")
                await asyncio.sleep(0.1)
                results.append("task2_end")
        
        await asyncio.gather(task1(), task2())
        
        # task1应该完全执行完后task2才开始
        t1_start_idx = results.index("task1_start")
        t1_end_idx = results.index("task1_end")
        t2_start_idx = results.index("task2_start")
        
        assert t1_end_idx < t2_start_idx, "Locks should be sequential"
    
    @pytest.mark.asyncio
    async def test_different_files_parallel(self):
        """测试不同文件可并行"""
        manager = FileLockManager()
        results = []
        
        async def task1():
            async with manager.acquire("file1.txt"):
                results.append("task1_start")
                await asyncio.sleep(0.1)
                results.append("task1_end")
        
        async def task2():
            async with manager.acquire("file2.txt"):
                results.append("task2_start")
                await asyncio.sleep(0.1)
                results.append("task2_end")
        
        await asyncio.gather(task1(), task2())
        
        # 两个任务应该并行执行
        assert "task1_start" in results
        assert "task2_start" in results
        assert "task1_end" in results
        assert "task2_end" in results


class TestTaskScheduler:
    """任务调度器测试"""
    
    @pytest.mark.asyncio
    async def test_read_only_parallel(self):
        """测试读操作并行执行"""
        classifier = TaskClassifier()
        scheduler = TaskScheduler(classifier)
        
        results = []
        
        async def make_read_task(task_id: str):
            async def execute():
                results.append(f"{task_id}_start")
                await asyncio.sleep(0.1)
                results.append(f"{task_id}_end")
            
            task = Task(
                task_id=task_id,
                task_type=TaskType.READ_ONLY,
                execute_fn=execute,
            )
            await scheduler.submit(task)
        
        await asyncio.gather(
            make_read_task("read1"),
            make_read_task("read2"),
        )
        await scheduler.wait_all()
        
        # 读操作应该并行执行
        status = scheduler.get_status()
        assert status["completed"] == 2
    
    @pytest.mark.asyncio
    async def test_same_file_write_serial(self):
        """测试同文件写操作串行"""
        classifier = TaskClassifier()
        scheduler = TaskScheduler(classifier)
        
        results = []
        
        async def make_write_task(task_id: str):
            async def execute():
                results.append(f"{task_id}_start")
                await asyncio.sleep(0.1)
                results.append(f"{task_id}_end")
            
            task = Task(
                task_id=task_id,
                task_type=TaskType.WRITE_SAME_FILE,
                files=["same_file.txt"],
                execute_fn=execute,
            )
            await scheduler.submit(task)
        
        await asyncio.gather(
            make_write_task("write1"),
            make_write_task("write2"),
        )
        await scheduler.wait_all()
        
        # 同文件写应该串行
        write1_start_idx = results.index("write1_start")
        write1_end_idx = results.index("write1_end")
        write2_start_idx = results.index("write2_start")
        
        assert write1_end_idx < write2_start_idx, "Same file writes should be serial"
    
    @pytest.mark.asyncio
    async def test_diff_file_write_parallel(self):
        """测试不同文件写操作并行"""
        classifier = TaskClassifier()
        scheduler = TaskScheduler(classifier)
        
        results = []
        
        async def make_write_task(task_id: str, file: str):
            async def execute():
                results.append(f"{task_id}_start")
                await asyncio.sleep(0.1)
                results.append(f"{task_id}_end")
            
            task = Task(
                task_id=task_id,
                task_type=TaskType.WRITE_DIFF_FILE,
                files=[file],
                execute_fn=execute,
            )
            await scheduler.submit(task)
        
        await asyncio.gather(
            make_write_task("write1", "file1.txt"),
            make_write_task("write2", "file2.txt"),
        )
        await scheduler.wait_all()
        
        status = scheduler.get_status()
        assert status["completed"] == 2
    
    @pytest.mark.asyncio
    async def test_verify_parallel_with_implementation(self):
        """测试验证任务与实现任务并行"""
        classifier = TaskClassifier()
        scheduler = TaskScheduler(classifier)
        
        results = []
        
        async def impl_task():
            async def execute():
                results.append("impl_start")
                await asyncio.sleep(0.15)
                results.append("impl_end")
            
            task = Task(
                task_id="impl",
                task_type=TaskType.WRITE_SAME_FILE,
                files=["impl.py"],
                execute_fn=execute,
            )
            await scheduler.submit(task)
        
        async def verify_task():
            await asyncio.sleep(0.05)  # 稍微延迟
            async def execute():
                results.append("verify_start")
                await asyncio.sleep(0.1)
                results.append("verify_end")
            
            task = Task(
                task_id="verify",
                task_type=TaskType.VERIFY,
                execute_fn=execute,
            )
            await scheduler.submit(task)
        
        await asyncio.gather(impl_task(), verify_task())
        await scheduler.wait_all()
        
        status = scheduler.get_status()
        assert status["completed"] == 2


class TestNoDeadlock:
    """死锁测试 - 验证多文件锁不会死锁"""
    
    @pytest.mark.asyncio
    async def test_multiple_files_no_deadlock(self):
        """测试多文件按顺序获取锁不会死锁"""
        manager = FileLockManager()
        results = []
        
        async def task_a():
            async with manager.acquire_multiple(["a.txt", "b.txt", "c.txt"]):
                results.append("task_a")
                await asyncio.sleep(0.05)
        
        async def task_b():
            async with manager.acquire_multiple(["c.txt", "b.txt", "a.txt"]):
                results.append("task_b")
                await asyncio.sleep(0.05)
        
        # 如果按字母排序，两个任务会以相同顺序获取锁，不会死锁
        # 等待足够长时间确保完成
        try:
            await asyncio.wait_for(
                asyncio.gather(task_a(), task_b()),
                timeout=2.0
            )
            assert len(results) == 2
        except asyncio.TimeoutError:
            pytest.fail("Deadlock detected - tasks did not complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
