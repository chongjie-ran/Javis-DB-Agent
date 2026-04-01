"""
并行 Agent 执行器 - 核心模块
根据 Intent 类型决定并行/串行策略，并发执行多个 Agent
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from src.agents.base import BaseAgent, AgentResponse
from .result_aggregator import ResultAggregator, AggregatedResult
from .strategy import ExecutionStrategy, ParallelStrategy, SequentialStrategy, SEQUENTIAL_INTENTS
from .confidence import ConfidenceCalculator

if TYPE_CHECKING:
    from src.agents.orchestrator import Intent

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果包装器"""
    intent: Intent
    agent_responses: list[AgentResponse]
    aggregated: AggregatedResult
    execution_mode: str  # "parallel" or "sequential"
    total_time_ms: int
    partial_failures: list[str] = field(default_factory=list)


class ParallelAgentExecutor:
    """
    并行 Agent 执行器
    
    核心功能：
    1. 根据 Intent 类型决定并行/串行策略
    2. asyncio.gather 并发执行多个 Agent
    3. 置信度评分 + 加权聚合结果
    4. 超时控制 + 部分失败处理
    
    使用方式：
    ```python
    executor = ParallelAgentExecutor(orchestrator)
    result = await executor.execute(
        goal="分析这个告警",
        intent=Intent.DIAGNOSE,
        agents=[diagnostic_agent, risk_agent],
        context={}
    )
    ```
    """

    def __init__(self, orchestrator=None):
        """
        初始化执行器
        
        Args:
            orchestrator: OrchestratorAgent 实例（用于获取Agent）
        """
        self._orchestrator = orchestrator
        self._aggregator = ResultAggregator()
        self._confidence_calc = ConfidenceCalculator()
        self._parallel_strategy = ParallelStrategy()
        self._sequential_strategy = SequentialStrategy()

    def _get_strategy(self, intent: "Intent", agent_names: list[str]) -> ExecutionStrategy:
        """根据 Intent 获取执行策略"""
        intent_value = intent.value if hasattr(intent, 'value') else str(intent)
        should_parallel = self._parallel_strategy.should_parallel(intent_value, agent_names)
        if intent_value in SEQUENTIAL_INTENTS:
            return self._sequential_strategy
        elif should_parallel:
            return self._parallel_strategy
        else:
            return self._sequential_strategy

    async def execute(
        self,
        goal: str,
        intent: Intent,
        agents: list[BaseAgent],
        context: dict,
        timeout_ms: int = 60000
    ) -> ExecutionResult:
        """
        执行多Agent任务
        
        Args:
            goal: 用户目标
            intent: 识别的意图
            agents: Agent 列表
            context: 执行上下文
            timeout_ms: 整体超时时间（毫秒）
            
        Returns:
            ExecutionResult 执行结果
        """
        start_time = time.time()
        
        agent_names = [a.name for a in agents]
        strategy = self._get_strategy(intent, agent_names)
        
        # 决定执行模式
        intent_value = intent.value if hasattr(intent, 'value') else str(intent)
        execution_mode = "parallel" if strategy.should_parallel(intent_value, agent_names) else "sequential"
        
        logger.info(f"[ParallelExecutor] Intent={intent.value}, Mode={execution_mode}, Agents={agent_names}")
        
        if execution_mode == "parallel":
            responses = await self._execute_parallel(agents, goal, context, strategy)
        else:
            responses = await self._execute_sequential(agents, goal, context, strategy)
        
        total_time_ms = int((time.time() - start_time) * 1000)
        
        # 聚合结果
        aggregated = self._aggregator.aggregate(responses, intent.value)
        
        # 收集部分失败
        partial_failures = [
            r.metadata.get("agent", "unknown") + ": " + (r.error or "unknown")
            for r in responses
            if not r.success
        ]
        
        return ExecutionResult(
            intent=intent,
            agent_responses=responses,
            aggregated=aggregated,
            execution_mode=execution_mode,
            total_time_ms=total_time_ms,
            partial_failures=partial_failures,
        )

    async def _execute_parallel(
        self,
        agents: list[BaseAgent],
        goal: str,
        context: dict,
        strategy: ExecutionStrategy
    ) -> list[AgentResponse]:
        """
        并行执行多个 Agent
        
        Args:
            agents: Agent 列表
            goal: 用户目标
            context: 执行上下文
            strategy: 执行策略
            
        Returns:
            AgentResponse 列表
        """
        tasks = []
        for agent in agents:
            timeout = strategy.get_timeout(agent.name)
            task = self._execute_with_timeout(agent, goal, context, timeout)
            tasks.append(task)
        
        # 使用 asyncio.gather 并发执行，允许部分失败
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_name = agents[i].name if i < len(agents) else "unknown"
                logger.error(f"[ParallelExecutor] Agent {agent_name} failed: {result}")
                responses.append(AgentResponse(
                    success=False,
                    error=str(result),
                    metadata={"agent": agent_name}
                ))
            else:
                responses.append(result)
        
        return responses

    async def _execute_sequential(
        self,
        agents: list[BaseAgent],
        goal: str,
        context: dict,
        strategy: ExecutionStrategy
    ) -> list[AgentResponse]:
        """
        串行执行多个 Agent（兼容模式）
        
        Args:
            agents: Agent 列表
            goal: 用户目标
            context: 执行上下文
            strategy: 执行策略
            
        Returns:
            AgentResponse 列表
        """
        responses = []
        for agent in agents:
            timeout = strategy.get_timeout(agent.name)
            response = await self._execute_with_timeout(agent, goal, context, timeout)
            responses.append(response)
            
            # 如果某个Agent失败，可以选择继续或停止
            # 这里选择继续执行其他Agent
            if not response.success:
                logger.warning(f"[ParallelExecutor] Agent {agent.name} failed, continuing...")
        
        return responses

    async def _execute_with_timeout(
        self,
        agent: BaseAgent,
        goal: str,
        context: dict,
        timeout_ms: int
    ) -> AgentResponse:
        """
        带超时的 Agent 执行
        
        Args:
            agent: Agent 实例
            goal: 用户目标
            context: 执行上下文
            timeout_ms: 超时时间（毫秒）
            
        Returns:
            AgentResponse
        """
        try:
            response = await asyncio.wait_for(
                agent.process(goal, context),
                timeout=timeout_ms / 1000.0  # 转换为秒
            )
            # 确保 metadata 包含 agent 名称
            if "agent" not in response.metadata:
                response.metadata["agent"] = agent.name
            return response
        except asyncio.TimeoutError:
            logger.warning(f"[ParallelExecutor] Agent {agent.name} timed out after {timeout_ms}ms")
            return AgentResponse(
                success=False,
                error=f"执行超时（{timeout_ms}ms）",
                metadata={"agent": agent.name, "timeout": True}
            )
        except Exception as e:
            logger.error(f"[ParallelExecutor] Agent {agent.name} exception: {e}")
            return AgentResponse(
                success=False,
                error=f"执行异常: {str(e)}",
                metadata={"agent": agent.name, "exception": True}
            )

    async def execute_single(
        self,
        agent: BaseAgent,
        goal: str,
        context: dict
    ) -> AgentResponse:
        """
        执行单个 Agent（便捷方法）
        
        Args:
            agent: Agent 实例
            goal: 用户目标
            context: 执行上下文
            
        Returns:
            AgentResponse
        """
        try:
            response = await agent.process(goal, context)
            response.metadata["agent"] = agent.name
            return response
        except Exception as e:
            logger.error(f"[ParallelExecutor] Single execution failed: {e}")
            return AgentResponse(
                success=False,
                error=str(e),
                metadata={"agent": agent.name}
            )

    def set_orchestrator(self, orchestrator):
        """设置编排器引用"""
        self._orchestrator = orchestrator

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """从编排器获取 Agent"""
        if self._orchestrator:
            return self._orchestrator.get_agent(name)
        return None
