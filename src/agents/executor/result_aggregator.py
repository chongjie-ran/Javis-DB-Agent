"""
结果聚合器模块
负责多Agent结果的加权聚合、置信度归一化、冲突检测
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
from src.agents.base import AgentResponse
from .confidence import ConfidenceCalculator, AgentConfidence

logger = logging.getLogger(__name__)


@dataclass
class AggregatedResult:
    """聚合后的结果"""
    content: str                           # 聚合后的内容
    confidence: float                      # 整体置信度
    agent_results: list[AgentResponse]     # 各Agent的原始结果
    agent_confidences: list[AgentConfidence]  # 各Agent的置信度
    conflicts: list[str] = field(default_factory=list)  # 检测到的冲突
    partial_failures: list[str] = field(default_factory=list)  # 部分失败信息
    metadata: dict = field(default_factory=dict)


@dataclass
class ConflictInfo:
    """冲突信息"""
    agent_a: str
    agent_b: str
    description: str
    severity: str  # "high", "medium", "low"


class ResultAggregator:
    """
    结果聚合器
    
    功能：
    1. 多Agent结果加权平均聚合
    2. 置信度归一化
    3. 冲突检测与处理
    4. 部分失败处理
    """

    def __init__(self):
        self._confidence_calc = ConfidenceCalculator()

    def aggregate(
        self,
        results: list[AgentResponse],
        intent_name: str = ""
    ) -> AggregatedResult:
        """
        聚合多Agent结果
        
        Args:
            results: Agent响应列表
            intent_name: 意图名称（用于日志）
            
        Returns:
            AggregatedResult 聚合后的结果
        """
        if not results:
            return AggregatedResult(
                content="",
                confidence=0.0,
                agent_results=[],
                agent_confidences=[],
            )

        # 过滤成功结果
        successful = [r for r in results if r.success and r.content]
        failed = [r for r in results if not r.success or not r.content]

        if not successful:
            # 全部失败
            return AggregatedResult(
                content=self._format_all_failed(failed),
                confidence=0.0,
                agent_results=results,
                agent_confidences=[],
                partial_failures=[self._get_error_summary(r) for r in failed],
            )

        # 计算各Agent置信度
        confidences = []
        for r in results:
            conf = self._confidence_calc.compute_weighted_confidence(
                agent_name=r.metadata.get("agent", "unknown"),
                success=r.success,
                has_content=bool(r.content),
                execution_time_ms=r.execution_time_ms,
                error=r.error,
                tool_calls_count=len(r.tool_calls),
            )
            confidences.append(conf)

        # 置信度归一化
        normalized = self._confidence_calc.normalize_scores(
            [(c.agent_name, c.final_score) for c in confidences]
        )
        # 更新置信度对象
        for conf in confidences:
            for name, norm_score in normalized:
                if conf.agent_name == name:
                    conf.final_score = norm_score
                    break

        # 冲突检测
        conflicts = self._detect_conflicts(successful)

        # 聚合内容
        content = self._merge_content(successful, confidences, conflicts)

        # 计算整体置信度
        overall_confidence = sum(c.final_score for c in confidences if c.agent_name in [r.metadata.get("agent", "") for r in successful])
        overall_confidence = overall_confidence / len(successful) if successful else 0.0

        # 部分失败信息
        partial_failures = []
        for r in failed:
            error_summary = self._get_error_summary(r)
            if error_summary:
                partial_failures.append(error_summary)

        return AggregatedResult(
            content=content,
            confidence=overall_confidence,
            agent_results=results,
            agent_confidences=confidences,
            conflicts=[c.description for c in conflicts],
            partial_failures=partial_failures,
            metadata={
                "intent": intent_name,
                "total_agents": len(results),
                "successful_agents": len(successful),
                "failed_agents": len(failed),
            }
        )

    def _format_all_failed(self, failed: list[AgentResponse]) -> str:
        """格式化全部失败的情况"""
        parts = ["⚠️ 所有Agent执行失败："]
        for r in failed:
            agent_name = r.metadata.get("agent", "unknown")
            error = r.error or "未知错误"
            parts.append(f"- {agent_name}: {error}")
        return "\n".join(parts)

    def _get_error_summary(self, r: AgentResponse) -> str:
        """获取错误摘要"""
        agent_name = r.metadata.get("agent", "unknown")
        error = r.error or "未知错误"
        return f"{agent_name}: {error[:100]}"

    def _detect_conflicts(self, results: list[AgentResponse]) -> list[ConflictInfo]:
        """
        检测结果冲突
        
        通过简单的关键词冲突检测：
        - 健康状态：healthy vs unhealthy
        - 风险等级：high vs low
        - 结论矛盾
        
        Args:
            results: 成功的Agent结果列表
            
        Returns:
            冲突信息列表
        """
        conflicts = []

        if len(results) < 2:
            return conflicts

        # 收集各Agent的关键结论
        conclusions = {}
        for r in results:
            agent = r.metadata.get("agent", "unknown")
            content_lower = r.content.lower()
            conclusions[agent] = content_lower

        # 检测风险等级冲突
        risk_high_agents = []
        risk_low_agents = []
        for agent, content in conclusions.items():
            if any(kw in content for kw in ["风险高", "高风险", "risk high", "严重", "critical"]):
                risk_high_agents.append(agent)
            if any(kw in content for kw in ["风险低", "低风险", "risk low", "正常", "healthy"]):
                risk_low_agents.append(agent)

        if risk_high_agents and risk_low_agents:
            conflicts.append(ConflictInfo(
                agent_a=", ".join(risk_high_agents),
                agent_b=", ".join(risk_low_agents),
                description=f"风险评估冲突：{', '.join(risk_high_agents)} 认为高风险，{', '.join(risk_low_agents)} 认为低风险",
                severity="high"
            ))

        # 检测健康状态冲突
        healthy_agents = []
        unhealthy_agents = []
        for agent, content in conclusions.items():
            if any(kw in content for kw in ["健康", "healthy", "正常"]):
                healthy_agents.append(agent)
            if any(kw in content for kw in ["异常", "unhealthy", "故障", "error", "问题"]):
                unhealthy_agents.append(agent)

        if healthy_agents and unhealthy_agents:
            conflicts.append(ConflictInfo(
                agent_a=", ".join(healthy_agents),
                agent_b=", ".join(unhealthy_agents),
                description=f"健康状态冲突：{', '.join(healthy_agents)} 认为正常，{', '.join(unhealthy_agents)} 认为异常",
                severity="high"
            ))

        return conflicts

    def _merge_content(
        self,
        results: list[AgentResponse],
        confidences: list[AgentConfidence],
        conflicts: list[ConflictInfo]
    ) -> str:
        """
        合并多Agent内容
        
        按置信度排序，高置信度结果优先展示
        
        Args:
            results: 成功的结果列表
            confidences: 置信度列表
            conflicts: 冲突信息列表
            
        Returns:
            合并后的内容
        """
        # 按置信度排序
        sorted_results = sorted(
            zip(results, confidences),
            key=lambda x: x[1].final_score,
            reverse=True
        )

        parts = []

        # 添加冲突警告（如果存在）
        if conflicts:
            conflict_warnings = []
            for c in conflicts:
                if c.severity == "high":
                    conflict_warnings.append(f"⚠️ 冲突: {c.description}")
            if conflict_warnings:
                parts.append("\n".join(conflict_warnings))
                parts.append("---")

        # 按置信度顺序添加结果
        for r, conf in sorted_results:
            agent_name = r.metadata.get("agent", "unknown")
            confidence_pct = int(conf.final_score * 100)

            # 添加Agent结果头
            header = f"## [{agent_name}] (置信度: {confidence_pct}%)"
            parts.append(header)
            parts.append(r.content)
            parts.append("")  # 空行分隔

        return "\n".join(parts)

    def aggregate_simple(self, results: list[AgentResponse]) -> dict:
        """
        简单聚合 - 兼容旧接口
        
        Args:
            results: Agent响应列表
            
        Returns:
            {"content": str, "parts": list[str]}
        """
        if not results:
            return {"content": None}

        successful = [r for r in results if r.success and r.content]
        if not successful:
            return {"content": None}

        if len(successful) == 1:
            return {"content": successful[0].content}

        aggregated_parts = []
        for r in successful:
            agent_name = r.metadata.get("agent", "Agent")
            aggregated_parts.append(f"## {agent_name} 结果\n\n{r.content}")

        return {
            "content": "\n\n".join(aggregated_parts),
            "parts": aggregated_parts,
        }
