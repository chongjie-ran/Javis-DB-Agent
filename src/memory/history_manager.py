"""history_manager.py - 短期记忆管理器 (V3.0 Phase 2)

管理 HISTORY.md 事件日志，提供追加、查询、grep功能。
"""

import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HistoryEntry:
    """历史记录条目

    Attributes:
        timestamp: 时间戳
        event: 事件内容
        category: 事件类别（iteration/error/tool/complete）
        metadata: 额外元数据
    """
    event: str
    category: str = "general"
    timestamp: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_markdown(self) -> str:
        """转换为Markdown格式

        Returns:
            str: Markdown格式的条目
        """
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M")
        meta_str = ""
        if self.metadata:
            meta_parts = [f"{k}={v}" for k, v in self.metadata.items()]
            meta_str = f" [{', '.join(meta_parts)}]"

        return f"- [{self.category}] {self.event}{meta_str}"


class HistoryManager:
    """短期记忆管理器 - 事件日志

    管理 HISTORY.md 文件，提供：
    - append: 追加事件
    - get_recent: 获取最近N条
    - grep: 模式搜索
    - count: 统计条目数

    文件格式：
        ## YYYY-MM-DD HH:MM
        - [category] 事件内容 [metadata]

    使用示例：
        manager = HistoryManager("/path/to/workspace")
        await manager.append(HistoryEntry("完成了SQL优化", category="iteration"))
        recent = manager.get_recent(10)
        matches = manager.grep("error|failed")
    """

    def __init__(self, workspace: str):
        """初始化历史管理器

        Args:
            workspace: 工作区路径
        """
        self.workspace = workspace
        self.history_file = os.path.join(workspace, "HISTORY.md")

    def _ensure_file(self):
        """确保历史文件存在"""
        if not os.path.exists(self.history_file):
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.write("# 历史记录\n\n")
                f.write("> 短期记忆 - 事件日志\n\n")

    def _get_date_header(self, dt: Optional[datetime] = None) -> str:
        """获取日期头

        Args:
            dt: 日期时间，None则使用当前时间

        Returns:
            str: Markdown日期头
        """
        if dt is None:
            dt = datetime.now()
        return f"## {dt.strftime('%Y-%m-%d')}"

    async def append(self, entry: HistoryEntry) -> str:
        """追加事件到历史

        Args:
            entry: 历史条目

        Returns:
            str: 追加的内容
        """
        self._ensure_file()

        markdown = entry.to_markdown()
        date_header = self._get_date_header(entry.timestamp)

        with open(self.history_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否需要新的日期头
        lines = content.split('\n')
        last_date_header = None
        insert_pos = len(content)

        for i, line in enumerate(lines):
            if line.startswith('## '):
                last_date_header = line

        # 如果最后日期头不是今天，添加新的日期头
        if last_date_header != date_header:
            # 在文件末尾添加新日期头
            if content.endswith('\n'):
                insert_pos = len(content)
            else:
                insert_pos = len(content)
                markdown = '\n\n' + date_header + '\n' + markdown
        else:
            # 同一日期，检查是否需要换行
            if not content.endswith('\n\n'):
                if content.endswith('\n'):
                    markdown = '\n' + markdown
                else:
                    markdown = '\n\n' + markdown

        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(markdown)

        return markdown

    def get_recent(self, count: int = 10) -> list[str]:
        """获取最近N条事件

        Args:
            count: 获取数量

        Returns:
            list[str]: 最近的事件列表
        """
        if not os.path.exists(self.history_file):
            return []

        with open(self.history_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 收集所有事件行（以- 开头）
        events = []
        for line in lines:
            if line.strip().startswith('- '):
                events.append(line.strip())

        # 返回最后count条
        return events[-count:] if len(events) > count else events

    def grep(self, pattern: str, case_sensitive: bool = False) -> list[str]:
        """搜索匹配的事件

        Args:
            pattern: 正则表达式模式
            case_sensitive: 是否区分大小写

        Returns:
            list[str]: 匹配的事件列表
        """
        if not os.path.exists(self.history_file):
            return []

        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            regex = re.compile(pattern, flags)
        except re.error:
            # 如果正则无效，当作普通字符串搜索
            pattern = re.escape(pattern)
            regex = re.compile(pattern, flags)

        with open(self.history_file, 'r', encoding='utf-8') as f:
            content = f.read()

        matches = []
        for line in content.split('\n'):
            if line.strip().startswith('- ') and regex.search(line):
                matches.append(line.strip())

        return matches

    def count(self) -> int:
        """统计事件总数

        Returns:
            int: 事件数量
        """
        if not os.path.exists(self.history_file):
            return 0

        with open(self.history_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return len([l for l in content.split('\n') if l.strip().startswith('- ')])

    def get_by_category(self, category: str) -> list[str]:
        """按类别获取事件

        Args:
            category: 类别名（如 error, iteration, tool）

        Returns:
            list[str]: 该类别的所有事件
        """
        pattern = rf'\[\s*{re.escape(category)}\s*\]'
        return self.grep(pattern)

    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> list[str]:
        """按日期范围获取事件

        Args:
            start_date: 开始日期
            end_date: 结束日期，None则到今天

        Returns:
            list[str]: 该日期范围内的事件
        """
        if end_date is None:
            end_date = datetime.now()

        if not os.path.exists(self.history_file):
            return []

        with open(self.history_file, 'r', encoding='utf-8') as f:
            content = f.read()

        results = []
        current_date = None
        in_range = False

        for line in content.split('\n'):
            # 检查日期头
            date_match = re.match(r'^## (\d{4}-\d{2}-\d{2})', line)
            if date_match:
                current_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                in_range = start_date <= current_date <= end_date
                continue

            if in_range and line.strip().startswith('- '):
                results.append(line.strip())

        return results

    def clear(self) -> bool:
        """清空历史（谨慎使用）

        Returns:
            bool: 是否成功
        """
        if not os.path.exists(self.history_file):
            return True

        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.write("# 历史记录\n\n")
                f.write("> 短期记忆 - 事件日志\n\n")
            return True
        except Exception:
            return False
