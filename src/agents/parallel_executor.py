"""
V2.6 R2 - 并行Agent执行引擎
============================
职责：
1. 根据 Intent 判断执行模式（并行/串行）
2. 并行触发多个Agent（asyncio.gather）
3. 聚合多Agent结果
4. 计算加权置信度
5. 处理超时和异常
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.agents.base import BaseAgent, AgentResponse
from src.agents.orchestrator import Intent

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """执行模式"""
    PARALLEL = "parallel"
    SERIAL = "serial"


@dataclass
class AgentExecutionResult:
    """单个Agent执行结果"""
    agent_name: str
    success: bool
    content: str = ""
    confidence: float = 1.0
    error: str = ""
    execution_time_ms: int = 0
    is_timed_out: bool = False


@dataclass
class ParallelExecutionResult:
    """并行执行聚合结果"""
    results: list[AgentExecutionResult]
    aggregated_content: str
    final_confidence: float
    execution_mode: ExecutionMode
    total_time_ms: int
    timed_out_agents: list[str] = field(default_factory=list)
    failed_agents: list[str] = field(default_factory=list)


class ParallelExecutor:
    """
    并行Agent执行引擎 - V2.6 R2 新增

    职责：
    1. 根据 Intent 判断执行模式（并行/串行）
    2. 并行触发多个Agent
    3. 聚合多Agent结果
    4. 计算加权置信度
    5. 处理超时和异常
    """

    # 并行执行的 Intent 组合配置
    PARALLEL_CONFIGS: dict[Intent, dict] = {
        Intent.DIAGNOSE: {
            "agents": ["diagnostic", "risk"],
            "timeout_seconds": 30,
            "weights": {"diagnostic": 0.6, "risk": 0.4},
        },
        Intent.SQL_ANALYZE: {
            "agents": ["sql_analyzer", "risk"],
            "timeout_seconds": 30,
            "weights": {"sql_analyzer": 0.6, "risk": 0.4},
        },
        Intent.ANALYZE_SESSION: {
            "agents": ["session_analyzer", "performance"],
            "timeout_seconds": 30,
            "weights": {"session_analyzer": 0.5, "performance": 0.5},
        },
    }

    # 单Agent Intent（串行）
    SERIAL_CONFIGS: dict[Intent, dict] = {
        Intent.INSPECT: {"agents": ["inspector"]},
        Intent.REPORT: {"agents": ["reporter"]},
        Intent.RISK_ASSESS: {"agents": ["risk"]},
        Intent.GENERAL: {"agents": []},  # 无Agent，LLM fallback
    }

    def __init__(self, agent_registry: dict[str, BaseAgent]):
        """
        Args:
            agent_registry: Agent名称到Agent实例的映射字典
        """
        self._agent_registry = agent_registry
        self._default_timeout = 30

    async def execute(
        self,
        goal: str,
        intent: Intent,
        context: dict,
    ) -> ParallelExecutionResult:
        """
        执行Agent任务

        Args:
            goal: 用户目标
            intent: 识别的意图
            context: 上下文字典

        Returns:
            ParallelExecutionResult: 包含所有Agent结果和聚合结果
        """
        start_time = time.time()

        # Step 1: 判断执行模式
        config = self.PARALLEL_CONFIGS.get(intent)
        if config:
            mode = ExecutionMode.PARALLEL
        elif intent in self.SERIAL_CONFIGS:
            mode = ExecutionMode.SERIAL
        else:
            # 未配置的Intent，默认串行
            mode = ExecutionMode.SERIAL

        # Step 2: 根据模式执行
        if mode == ExecutionMode.PARALLEL and config:
            results = await self._execute_parallel(
                goal=goal,
                agents=config["agents"],
                weights=config.get("weights", {}),
                timeout=config.get("timeout_seconds", self._default_timeout),
                context=context,
            )
        else:
            results = await self._execute_serial(
                goal=goal,
                intent=intent,
                context=context,
            )

        # Step 3: 聚合结果
        aggregated, final_confidence = self._aggregate(
            results=results,
            intent=intent,
        )

        total_time_ms = int((time.time() - start_time) * 1000)

        return ParallelExecutionResult(
            results=results,
            aggregated_content=aggregated,
            final_confidence=final_confidence,
            execution_mode=mode,
            total_time_ms=total_time_ms,
            timed_out_agents=[r.agent_name for r in results if r.is_timed_out],
            failed_agents=[r.agent_name for r in results if not r.success and not r.is_timed_out],
        )

    async def _execute_parallel(
        self,
        goal: str,
        agents: list[str],
        weights: dict[str, float],
        timeout: int,
        context: dict,
    ) -> list[AgentExecutionResult]:
        """并行执行多个Agent"""
        tasks = []
        agent_names_for_errors = []

        for agent_name in agents:
            agent = self._agent_registry.get(agent_name)
            if agent:
                tasks.append(
                    self._run_agent_with_timeout(
                        agent=agent,
                        goal=goal,
                        context=context,
                        timeout=timeout,
                    )
                )
            else:
                # Agent 不存在，立即返回一个失败结果（不参与并行）
                tasks.append(
                    asyncio.sleep(
                        0,
                        result=AgentExecutionResult(
                            agent_name=agent_name,
                            success=False,
                            error=f"Agent '{agent_name}' not found in registry",
                        ),
                    )
                )
            agent_names_for_errors.append(agent_name)

        # 并行等待所有任务（return_exceptions=True 确保一个失败不Kill其他）
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, Exception):
                agent_name = agent_names_for_errors[i] if i < len(agent_names_for_errors) else f"agent_{i}"
                results.append(AgentExecutionResult(
                    agent_name=agent_name,
                    success=False,
                    error=str(raw),
                ))
            else:
                results.append(raw)

        return results

    async def _run_agent_with_timeout(
        self,
        agent: BaseAgent,
        goal: str,
        context: dict,
        timeout: int,
    ) -> AgentExecutionResult:
        """运行单个Agent，带超时保护"""
        start_time = time.time()
        agent_name = agent.name

        try:
            response = await asyncio.wait_for(
                agent.process(goal, context),
                timeout=timeout,
            )
            execution_time_ms = int((time.time() - start_time) * 1000)

            return AgentExecutionResult(
                agent_name=agent_name,
                success=response.success,
                content=response.content or "",
                confidence=response.metadata.get("confidence", 1.0) if response.metadata else 1.0,
                error=response.error or "",
                execution_time_ms=execution_time_ms,
                is_timed_out=False,
            )
        except asyncio.TimeoutError:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return AgentExecutionResult(
                agent_name=agent_name,
                success=False,
                error=f"Agent '{agent_name}' timed out after {timeout}s",
                execution_time_ms=execution_time_ms,
                is_timed_out=True,
            )
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return AgentExecutionResult(
                agent_name=agent_name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time_ms,
                is_timed_out=False,
            )

    async def _execute_serial(
        self,
        goal: str,
        intent: Intent,
        context: dict,
    ) -> list[AgentExecutionResult]:
        """串行执行Agent（fallback或单Agent场景）"""
        results = []

        # 获取单Agent配置
        config = self.SERIAL_CONFIGS.get(intent)
        agent_names = config["agents"] if config else []

        for agent_name in agent_names:
            agent = self._agent_registry.get(agent_name)
            if not agent:
                continue

            start_time = time.time()
            try:
                response = await agent.process(goal, context)
                execution_time_ms = int((time.time() - start_time) * 1000)
                results.append(AgentExecutionResult(
                    agent_name=agent.name,
                    success=response.success,
                    content=response.content or "",
                    confidence=response.metadata.get("confidence", 1.0) if response.metadata else 1.0,
                    error=response.error or "",
                    execution_time_ms=execution_time_ms,
                ))
            except Exception as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                results.append(AgentExecutionResult(
                    agent_name=agent_name,
                    success=False,
                    error=str(e),
                    execution_time_ms=execution_time_ms,
                ))

        return results

    def _aggregate(
        self,
        results: list[AgentExecutionResult],
        intent: Intent,
    ) -> tuple[str, float]:
        """
        聚合多Agent结果，计算加权置信度

        策略：
        - 多Agent结果按顺序拼接
        - 置信度 = 加权平均（仅计算成功的Agent）
        - 全部失败时置信度=0，输出错误摘要
        """
        if not results:
            return "", 0.0

        # 获取权重配置
        config = self.PARALLEL_CONFIGS.get(intent)
        weights = config.get("weights", {}) if config else {}

        # 只对成功的Agent计算加权平均
        successful = [r for r in results if r.success and r.content]

        if not successful:
            # 全部失败，聚合内容为错误摘要
            error_summary = "; ".join(
                r.error or f"{r.agent_name} failed"
                for r in results if r.error
            )
            return f"[聚合失败] {error_summary}" if error_summary else "[所有Agent执行失败]", 0.0

        # 加权置信度计算
        total_weight = 0.0
        weighted_confidence = 0.0
        for r in successful:
            w = weights.get(r.agent_name, 1.0 / len(successful))
            weighted_confidence += w * r.confidence
            total_weight += w

        # 归一化
        final_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0
        final_confidence = min(final_confidence, 1.0)  # 不超过1.0

        # 内容聚合：按agent顺序拼接
        content_parts = []
        for r in successful:
            content_parts.append(f"## [{r.agent_name}]\n\n{r.content}")

        aggregated = "\n\n".join(content_parts)
        return aggregated, final_confidence
