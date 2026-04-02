"""memory_manager.py - 长期记忆管理器 (V3.0 Phase 2)

管理 MEMORY.md 结构化事实，提供分类存储和记忆整合功能。
"""

import os
import re
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class MemoryTypeEnum(str, Enum):
    """记忆类型枚举"""
    USER = "user"           # 用户偏好、工作风格
    FEEDBACK = "feedback"   # 用户纠正、项目反馈
    PROJECT = "project"     # 当前任务、进度、阻塞点
    REFERENCE = "reference" # 文档链接、代码位置
    PATTERN = "pattern"     # 发现的工作模式、规律


@dataclass
class MemoryRecord:
    """记忆记录

    Attributes:
        memory_type: 记忆类型
        content: 记忆内容
        created_at: 创建时间
        updated_at: 更新时间
        tags: 标签列表
        access_count: 访问次数
    """
    memory_type: str
    content: str
    created_at: datetime = None
    updated_at: datetime = None
    tags: list = None
    access_count: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.tags is None:
            self.tags = []

    def to_markdown(self) -> str:
        """转换为Markdown格式

        Returns:
            str: Markdown格式的记忆
        """
        ts = self.updated_at.strftime("%Y-%m-%d %H:%M")
        tags_str = ", ".join(self.tags) if self.tags else ""
        header = f"## [{self.memory_type}] {ts}"
        if tags_str:
            header += f" #{tags_str}"

        return f"{header}\n\n{self.content}\n"

    def increment_access(self):
        """增加访问计数"""
        self.access_count += 1
        self.updated_at = datetime.now()


