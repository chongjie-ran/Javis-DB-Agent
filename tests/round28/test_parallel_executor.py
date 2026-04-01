"""
V2.6 R2 - 并行Agent执行引擎测试
================================
测试范围：F2 并行 Agent 执行引擎

覆盖范围：
1. 并行执行基础 - 多Agent并行触发、结果聚合、超时处理
2. 串行执行兼容 - 非并行Intent走串行、单Agent场景
3. 置信度评分 - 权重计算、多Agent结果加权平均
4. 场景分类 - DIAGNOSE/SQL_ANALYZE/ANALYZE_SESSION 并行组合
5. 异常处理 - 部分失败/全部失败/超时场景

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round28/test_parallel_executor.py -v --tb=short

前置条件：
    - PostgreSQL 真实实例（本地或 docker-compose）
    - 可选：Ollama LLM 服务（部分测试需要）
"""

import asyncio
import sys
import os
import time
import uuid
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import pytest

# ── Path Setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.base import BaseAgent, AgentResponse
from src.agents.orchestrator import OrchestratorAgent, Intent


# ============================================================================
# SECTION 1: ParallelExecutor 核心实现（测试目标）
# ============================================================================
# 说明：以下 ParallelExecutor 是待测模块的接口规范。
# 悟通实现后，以下类定义应替换为从 src.agents.parallel_executor 导入。
# 目前用于定义测试接口和 mock 策略。
# ============================================================================

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
    PARALLEL_CONFIGS = {
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
    SERIAL_CONFIGS = {
        Intent.INSPECT: {"agents": ["inspector"]},
        Intent.REPORT: {"agents": ["reporter"]},
        Intent.RISK_ASSESS: {"agents": ["risk"]},
        Intent.GENERAL: {"agents": []},  # 无Agent，LLM fallback
    }

    def __init__(self, agent_registry: dict[str, BaseAgent]):
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
            # 默认串行
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
                # Agent 不存在，记录失败
                tasks.append(
                    asyncio.sleep(0, result=AgentExecutionResult(
                        agent_name=agent_name,
                        success=False,
                        error=f"Agent '{agent_name}' not found in registry",
                    ))
                )

        # 并行等待所有任务
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, Exception):
                agent_name = agents[i] if i < len(agents) else f"agent_{i}"
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
                confidence=response.metadata.get("confidence", 1.0),
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
                    confidence=response.metadata.get("confidence", 1.0),
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
        - 全部失败时置信度=0
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

        final_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0
        final_confidence = min(final_confidence, 1.0)  # 不超过1.0

        # 内容聚合：按agent顺序拼接
        content_parts = []
        for r in successful:
            content_parts.append(f"## [{r.agent_name}]\n\n{r.content}")

        aggregated = "\n\n".join(content_parts)
        return aggregated, final_confidence


# ============================================================================
# SECTION 2: Mock Agent（用于隔离测试）
# ============================================================================

class MockBaseAgent(BaseAgent):
    """可配置延迟和结果的 Mock Agent"""

    name: str = "mock"
    description: str = "Mock Agent for Testing"

    def __init__(
        self,
        name: str = "mock",
        delay: float = 0.0,
        success: bool = True,
        content: str = "mock response",
        confidence: float = 1.0,
        error: str = "",
    ):
        super().__init__()
        self.name = name
        self.description = f"Mock Agent: {name}"
        self._delay = delay
        self._success = success
        self._content = content
        self._confidence = confidence
        self._error = error

    def _build_system_prompt(self) -> str:
        return f"You are a mock agent: {self.name}"

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return AgentResponse(
            success=self._success,
            content=self._content,
            metadata={"agent": self.name, "confidence": self._confidence},
            error=self._error if not self._success else "",
        )


# ============================================================================
# SECTION 3: Fixtures
# ============================================================================

@pytest.fixture
def mock_agent_registry():
    """标准 mock Agent 注册表"""
    return {
        "diagnostic": MockBaseAgent(
            name="diagnostic",
            delay=0.1,
            content="Diagnostic result: root cause identified",
            confidence=0.85,
        ),
        "risk": MockBaseAgent(
            name="risk",
            delay=0.1,
            content="Risk assessment: L3 medium risk",
            confidence=0.90,
        ),
        "sql_analyzer": MockBaseAgent(
            name="sql_analyzer",
            delay=0.1,
            content="SQL analysis: slow query detected, index建议",
            confidence=0.80,
        ),
        "session_analyzer": MockBaseAgent(
            name="session_analyzer",
            delay=0.1,
            content="Session analysis: 5 active sessions found",
            confidence=0.88,
        ),
        "performance": MockBaseAgent(
            name="performance",
            delay=0.1,
            content="Performance analysis: CPU usage 85%",
            confidence=0.82,
        ),
        "inspector": MockBaseAgent(
            name="inspector",
            delay=0.1,
            content="Inspection result: all systems nominal",
            confidence=0.95,
        ),
        "reporter": MockBaseAgent(
            name="reporter",
            delay=0.1,
            content="Report generated successfully",
            confidence=0.95,
        ),
    }


