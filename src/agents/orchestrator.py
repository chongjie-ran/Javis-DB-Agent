"""统一编排Agent - 任务分解与多Agent协同"""
from typing import Optional
from enum import Enum

from src.agents.base import BaseAgent, AgentResponse
from src.agents.diagnostic import DiagnosticAgent
from src.agents.risk import RiskAgent
from src.agents.sql_analyzer import SQLAnalyzerAgent
from src.agents.inspector import InspectorAgent
from src.agents.reporter import ReporterAgent


class Intent(Enum):
    """用户意图"""
    DIAGNOSE = "diagnose"           # 告警诊断
    SQL_ANALYZE = "sql_analyze"    # SQL分析
    INSPECT = "inspect"            # 健康巡检
    REPORT = "report"              # 报告生成
    RISK_ASSESS = "risk_assess"    # 风险评估
    GENERAL = "general"            # 通用问答


class OrchestratorAgent(BaseAgent):
    """统一编排Agent - 负责任务分解、Agent选择、结果汇总"""
    
    name = "orchestrator"
    description = "统一编排Agent：解析用户目标，协调专业Agent完成任务"
    
    system_prompt = """你是一个专业的数据库运维智能助手（Copilot）。

角色定义：
- 你是数据库运维的统一入口
- 你负责理解用户目标，选择合适的专业Agent
- 你协调多个Agent协作，汇总最终结果
- 你不直接执行操作，通过Agent和工具完成

你的专长Agent团队：
1. diagnostic: 诊断Agent - 告警根因分析
2. risk: 风险评估Agent - 风险分级和处置建议
3. sql_analyzer: SQL分析Agent - SQL性能分析
4. inspector: 巡检Agent - 健康检查
5. reporter: 报告Agent - 报告生成

工作流程：
1. 理解用户目标
2. 识别用户意图类型
3. 选择合适的Agent（可能多个）
4. 构建执行计划
5. 协调Agent执行
6. 汇总结果反馈

安全原则：
- 所有操作必须通过工具，不直接操作数据库
- 高风险操作必须提示用户确认
- 不确定的结论要标注置信度

当前阶段（Copilot）：
- 以问答和建议为主
- 不自动执行高风险操作
- 用户决策优先
"""
    
    available_tools = []  # 编排Agent不直接调用工具，通过子Agent
    
    # Agent实例注册表
    _agent_registry: dict[str, BaseAgent] = {}
    
    def __init__(self):
        super().__init__()
        self._init_agents()
    
    def _init_agents(self):
        """初始化子Agent"""
        self._agent_registry = {
            "diagnostic": DiagnosticAgent(),
            "risk": RiskAgent(),
            "sql_analyzer": SQLAnalyzerAgent(),
            "inspector": InspectorAgent(),
            "reporter": ReporterAgent(),
        }
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agent_registry.get(name)
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """处理用户目标"""
        # 1. 识别意图
        intent = await self._recognize_intent(goal)
        
        # 2. 选择Agent
        selected_agents = self._select_agents(intent, goal)
        
        # 3. 构建执行计划
        plan = self._build_plan(selected_agents, goal, context)
        
        # 4. 执行计划
        results = await self._execute_plan(plan, context)
        
        # 5. 汇总结果
        aggregated = self._aggregate_results(results, intent)
        
        return AgentResponse(
            success=True,
            content=aggregated["content"],
            metadata={
                "agent": self.name,
                "intent": intent.value,
                "agents_used": [a.name for a in selected_agents],
                "plan": plan,
            }
        )
    
    async def _recognize_intent(self, goal: str) -> Intent:
        """识别用户意图"""
        prompt = f"""请识别以下用户目标的意图类型：

目标：{goal}

可选意图：
- diagnose: 告警诊断、根因分析
- sql_analyze: SQL分析、慢SQL分析
- inspect: 健康巡检、状态检查
- report: 报告生成
- risk_assess: 风险评估
- general: 通用问答

请只输出意图名称（如：diagnose）。
"""
        result = await self.think(prompt)
        result = result.strip().lower()
        
        for intent in Intent:
            if intent.value in result:
                return intent
        return Intent.GENERAL
    
    def _select_agents(self, intent: Intent, goal: str) -> list[BaseAgent]:
        """选择合适的Agent"""
        mapping = {
            Intent.DIAGNOSE: ["diagnostic", "risk"],
            Intent.SQL_ANALYZE: ["sql_analyzer", "risk"],
            Intent.INSPECT: ["inspector"],
            Intent.REPORT: ["reporter"],
            Intent.RISK_ASSESS: ["risk"],
            Intent.GENERAL: [],
        }
        
        agent_names = mapping.get(intent, ["diagnostic"])
        return [self._agent_registry[name] for name in agent_names if name in self._agent_registry]
    
    def _build_plan(self, agents: list[BaseAgent], goal: str, context: dict) -> list[dict]:
        """构建执行计划"""
        plan = []
        for agent in agents:
            # 支持传入Agent对象或Agent名称字符串
            if isinstance(agent, str):
                agent_name = agent
            else:
                agent_name = agent.name
            plan.append({
                "agent": agent_name,
                "task": goal,
                "depends_on": [],
            })
        return plan
    
    async def _execute_plan(self, plan: list[dict], context: dict) -> list[AgentResponse]:
        """执行计划"""
        results = []
        for step in plan:
            agent = self.get_agent(step["agent"])
            if agent:
                response = await agent.process(step["task"], context)
                results.append(response)
        return results
    
    def _aggregate_results(self, results: list[AgentResponse], intent: Intent) -> dict:
        """汇总结果"""
        if not results:
            return {"content": "未找到相关信息"}
        
        if len(results) == 1:
            return {"content": results[0].content}
        
        # 多Agent结果汇总
        aggregated_parts = []
        for r in results:
            if r.success:
                aggregated_parts.append(f"## {r.metadata.get('agent', 'Agent')} 结果\n\n{r.content}")
            else:
                aggregated_parts.append(f"## {r.metadata.get('agent', 'Agent')} 失败\n\n{r.error}")
        
        return {
            "content": "\n\n".join(aggregated_parts),
            "parts": aggregated_parts,
        }
    
    async def handle_chat(self, user_input: str, context: dict) -> AgentResponse:
        """处理对话"""
        return await self.process(user_input, context)
    
    async def handle_diagnose(self, alert_id: str, context: dict) -> AgentResponse:
        """处理告警诊断"""
        diagnostic = self.get_agent("diagnostic")
        risk = self.get_agent("risk")
        
        # 先诊断
        diag_result = await diagnostic.diagnose_alert(alert_id, context)
        
        # 再评估风险
        context["extra_info"] = f"诊断结论：{diag_result.content}"
        risk_result = await risk.assess_risk(f"告警 {alert_id} 的风险", context)
        
        return AgentResponse(
            success=True,
            content=f"## 诊断结论\n\n{diag_result.content}\n\n## 风险评估\n\n{risk_result.content}",
            metadata={
                "agent": self.name,
                "intent": Intent.DIAGNOSE.value,
                "diagnostic": diag_result.metadata,
                "risk": risk_result.metadata,
            }
        )
