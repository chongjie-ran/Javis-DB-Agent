"""SQL分析Agent - Round 13 增强：索引建议、执行计划解读、SQL改写"""
from src.agents.base import BaseAgent, AgentResponse


class SQLAnalyzerAgent(BaseAgent):
    """SQL分析Agent - SQL画像、慢SQL、锁阻塞分析、优化建议"""
    
    name = "sql_analyzer"
    description = "SQL分析Agent：分析SQL执行情况，提供索引建议和优化建议"
    
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
5. 索引建议（MySQL/PG语法分别输出）
6. 执行计划解读（标注性能问题）
7. SQL改写建议（基于执行计划优化）

索引建议规则：
- MySQL语法：CREATE INDEX idx_name ON table(col);
- PostgreSQL语法：CREATE INDEX idx_name ON table USING btree(col);
- 复合索引：考虑列顺序（等值列在前，范围列在后）
- 覆盖索引：包含查询所需全部列，避免回表

执行计划解读：
- TABLE ACCESS FULL：全表扫描，性能问题严重
- INDEX RANGE SCAN：正常，使用了索引
- INDEX FULL SCAN：可能可优化
- NESTED LOOP：数据量小可接受，大数据量需优化
- HASH JOIN：适合大数据量关联
- MERGE JOIN：需要排序输入
- 关注cost值，越高性能越差
- 关注cardinality/rows，估算不准确需分析

SQL改写建议：
- 基于执行计划问题给出优化SQL
- 避免SELECT *，明确列名
- 使用绑定变量
- 分解复杂查询
- 添加合适LIMIT

安全原则：
- 永远不直接执行SQL
- 永远不返回原始数据（只返回分析结论）
- 所有建议需经过风险评估

输出格式：
- sql_fingerprint: SQL指纹
- analysis: 分析结论
- performance_impact: 性能影响等级 (high/medium/low)
- optimization_suggestions: 优化建议列表
- index_suggestions: 索引建议（MySQL/PG分别）
- plan_analysis: 执行计划解读
- rewritten_sql: 优化后的SQL
- risk_level: 建议操作的最低风险级别
"""
    
    available_tools = [
        "query_slow_sql",
        "query_session",
        "query_lock",
        "query_sql_plan",
        "analyze_sql_pattern",
        "analyze_explain_plan",
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
    
    async def suggest_indexes(self, sql: str, db_type: str, context: dict) -> AgentResponse:
        """为SQL生成索引建议（MySQL/PG分别）"""
        context["sql"] = sql
        context["db_type"] = db_type
        
        # 获取执行计划分析
        plan_result = None
        try:
            plan_result = await self.call_tool("analyze_explain_plan", {"sql_text": sql}, context)
        except Exception:
            pass
        
        # 生成分析prompt
        plan_info = ""
        if plan_result and plan_result.success:
            plan_info = f"\n\n执行计划分析结果：{plan_result.data}"
        
        prompt = f"""请为以下SQL生成索引建议：

SQL: {sql}
数据库类型: {db_type}
{plan_info}

请分别给出：
1. MySQL语法索引建议
2. PostgreSQL语法索引建议
3. 索引列顺序建议
4. 是否需要覆盖索引
5. 注意事项（索引大小、选择性等）
"""
        result = await self.think(prompt)
        
        return AgentResponse(
            success=True,
            content=result,
            metadata={
                "agent": self.name,
                "action": "suggest_indexes",
                "db_type": db_type,
            }
        )
    
    async def interpret_plan(self, plan_output: str, context: dict) -> AgentResponse:
        """解读执行计划，标注性能问题"""
        prompt = f"""请解读以下执行计划，标注性能问题：

执行计划：
{plan_output}

请分析：
1. 各步骤操作类型和性能影响
2. 识别的性能问题（全表扫描、嵌套循环过深等）
3. 问题严重程度（high/medium/low）
4. 优化建议
"""
        result = await self.think(prompt)
        return AgentResponse(
            success=True,
            content=result,
            metadata={
                "agent": self.name,
                "action": "interpret_plan",
            }
        )
    
    async def rewrite_sql(self, sql: str, plan_issues: list, context: dict) -> AgentResponse:
        """基于执行计划问题改写SQL"""
        prompt = f"""请基于以下执行计划问题改写SQL：

原始SQL: {sql}

执行计划问题：
{plan_issues}

请给出：
1. 优化后的SQL（MySQL兼容）
2. 优化点说明
3. 预期性能提升
4. 注意事项
"""
        result = await self.think(prompt)
        return AgentResponse(
            success=True,
            content=result,
            metadata={
                "agent": self.name,
                "action": "rewrite_sql",
            }
        )
