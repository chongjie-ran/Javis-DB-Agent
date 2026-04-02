"""memory_optimizer.py - 记忆优化器 (V3.0 Phase 2)

提供记忆压缩、清理、归档功能。
"""

import re
import os
from datetime import datetime, timedelta
from typing import Optional


class MemoryOptimizer:
    """记忆优化器

    功能：
    - compress: 单条记忆超过指定大小自动压缩
    - cleanup_old: 清理超过指定天数的低频记忆
    - archive_low_frequency: 低频且超过指定天数 → 归档而非删除

    使用示例：
        optimizer = MemoryOptimizer()
        compressed = optimizer.compress(long_content, max_size_kb=5)
        optimizer.cleanup_old("MEMORY.md", older_than_days=180)
    """

    def __init__(self, max_size_kb: int = 5):
        """初始化记忆优化器

        Args:
            max_size_kb: 单条记忆最大大小（KB），超过则压缩
        """
        self.max_size_kb = max_size_kb
        self.max_size_bytes = max_size_kb * 1024

    def compress(self, content: str, max_size_kb: Optional[int] = None) -> str:
        """压缩单条记忆

        当内容超过指定大小时，保留关键信息并压缩。

        Args:
            content: 原始内容
            max_size_kb: 最大大小（KB），None则使用默认值

        Returns:
            str: 压缩后的内容
        """
        if max_size_kb is not None:
            max_bytes = max_size_kb * 1024
        else:
            max_bytes = self.max_size_bytes

        content_bytes = content.encode('utf-8')
        if len(content_bytes) <= max_bytes:
            return content

        # 压缩策略：保留开头和结尾，中间部分摘要
        # 计算可保留的首尾长度（各40%）
        head_size = int(max_bytes * 0.4)
        tail_size = int(max_bytes * 0.4)
        head_size = min(head_size, len(content))

        # 找到合适的断点（句号或换行）
        head = content[:head_size]
        tail_start = len(content) - tail_size

        # 找到尾部开始的合适位置
        if tail_start > head_size:
            # 从句子边界开始
            for i in range(tail_start, len(content)):
                if content[i] in '。.!？?；;\n':
                    tail_start = i + 1
                    break

        tail = content[tail_start:]

        # 生成摘要说明
        original_lines = content.count('\n') + 1
        compressed_lines = head.count('\n') + 1 + tail.count('\n') + 1
        summary = f"\n\n[... 内容已压缩，原{original_lines}行，保留首尾 ...]"

        return head + summary + tail

    def _is_low_frequency(
        self,
        content: str,
        reference_date: datetime,
        older_than_days: int = 180,
    ) -> bool:
        """判断记忆是否为低频

        通过检查内容中的时间戳或访问记录判断频率。

        Args:
            content: 记忆内容
            reference_date: 参考日期
            older_than_days: 超过多少天视为低频

        Returns:
            bool: 是否低频
        """
        # 检查是否有时间戳
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
        ]

        has_timestamp = any(re.search(p, content) for p in date_patterns)

        # 如果没有时间戳，检查是否包含"低频"标记
        if not has_timestamp:
            return '[low-frequency]' in content.lower()

        # 如果有旧时间戳，可能低频
        if has_timestamp:
            for pattern in date_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    try:
                        if '/' in matches[0]:
                            date = datetime.strptime(matches[0], '%Y/%m/%d')
                        else:
                            date = datetime.strptime(matches[0], '%Y-%m-%d')
                        if (reference_date - date).days > older_than_days:
                            return True
                    except ValueError:
                        continue

        return False

    def cleanup_old(
        self,
        memory_file: str,
        older_than_days: int = 180,
        dry_run: bool = False,
    ) -> dict:
        """清理过期的低频记忆

        Args:
            memory_file: 记忆文件路径
            older_than_days: 超过多少天清理（默认180天=6个月）
            dry_run: True则只返回统计，不实际删除

        Returns:
            dict: 清理结果统计
        """
        if not os.path.exists(memory_file):
            return {
                'status': 'skipped',
                'reason': 'file_not_found',
                'removed_count': 0,
                'removed_size': 0,
            }

        with open(memory_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        reference_date = datetime.now()
        remove_indices = []
        removed_size = 0

        # 解析文件，识别记忆条目
        i = 0
        current_entry_lines = []
        current_entry_start = None

        while i < len(lines):
            line = lines[i]

            # 检测记忆条目开始（## 类型标签）
            if re.match(r'^## \w+', line.strip()):
                # 保存上一个条目
                if current_entry_start is not None:
                    entry_content = ''.join(current_entry_lines)
                    if self._is_low_frequency(entry_content, reference_date, older_than_days):
                        remove_indices.extend(range(current_entry_start, i))
                        removed_size += len(entry_content.encode('utf-8'))

                current_entry_start = i
                current_entry_lines = [line]
            elif current_entry_start is not None:
                current_entry_lines.append(line)

            i += 1

        # 处理最后一个条目
        if current_entry_start is not None:
            entry_content = ''.join(current_entry_lines)
            if self._is_low_frequency(entry_content, reference_date, older_than_days):
                remove_indices.extend(range(current_entry_start, len(lines)))
                removed_size += len(entry_content.encode('utf-8'))

        if dry_run or not remove_indices:
            return {
                'status': 'success',
                'dry_run': dry_run,
                'removed_count': len(set(remove_indices)),
                'removed_size': removed_size,
            }

        # 执行删除
        new_lines = [line for idx, line in enumerate(lines) if idx not in remove_indices]

        with open(memory_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        return {
            'status': 'success',
            'dry_run': dry_run,
            'removed_count': len(set(remove_indices)),
            'removed_size': removed_size,
        }

    def archive_low_frequency(
        self,
        memory_file: str,
        archive_file: Optional[str] = None,
        older_than_days: int = 180,
    ) -> dict:
        """归档低频记忆（非删除）

        将低频且过期的记忆移动到归档文件。

        Args:
            memory_file: 记忆文件路径
            archive_file: 归档文件路径，None则自动生成
            older_than_days: 超过多少天归档（默认180天=6个月）

        Returns:
            dict: 归档结果统计
        """
        if not os.path.exists(memory_file):
            return {
                'status': 'skipped',
                'reason': 'file_not_found',
                'archived_count': 0,
            }

        if archive_file is None:
            base, ext = os.path.splitext(memory_file)
            archive_file = f"{base}_archive{ext}"

        with open(memory_file, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        reference_date = datetime.now()

        archive_lines = []
        keep_lines = []
        current_entry_lines = []
        current_entry_start = None

        for i, line in enumerate(lines):
            # 检测记忆条目开始
            if re.match(r'^## \w+', line.strip()):
                # 保存上一个条目
                if current_entry_start is not None:
                    entry_content = '\n'.join(current_entry_lines)
                    if self._is_low_frequency(entry_content, reference_date, older_than_days):
                        archive_lines.extend(current_entry_lines)
                    else:
                        keep_lines.extend(current_entry_lines)

                current_entry_start = len(keep_lines) if keep_lines else 0
                current_entry_lines = [line]
            elif current_entry_lines:
                current_entry_lines.append(line)

        # 处理最后一个条目
        if current_entry_lines:
            entry_content = '\n'.join(current_entry_lines)
            if self._is_low_frequency(entry_content, reference_date, older_than_days):
                archive_lines.extend(current_entry_lines)
            else:
                keep_lines.extend(current_entry_lines)

        # 写入归档文件
        archived_count = len([l for l in archive_lines if l.startswith('## ')])
        if archive_lines:
            archive_header = f"\n\n<!-- Archived: {datetime.now().isoformat()} -->\n"
            with open(archive_file, 'a', encoding='utf-8') as f:
                f.write(archive_header)
                f.write('\n'.join(archive_lines))

        # 更新原文件
        if keep_lines:
            with open(memory_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(keep_lines))

        return {
            'status': 'success',
            'archived_count': archived_count,
            'archive_file': archive_file,
        }
