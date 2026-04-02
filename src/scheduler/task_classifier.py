"""任务分类器 - 根据任务描述判断任务类型"""

import asyncio
import inspect
from enum import Enum
from typing import Optional, Awaitable


class TaskType(Enum):
    """任务类型枚举"""
    READ_ONLY = "read_only"           # 读操作：自由并行
    WRITE_SAME_FILE = "write_same_file"   # 同文件写：串行
    WRITE_DIFF_FILE = "write_diff_file"    # 不同文件写：并行
    VERIFY = "verify"                 # 验证：与实现并行


class Task:
    """任务数据结构"""
    
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        files: list[str] = None,       # 涉及的文件
        blocked_by: list[str] = None,  # 被哪些任务阻塞
        execute_fn: Optional[Awaitable] = None,  # 执行函数
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.files = files or []
        self.blocked_by = blocked_by or []
        self.status = "pending"
        self.error: Optional[str] = None
        self._execute_fn = execute_fn
    
    async def execute(self):
        """执行任务"""
        if self._execute_fn:
            if inspect.iscoroutinefunction(self._execute_fn):
                await self._execute_fn()
            else:
                # 同步函数，直接调用
                self._execute_fn()


class TaskClassifier:
    """任务分类器 - 根据任务描述判断任务类型"""
    
    READ_ONLY_PATTERNS = [
        "read", "search", "grep", "find", "analyze",
        "inspect", "query", "fetch", "get", "list",
        "show", "display", "view", "cat", "head", "tail",
    ]
    
    WRITE_PATTERNS = [
        "write", "edit", "create", "delete", "modify",
        "update", "patch", "append", "insert", "remove",
        "replace", "add", "set",
    ]
    
    VERIFY_PATTERNS = [
        "test", "verify", "validate", "check", "assert",
        "pytest", "unittest", "coverage", "lint", "format",
    ]
    
    def _matches(self, text: str, patterns: list[str]) -> bool:
        """检查文本是否匹配任一模式"""
        for pattern in patterns:
            if pattern in text:
                return True
        return False
    
    def classify(self, task_description: str) -> TaskType:
        """根据任务描述分类
        
        Args:
            task_description: 任务描述（通常为工具名+参数）
            
        Returns:
            TaskType: 任务类型
        """
        desc_lower = task_description.lower()
        
        if self._matches(desc_lower, self.VERIFY_PATTERNS):
            return TaskType.VERIFY
        elif self._matches(desc_lower, self.WRITE_PATTERNS):
            # 需要检查是否写同一文件，默认认为是同文件写
            return TaskType.WRITE_SAME_FILE
        elif self._matches(desc_lower, self.READ_ONLY_PATTERNS):
            return TaskType.READ_ONLY
        else:
            # 默认读操作
            return TaskType.READ_ONLY
    
    def classify_with_files(
        self,
        task_description: str,
        files: list[str]
    ) -> tuple[TaskType, list[str]]:
        """根据任务描述和涉及文件分类
        
        Args:
            task_description: 任务描述
            files: 涉及的文件列表
            
        Returns:
            tuple[TaskType, list[str]]: (任务类型, 涉及的文件)
        """
        task_type = self.classify(task_description)
        
        # 如果是写操作且没有指定文件，设置为WRITE_DIFF_FILE（默认并行）
        if task_type == TaskType.WRITE_SAME_FILE and not files:
            return TaskType.WRITE_DIFF_FILE, files
        
        return task_type, files
