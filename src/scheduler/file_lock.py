"""文件锁管理器 - 提供文件级别的并发控制"""

import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict


class FileLockManager:
    """文件锁管理器 - 使用asyncio.Lock实现文件级别的互斥访问
    
    特性：
    - 每个文件一个锁，避免写冲突
    - 按路径排序获取多个锁，避免死锁
    - 线程安全，支持异步并发
    """
    
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock: asyncio.Lock = asyncio.Lock()  # 保护_locks字典
    
    async def get_lock(self, file_path: str) -> asyncio.Lock:
        """获取指定文件的锁
        
        Args:
            file_path: 文件路径
            
        Returns:
            asyncio.Lock: 该文件的锁
        """
        async with self._lock:
            if file_path not in self._locks:
                self._locks[file_path] = asyncio.Lock()
            return self._locks[file_path]
    
    @asynccontextmanager
    async def acquire(self, file_path: str):
        """获取单个文件锁的上下文管理器
        
        Args:
            file_path: 文件路径
            
        Usage:
            async with lock_manager.acquire("path/to/file"):
                # 访问文件的临界区
                pass
        """
        lock = await self.get_lock(file_path)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
    
    @asynccontextmanager
    async def acquire_multiple(self, file_paths: list[str]):
        """获取多个文件锁的上下文管理器（按字母顺序避免死锁）
        
        Args:
            file_paths: 文件路径列表
            
        Usage:
            async with lock_manager.acquire_multiple(["file1.py", "file2.py"]):
                # 同时访问多个文件的临界区
                pass
        """
        if not file_paths:
            yield
            return
        
        # 按路径排序避免死锁
        sorted_paths = sorted(set(file_paths))
        locks = []
        
        # 按顺序获取所有锁
        for path in sorted_paths:
            lock = await self.get_lock(path)
            await lock.acquire()
            locks.append(lock)
        
        try:
            yield
        finally:
            # 逆序释放锁
            for lock in reversed(locks):
                lock.release()
    
    def release_all(self):
        """释放所有锁（用于测试或重置）"""
        # 注意：这是一个同步方法，不应在持有锁时调用
        self._locks.clear()
