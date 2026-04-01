"""
Agent 置信度计算模块
定义各Agent的置信度基线，提供置信度计算和归一化功能
"""
from dataclasses import dataclass
from typing import Optional

# Agent 置信度基线
AGENT_CONFIDENCE: dict[str, float] = {
    "diagnostic": 0.9,
    "risk": 0.85,
    "sql_analyzer": 0.9,
    "session_analyzer": 0.85,
    "performance": 0.8,
    "alert": 0.85,
    "capacity": 0.8,
    "inspector": 0.9,
    "reporter": 0.95,
    "backup": 0.85,
}


@dataclass
class AgentConfidence:
    """Agent置信度信息"""
    agent_name: str
    baseline: float          # 置信度基线
    dynamic_score: float     # 动态置信度（基于执行情况）
    final_score: float       # 最终置信度 = baseline * dynamic_score

    def __post_init__(self):
        # 最终置信度 = 基线 * 动态分数
        self.final_score = self.baseline * self.dynamic_score


class ConfidenceCalculator:
    """
    置信度计算器
    
    职责：
    1. 根据Agent类型返回基线置信度
    2. 根据执行结果计算动态置信度
    3. 提供置信度归一化功能
    """

    @staticmethod
    def get_baseline(agent_name: str) -> float:
        """
        获取Agent置信度基线
        
        Args:
            agent_name: Agent名称
            
        Returns:
            置信度基线值 (0.0-1.0)
        """
        return AGENT_CONFIDENCE.get(agent_name, 0.75)

    @staticmethod
    def calculate_dynamic_score(
        success: bool,
        has_content: bool,
        execution_time_ms: int,
        error: str = "",
        tool_calls_count: int = 0
    ) -> float:
        """
        计算动态置信度分数
        
        基于执行情况动态调整置信度：
        - 成功执行 + 有内容：分数接近1.0
        - 执行失败：降低分数
        - 超时：显著降低分数
        - 有错误信息：根据错误类型降低
        
        Args:
            success: 执行是否成功
            has_content: 是否有有效内容输出
            execution_time_ms: 执行时间(毫秒)
            error: 错误信息
            tool_calls_count: 工具调用次数
            
        Returns:
            动态置信度分数 (0.0-1.0)
        """
        if not success:
            # 执行失败，根据错误类型调整
            if "timeout" in error.lower():
                return 0.3
            if "permission" in error.lower() or "权限" in error:
                return 0.4
            if "connection" in error.lower() or "连接" in error:
                return 0.5
            return 0.2

        if not has_content:
            return 0.1

        # 基础分数
        score = 0.8

        # 执行时间调整（超时意味可能不完整）
        if execution_time_ms > 30000:  # 超过30秒
            score -= 0.1
        elif execution_time_ms < 5000:  # 执行很快，可能分析不够深入
            score += 0.05

        # 工具调用次数调整（合理调用说明有实质性分析）
        if tool_calls_count > 0:
            score += min(0.1, tool_calls_count * 0.02)

        return max(0.1, min(1.0, score))

    @staticmethod
    def normalize_scores(scores: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """
        归一化多个Agent的置信度分数
        
        使用softmax风格的归一化，确保总分合理。
        
        Args:
            scores: [(agent_name, score), ...] 列表
            
        Returns:
            归一化后的 [(agent_name, normalized_score), ...]
        """
        if not scores:
            return []

        if len(scores) == 1:
            return [(scores[0][0], 1.0)]

        # 计算总和
        total = sum(s[1] for s in scores)
        if total == 0:
            # 全零情况，平分
            norm = 1.0 / len(scores)
            return [(s[0], norm) for s in scores]

        # 归一化
        return [(s[0], s[1] / total) for s in scores]

    @staticmethod
    def compute_weighted_confidence(
        agent_name: str,
        success: bool,
        has_content: bool,
        execution_time_ms: int,
        error: str = "",
        tool_calls_count: int = 0
    ) -> AgentConfidence:
        """
        计算Agent的完整置信度信息
        
        Args:
            agent_name: Agent名称
            success: 执行是否成功
            has_content: 是否有有效内容
            execution_time_ms: 执行时间
            error: 错误信息
            tool_calls_count: 工具调用次数
            
        Returns:
            AgentConfidence 对象
        """
        baseline = ConfidenceCalculator.get_baseline(agent_name)
        dynamic_score = ConfidenceCalculator.calculate_dynamic_score(
            success=success,
            has_content=has_content,
            execution_time_ms=execution_time_ms,
            error=error,
            tool_calls_count=tool_calls_count
        )
        return AgentConfidence(
            agent_name=agent_name,
            baseline=baseline,
            dynamic_score=dynamic_score,
            final_score=baseline * dynamic_score
        )
