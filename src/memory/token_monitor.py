"""token_monitor.py - Token预算监控 (V3.0 Phase 2)"""

from enum import Enum
from dataclasses import dataclass


class TokenStatus(str, Enum):
    """Token状态枚举"""
    NORMAL = "normal"      # < 80%
    WARNING = "warning"    # 80% - 95%
    DANGER = "danger"      # 95% - 100%
    EXHAUSTED = "exhausted"  # >= 100%


@dataclass
class TokenBudget:
    """Token预算信息"""
    current: int
    threshold: int
    status: TokenStatus
    percentage: float

    @property
    def remaining(self) -> int:
        return max(0, self.threshold - self.current)


class TokenMonitor:
    """Token预算监控器

    监控当前token使用量，在接近阈值时触发记忆整合。

    阈值配置：
    - warning_threshold: 80% 警告
    - danger_threshold: 95% 危险
    - threshold: 100% 上限

    使用示例：
        monitor = TokenMonitor()
        status = monitor.check(85000)  # WARNING
        should_consolidate = monitor.should_consolidate(85000)  # True
    """

    def __init__(
        self,
        warning_threshold: int = 80000,
        danger_threshold: int = 95000,
        threshold: int = 100000,
    ):
        """初始化Token监控器

        Args:
            warning_threshold: 警告阈值（默认80%）
            danger_threshold: 危险阈值（默认95%）
            threshold: 总预算阈值（默认100000）
        """
        self.warning_threshold = warning_threshold
        self.danger_threshold = danger_threshold
        self.threshold = threshold

    def check(self, token_count: int) -> TokenStatus:
        """检查当前token状态

        Args:
            token_count: 当前token数量

        Returns:
            TokenStatus: 当前状态
        """
        if token_count >= self.threshold:
            return TokenStatus.EXHAUSTED
        elif token_count >= self.danger_threshold:
            return TokenStatus.DANGER
        elif token_count >= self.warning_threshold:
            return TokenStatus.WARNING
        return TokenStatus.NORMAL

    def should_consolidate(self, token_count: int) -> bool:
        """判断是否应该触发记忆整合

        当token超过80%阈值时触发整合。

        Args:
            token_count: 当前token数量

        Returns:
            bool: 是否应该整合
        """
        return token_count > self.threshold * 0.8

    def get_budget(self, token_count: int) -> TokenBudget:
        """获取完整的预算信息

        Args:
            token_count: 当前token数量

        Returns:
            TokenBudget: 完整的预算信息对象
        """
        status = self.check(token_count)
        percentage = (token_count / self.threshold * 100) if self.threshold > 0 else 0
        return TokenBudget(
            current=token_count,
            threshold=self.threshold,
            status=status,
            percentage=round(percentage, 2),
        )

    def get_warning_percentage(self) -> float:
        """获取警告阈值百分比

        Returns:
            float: 警告阈值百分比
        """
        return (self.warning_threshold / self.threshold * 100) if self.threshold > 0 else 0

    def get_danger_percentage(self) -> float:
        """获取危险阈值百分比

        Returns:
            float: 危险阈值百分比
        """
        return (self.danger_threshold / self.threshold * 100) if self.threshold > 0 else 0
