"""
AutoMemory - 自动记忆机制 (V3.1 P0改进)

Claude Code Auto Memory 借鉴：
- 自动从纠正中学习
- 轻量提取，不干扰主流程
- 类型分类 + 绝对不记过滤器

工作流程：
1. 每次会话结束时分析纠正
2. 按类型分类提取记忆
3. 写入记忆B层（SQLite）
4. 下次类似场景自动检索
"""

import re
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List

from .memory_manager import MemoryManager, MemoryRecord


@dataclass
class Correction:
    """纠正记录"""
    original_action: str       # 原始行为/结论
    correction: str           # 纠正内容
    reason: Optional[str] = None  # 纠正原因
    timestamp: datetime = None
    session_id: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AutoMemory:
    """
    自动记忆系统

    从纠正中自动提取学习点，不干扰主流程。

    记忆类型（与MemoryManager一致）：
    - feedback: 被纠正的行为
    - pattern: 发现的工作模式
    - reference: 代码/文档位置

    绝对不记过滤器：
    - 代码语法（grep能查到）
    - Git历史（git log能查到）
    - 常识性知识（公开文档能查到）
    """

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self._session_corrections: List[Correction] = []

    def record_correction(self, original: str, correction: str, reason: Optional[str] = None) -> None:
        """
        记录一次纠正

        Args:
            original: 原始行为/结论
            correction: 纠正内容
            reason: 纠正原因
        """
        corr = Correction(
            original_action=original,
            correction=correction,
            reason=reason,
        )
        self._session_corrections.append(corr)
        print(f"[AutoMemory] 记录纠正: {original[:50]}... -> {correction[:50]}...")

    def should_remember(self, content: str) -> bool:
        """
        记忆过滤器：判断内容是否值得记忆

        绝对不记清单：
        - 代码语法（包含def/class/import等关键字）
        - Git命令（包含git commit/push等）
        - 调试步骤（包含print/logger/debug等）
        """
        # 绝对不记模式（更精确的匹配）
        never_remember_patterns = [
            r'^\s*def\s+\w+\s*\(',      # 函数定义（行首）
            r'^\s*class\s+\w+\s*[:(]',   # 类定义
            r'^\s*(import\s+\S+|from\s+\S+\s+import\b)',              # 导入语句
            r'git\s+(commit|push|pull|merge|checkout|branch)\s+',  # Git操作
            r'^\s*print\s*\(',             # print调试
            r'logger\.(debug|info|warning|error)\s*\(',  # 日志
        ]

        for pattern in never_remember_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return False

        # 长度检查：太短的不值得记
        if len(content) < 3:  # Minimum meaningful content length
            return False

        return True

    def extract_memory_type(self, correction: Correction) -> str:
        """
        从纠正中推断记忆类型

        Returns:
            str: feedback/pattern/reference
        """
        correction_text = f"{correction.original_action} {correction.correction}"

        # 模式识别
        if any(kw in correction_text.lower() for kw in ["总是", "每次", "规律", "模式"]):
            return "pattern"
        # 引用识别
        elif any(kw in correction_text.lower() for kw in ["在", "位置", "文件", "代码"]):
            return "reference"
        # 默认反馈
        return "feedback"

    def consolidate_session(self) -> int:
        """
        会话结束时整合记忆

        Returns:
            int: 写入的记忆数量
        """
        if not self._session_corrections:
            return 0

        count = 0
        for corr in self._session_corrections:
            # 过滤
            if not self.should_remember(corr.correction):
                continue

            # 确定类型
            mem_type = self.extract_memory_type(corr)

            # 构建记忆内容
            content = f"原始: {corr.original_action}\n纠正: {corr.correction}"
            if corr.reason:
                content += f"\n原因: {corr.reason}"

            # 写入记忆
            import asyncio
            record = MemoryRecord(
                memory_type=mem_type,
                content=content,
                tags=["auto-memory", "correction"],
            )
            asyncio.run(self.memory_manager.save(
                content=content,
                memory_type=mem_type,
                tags=["auto-memory", "correction"],
            ))
            count += 1

        # 清空会话记录
        self._session_corrections.clear()
        print(f"[AutoMemory] 会话结束，写入 {count} 条记忆")
        return count

    def get_learnings(self, context: str, limit: int = 3) -> List[str]:
        """
        获取相关学习点

        Args:
            context: 当前上下文/任务描述
            limit: 返回数量

        Returns:
            List[str]: 相关记忆列表
        """
        # 搜索相关记忆
        results = self.memory_manager.search(context)[:limit * 2]

        learnings = []
        for record in results:
            if record.memory_type == "feedback":
                learnings.append(f"[反馈] {record.content[:100]}...")

        return learnings[:limit]
