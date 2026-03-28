"""风险评估Agent"""
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import RiskLevel


class RiskAgent(BaseAgent):
    """风险评估Agent - 评估风险级别和处置建议"""
    
    name = "risk"
    description = "风险评估Agent：评估诊断结果的风险级别，判断是否可自动处置"
    
    system_prompt = """你是一个专业的数据库运维风险评估专家。

角色定义：
- 你是 risk agent，负责评估操作/故障的风险级别
- 你的职责是给出风险分级和处置建议
- 遵循最小风险原则

风险级别定义：
- L1 (只读分析): 查看数据、分析问题 - 无需审批
- L2 (自动诊断): 自动诊断、根因分析 - 无需审批
- L3 (低风险执行): 低风险操作、日志记录 - 需记录
- L4 (中风险执行): 中等风险操作 - 需单签审批
- L5 (高风险执行): 高风险操作、破坏性操作 - 需双人审批/禁止

输出格式：
- risk_level: L1/L2/L3/L4/L5
- can_auto_handle: true/false
- approval_required: true/false
- impact_assessment: 影响范围评估
- recommended_actions: 建议操作列表
- warnings: 风险警告（如有）
"""
    
    available_tools = [
        "query_instance_status",
        "query_replication",
        "analyze_impact",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        prompt = f"""请评估以下场景的风险：

场景描述：{goal}

相关上下文：
{context.get('extra_info', '')}

请给出风险评估结果。
"""
        result = await self.think(prompt)
        return AgentResponse(success=True, content=result, metadata={"agent": self.name})
    
    async def assess_risk(self, scenario: str, context: dict) -> AgentResponse:
        """评估风险"""
        return await self.process(scenario, context)
    
    def get_risk_from_diagnostic(self, diagnostic_result: str) -> dict:
        """从诊断结果推断风险级别"""
        import re
        # 简单关键词匹配
        high_risk_keywords = ["主库", "切换", "HA", "故障", "数据丢失", "主从"]
        medium_risk_keywords = ["锁等待", "慢查询", "性能下降"]
        
        if any(k in diagnostic_result for k in high_risk_keywords):
            return {"risk_level": RiskLevel.L4_MEDIUM, "can_auto": False}
        elif any(k in diagnostic_result for k in medium_risk_keywords):
            return {"risk_level": RiskLevel.L3_LOW_RISK, "can_auto": True}
        else:
            return {"risk_level": RiskLevel.L2_DIAGNOSE, "can_auto": True}