class MemoryManager:
    """长期记忆管理器 - 结构化事实

    管理 MEMORY.md 文件，提供：
    - save: 保存带类型标签的记忆
    - get: 获取记忆
    - list: 列出所有记忆
    - consolidate: 将近期事件整合为长期事实
    - search: 搜索记忆

    记忆类型：
    - user: 用户偏好、工作风格
    - feedback: 用户纠正、项目反馈
    - project: 当前任务、进度、阻塞点
    - reference: 文档链接、代码位置
    - pattern: 发现的工作模式、规律

    使用示例：
        manager = MemoryManager("/path/to/workspace")
        await manager.save("用户偏好简洁的SQL", MemoryTypeEnum.USER)
        records = manager.list_by_type(MemoryTypeEnum.PROJECT)
    """

    MEMORY_TYPES = {
        "user": "用户偏好、工作风格",
        "feedback": "用户纠正、项目反馈",
        "project": "当前任务、进度、阻塞点",
        "reference": "文档链接、代码位置",
        "pattern": "发现的工作模式、规律",
    }

    def __init__(self, workspace: str):
        """初始化记忆管理器

        Args:
            workspace: 工作区路径
        """
        self.workspace = workspace
        self.memory_file = os.path.join(workspace, "MEMORY.md")
        self._cache = None
        self._cache_time = None

    def _ensure_file(self):
        """确保记忆文件存在"""
        if not os.path.exists(self.memory_file):
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            self._write_header()

    def _write_header(self):
        """写入文件头"""
        header = """# 长期记忆

> 结构化事实存储

## 记忆类型说明

| 类型 | 说明 |
|------|------|
| user | 用户偏好、工作风格 |
| feedback | 用户纠正、项目反馈 |
| project | 当前任务、进度、阻塞点 |
| reference | 文档链接、代码位置 |
| pattern | 发现的工作模式、规律 |

---

"""
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write(header)

    def _parse_memory_file(self) -> list[MemoryRecord]:
        """解析记忆文件

        Returns:
            list[MemoryRecord]: 记忆记录列表
        """
        if not os.path.exists(self.memory_file):
            return []

        with open(self.memory_file, 'r', encoding='utf-8') as f:
            content = f.read()

        records = []
        current_type = None
        current_timestamp = None
        current_tags = []
        current_content_lines = []

        for line in content.split('\n'):
            # 检查类型头
            type_match = re.match(r'^## \[(\w+)\] (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', line)
            if type_match:
                # 保存上一个记忆
                if current_type is not None and current_content_lines:
                    content = '\n'.join(current_content_lines).strip()
                    if content:
                        records.append(MemoryRecord(
                            memory_type=current_type,
                            content=content,
                            created_at=datetime.fromisoformat(current_timestamp.replace(' ', 'T')),
                            updated_at=datetime.fromisoformat(current_timestamp.replace(' ', 'T')),
                            tags=current_tags,
                        ))

                current_type = type_match.group(1)
                current_timestamp = type_match.group(2)

                # 检查标签
                tag_match = re.search(r'#(.+)$', line)
                if tag_match:
                    current_tags = [t.strip() for t in tag_match.group(1).split(',')]
                else:
                    current_tags = []

                current_content_lines = []
                continue

            # 跳过标题和分隔线
            if line.startswith('# ') or line.startswith('---'):
                continue

            # 累积内容
            if current_type is not None:
                current_content_lines.append(line)

        # 保存最后一个记忆
        if current_type is not None and current_content_lines:
            content = '\n'.join(current_content_lines).strip()
            if content:
                records.append(MemoryRecord(
                    memory_type=current_type,
                    content=content,
                    created_at=datetime.fromisoformat(current_timestamp.replace(' ', 'T')),
                    updated_at=datetime.fromisoformat(current_timestamp.replace(' ', 'T')),
                    tags=current_tags,
                ))

        return records

    def _refresh_cache(self):
        """刷新缓存"""
        self._cache = self._parse_memory_file()
        self._cache_time = datetime.now()

    async def save(
        self,
        content: str,
        memory_type: str,
        tags: Optional[list] = None,
    ) -> MemoryRecord:
        """保存长期记忆

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            tags: 标签列表

        Returns:
            MemoryRecord: 保存的记忆记录
        """
        if memory_type not in self.MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}")

        self._ensure_file()

        record = MemoryRecord(
            memory_type=memory_type,
            content=content,
            tags=tags or [],
        )

        # 追加到文件
        with open(self.memory_file, 'a', encoding='utf-8') as f:
            f.write("\n")
            f.write(record.to_markdown())

        # 清除缓存
        self._cache = None

        return record

    async def consolidate(self, recent_history: list[str]) -> list[MemoryRecord]:
        """将近期事件整合为长期事实

        这是一个占位方法，实际的LLM整合逻辑需要在调用时提供。
        当前实现只是将历史记录追加到project类型记忆中。

        Args:
            recent_history: 最近的HISTORY.md条目列表

        Returns:
            list[MemoryRecord]: 新创建的记忆记录
        """
        if not recent_history:
            return []

        # 将历史整合为摘要
        summary = "### 近期事件摘要\n\n"
        for entry in recent_history[-20:]:  # 最多20条
            summary += f"- {entry}\n"

        # 保存为project类型记忆
        record = await self.save(
            content=summary,
            memory_type=MemoryTypeEnum.PROJECT,
            tags=["consolidated", datetime.now().strftime("%Y-%m-%d")],
        )

        return [record]

    def get(self, memory_type: Optional[str] = None) -> list[MemoryRecord]:
        """获取记忆

        Args:
            memory_type: 记忆类型过滤，None则返回所有

        Returns:
            list[MemoryRecord]: 记忆记录列表
        """
        if self._cache is None:
            self._refresh_cache()

        if memory_type is None:
            return self._cache

        return [r for r in self._cache if r.memory_type == memory_type]

    def list_by_type(self, memory_type: MemoryTypeEnum) -> list[MemoryRecord]:
        """按类型列出记忆

        Args:
            memory_type: 记忆类型

        Returns:
            list[MemoryRecord]: 该类型的所有记忆
        """
        return self.get(memory_type.value)

    def search(self, keyword: str, case_sensitive: bool = False) -> list[MemoryRecord]:
        """搜索记忆

        Args:
            keyword: 关键词
            case_sensitive: 是否区分大小写

        Returns:
            list[MemoryRecord]: 匹配的记忆
        """
        if self._cache is None:
            self._refresh_cache()

        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(keyword), flags)

        return [r for r in self._cache if pattern.search(r.content)]

    def count(self) -> dict:
        """统计各类型记忆数量

        Returns:
            dict: {类型: 数量}
        """
        if self._cache is None:
            self._refresh_cache()

        counts = {}
        for record in self._cache:
            counts[record.memory_type] = counts.get(record.memory_type, 0) + 1

        return counts

    def delete(self, memory_type: str, content_hint: str) -> bool:
        """删除记忆（通过内容匹配）

        Args:
            memory_type: 记忆类型
            content_hint: 内容提示（部分匹配）

        Returns:
            bool: 是否删除成功
        """
        if self._cache is None:
            self._refresh_cache()

        # 找到要删除的记录
        to_delete = None
        for record in self._cache:
            if record.memory_type == memory_type and content_hint in record.content:
                to_delete = record
                break

        if to_delete is None:
            return False

        # 重写文件
        self._refresh_cache()
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write("# 长期记忆\n\n> 结构化事实存储\n\n")
            f.write("## 记忆类型说明\n\n")
            f.write("| 类型 | 说明 |\n")
            f.write("|------|------|\n")
            for mtype, desc in self.MEMORY_TYPES.items():
                f.write(f"| {mtype} | {desc} |\n")
            f.write("\n---\n\n")

            for record in self._cache:
                if record != to_delete:
                    f.write(record.to_markdown())
                    f.write("\n")

        self._cache = None
        return True

    def clear_type(self, memory_type: str) -> int:
        """清空指定类型的所有记忆

        Args:
            memory_type: 记忆类型

        Returns:
            int: 删除的记忆数量
        """
        if self._cache is None:
            self._refresh_cache()

        to_keep = [r for r in self._cache if r.memory_type != memory_type]
        deleted_count = len(self._cache) - len(to_keep)

        if deleted_count == 0:
            return 0

        # 重写文件
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            f.write("# 长期记忆\n\n> 结构化事实存储\n\n")
            f.write("## 记忆类型说明\n\n")
            f.write("| 类型 | 说明 |\n")
            f.write("|------|------|\n")
            for mtype, desc in self.MEMORY_TYPES.items():
                f.write(f"| {mtype} | {desc} |\n")
            f.write("\n---\n\n")

            for record in to_keep:
                f.write(record.to_markdown())
                f.write("\n")

        self._cache = None
        return deleted_count
