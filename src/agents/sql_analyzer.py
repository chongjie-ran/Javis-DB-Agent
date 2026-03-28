"""SQL分析Agent"""
from src.agents.base import BaseAgent, AgentResponse


class SQLAnalyzerAgent(BaseAgent):
    """SQL分析Agent - SQL画像、慢SQL、锁阻塞分析、优化建议"""
    
    name = "sql_analyzer"
    description = "SQL分析Agent：分析SQL执行情况，提供优化建议"
    
    system_prompt = """你是一个专业的数据库SQL分析专家。

角色定义：
- 你是 sql_analyzer agent，负责SQL性能分析和优化建议
- 你的输入是SQL文本、执行计划或会话信息
- 你的输出是分析结论和优化建议

分析维度：
1. 执行频率与资源消耗
2. 执行计划分析（全表扫描、索引缺失等）
3. 锁等待与阻塞链
4. 性能趋势（历史对比）
5. 优化建议（索引、改写、参数调整）

安全原则：
- 永远不直接执行SQL
- 永远不返回原始数据（只返回分析结论）
- 所有建议需经过风险评估

输出格式：
- sql_fingerprint: SQL指纹
- analysis: 分析结论
- performance_impact: 性能影响等级 (high/medium/low)
- optimization_suggestions: 优化建议列表
- risk_level: 建议操作的最低风险级别
"""
    
    available_tools = [
        "query_slow_sql",
        "query_session",
        "query_lock",
        "query_sql_plan",
        "analyze_sql_pattern",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        prompt = f"""请分析以下SQL：

SQL信息：{goal}

上下文：{context.get('extra_info', '')}

请进行SQL分析并给出优化建议。
"""
        result = await self.think(prompt)
        return AgentResponse(success=True, content=result, metadata={"agent": self.name})
    
    async def analyze_sql(self, sql: str, context: dict) -> AgentResponse:
        """分析指定SQL"""
        context["sql"] = sql
        return await self.process(f"分析SQL: {sql[:100]}", context)
    
    async def analyze_session(self, session_id: str, context: dict) -> AgentResponse:
        """分析指定会话的SQL"""
        context["session_id"] = session_id
        return await self.process(f"分析会话 {session_id} 的SQL", context)
