"""
执行策略模块
定义并行/串行执行策略，根据Intent类型决定执行方式
"""
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.orchestrator import Intent

# 并行Intent配置：哪些Intent需要并行执行哪些Agent（使用字符串key避免循环导入）
PARALLEL_INTENTS: dict[str, list[str]] = {
    "diagnose": ["diagnostic", "risk"],
    "sql_analyze": ["sql_analyzer", "risk"],
    "analyze_session": ["session_analyzer", "performance"],
    "root_cause": ["alert", "diagnostic", "risk"],
    "inspect": ["inspector", "capacity"],
    "risk_assess": ["risk", "sql_analyzer", "session_analyzer"],
}

# 需要串行执行的Intent（按顺序依赖）- 使用字符串
SEQUENTIAL_INTENTS: set[str] = {
    "report",           # 报告需要先生成内容
    "detect_deadlock",  # 死锁检测需要先分析会话
    "suggest_index",    # 索引建议需要先分析SQL
    "predict_growth",   # 增长预测需要先有容量数据
    "capacity_report",  # 容量报告需要先收集数据
    "analyze_alert",    # 告警分析需要先收集上下文
    "deduplicate_alerts",  # 告警去重需要先分析
    "predictive_alert",    # 预测性告警需要先分析趋势
    "analyze_backup",      # 备份分析需要先检查状态
    "analyze_performance", # 性能分析需要先收集指标
    "general",             # 通用问答串行执行
}

# Agent执行超时配置（毫秒）
AGENT_TIMEOUT: dict[str, int] = {
    "diagnostic": 30000,
    "risk": 20000,
    "sql_analyzer": 30000,
    "session_analyzer": 25000,
    "performance": 30000,
    "alert": 25000,
    "capacity": 25000,
    "inspector": 20000,
    "reporter": 15000,
    "backup": 30000,
}
DEFAULT_TIMEOUT_MS = 30000  # 默认超时30秒


class ExecutionStrategy(ABC):
    """执行策略抽象基类"""

    @abstractmethod
    def should_parallel(self, intent_value: str, agent_names: list[str]) -> bool:
        """
        判断是否应该并行执行
        
        Args:
            intent_value: Intent值字符串
            agent_names: 计划的Agent列表
            
        Returns:
            True=并行, False=串行
        """
        pass

    @abstractmethod
    def get_timeout(self, agent_name: str) -> int:
        """
        获取Agent执行超时时间
        
        Args:
            agent_name: Agent名称
            
        Returns:
            超时时间（毫秒）
        """
        pass

    @abstractmethod
    def get_expected_agents(self, intent_value: str) -> list[str]:
        """
        获取Intent预期的Agent列表
        
        Args:
            intent_value: Intent值字符串
            
        Returns:
            Agent名称列表
        """
        pass


class ParallelStrategy(ExecutionStrategy):
    """并行执行策略"""

    def should_parallel(self, intent_value: str, agent_names: list[str]) -> bool:
        # 如果Intent配置为串行，则串行
        if intent_value in SEQUENTIAL_INTENTS:
            return False
        
        # 如果只有单个Agent，无需并行
        if len(agent_names) <= 1:
            return False
        
        # 如果Intent配置为并行，则并行
        if intent_value in PARALLEL_INTENTS:
            return True
        
        # 默认：2个以上Agent可以并行
        return len(agent_names) >= 2

    def get_timeout(self, agent_name: str) -> int:
        return AGENT_TIMEOUT.get(agent_name, DEFAULT_TIMEOUT_MS)

    def get_expected_agents(self, intent_value: str) -> list[str]:
        return PARALLEL_INTENTS.get(intent_value, [])


class SequentialStrategy(ExecutionStrategy):
    """串行执行策略"""

    def should_parallel(self, intent_value: str, agent_names: list[str]) -> bool:
        return False  # 始终串行

    def get_timeout(self, agent_name: str) -> int:
        # 串行模式下可以给更长超时
        base_timeout = AGENT_TIMEOUT.get(agent_name, DEFAULT_TIMEOUT_MS)
        return int(base_timeout * 1.5)

    def get_expected_agents(self, intent_value: str) -> list[str]:
        return []  # 串行模式不预设Agent列表
