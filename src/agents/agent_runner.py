"""AgentRunner - 基于Hook的Agent执行引擎 (V3.0 Phase 1)

Phase 1 核心组件：将现有的AgentLoop改为基于AgentRunner+Hook的执行引擎。

设计原则：
1. Hook驱动：所有生命周期节点通过Hook扩展
2. 错误隔离：单个Hook失败不影响其他Hook和主循环
3. 上下文贯穿：AgentHookContext贯穿整个执行链
4. 向后兼容：保留现有Agent的业务逻辑

Hook点调用顺序：
    on_start
      ↓
    [迭代循环] ───────────────────────────────┐
      ├── before_iteration                      │
      │     ↓                                   │
      ├── before_execute_tools ──→ execute_tools → after_execute_tools
      │     ↓                                   │
      ├── before_llm ──→ llm_loop → on_stream → after_llm
      │     ↓                                   │
      └── after_iteration ─────────────────────┘
      ↓
    on_complete
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext
from src.hooks.hook_events import AgentHookEvent
from src.hooks.composite_hook import CompositeHook
from src.tools.base import BaseTool, ToolResult

from .agent_run_spec import AgentRunSpec
from .run_result import RunResult

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    基于Hook的Agent执行引擎

    核心职责：
    1. 管理Agent执行生命周期
    2. 调用Hook扩展点
    3. 协调LLM和工具执行
    4. 收集执行结果

    使用示例：
        runner = AgentRunner(
            llm_client=ollama_client,
            tools=[tool1, tool2],
            hooks=[TokenMonitorHook(), InstructionSelfContainValidator()]
        )
        spec = AgentRunSpec(goal="帮我分析告警123", context={"session_id": "s1"})
        result = await runner.run(spec)
    """

    def __init__(
        self,
        llm_client: Any,
        tools: list[BaseTool],
        hooks: list[AgentHook] | None = None,
        max_iterations: int = 10,
        timeout: int = 3600,
    ):
        """
        初始化AgentRunner

        Args:
            llm_client: LLM客户端（需支持complete和complete_stream方法）
            tools: 可用工具列表
            hooks: Hook列表（默认空列表）
            max_iterations: 最大迭代次数（默认10）
            timeout: 超时秒数（默认3600）
        """
        self.llm_client = llm_client
        self.tools = tools
        self.hooks = CompositeHook(hooks or [])
        self.max_iterations = max_iterations
        self.timeout = timeout

        # 构建工具名→工具的映射
        self._tool_map: dict[str, BaseTool] = {t.name: t for t in tools if hasattr(t, "name")}

        # 统计信息
        self._tokens_used = 0

    # ─────────────────────────────────────────────────────────────────
    # 公开API
    # ─────────────────────────────────────────────────────────────────

    async def run(self, spec: AgentRunSpec) -> RunResult:
        """
        执行Agent（基于Hook的执行循环）

        核心流程：
        1. 初始化上下文
        2. 调用 on_start Hook
        3. 迭代执行直到 is_complete() 或达到最大迭代
        4. 调用 on_complete Hook
        5. 返回执行结果

        Args:
            spec: Agent执行规格

        Returns:
            RunResult: 执行结果
        """
        start_time = time.time()
        context = self._create_context(spec, iteration=0)

        # ON_START Hook
        try:
            context = await self._call_hook("on_start", context)
        except Exception as e:
            logger.warning(f"[AgentRunner] on_start hook failed: {e}")
            context.error = e
            context.add_warning(f"on_start hook error: {e}")

        # 主循环
        while not spec.is_complete() and context.iteration < spec.max_iterations:
            context.iteration += 1

            try:
                # BEFORE_ITERATION Hook
                context = await self._call_hook("before_iteration", context)
                if context.blocked:
                    logger.info(f"[AgentRunner] Iteration blocked by hook: {context.block_reason}")
                    break

                # ── 工具执行阶段 ───────────────────────────────────────
                # BEFORE_EXECUTE_TOOLS Hook
                context = await self._call_hook("before_execute_tools", context)
                if context.blocked:
                    logger.info(f"[AgentRunner] Tools execution blocked: {context.block_reason}")
                    break

                # 执行工具
                tool_results = await self._execute_tools(context)
                context.tool_results = tool_results

                # AFTER_EXECUTE_TOOLS Hook
                context = await self._call_hook("after_execute_tools", context)

                # ── LLM响应阶段 ────────────────────────────────────────
                # BEFORE_LLM Hook
                context = await self._call_hook("before_llm", context)

                # LLM调用
                response = await self._llm_loop(context)

                # ON_STREAM Hook（流式处理）
                if isinstance(response, AsyncIterator):
                    async for chunk in response:
                        context = await self._call_hook("on_stream", context, chunk)
                        context.llm_response += chunk
                else:
                    # 非流式响应
                    context.llm_response = response
                    context = await self._call_hook("on_stream", context, response)

                # AFTER_LLM Hook
                context = await self._call_hook("after_llm", context)

                # AFTER_ITERATION Hook
                context = await self._call_hook("after_iteration", context)
                if context.blocked:
                    logger.info(f"[AgentRunner] Iteration blocked after iteration: {context.block_reason}")
                    break

            except Exception as e:
                logger.error(f"[AgentRunner] Iteration {context.iteration} error: {e}", exc_info=True)
                context.error = e
                context = await self._call_hook("on_error", context, e)
                if context.blocked:
                    break

        # 计算执行时间
        duration_ms = int((time.time() - start_time) * 1000)
        context.token_count = self._tokens_used

        # ON_COMPLETE Hook
        try:
            context = await self._call_hook("on_complete", context)
        except Exception as e:
            logger.warning(f"[AgentRunner] on_complete hook failed: {e}")
            context.add_warning(f"on_complete hook error: {e}")

        # 构建结果
        result = RunResult(
            context=context,
            success=not context.blocked and context.error is None,
            output=context.llm_response or context.stream_chunk,
            iterations=context.iteration,
            tokens_used=self._tokens_used,
            errors=[str(context.error)] if context.error else [],
            duration_ms=duration_ms,
            stop_reason=self._determine_stop_reason(context, spec),
            metadata={
                "tool_results_count": len(context.tool_results),
                "warnings_count": len(context.warnings),
            },
        )

        logger.info(
            f"[AgentRunner] Run completed: success={result.success}, "
            f"iterations={result.iterations}, tokens={result.tokens_used}, "
            f"stop_reason={result.stop_reason}"
        )

        return result

    def register_hook(self, hook: AgentHook) -> None:
        """注册额外的Hook（运行时）"""
        self.hooks.register(hook)

    def unregister_hook(self, name: str) -> bool:
        """注销Hook"""
        return self.hooks.unregister(name)

    def list_hooks(self) -> list[AgentHook]:
        """列出所有已注册的Hook"""
        return self.hooks.list_hooks()

    # ─────────────────────────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────────────────────────

    def _create_context(self, spec: AgentRunSpec, iteration: int) -> AgentHookContext:
        """创建Hook上下文"""
        return AgentHookContext(
            event=AgentHookEvent.before_iteration,
            goal=spec.goal,
            session_id=spec.session_id,
            user_id=spec.user_id,
            max_iterations=spec.max_iterations,
            token_budget=spec.token_budget,
            iteration=iteration,
        )

    async def _call_hook(self, method_name: str, context: AgentHookContext, *args, **kwargs) -> AgentHookContext:
        """统一Hook调用（错误隔离）"""
        method = getattr(self.hooks, method_name, None)
        if method is None:
            return context

        try:
            if args:
                return method(context, *args, **kwargs)
            return method(context)
        except Exception as e:
            logger.warning(
                f"[AgentRunner] Hook.{method_name} failed: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            context.error = e
            context.add_warning(f"Hook.{method_name} error: {e}")
            return context

    async def _execute_tools(self, context: AgentHookContext) -> list[dict]:
        """
        执行工具

        从context.tools_to_execute获取要执行的工具列表，
        调用对应工具并返回结果。

        Args:
            context: Hook上下文

        Returns:
            工具执行结果列表
        """
        results = []
        tools_to_exec = context.tools_to_execute or []

        for tool_spec in tools_to_exec:
            tool_name = tool_spec.get("name", "")
            params = tool_spec.get("params", {})

            tool = self._tool_map.get(tool_name)
            if not tool:
                results.append({
                    "name": tool_name,
                    "success": False,
                    "error": f"Tool not found: {tool_name}",
                })
                continue

            try:
                # 构建执行上下文
                exec_context = {
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "goal": context.goal,
                    "iteration": context.iteration,
                }

                # 执行工具
                result = await tool.execute(params, exec_context)

                # 转换结果为字典
                results.append({
                    "name": tool_name,
                    "success": result.success,
                    "result": result.result if hasattr(result, "result") else str(result),
                    "error": result.error if hasattr(result, "error") else "",
                    "execution_time_ms": result.execution_time_ms if hasattr(result, "execution_time_ms") else 0,
                })

            except Exception as e:
                logger.error(f"[AgentRunner] Tool {tool_name} execution failed: {e}")
                results.append({
                    "name": tool_name,
                    "success": False,
                    "error": str(e),
                })

        return results

    async def _llm_loop(self, context: AgentHookContext) -> str | AsyncIterator[str]:
        """
        LLM调用循环

        构建Prompt并调用LLM，返回响应内容。

        Args:
            context: Hook上下文

        Returns:
            LLM响应（非流式返回字符串，流式返回AsyncIterator）
        """
        # 构建Prompt
        prompt = self._build_prompt(context)

        # 估计token（简化估算：按字符数/4）
        self._tokens_used += len(prompt) // 4

        try:
            # 调用LLM
            response = await self.llm_client.complete(prompt)
            return response
        except Exception as e:
            logger.error(f"[AgentRunner] LLM call failed: {e}")
            return f"[LLM调用失败] {type(e).__name__}: {str(e)}"

    def _build_prompt(self, context: AgentHookContext) -> str:
        """构建LLM Prompt"""
        parts = []

        # 添加goal
        if context.goal:
            parts.append(f"## 目标\n{context.goal}")

        # 添加工具执行结果
        if context.tool_results:
            tool_results_text = "\n".join([
                f"- {r['name']}: {'成功' if r.get('success') else '失败 - ' + r.get('error', '')}"
                for r in context.tool_results
            ])
            parts.append(f"## 工具执行结果\n{tool_results_text}")

        # 添加之前的LLM响应（用于多轮对话）
        if context.llm_response:
            parts.append(f"## 之前的回复\n{context.llm_response}")

        return "\n\n".join(parts)

    def _determine_stop_reason(self, context: AgentHookContext, spec: AgentRunSpec) -> str:
        """确定停止原因"""
        if context.blocked:
            return "hook_blocked"
        if context.error:
            return "error"
        if context.iteration >= spec.max_iterations:
            return "iteration_limit"
        if context.is_token_over_budget():
            return "token_limit"
        if spec.is_complete():
            return "complete"
        return "unknown"
