# Agents模块 (V3.0 Phase 1)
#
# Phase 0: 8个Hook点 + CompositeHook (src/hooks/)
# Phase 1: AgentRunner + AgentRunSpec + RunResult + 指令自包含验证Hook
#
# 核心组件：
# - AgentRunner: 基于Hook的执行引擎
# - AgentRunSpec: 执行规格定义
# - RunResult: 执行结果
# - InstructionSelfContainValidator: 指令自包含验证
# - SelfJustificationGuard: 自我合理化防护
# - TokenMonitorHook: Token监控

from .agent_runner import AgentRunner
from .agent_run_spec import AgentRunSpec
from .run_result import RunResult
from .instruction_validator import (
    InstructionSelfContainValidator,
    InstructionNotSelfContainedError,
    SelfJustificationGuard,
    TokenMonitorHook,
)

# 导出所有Agent
from .base import BaseAgent, AgentResponse
from .orchestrator import OrchestratorAgent, Intent
from .diagnostic import DiagnosticAgent
from .risk import RiskAgent
from .sql_analyzer import SQLAnalyzerAgent
from .inspector import InspectorAgent
from .reporter import ReporterAgent
from .session_analyzer_agent import SessionAnalyzerAgent
from .capacity_agent import CapacityAgent
from .alert_agent import AlertAgent
from .backup_agent import BackupAgent
from .performance_agent import PerformanceAgent

__all__ = [
    # Phase 1 核心组件
    "AgentRunner",
    "AgentRunSpec",
    "RunResult",
    "InstructionSelfContainValidator",
    "InstructionNotSelfContainedError",
    "SelfJustificationGuard",
    "TokenMonitorHook",
    # Agent基类
    "BaseAgent",
    "AgentResponse",
    # Agent实现
    "OrchestratorAgent",
    "Intent",
    "DiagnosticAgent",
    "RiskAgent",
    "SQLAnalyzerAgent",
    "InspectorAgent",
    "ReporterAgent",
    "SessionAnalyzerAgent",
    "CapacityAgent",
    "AlertAgent",
    "BackupAgent",
    "PerformanceAgent",
]
