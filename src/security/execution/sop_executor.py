"""SOP执行器 - 标准操作流程自动执行"""
import asyncio
import logging
import time
import uuid
import os
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

# YAML SOP 加载器和 Action→Tool 映射器
try:
    from .yaml_sop_loader import YAMLSOPLoader
    _HAS_YAML_LOADER = True
except ImportError:
    YAMLSOPLoader = None
    _HAS_YAML_LOADER = False

try:
    from .action_tool_mapper import ActionToolMapper
    _HAS_ACTION_MAPPER = True
except ImportError:
    ActionToolMapper = None
    _HAS_ACTION_MAPPER = False

# ApprovalGate
try:
    from ...gateway.approval import ApprovalGate
    _HAS_APPROVAL_GATE = True
except ImportError:
    ApprovalGate = None
    _HAS_APPROVAL_GATE = False


class SOPStatus(Enum):
    """SOP执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ABORTED = "aborted"
    PAUSED = "paused"


class SOPStepStatus(Enum):
    """SOP步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class SOPStepResult:
    """SOP步骤执行结果"""
    step_id: str
    step_name: str
    status: SOPStepStatus
    tool_name: str
    input_params: dict
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    approver: Optional[str] = None  # 审批人（如有）
    retry_count: int = 0


@dataclass
class SOPExecutionResult:
    """SOP执行结果"""
    execution_id: str
    sop_id: str
    sop_name: str
    status: SOPStatus
    step_results: List[SOPStepResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    final_result: dict = field(default_factory=dict)
    error: Optional[str] = None
    aborted_at_step: Optional[int] = None  # 中止步骤号

    @property
    def success(self) -> bool:
        return self.status == SOPStatus.COMPLETED

    @property
    def total_steps(self) -> int:
        return len(self.step_results)

    @property
    def completed_steps(self) -> int:
        return sum(1 for r in self.step_results if r.status == SOPStepStatus.COMPLETED)


class SOPExecutor:
    """
    SOP执行器

    支持：
    - 多步骤顺序执行
    - 步骤级超时控制
    - 失败自动重试
    - 审批联动
    - 暂停/恢复/中止
    - 回滚支持
    """

    def __init__(self, tool_registry: Optional[object] = None, action_mapper: Optional["ActionToolMapper"] = None, yaml_sop_dir: Optional[str] = None):
        """
        初始化 SOP 执行器。

        Args:
            tool_registry: 工具注册表，用于调用真实工具。
                          若为 None，则使用 mock 行为（向后兼容）。
            action_mapper: Action → Tool 名称映射器。
                           若为 None，则自动创建默认实例。
            yaml_sop_dir:  YAML SOP 文件目录。
                          若为 None，则使用环境变量 JAVIS_SOP_YAML_DIR
                          或默认路径 knowledge/sop_yaml/。
        """
        self.tool_registry = tool_registry
        self.action_mapper = ActionToolMapper() if (_HAS_ACTION_MAPPER and action_mapper is None) else action_mapper
        self.yaml_sop_dir = yaml_sop_dir or os.environ.get("JAVIS_SOP_YAML_DIR", "")
        self._executions: Dict[str, SOPExecutionResult] = {}
        self._sops: Dict[str, dict] = self._load_default_sops()

    def _load_default_sops(self) -> Dict[str, dict]:
        """
        加载默认 SOP 定义。

        加载顺序（优先级从高到低）：
        1. YAML SOP 文件（knowledge/sop_yaml/）
        2. 硬编码 SOP（向后兼容 fallback）
        """
        sops = {}

        # 1. 尝试从 YAML 目录加载
        if _HAS_YAML_LOADER and self.yaml_sop_dir:
            try:
                loader = YAMLSOPLoader(sop_dir=self.yaml_sop_dir)
                yaml_sops = loader.load_all()
                if yaml_sops:
                    sops.update(yaml_sops)
            except Exception:
                # YAML 加载失败不影响硬编码 SOP
                pass

        # 2. 硬编码 SOP（YAML 未覆盖时作为 fallback）
        hardcoded = self._hardcoded_sops()
        for key, sop in hardcoded.items():
            if key not in sops:
                sops[key] = sop

        return sops

    def _hardcoded_sops(self) -> Dict[str, dict]:
        """硬编码 SOP 定义（YAML 加载失败时的 fallback）"""
        return {
            "refresh_stats": {
                "id": "refresh_stats",
                "name": "刷新统计信息",
                "description": "执行ANALYZE TABLE更新统计信息",
                "steps": [
                    {
                        "step": 1,
                        "action": "execute_sql",
                        "params": {"sql": "ANALYZE TABLE {table}"},
                        "description": "执行统计信息刷新",
                        "risk_level": 2,
                        "timeout_seconds": 60,
                    },
                    {
                        "step": 2,
                        "action": "verify_stats_updated",
                        "params": {},
                        "description": "验证统计信息已更新",
                        "risk_level": 1,
                        "timeout_seconds": 30,
                    },
                ],
                "risk_level": 2,
                "timeout_seconds": 120,
            },
            "kill_idle_session": {
                "id": "kill_idle_session",
                "name": "清理空闲会话",
                "description": "查找并终止空闲会话",
                "steps": [
                    {
                        "step": 1,
                        "action": "find_idle_sessions",
                        "params": {},
                        "description": "查找空闲会话",
                        "risk_level": 1,
                        "timeout_seconds": 30,
                    },
                    {
                        "step": 2,
                        "action": "kill_session",
                        "params": {"session_id": "{session_id}"},
                        "description": "终止会话",
                        "risk_level": 3,
                        "timeout_seconds": 30,
                        "require_approval": True,
                    },
                    {
                        "step": 3,
                        "action": "verify_session_killed",
                        "params": {},
                        "description": "验证会话已终止",
                        "risk_level": 1,
                        "timeout_seconds": 30,
                    },
                ],
                "risk_level": 3,
                "timeout_seconds": 120,
            },
            "慢SQL优化": {
                "id": "slow_sql_optimization",
                "name": "慢SQL诊断优化",
                "description": "诊断慢SQL并建议优化",
                "steps": [
                    {
                        "step": 1,
                        "action": "find_slow_queries",
                        "params": {},
                        "description": "查找慢查询",
                        "risk_level": 1,
                        "timeout_seconds": 60,
                    },
                    {
                        "step": 2,
                        "action": "explain_query",
                        "params": {},
                        "description": "分析执行计划",
                        "risk_level": 1,
                        "timeout_seconds": 60,
                    },
                    {
                        "step": 3,
                        "action": "suggest_index",
                        "params": {},
                        "description": "建议索引",
                        "risk_level": 1,
                        "timeout_seconds": 30,
                    },
                ],
                "risk_level": 1,
                "timeout_seconds": 300,
            },
            "lock_wait_diagnosis": {
                "id": "lock_wait_diagnosis",
                "name": "锁等待诊断",
                "description": "诊断锁等待问题",
                "steps": [
                    {
                        "step": 1,
                        "action": "find_blocking_sessions",
                        "params": {},
                        "description": "查找阻塞会话",
                        "risk_level": 1,
                        "timeout_seconds": 30,
                    },
                    {
                        "step": 2,
                        "action": "analyze_lock_chain",
                        "params": {},
                        "description": "分析锁等待链",
                        "risk_level": 1,
                        "timeout_seconds": 60,
                    },
                    {
                        "step": 3,
                        "action": "suggest_kill_blocker",
                        "params": {},
                        "description": "建议终止阻塞者",
                        "risk_level": 3,
                        "timeout_seconds": 30,
                        "require_approval": True,
                    },
                ],
                "risk_level": 3,
                "timeout_seconds": 180,
            },
        }

    def register_sop(self, sop: dict):
        """注册自定义SOP"""
        sop_id = sop.get("id") or sop.get("name")
        self._sops[sop_id] = sop

    def get_sop(self, sop_id: str) -> Optional[dict]:
        """获取SOP定义"""
        return self._sops.get(sop_id)

    def list_sops(self) -> List[dict]:
        """列出所有SOP"""
        return list(self._sops.values())

    async def execute(
        self,
        sop: dict,
        context: dict,
        max_retries: int = 3,
    ) -> SOPExecutionResult:
        """
        执行SOP

        Args:
            sop: SOP定义字典
            context: 执行上下文（包含参数等）
            max_retries: 最大重试次数

        Returns:
            SOPExecutionResult
        """
        execution_id = f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        sop_id = sop.get("id", "unknown")
        sop_name = sop.get("name", sop_id)
        steps = sop.get("steps", [])
        timeout_seconds = sop.get("timeout_seconds", 300)

        result = SOPExecutionResult(
            execution_id=execution_id,
            sop_id=sop_id,
            sop_name=sop_name,
            status=SOPStatus.PENDING,
            started_at=datetime.now(),
        )

        self._executions[execution_id] = result
        result.status = SOPStatus.RUNNING
        has_any_failure = False

        start_time = time.time()

        try:
            for step_def in steps:
                step_retries = step_def.get("retry_count", max_retries)
                step_attempt = 0
                step_result = None
                step_succeeded = False
                last_error_msg = None
                current_failed_result = None  # Track current attempt's failure only

                while step_attempt <= step_retries:
                    try:
                        step_result = await self._execute_step(
                            step_def, context, max_retries
                        )
                        # Check if step itself reports failure (retryable)
                        if step_result.status == SOPStepStatus.FAILED:
                            last_error_msg = step_result.error
                            current_failed_result = step_result
                            step_attempt += 1
                            if step_attempt <= step_retries:
                                continue
                            # Exhausted retries
                            break
                        # Step succeeded
                        step_succeeded = True
                        break
                    except asyncio.TimeoutError:
                        last_error_msg = f"步骤执行超时（{step_def.get('timeout_seconds', 60)}s）"
                        current_failed_result = SOPStepResult(
                            step_id=str(step_def.get("step", 0)),
                            step_name=step_def.get("description", step_def.get("action", "")),
                            status=SOPStepStatus.FAILED,
                            tool_name=step_def.get("action", ""),
                            input_params={},
                            error=last_error_msg,
                        )
                    except Exception as step_error:
                        last_error_msg = str(step_error)
                        current_failed_result = SOPStepResult(
                            step_id=str(step_def.get("step", 0)),
                            step_name=step_def.get("description", step_def.get("action", "")),
                            status=SOPStepStatus.FAILED,
                            tool_name=step_def.get("action", ""),
                            input_params={},
                            error=last_error_msg,
                        )

                    # Exception occurred - retry if possible
                    step_attempt += 1
                    if step_attempt <= step_retries:
                        continue
                    # Exhausted retries
                    break

                # Now add the appropriate result
                if step_succeeded and step_result:
                    result.step_results.append(step_result)
                elif current_failed_result:
                    result.step_results.append(current_failed_result)
                    has_any_failure = True
                    result.error = f"步骤失败: {last_error_msg}"
                    if step_def.get("critical") and sop.get("abort_on_critical_failure"):
                        result.status = SOPStatus.FAILED
                        result.aborted_at_step = step_def.get("step")
                        break

                if step_result and step_result.status == SOPStepStatus.WAITING_APPROVAL:
                    result.status = SOPStatus.WAITING_APPROVAL

            if result.status == SOPStatus.RUNNING:
                if has_any_failure:
                    result.status = SOPStatus.FAILED
                else:
                    result.status = SOPStatus.COMPLETED

        except asyncio.TimeoutError:
            result.status = SOPStatus.FAILED
            result.error = f"SOP执行超时（{timeout_seconds}s）"
        except Exception as e:
            result.status = SOPStatus.FAILED
            result.error = str(e)

        result.completed_at = datetime.now()
        result.duration_ms = int((time.time() - start_time) * 1000)
        result.final_result = {
            "status": result.status.value,
            "completed_steps": result.completed_steps,
            "total_steps": result.total_steps,
            "aborted_at_step": result.aborted_at_step,
            "error": result.error,
        }

        return result

    async def _execute_step(
        self,
        step_def: dict,
        context: dict,
        max_retries: int,
    ) -> SOPStepResult:
        """执行单个SOP步骤"""
        step_id = str(step_def.get("step", 0))
        action = step_def.get("action", "")
        params = step_def.get("params", {})
        timeout = step_def.get("timeout_seconds", 60)
        require_approval = step_def.get("require_approval", False)

        # 替换参数中的占位符
        resolved_params = self._resolve_params(params, context)

        result = SOPStepResult(
            step_id=step_id,
            step_name=step_def.get("description", action),
            status=SOPStepStatus.RUNNING,
            tool_name=action,
            input_params=resolved_params,
            started_at=datetime.now(),
        )

        # 审批检查
        if require_approval:
            approved = await self._check_approval(step_def, resolved_params, context)
            if not approved:
                result.status = SOPStepStatus.WAITING_APPROVAL
                result.error = "等待审批"
                return result

        # 执行步骤（带重试）
        attempts = 0
        last_error = None
        max_attempts = max_retries + 1  # 总尝试次数

        while attempts < max_attempts:
            try:
                output = await asyncio.wait_for(
                    self._call_tool(action, resolved_params, context),
                    timeout=timeout,
                )
                result.output = output
                result.status = SOPStepStatus.COMPLETED
                result.retry_count = max(0, attempts)
                break

            except asyncio.TimeoutError:
                last_error = f"步骤执行超时（{timeout}s）"
                result.status = SOPStepStatus.FAILED
                result.error = last_error
                break

            except Exception as e:
                last_error = str(e)
                attempts += 1
                if attempts < max_attempts:
                    await asyncio.sleep(0.5 * attempts)  # 指数退避
                else:
                    result.status = SOPStepStatus.FAILED
                    result.error = last_error
                    result.retry_count = attempts

        result.completed_at = datetime.now()
        if result.started_at and result.completed_at:
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )

        return result

    async def _check_approval(
        self,
        step_def: dict,
        params: dict,
        context: dict,
    ) -> bool:
        """
        检查操作是否已审批。

        流程：
        1. 若 risk_level 无需审批 → 直接放行
        2. 若无 ApprovalGate 实例 → 降级放行（记录警告）
        3. 有 ApprovalGate → 发起请求 → 同步等待结果（支持超时）

        Args:
            step_def: SOP步骤定义，包含 risk_level / action / step_id 等
            params: 已解析的步骤参数
            context: 执行上下文

        Returns:
            True: 审批通过
            False: 审批拒绝 / 超时 / 未知错误
        """
        action = step_def.get("action", "")
        risk_level = step_def.get("risk_level", 1)
        if isinstance(risk_level, int):
            risk_level = {1: "L3", 2: "L4", 3: "L5"}.get(risk_level, "L4")

        # L3 及以下无需审批
        if risk_level in ("L1", "L2", "L3", 1, 2):
            return True

        # 获取 ApprovalGate 实例
        approval_gate = context.get("approval_gate")
        if not approval_gate:
            logger.warning(
                f"[SECURITY] Approval required (risk={risk_level}) for action "
                f"'{action}' but no ApprovalGate in context. Allowing with warning."
            )
            return True  # 降级放行

        # 发起审批请求
        try:
            result = await approval_gate.request_approval(
                step_def=step_def, params=params, context=context
            )
            if not result.success:
                logger.warning(
                    f"[SECURITY] Approval request failed: {result.error}"
                )
                return False
            request_id = result.request_id
        except Exception as e:
            logger.error(
                f"[SECURITY] Failed to request approval for '{action}': {e}"
            )
            return False

        # 同步等待审批结果
        logger.info(
            f"[SECURITY] Waiting for approval: request_id={request_id} "
            f"action={action} risk_level={risk_level}"
        )
        start_time = time.time()
        while time.time() - start_time < approval_gate._timeout:
            approved, reason = await approval_gate.check_approval_status(request_id)
            if approved:
                logger.info(
                    f"[SECURITY] Approval granted: request_id={request_id} reason={reason}"
                )
                return True
            if reason in ("rejected", "timeout"):
                logger.info(
                    f"[SECURITY] Approval denied: request_id={request_id} reason={reason}"
                )
                return False
            await asyncio.sleep(1)

        # 循环结束 = 超时
        logger.warning(
            f"[SECURITY] Approval timeout: request_id={request_id} "
            f"elapsed={approval_gate._timeout}s"
        )
        return False

    async def _call_tool(
        self,
        tool_name: str,
        params: dict,
        context: dict,
    ) -> Any:
        """
        调用工具

        路由逻辑：
        1. 若有 tool_registry：
           a. 使用 action_mapper 将 SOP action 映射到工具名
           b. 从 registry 获取工具并执行
           c. 若工具未注册，抛出错误
        2. 若无 tool_registry：
           a. 检查是否为已知 mock action
           b. 是 → 返回模拟结果（向后兼容）
           c. 否 → 抛出 NotImplementedError
        """
        # 如果有tool_registry，从注册表获取工具（通过 action_mapper 路由）
        if self.tool_registry:
            # 1. 解析 action → tool_name
            if self.action_mapper:
                resolved_tool_name = self.action_mapper.resolve(tool_name)
            else:
                resolved_tool_name = tool_name

            # 2. 尝试从 registry 获取工具
            tool = self.tool_registry.get_tool(resolved_tool_name or tool_name)
            if tool:
                return await tool.execute(params, context)
            # 工具未注册 → 抛出错误
            raise NotImplementedError(f"Tool not registered: {resolved_tool_name or tool_name}")

        # 无registry时，检查是否为已知操作（mock fallback）
        known_actions = {
            "execute_sql", "verify_stats_updated",
            "find_idle_sessions", "find_blocking_session", "kill_session",
            "verify_session_killed", "verify_session_gone",
            "find_slow_queries", "explain_query", "suggest_index",
            "find_blocking_sessions", "analyze_lock_chain", "suggest_kill_blocker",
            "action_a", "action_b", "action_c",
            "slow_query", "unreliable_action", "precheck", "critical_action", "cleanup",
        }
        if tool_name not in known_actions:
            raise NotImplementedError(f"Unknown action: {tool_name}")

        # 模拟执行（仅用于已知操作）
        return {"status": "simulated", "tool": tool_name, "params": params}

    def _resolve_params(self, params: dict, context: dict) -> dict:
        """解析参数中的占位符"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and "{" in value:
                # 替换 {placeholder} 格式
                try:
                    resolved[key] = value.format(**context)
                except (KeyError, ValueError):
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    def get_execution(self, execution_id: str) -> Optional[SOPExecutionResult]:
        """获取执行记录"""
        return self._executions.get(execution_id)

    def list_executions(self) -> List[SOPExecutionResult]:
        """列出所有执行记录"""
        return list(self._executions.values())

    async def pause(self, execution_id: str) -> bool:
        """暂停SOP执行"""
        exec_result = self._executions.get(execution_id)
        if exec_result and exec_result.status == SOPStatus.RUNNING:
            exec_result.status = SOPStatus.PAUSED
            return True
        return False

    async def resume(self, execution_id: str) -> bool:
        """恢复SOP执行"""
        exec_result = self._executions.get(execution_id)
        if exec_result and exec_result.status == SOPStatus.PAUSED:
            exec_result.status = SOPStatus.RUNNING
            return True
        return False

    async def abort(self, execution_id: str) -> bool:
        """中止SOP执行"""
        exec_result = self._executions.get(execution_id)
        if exec_result and exec_result.status in (SOPStatus.RUNNING, SOPStatus.PAUSED):
            exec_result.status = SOPStatus.ABORTED
            return True
        return False