@pytest.fixture
def executor(mock_agent_registry):
    """ParallelExecutor 实例"""
    return ParallelExecutor(agent_registry=mock_agent_registry)


@pytest.fixture
def default_context():
    """标准测试上下文"""
    return {
        "user_id": "test-user",
        "session_id": f"session-{uuid.uuid4().hex[:8]}",
        "instance_id": "INS-TEST-001",
        "alert_id": "ALT-TEST-001",
    }


# ============================================================================
# SECTION 4: 并行执行基础测试 (PE-*)
# ============================================================================

class TestParallelExecutionBasics:
    """并行执行基础测试"""

    @pytest.mark.asyncio
    async def test_pe01_parallel_diagnose_triggers_both_agents(self, executor, default_context):
        """PE-01: DIAGNOSE Intent 并行触发 diagnostic + risk"""
        result = await executor.execute(
            goal="分析告警 ALT-001 的根因",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.PARALLEL
        assert len(result.results) == 2

        agent_names = {r.agent_name for r in result.results}
        assert agent_names == {"diagnostic", "risk"}

    @pytest.mark.asyncio
    async def test_pe02_parallel_sql_analyze_triggers_both_agents(self, executor, default_context):
        """PE-02: SQL_ANALYZE Intent 并行触发 sql_analyzer + risk"""
        result = await executor.execute(
            goal="分析这条SQL的性能",
            intent=Intent.SQL_ANALYZE,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.PARALLEL
        agent_names = {r.agent_name for r in result.results}
        assert agent_names == {"sql_analyzer", "risk"}

    @pytest.mark.asyncio
    async def test_pe03_parallel_analyze_session_triggers_both_agents(self, executor, default_context):
        """PE-03: ANALYZE_SESSION Intent 并行触发 session_analyzer + performance"""
        result = await executor.execute(
            goal="分析当前会话状态",
            intent=Intent.ANALYZE_SESSION,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.PARALLEL
        agent_names = {r.agent_name for r in result.results}
        assert agent_names == {"session_analyzer", "performance"}

    @pytest.mark.asyncio
    async def test_pe04_parallel_results_all_successful(self, executor, default_context):
        """PE-04: 并行执行全部成功"""
        result = await executor.execute(
            goal="分析告警 ALT-001",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        successful = [r for r in result.results if r.success]
        assert len(successful) == 2
        assert all(r.content for r in successful)

    @pytest.mark.asyncio
    async def test_pe05_parallel_execution_time_less_than_serial(self, executor, default_context):
        """PE-05: 并行执行时间应小于等于最长子任务时间（而非累加）"""
        slow_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.3,
                content="diagnostic done",
                confidence=0.85,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.3,
                content="risk done",
                confidence=0.90,
            ),
        }
        slow_executor = ParallelExecutor(agent_registry=slow_registry)

        result = await slow_executor.execute(
            goal="测试并行",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )
        elapsed = result.total_time_ms / 1000.0

        # 并行应该 ~300ms（最长），而不是 ~600ms（累加）
        assert elapsed < 0.55, f"并行执行耗时 {elapsed:.2f}s，未体现并行效果（期望<0.55s）"

    @pytest.mark.asyncio
    async def test_pe06_result_aggregation_contains_all_content(self, executor, default_context):
        """PE-06: 聚合结果包含所有Agent内容"""
        result = await executor.execute(
            goal="分析告警",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert "diagnostic" in result.aggregated_content
        assert "risk" in result.aggregated_content

    @pytest.mark.asyncio
    async def test_pe07_confidence_is_weighted_average(self, executor, default_context):
        """PE-07: 置信度为加权平均（diagnostic=0.6, risk=0.4; conf: 0.85, 0.90）"""
        result = await executor.execute(
            goal="分析告警",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # expected = 0.6*0.85 + 0.4*0.90 = 0.51 + 0.36 = 0.87
        expected = 0.6 * 0.85 + 0.4 * 0.90
        assert abs(result.final_confidence - expected) < 0.01

    @pytest.mark.asyncio
    async def test_pe08_sql_analyze_confidence_calculation(self, executor, default_context):
        """PE-08: SQL_ANALYZE 置信度计算正确（sql_analyzer=0.6, risk=0.4; conf: 0.80, 0.90）"""
        result = await executor.execute(
            goal="分析SQL性能",
            intent=Intent.SQL_ANALYZE,
            context=default_context,
        )

        expected = 0.6 * 0.80 + 0.4 * 0.90
        assert abs(result.final_confidence - expected) < 0.01

    @pytest.mark.asyncio
    async def test_pe09_analyze_session_confidence_calculation(self, executor, default_context):
        """PE-09: ANALYZE_SESSION 置信度计算正确（等权重 0.5+0.5; conf: 0.88, 0.82）"""
        result = await executor.execute(
            goal="分析会话",
            intent=Intent.ANALYZE_SESSION,
            context=default_context,
        )

        expected = 0.5 * 0.88 + 0.5 * 0.82
        assert abs(result.final_confidence - expected) < 0.01


# ============================================================================
# SECTION 5: 串行执行兼容测试 (SE-*)
# ============================================================================

class TestSerialExecutionCompatibility:
    """串行执行兼容测试"""

    @pytest.mark.asyncio
    async def test_se01_inspect_intent_runs_single_agent(self, executor, default_context):
        """SE-01: INSPECT Intent 串行执行 inspector"""
        result = await executor.execute(
            goal="查看实例列表",
            intent=Intent.INSPECT,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.SERIAL
        assert len(result.results) == 1
        assert result.results[0].agent_name == "inspector"

    @pytest.mark.asyncio
    async def test_se02_report_intent_runs_single_agent(self, executor, default_context):
        """SE-02: REPORT Intent 串行执行 reporter"""
        result = await executor.execute(
            goal="生成巡检报告",
            intent=Intent.REPORT,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.SERIAL
        assert len(result.results) == 1
        assert result.results[0].agent_name == "reporter"

    @pytest.mark.asyncio
    async def test_se03_risk_assess_intent_single_agent(self, executor, default_context):
        """SE-03: RISK_ASSESS Intent 串行执行 risk"""
        result = await executor.execute(
            goal="评估风险",
            intent=Intent.RISK_ASSESS,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.SERIAL
        assert len(result.results) == 1
        assert result.results[0].agent_name == "risk"

    @pytest.mark.asyncio
    async def test_se04_general_intent_no_agent(self, executor, default_context):
        """SE-04: GENERAL Intent 不调用Agent（返回空结果）"""
        result = await executor.execute(
            goal="你好",
            intent=Intent.GENERAL,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.SERIAL
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_se05_serial_timing_additive(self, executor, default_context):
        """SE-05: 串行执行时间约等于任务时间"""
        start = time.time()
        result = await executor.execute(
            goal="生成报告",
            intent=Intent.REPORT,
            context=default_context,
        )
        elapsed = result.total_time_ms / 1000.0

        # 单Agent约0.1s
        assert elapsed < 0.2, f"串行执行耗时 {elapsed:.2f}s，异常"


# ============================================================================
# SECTION 6: 置信度评分测试 (CF-*)
# ============================================================================

class TestConfidenceScoring:
    """置信度评分测试"""

    @pytest.mark.asyncio
    async def test_cf01_all_agents_succeed_weighted_average(self, executor, default_context):
        """CF-01: 全部成功时，置信度为加权平均"""
        result = await executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert result.final_confidence > 0
        assert result.final_confidence <= 1.0

    @pytest.mark.asyncio
    async def test_cf02_partial_failure_recalculates(self, default_context):
        """CF-02: 部分Agent失败时，置信度仅基于成功的Agent重新计算"""
        partial_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=False,
                content="",
                error="diagnostic failed",
                confidence=0.85,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=True,
                content="risk result",
                confidence=0.90,
            ),
        }
        partial_executor = ParallelExecutor(agent_registry=partial_registry)

        result = await partial_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # 只有risk成功，归一化后权重1.0，置信度=0.90
        assert result.final_confidence == 0.90

    @pytest.mark.asyncio
    async def test_cf03_all_fail_zero_confidence(self, default_context):
        """CF-03: 全部失败时置信度为0"""
        fail_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=False,
                content="",
                error="failed",
                confidence=0.85,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=False,
                content="",
                error="failed",
                confidence=0.90,
            ),
        }
        fail_executor = ParallelExecutor(agent_registry=fail_registry)

        result = await fail_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert result.final_confidence == 0.0
        assert "[聚合失败]" in result.aggregated_content

    @pytest.mark.asyncio
    async def test_cf04_confidence_never_exceeds_one(self, default_context):
        """CF-04: 置信度不超过1.0（输入异常值）"""
        high_conf_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=True,
                content="ok",
                confidence=1.5,  # 异常值
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=True,
                content="ok",
                confidence=1.5,  # 异常值
            ),
        }
        high_executor = ParallelExecutor(agent_registry=high_conf_registry)

        result = await high_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert result.final_confidence <= 1.0


# ============================================================================
# SECTION 7: 场景分类测试 (SC-*)
# ============================================================================

class TestScenarioClassification:
    """场景分类测试"""

    @pytest.mark.asyncio
    async def test_sc01_diagnose_parallel_agents_correct(self, executor, default_context):
        """SC-01: DIAGNOSE 场景：diagnostic + risk 并行"""
        result = await executor.execute(
            goal="帮我看看这个告警",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        agent_names = sorted([r.agent_name for r in result.results])
        assert agent_names == ["diagnostic", "risk"]
        assert result.execution_mode == ExecutionMode.PARALLEL

    @pytest.mark.asyncio
    async def test_sc02_sql_analyze_parallel_agents_correct(self, executor, default_context):
        """SC-02: SQL_ANALYZE 场景：sql_analyzer + risk 并行"""
        result = await executor.execute(
            goal="分析这条SQL",
            intent=Intent.SQL_ANALYZE,
            context=default_context,
        )

        agent_names = sorted([r.agent_name for r in result.results])
        assert agent_names == ["risk", "sql_analyzer"]
        assert result.execution_mode == ExecutionMode.PARALLEL

    @pytest.mark.asyncio
    async def test_sc03_analyze_session_parallel_agents_correct(self, executor, default_context):
        """SC-03: ANALYZE_SESSION 场景：session_analyzer + performance 并行"""
        result = await executor.execute(
            goal="会话分析",
            intent=Intent.ANALYZE_SESSION,
            context=default_context,
        )

        agent_names = sorted([r.agent_name for r in result.results])
        assert agent_names == ["performance", "session_analyzer"]
        assert result.execution_mode == ExecutionMode.PARALLEL

    @pytest.mark.asyncio
    async def test_sc04_diagnose_weights_configured(self, executor):
        """SC-04: DIAGNOSE 权重配置存在且有效"""
        config = ParallelExecutor.PARALLEL_CONFIGS[Intent.DIAGNOSE]
        weights = config.get("weights", {})

        assert "diagnostic" in weights
        assert "risk" in weights
        assert weights["diagnostic"] > 0
        assert weights["risk"] > 0

    @pytest.mark.asyncio
    async def test_sc05_unknown_intent_falls_back_to_serial(self, executor, default_context):
        """SC-05: GENERAL Intent 降级为串行模式（无Agent配置）"""
        result = await executor.execute(
            goal="未知任务",
            intent=Intent.GENERAL,
            context=default_context,
        )

        assert result.execution_mode == ExecutionMode.SERIAL
        assert len(result.results) == 0


# ============================================================================
# SECTION 8: 异常处理测试 (EX-*)
# ============================================================================

class TestExceptionHandling:
    """异常处理测试"""

    @pytest.mark.asyncio
    async def test_ex01_partial_agent_failure_one_survives(self, default_context):
        """EX-01: 部分Agent失败时，存活的Agent结果仍被使用"""
        partial_fail_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=False,
                content="",
                error="诊断失败",
                confidence=0.85,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=True,
                content="Risk assessment: L3 risk",
                confidence=0.90,
            ),
        }
        pe = ParallelExecutor(agent_registry=partial_fail_registry)

        result = await pe.execute(
            goal="分析告警",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # risk 成功
        assert any(r.success and r.agent_name == "risk" for r in result.results)
        # diagnostic 失败
        assert any(not r.success and r.agent_name == "diagnostic" for r in result.results)
        # 聚合结果包含 risk 内容
        assert "Risk assessment" in result.aggregated_content or "risk" in result.aggregated_content.lower()
        assert result.final_confidence > 0

    @pytest.mark.asyncio
    async def test_ex02_all_agents_fail_graceful_error(self, default_context):
        """EX-02: 全部Agent失败时，返回错误摘要而非崩溃"""
        all_fail_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=False,
                content="",
                error="诊断服务不可用",
                confidence=0.0,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=False,
                content="",
                error="风险评估服务超时",
                confidence=0.0,
            ),
        }
        pe = ParallelExecutor(agent_registry=all_fail_registry)

        result = await pe.execute(
            goal="分析告警",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        assert result.final_confidence == 0.0
        assert len(result.results) == 2
        assert all(not r.success for r in result.results)
        assert ("聚合失败" in result.aggregated_content or
                "诊断服务不可用" in result.aggregated_content)

    @pytest.mark.asyncio
    async def test_ex03_timeout_handling_agent_marked(self, default_context):
        """EX-03: 超时场景下，Agent被正确标记为超时"""
        slow_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=5.0,  # 5秒，超过配置的timeout
                success=True,
                content="done",
                confidence=0.85,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.1,
                success=True,
                content="risk done",
                confidence=0.90,
            ),
        }
        slow_executor = ParallelExecutor(agent_registry=slow_registry)
        slow_executor.PARALLEL_CONFIGS[Intent.DIAGNOSE]["timeout_seconds"] = 1

        result = await slow_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # diagnostic 应该超时
        assert any(r.agent_name == "diagnostic" and r.is_timed_out for r in result.results)

    @pytest.mark.asyncio
    async def test_ex04_timeout_does_not_kill_other_agents(self, default_context):
        """EX-04: 一个Agent超时不影响其他Agent完成"""
        slow_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=5.0,
                success=False,
                error="timeout",
                confidence=0.0,
            ),
            "risk": MockBaseAgent(
                name="risk",
                delay=0.2,
                success=True,
                content="risk completed",
                confidence=0.90,
            ),
        }
        slow_executor = ParallelExecutor(agent_registry=slow_registry)
        slow_executor.PARALLEL_CONFIGS[Intent.DIAGNOSE]["timeout_seconds"] = 1

        result = await slow_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # risk 应该成功完成
        assert any(r.success and r.agent_name == "risk" for r in result.results)
        # diagnostic 超时
        timed_out = [r for r in result.results if r.is_timed_out]
        assert len(timed_out) >= 1

    @pytest.mark.asyncio
    async def test_ex05_empty_agent_registry_no_crash(self, default_context):
        """EX-05: 空Agent注册表不崩溃"""
        empty_executor = ParallelExecutor(agent_registry={})

        result = await empty_executor.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # 不崩溃，全部失败
        assert result.final_confidence == 0.0
        assert len(result.results) == 2  # 两个agent配置，但都不存在

    @pytest.mark.asyncio
    async def test_ex06_missing_agent_in_registry_handled(self, default_context):
        """EX-06: 注册表中缺失的Agent被正确处理为失败"""
        partial_registry = {
            "diagnostic": MockBaseAgent(
                name="diagnostic",
                delay=0.1,
                success=True,
                content="diagnostic ok",
                confidence=0.85,
            ),
            # risk 缺失
        }
        pe = ParallelExecutor(agent_registry=partial_registry)

        result = await pe.execute(
            goal="分析",
            intent=Intent.DIAGNOSE,
            context=default_context,
        )

        # diagnostic 成功，risk 失败（not found）
        assert any(r.success and r.agent_name == "diagnostic" for r in result.results)
        assert any(r.agent_name == "risk" and not r.success for r in result.results)
        assert "not found" in next(
            r.error for r in result.results if r.agent_name == "risk"
        ).lower()


