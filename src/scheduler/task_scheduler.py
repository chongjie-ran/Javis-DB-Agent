"""任务调度器 - 根据任务类型调度执行"""

import asyncio
from typing import Dict, Set, Optional, Callable

from task_classifier import TaskType, Task
from file_lock import FileLockManager


class TaskScheduler:
    """任务调度器 - 根据任务类型控制并发
    
    调度策略：
    - READ_ONLY: 直接并行执行
    - WRITE_SAME_FILE: 获取文件锁后执行（串行）
    - WRITE_DIFF_FILE: 直接并行执行
    - VERIFY: 直接并行执行（可与实现并行）
    """
    
    def __init__(
        self,
        classifier,  # TaskClassifier
        lock_manager: Optional[FileLockManager] = None,
    ):
        self.classifier = classifier
        self.lock_manager = lock_manager or FileLockManager()
        self.tasks: Dict[str, Task] = {}
        self.running: Set[str] = set()
        self.completed: Set[str] = set()
        self.failed: Set[str] = set()
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def submit(self, task: Task) -> asyncio.Task:
        """提交任务并开始执行
        
        Args:
            task: 任务对象
            
        Returns:
            asyncio.Task: 任务对应的协程对象
        """
        self.tasks[task.task_id] = task
        
        if task.task_type == TaskType.READ_ONLY:
            # 读操作直接并行执行
            asyncio_task = asyncio.create_task(self._run_task(task))
            self._running_tasks[task.task_id] = asyncio_task
            return asyncio_task
        
        elif task.task_type == TaskType.WRITE_SAME_FILE:
            # 同文件写需要获取锁，串行执行
            asyncio_task = asyncio.create_task(self._run_with_lock(task))
            self._running_tasks[task.task_id] = asyncio_task
            return asyncio_task
        
        elif task.task_type == TaskType.WRITE_DIFF_FILE:
            # 不同文件写可并行
            asyncio_task = asyncio.create_task(self._run_task(task))
            self._running_tasks[task.task_id] = asyncio_task
            return asyncio_task
        
        elif task.task_type == TaskType.VERIFY:
            # 验证可与实现并行
            asyncio_task = asyncio.create_task(self._run_task(task))
            self._running_tasks[task.task_id] = asyncio_task
            return asyncio_task
        
        else:
            # 默认读操作
            asyncio_task = asyncio.create_task(self._run_task(task))
            self._running_tasks[task.task_id] = asyncio_task
            return asyncio_task
    
    async def submit_with_files(
        self,
        task_id: str,
        task_description: str,
        files: list[str],
        execute_fn: Optional[Callable] = None,
    ) -> asyncio.Task:
        """根据描述和文件自动分类后提交任务
        
        Args:
            task_id: 任务ID
            task_description: 任务描述
            files: 涉及的文件列表
            execute_fn: 执行函数
            
        Returns:
            asyncio.Task: 任务对应的协程对象
        """
        task_type, resolved_files = self.classifier.classify_with_files(
            task_description, files
        )
        
        task = Task(
            task_id=task_id,
            task_type=task_type,
            files=resolved_files,
            execute_fn=execute_fn,
        )
        
        return await self.submit(task)
    
    async def _run_with_lock(self, task: Task):
        """带文件锁的任务执行
        
        Args:
            task: 任务对象
        """
        if task.files:
            async with self.lock_manager.acquire_multiple(task.files):
                await self._run_task(task)
        else:
            # 没有文件参数，直接执行
            await self._run_task(task)
    
    async def _run_task(self, task: Task):
        """执行任务
        
        Args:
            task: 任务对象
        """
        self.running.add(task.task_id)
        task.status = "running"
        
        try:
            await task.execute()
            task.status = "completed"
            self.completed.add(task.task_id)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            self.failed.add(task.task_id)
        finally:
            self.running.discard(task.task_id)
            self._running_tasks.pop(task.task_id, None)
    
    async def wait_all(self):
        """等待所有任务完成"""
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
    
    def get_status(self) -> dict:
        """获取调度器状态
        
        Returns:
            dict: 状态信息
        """
        return {
            "total": len(self.tasks),
            "running": len(self.running),
            "completed": len(self.completed),
            "failed": len(self.failed),
            "tasks": {tid: t.status for tid, t in self.tasks.items()},
        }
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取指定任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Task]: 任务对象
        """
        return self.tasks.get(task_id)
    
    def reset(self):
        """重置调度器状态"""
        self.tasks.clear()
        self.running.clear()
        self.completed.clear()
        self.failed.clear()
        self._running_tasks.clear()
