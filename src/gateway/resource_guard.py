"""资源监控保护器，防止内存泄漏和资源耗尽

V3.3 P0 - 资源限制保护核心组件
依赖: psutil
"""
import asyncio
import shutil
import threading
from typing import Tuple, Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


class ResourceGuardError(Exception):
    """资源超限时抛出的异常"""
    def __init__(self, resource_type: str, current: float, limit: float, unit: str):
        self.resource_type = resource_type
        self.current = current
        self.limit = limit
        self.unit = unit
        super().__init__(
            f"ResourceGuard: {resource_type} exceeded limit "
            f"({current:.1f}{unit} > {limit:.1f}{unit})"
        )


class ResourceGuard:
    """资源监控保护器，防止内存泄漏和资源耗尽"""
    
    def __init__(
        self,
        memory_threshold_mb: float = 500.0,
        file_handle_limit: int = 1000,
        disk_threshold_gb: float = 10.0,
    ):
        self.memory_threshold_mb = memory_threshold_mb
        self.file_handle_limit = file_handle_limit
        self.disk_threshold_gb = disk_threshold_gb
        
        self._lock = threading.Lock()
        self._disabled = False
    
    def check_memory(self) -> Tuple[bool, float]:
        """检查内存使用情况
        Returns: (是否超限, 当前内存MB)
        """
        if psutil is None:
            return False, 0.0
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            exceeded = memory_mb > self.memory_threshold_mb
            return exceeded, memory_mb
        except Exception:
            return False, 0.0
    
    def check_file_handles(self) -> Tuple[bool, int]:
        """检查文件句柄数量
        Returns: (是否超限, 当前句柄数)
        """
        if psutil is None:
            return False, 0
        
        try:
            process = psutil.Process()
            num_fds = process.num_fds()
            exceeded = num_fds > self.file_handle_limit
            return exceeded, num_fds
        except (AttributeError, OSError):
            # Windows 不支持 num_fds
            return False, 0
    
    def check_disk(self, path: str = ".") -> Tuple[bool, float]:
        """检查磁盘可用空间
        Returns: (是否超限, 可用空间GB)
        """
        try:
            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024 ** 3)
            # 阈值是"低于多少算危险"，所以 free < threshold 表示危险
            exceeded = free_gb < self.disk_threshold_gb
            return exceeded, free_gb
        except Exception:
            return False, 0.0
    
    def guard(self) -> None:
        """如果任一资源超限，抛出 ResourceGuardError"""
        with self._lock:
            if self._disabled:
                return
            
            memory_exceeded, memory_mb = self.check_memory()
            if memory_exceeded:
                raise ResourceGuardError(
                    "memory", memory_mb, self.memory_threshold_mb, "MB"
                )
            
            fds_exceeded, num_fds = self.check_file_handles()
            if fds_exceeded:
                raise ResourceGuardError(
                    "file_handles", num_fds, self.file_handle_limit, ""
                )
            
            disk_exceeded, free_gb = self.check_disk()
            if disk_exceeded:
                raise ResourceGuardError(
                    "disk_free", free_gb, self.disk_threshold_gb, "GB"
                )
    
    async def async_guard(self) -> None:
        """异步版本：在独立线程中执行同步检查"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.guard)
    
    def disable(self) -> None:
        """禁用资源检查（用于测试）"""
        with self._lock:
            self._disabled = True
    
    def enable(self) -> None:
        """启用资源检查"""
        with self._lock:
            self._disabled = False
    
    def get_status(self) -> dict:
        """获取当前资源状态快照"""
        memory_exceeded, memory_mb = self.check_memory()
        fds_exceeded, num_fds = self.check_file_handles()
        disk_exceeded, free_gb = self.check_disk()
        
        return {
            "memory_mb": round(memory_mb, 1),
            "memory_exceeded": memory_exceeded,
            "memory_limit_mb": self.memory_threshold_mb,
            "file_handles": num_fds,
            "file_handles_exceeded": fds_exceeded,
            "file_handles_limit": self.file_handle_limit,
            "disk_free_gb": round(free_gb, 1),
            "disk_exceeded": disk_exceeded,
            "disk_threshold_gb": self.disk_threshold_gb,
            "disabled": self._disabled,
        }


# 全局默认实例
_default_guard: Optional[ResourceGuard] = None
_default_guard_lock = threading.Lock()


def get_default_guard() -> ResourceGuard:
    """获取默认全局资源保护器（双重检查锁单例）"""
    global _default_guard
    if _default_guard is None:
        with _default_guard_lock:
            if _default_guard is None:
                _default_guard = ResourceGuard()
    return _default_guard
