"""巡检Agent"""
from src.agents.base import BaseAgent, AgentResponse


class InspectorAgent(BaseAgent):
    """巡检Agent - 健康评分、风险项、治理建议"""
    
    name = "inspector"
    description = "巡检Agent：执行数据库健康检查，输出健康评分和风险项"
    
    system_prompt = """你是一个专业的数据库运维巡检专家。

角色定义：
- 你是 inspector agent，负责数据库健康检查
- 你的职责是全面检查实例状态，识别风险项
- 你的输出是结构化的巡检报告

巡检维度：
1. 实例基础状态（CPU/内存/IO/连接数）
2. 主从复制状态（延迟、断开）
3. 锁与会话健康（长时间锁、阻塞链）
4. 慢查询与Top SQL
5. 存储与表空间
6. 参数配置合规性
7. 安全与权限

健康评分标准：
- 90-100: 优秀
- 75-89: 良好
- 60-74: 一般
- 40-59: 较差
- <40: 危险

输出格式：
- health_score: 健康评分 (0-100)
- status: 健康状态 (excellent/good/fair/poor/critical)
- findings: 问题列表 [{severity, category, description, suggestion}]
- summary: 总结
- priority_fixes: 优先修复项
"""
    
    available_tools = [
        "query_instance_status",
        "query_replication",
        "query_slow_sql",
        "query_session",
        "query_storage",
        "query_parameters",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        prompt = f"""请执行数据库巡检：

目标：{goal}

上下文：{context.get('extra_info', '')}

请调用相关工具获取数据，然后输出巡检报告。
"""
        result = await self.think(prompt)
        return AgentResponse(success=True, content=result, metadata={"agent": self.name})
    
    async def inspect_instance(self, instance_id: str, context: dict) -> AgentResponse:
        """巡检指定实例"""
        context["instance_id"] = instance_id
        return await self.process(f"巡检实例 {instance_id}", context)
    
    async def full_inspection(self, instance_ids: list[str], context: dict) -> AgentResponse:
        """全面巡检"""
        context["instance_ids"] = instance_ids
        return await self.process(f"全面巡检 {len(instance_ids)} 个实例", context)