# ============================================================================
# SECTION 9: 集成测试占位 (IT-*)
# ============================================================================
# 这些测试需要悟通实现后，连接真实PostgreSQL环境运行。
# 目前跳过，待 ParallelExecutor 实现后启用。
# ============================================================================

class TestPostgresIntegration:
    """
    集成测试：真实PostgreSQL环境
    占位 - 悟通实现 ParallelExecutor 后完成
    """

    @pytest.mark.skip(reason="IT-01: 等待悟通实现 ParallelExecutor 后启用")
    @pytest.mark.asyncio
    async def test_it01_real_postgres_parallel_diagnose(self, default_context):
        """IT-01: 真实PG环境下 DIAGNOSE 并行执行"""
        pass

    @pytest.mark.skip(reason="IT-02: 等待悟通实现 ParallelExecutor 后启用")
    @pytest.mark.asyncio
    async def test_it02_real_postgres_sql_analyze(self, default_context):
        """IT-02: 真实PG环境下 SQL_ANALYZE 并行执行"""
        pass

    @pytest.mark.skip(reason="IT-03: 等待悟通实现 ParallelExecutor 后启用")
    @pytest.mark.asyncio
    async def test_it03_real_postgres_session_analyze(self, default_context):
        """IT-03: 真实PG环境下 ANALYZE_SESSION 并行执行"""
        pass
