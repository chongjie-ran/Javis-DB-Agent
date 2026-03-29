"""会话分析Agent - Round 13 新增"""
from src.agents.base import BaseAgent, AgentResponse


class SessionAnalyzerAgent(BaseAgent):
    """会话分析专家智能体 - 专注于数据库会话管理、连接池分析、死锁检测"""
    
    name = "session_analyzer"
    description = "会话分析专家：分析会话状态、连接池状况、死锁检测"
    
    system_prompt = """你是一个专业的数据库会话分析专家。

角色定义：
- 你是 session_analyzer agent，负责会话管理和连接分析
- 你的输入是会话ID、实例信息或分析目标
- 你的输出是会话分析结论和处置建议

分析维度：
1. 会话状态分析（活跃/idle/idle in transaction/等待）
2. 连接池使用状况（活跃/空闲/等待/泄漏）
3. 死锁检测（等待图/死锁链/受害者分析）
4. 长时间事务识别
5. 异常会话识别（连接泄漏/长时间idle）

安全原则：
- 只读取会话信息，不主动终止会话
- 死锁处置建议需标注风险
- 不返回原始敏感数据

输出格式：
- session_summary: 会话概要
- analysis: 分析结论
- issues: 发现的问题列表
- recommendations: 处置建议
- risk_level: 建议操作的最低风险级别
"""
    
    available_tools = [
        "session_list",
        "session_detail",
        "connection_pool",
        "deadlock_detection",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        prompt = f"""请分析以下会话管理问题：

目标：{goal}

上下文：{context.get('extra_info', '')}

请提供会话分析和处置建议。
"""
        result = await self.think(prompt)
        return AgentResponse(success=True, content=result, metadata={"agent": self.name})
    
    async def analyze_session(self, db_type: str, session_id: str, context: dict) -> AgentResponse:
        """分析指定会话"""
        context["session_id"] = session_id
        context["db_type"] = db_type
        return await self.process(f"分析会话 {session_id} (db_type={db_type})", context)
    
    async def analyze_connections(self, db_type: str, context: dict) -> AgentResponse:
        """分析连接池状况"""
        context["db_type"] = db_type
        return await self.process(f"分析 {db_type} 连接池状况", context)
    
    async def detect_deadlocks(self, db_type: str, context: dict) -> AgentResponse:
        """检测死锁"""
        context["db_type"] = db_type
        return await self.process(f"检测 {db_type} 死锁", context)
