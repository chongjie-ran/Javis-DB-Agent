"""报告生成Agent"""
from src.agents.base import BaseAgent, AgentResponse


class ReporterAgent(BaseAgent):
    """报告生成Agent - RCA报告、巡检报告、领导摘要"""
    
    name = "reporter"
    description = "报告生成Agent：生成结构化报告（RCA/巡检报告/摘要）"
    
    system_prompt = """你是一个专业的数据库运维报告生成专家。

角色定义：
- 你是 reporter agent，负责生成各类运维报告
- 你的输入是诊断数据、巡检数据或其他运维数据
- 你的输出是结构化的报告文本

支持的报告类型：
1. RCA报告（Root Cause Analysis）- 故障复盘
2. 巡检报告 - 健康检查结果
3. 领导摘要 - 执行摘要，高层汇报用
4. 周报/月报 - 周期汇总

报告结构：
- 执行摘要（一段话概括）
- 背景/问题描述
- 分析过程
- 结论与建议
- 附录（详细数据）

写作风格：
- 简洁、专业、客观
- 避免技术术语堆砌，用通俗语言解释
- 数据支撑结论
- 建议具体可执行
"""
    
    available_tools = [
        "query_instance_status",
        "query_replication",
        "query_slow_sql",
        "get_knowledge_case",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        report_type = context.get("report_type", "summary")
        data = context.get("report_data", "")
        
        prompt = f"""请生成{report_type}报告：

数据来源：
{data}

上下文：{context.get('extra_info', '')}

请生成结构化报告。
"""
        result = await self.think(prompt)
        return AgentResponse(success=True, content=result, metadata={"agent": self.name, "report_type": report_type})
    
    async def generate_rca(self, incident_id: str, context: dict) -> AgentResponse:
        """生成RCA报告"""
        context["report_type"] = "RCA"
        context["incident_id"] = incident_id
        return await self.process(f"生成RCA报告 {incident_id}", context)
    
    async def generate_inspection_report(self, instance_id: str, context: dict) -> AgentResponse:
        """生成巡检报告"""
        context["report_type"] = "巡检报告"
        context["instance_id"] = instance_id
        return await self.process(f"生成巡检报告 {instance_id}", context)
    
    async def generate_summary(self, data: str, context: dict) -> AgentResponse:
        """生成摘要报告"""
        context["report_type"] = "摘要"
        context["report_data"] = data
        return await self.process("生成摘要报告", context)
