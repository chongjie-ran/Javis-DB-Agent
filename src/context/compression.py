"""Context Compression - 对话历史压缩策略 (V3.2 P2)

压缩策略：
1. 识别并保留关键决策（analysis/conclusion/action决定）
2. 合并重复的tool调用结果
3. 截断超长中间结果
4. 保留首尾消息（系统提示+最近上下文）
5. 用摘要替换连续相似消息

工具函数 compress_messages() 可独立使用。
"""
import re
from typing import Any


# 关键词权重：出现这些词的消息优先级更高
DECISION_KEYWORDS = [
    "决定", "结论", "分析", "方案", "策略", "执行",
    "CREATE", "DROP", "ALTER", "DELETE", "TRUNCATE",  # DDL危险操作
    "confirmed", "approved", "conclusion", "decision", "action taken",
    "错误", "异常", "失败", "告警", "critical", "error",
]


def score_message_importance(message: dict) -> tuple[int, str]:
    """
    给单条消息打分，判断其重要性

    Returns:
        (importance_score, reason)
    """
    role = message.get("role", "")
    content = str(message.get("content", ""))

    # 系统消息和用户消息高优先级
    if role == "system":
        return 100, "system_prompt"
    if role == "user":
        return 80, "user_input"

    # 助手的最终决策/结论
    for kw in DECISION_KEYWORDS:
        if kw.lower() in content.lower():
            return 90, f"decision_keyword:{kw}"

    # 包含tool调用的assistant消息
    if message.get("tool_calls") or message.get("role") == "assistant":
        if role == "tool":
            return 30, "tool_result"
        return 50, "assistant_message"

    return 40, "routine"


def compress_messages(
    messages: list[dict],
    max_messages: int = 50,
    max_tokens_estimate: int = 80000,
) -> tuple[list[dict], dict]:
    """
    压缩消息列表，保留关键内容

    Args:
        messages: 原始消息列表
        max_messages: 最多保留消息条数
        max_tokens_estimate: token预算上限

    Returns:
        (compressed_messages, stats_dict)
    """
    if len(messages) <= max_messages:
        return list(messages), {"compressed": False, "removed": 0}

    stats = {
        "compressed": True,
        "removed": len(messages) - max_messages,
        "strategy": "importance_based",
    }

    # Step 1: 打分
    scored = []
    for i, msg in enumerate(messages):
        score, reason = score_message_importance(msg)
        scored.append((i, msg, score, reason))

    # Step 2: 排序 - 优先保留重要的
    # 策略：头尾必留，中间按分数
    preserved_indices = {0, len(messages) - 1}  # system + last
    # 找 system 消息索引
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            preserved_indices.add(i)

    # 保留分数最高的消息
    sorted_by_score = sorted(scored, key=lambda x: x[2], reverse=True)
    for idx, _, score, reason in sorted_by_score[:max_messages]:
        if idx not in preserved_indices:
            preserved_indices.add(idx)

    # Step 3: 构建压缩后的消息
    compressed = []
    kept_indices = sorted(preserved_indices)

    # 如果保留的仍然太多，按分数继续裁剪
    while len(kept_indices) > max_messages:
        # 找分数最低且不是user/system的
        lowest_score = None
        lowest_idx = None
        for idx in kept_indices:
            if idx not in {0, len(messages) - 1} and messages[idx].get("role") not in {"system", "user"}:
                s = next((x[2] for x in scored if x[0] == idx), 0)
                if lowest_score is None or s < lowest_score:
                    lowest_score = s
                    lowest_idx = idx
        if lowest_idx is not None:
            kept_indices.remove(lowest_idx)
            stats["removed"] += 1

    # Step 4: 对被删除的连续区间生成摘要
    # 找所有被删除的区间
    all_indices = set(range(len(messages)))
    removed = sorted(all_indices - set(kept_indices))

    kept_set = set(kept_indices)
    compressed = []
    skip_ranges = []  # [(start, end), ...]

    i = 0
    while i < len(messages):
        if i in kept_set:
            compressed.append(messages[i])
            i += 1
        else:
            # 找连续被删除的区间
            start = i
            while i < len(messages) and i not in kept_set:
                i += 1
            end = i - 1
            # 生成摘要消息
            summary = _summarize_range(messages[start:i])
            compressed.append(summary)
            stats["removed"] += (end - start + 1) - 1  # -1 because we added 1 summary

    stats["kept_messages"] = len(compressed)
    return compressed, stats


def _summarize_range(messages: list[dict]) -> dict:
    """为一组被压缩的消息生成摘要"""
    count = len(messages)
    tool_calls = sum(1 for m in messages if m.get("tool_calls"))
    tool_results = sum(1 for m in messages if m.get("role") == "tool")
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)

    summary_text = (
        f"[{count}条消息已压缩] "
        f"tool_calls={tool_calls}, tool_results={tool_results}, "
        f"原始字符数≈{total_chars}"
    )

    # 提取关键词
    all_content = " ".join(str(m.get("content", "")) for m in messages)
    key_findings = []
    for kw in ["错误", "告警", "失败", "error", "critical", "warning", "成功", "success"]:
        if kw.lower() in all_content.lower():
            key_findings.append(kw)

    if key_findings:
        summary_text += f" | 关键: {', '.join(set(key_findings))}"

    return {
        "role": "system",
        "content": summary_text,
        "_compressed": True,
        "_original_count": count,
    }


class ContextCompressor:
    """
    上下文压缩器

    使用方式:
        compressor = ContextCompressor(max_messages=40)
        compressed, stats = compressor.compress(messages)
    """

    def __init__(
        self,
        max_messages: int = 40,
        max_tokens_estimate: int = 80000,
        preserve_system: bool = True,
    ):
        self.max_messages = max_messages
        self.max_tokens_estimate = max_tokens_estimate
        self.preserve_system = preserve_system

    def compress(self, messages: list[dict]) -> tuple[list[dict], dict]:
        """压缩消息列表"""
        return compress_messages(
            messages,
            max_messages=self.max_messages,
            max_tokens_estimate=self.max_tokens_estimate,
        )
