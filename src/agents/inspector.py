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

可用工具（会通过 context.db_connector 传入真实连接）：
- pg_session_analysis: 分析PostgreSQL会话（idle/active/idle in transaction）
- pg_lock_analysis: 分析PostgreSQL锁等待
- pg_replication_status: 分析PostgreSQL复制状态
- pg_bloat_analysis: 分析表膨胀
- pg_index_analysis: 分析索引使用率

当 context 中有 pg_connector 或 db_connector 时，工具会执行真实 SQL 查询。
当没有连接器时，工具返回模拟数据。

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
        "pg_session_analysis",
        "pg_lock_analysis",
        "pg_replication_status",
        "pg_bloat_analysis",
        "pg_index_analysis",
    ]
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """
        处理数据库巡检请求。
        
        关键：实际调用工具获取真实数据，而不是仅依赖 LLM 推理。
        工具会通过 context.db_connector 使用真实数据库连接。
        """
        # 从 context 获取数据库连接器
        db_connector = context.get("db_connector") or context.get("pg_connector")
        pg_connector = context.get("pg_connector")
        mysql_connector = context.get("mysql_connector")

        # ── Step 1: 调用工具获取真实数据 ────────────────────────────────
        tool_results = {}

        # PG 会话分析
        if pg_connector:
            session_result = await self.call_tool(
                "pg_session_analysis",
                {"instance_id": context.get("instance_id", "PG-LOCAL"), "limit": 50},
                {**context, "db_connector": pg_connector}
            )
            tool_results["session"] = session_result

        # PG 锁分析
        if pg_connector:
            lock_result = await self.call_tool(
                "pg_lock_analysis",
                {"instance_id": context.get("instance_id", "PG-LOCAL"), "include_graph": True},
                {**context, "db_connector": pg_connector}
            )
            tool_results["lock"] = lock_result

        # PG 复制状态
        if pg_connector:
            rep_result = await self.call_tool(
                "pg_replication_status",
                {"instance_id": context.get("instance_id", "PG-LOCAL")},
                {**context, "db_connector": pg_connector}
            )
            tool_results["replication"] = rep_result

        # PG 膨胀分析
        if pg_connector:
            bloat_result = await self.call_tool(
                "pg_bloat_analysis",
                {"instance_id": context.get("instance_id", "PG-LOCAL"), "min_bloat_percent": 10.0},
                {**context, "db_connector": pg_connector}
            )
            tool_results["bloat"] = bloat_result

        # PG 索引分析
        if pg_connector:
            idx_result = await self.call_tool(
                "pg_index_analysis",
                {"instance_id": context.get("instance_id", "PG-LOCAL")},
                {**context, "db_connector": pg_connector}
            )
            tool_results["index"] = idx_result

        # MySQL 健康检查（使用异步 API 方法）
        if mysql_connector:
            try:
                sessions = await mysql_connector.get_sessions(limit=10)
                mysql_health = {
                    "sessions_count": len(sessions),
                    "active_sessions": len([s for s in sessions if getattr(s, "status", "") == "active"]),
                }
                tool_results["mysql"] = mysql_health
            except Exception as e:
                tool_results["mysql_error"] = str(e)

        # ── Step 2: 构建上下文提示词 ─────────────────────────────────────
        # 将工具结果格式化为文本，供 LLM 生成报告
        context_text = self._format_tool_results(tool_results)

        prompt = f"""请根据以下真实数据库巡检数据，生成结构化的健康报告。

## 用户问题
{goal}

## 真实巡检数据
{context_text}

请生成包含以下字段的巡检报告：
- health_score: 0-100 健康评分
- status: excellent/good/fair/poor/critical
- findings: 问题列表（每项含 severity/category/description/suggestion）
- summary: 总结
- priority_fixes: 优先修复项

如果某些数据获取失败（如无从库），请基于可用数据生成报告，不要说"未找到相关信息"。
"""
        
        result = await self.think(prompt)
        return AgentResponse(
            success=True,
            content=result,
            metadata={
                "agent": self.name,
                "tool_results_count": len([v for v in tool_results.values() if v]),
                "has_real_data": bool(db_connector or pg_connector or mysql_connector),
            }
        )
    
    def _format_tool_results(self, tool_results: dict) -> str:
        """将工具结果格式化为可读文本"""
        lines = []
        
        for key, result in tool_results.items():
            if key == "mysql_error":
                lines.append(f"[MySQL] 获取失败: {result}")
                continue
            
            if hasattr(result, "success"):
                # ToolResult object
                if result.success:
                    lines.append(f"\n=== {key.upper()} ===")
                    if isinstance(result.data, dict):
                        for k, v in result.data.items():
                            if isinstance(v, list):
                                lines.append(f"  {k}: {len(v)} 条记录")
                                if v:
                                    lines.append(f"    示例: {v[0]}")
                            elif isinstance(v, dict):
                                lines.append(f"  {k}: {v}")
                            else:
                                lines.append(f"  {k}: {v}")
                    else:
                        lines.append(f"  {result.data}")
                else:
                    lines.append(f"[{key}] 失败: {result.error}")
            else:
                # 直接是 dict (mysql_health)
                lines.append(f"\n=== MYSQL ===")
                if isinstance(result, dict):
                    for k, v in result.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {result}")
        
        if not lines:
            return "（无可用数据，请检查数据库连接）"
        
        return "\n".join(lines)
    
    async def inspect_instance(self, instance_id: str, context: dict) -> AgentResponse:
        """巡检指定实例"""
        context["instance_id"] = instance_id
        return await self.process(f"巡检实例 {instance_id}", context)
    
    async def full_inspection(self, instance_ids: list[str], context: dict) -> AgentResponse:
        """全面巡检"""
        context["instance_ids"] = instance_ids
        return await self.process(f"全面巡检 {len(instance_ids)} 个实例", context)
