"""Action → Tool 名称映射器

将 SOP action 名称映射到 ToolRegistry 中注册的工具名。
实现方案参考道衍设计文档 V2.0 Round 1。

使用方式：
    mapper = ActionToolMapper()
    tool_name = mapper.resolve("find_slow_queries")  # → "pg_session_analysis"
"""
from typing import Dict, Optional, List


# ---------------------------------------------------------------------------
# 默认映射表：SOP action → ToolRegistry 工具名
# ---------------------------------------------------------------------------
# 映射依据：postgres_tools.py 中的工具定义
#   - pg_session_analysis  → 会话分析（活跃/idle/idle in transaction）
#   - pg_lock_analysis     → 锁分析（阻塞会话/锁链）
#   - pg_slow_query       → 慢SQL分析（需要确认是否存在）
#   - pg_kill_session     → 会话终止
#
# 硬编码 SOP 中的 action 与 postgres_tools 的对应关系：
#   find_idle_sessions      → pg_session_analysis（带 state_filter）
#   find_blocking_sessions  → pg_lock_analysis
#   analyze_lock_chain      → pg_lock_analysis
#   find_slow_queries      → pg_session_analysis（配合 state_filter 或专用工具）
#   suggest_kill_blocker    → pg_kill_session（待实现）
#   execute_sql             → pg_execute_sql（待实现）
#   verify_*                → 对应查询工具
# ---------------------------------------------------------------------------

ACTION_TO_TOOL: Dict[str, str] = {
    # --- 会话管理 ---
    "find_idle_sessions":       "pg_session_analysis",
    "find_slow_queries":        "pg_session_analysis",   # 慢查询也是会话状态的一种
    "kill_session":             "pg_kill_session",        # 待 pg_kill_session 工具实现
    "verify_session_gone":      "pg_session_analysis",   # 通过查询验证会话消失
    "verify_session_killed":     "pg_session_analysis",
    "find_blocking_session":    "pg_lock_analysis",
    "find_blocking_sessions":    "pg_lock_analysis",

    # --- 锁分析 ---
    "analyze_lock_chain":       "pg_lock_analysis",
    "suggest_kill_blocker":     "pg_kill_session",

    # --- SQL执行 ---
    "execute_sql":              "pg_execute_sql",        # 待实现
    "verify_stats_updated":     "pg_session_analysis",   # 复用会话分析做简单验证

    # --- 索引/优化建议 ---
    "suggest_index":            "pg_index_analysis",

    # --- 复制相关 ---
    "check_replication":        "pg_replication_status",

    # --- 测试/桩 ---
    "action_a":                None,   # 测试桩，无真实工具
    "action_b":                None,
    "action_c":                None,
    "slow_query":              None,
    "unreliable_action":       None,
    "precheck":                None,
    "critical_action":          None,
    "cleanup":                 None,
    "explain_query":           None,   # 待实现 pg_explain
}


class ActionToolMapper:
    """
    SOP Action → Tool 名称映射器

    支持：
    - 默认映射表 + 自定义映射覆盖
    - 未知 action 返回 None（由调用方决定 fallback）
    - 批量注册
    """

    def __init__(self, custom_map: Optional[Dict[str, str]] = None):
        """
        Args:
            custom_map: 自定义映射表，会覆盖默认 ACTION_TO_TOOL 中的同名 key
        """
        self._map: Dict[str, str] = {**ACTION_TO_TOOL, **(custom_map or {})}

    def resolve(self, action: str) -> Optional[str]:
        """
        将 SOP action 映射到工具名。

        Args:
            action: SOP 中定义的 action 名称

        Returns:
            工具名（str），或 None（无映射，使用 mock）
        """
        return self._map.get(action)

    def register(self, action: str, tool_name: str) -> None:
        """动态注册单个映射"""
        self._map[action] = tool_name

    def register_batch(self, mappings: Dict[str, str]) -> None:
        """批量注册映射"""
        self._map.update(mappings)

    def get_all_actions(self) -> List[str]:
        """返回所有已注册 action 名称"""
        return list(self._map.keys())

    def get_all_mappings(self) -> Dict[str, str]:
        """返回完整映射表（包含 None 值）"""
        return dict(self._map)
