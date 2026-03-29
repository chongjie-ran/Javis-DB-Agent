"""诊断Agent - 根因分析与告警关联推理
实现A告警→B告警→C告警的链式诊断逻辑
"""
from typing import Optional, Any
from src.agents.base import BaseAgent, AgentResponse
from src.tools.base import ToolDefinition, ToolParam, RiskLevel, ToolResult
from src.gateway.alert_correlator import (
    AlertCorrelator,
    get_mock_alert_correlator,
    AlertRole,
    CorrelationResult,
)


class DiagnosticAgent(BaseAgent):
    """诊断Agent - 负责根因分析与告警关联"""

    name = "diagnostic"
    description = "诊断Agent:接收告警/故障信息,进行根因分析和告警关联推理,输出诊断路径和置信度"

    system_prompt = """你是一个专业的数据库运维诊断专家。

角色定义:
- 你是 diagnostic agent,负责数据库故障的根因分析
- 你通过工具获取诊断数据,不能直接访问数据库
- 你的职责是分析问题、找出根因、给出排查路径
- 你需要具备告警关联分析能力,能够发现关联告警形成诊断链

工作流程:
1. 接收告警/故障上下文
2. 调用告警关联推理引擎,查找关联告警
3. 调用查询工具获取相关数据(实例状态、会话、锁、SQL等)
4. 结合知识库规则进行匹配
5. 输出诊断结论:根因 + 置信度 + 下一步行动 + 告警关联链

输出格式要求:
- root_cause: 根本原因描述
- confidence: 置信度 (0.0-1.0)
- evidence: 支持诊断的证据列表
- next_steps: 下一步排查步骤
- severity: 严重程度 (critical/high/medium/low)
- alert_chain: 告警关联链 [{"alert_id": "...", "role": "...", "confidence": ...}]
- diagnostic_path: 诊断路径 ["ALT-001", "ALT-002", "ALT-003"]
"""

    available_tools = [
        "query_instance_status",
        "query_session",
        "query_lock",
        "query_slow_sql",
        "query_replication",
        "query_alert_detail",
        "query_related_alerts",  # 新增:查询关联告警
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._correlator = None

    def _get_correlator(self) -> AlertCorrelator:
        """获取告警关联器"""
        if self._correlator is None:
            self._correlator = get_mock_alert_correlator()
        return self._correlator

    def _build_system_prompt(self) -> str:
        return self.system_prompt

    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """处理诊断请求"""
        # 构造诊断Prompt
        alert_info = context.get("alert_info", {})
        instance_id = context.get("instance_id", "")
        primary_alert_id = alert_info.get("alert_id", context.get("alert_id", ""))

        prompt = f"""请分析以下告警/故障:

告警信息:
- 告警ID: {alert_info.get('alert_id', 'N/A')}
- 告警类型: {alert_info.get('alert_type', 'N/A')}
- 告警级别: {alert_info.get('severity', 'N/A')}
- 实例ID: {instance_id}

上下文:
{context.get('extra_info', '')}

请进行诊断分析,先调用相关工具获取数据,再给出结论。
"""

        # 直接让LLM分析
        result = await self.think(prompt)

        return AgentResponse(
            success=True,
            content=result,
            metadata={"agent": self.name, "instance_id": instance_id}
        )

    async def diagnose_alert(self, alert_id: str, context: dict) -> AgentResponse:
        """
        诊断指定告警(带关联推理)

        这是主要的诊断入口,会自动:
        1. 查找关联告警
        2. 构建诊断链
        3. 给出根因分析
        """
        # 保存原始alert_id
        context["alert_info"] = {"alert_id": alert_id}

        # 获取Mock客户端(如果有)
        mock_client = context.get("mock_client")

        # 执行关联分析
        correlation_result = None
        if mock_client:
            try:
                correlator = self._get_correlator()
                all_alerts = await mock_client.get_alerts(status="active")

                correlation_result = await correlator.correlate_alerts(
                    primary_alert_id=alert_id,
                    all_alerts=all_alerts,
                    mock_client=mock_client,
                )

                # 更新context中的告警信息
                context["alert_info"] = {
                    "alert_id": alert_id,
                    "correlation_chain": [
                        {
                            "alert_id": n.alert_id,
                            "alert_name": n.alert_name,
                            "role": n.role.value,
                            "confidence": n.confidence,
                        }
                        for n in correlation_result.correlation_chain
                    ],
                    "diagnostic_path": correlation_result.diagnostic_path,
                    "root_cause": correlation_result.root_cause,
                    "confidence": correlation_result.confidence,
                }

                # 同时更新顶层context字段以保持兼容性
                context["correlation_chain"] = context["alert_info"]["correlation_chain"]
                context["diagnostic_path"] = correlation_result.diagnostic_path
                context["root_cause"] = correlation_result.root_cause
                context["correlation_result"] = correlation_result

            except Exception as e:
                # 关联分析失败不影响主流程
                context["correlation_error"] = str(e)

        # 调用基础处理
        result = await self.process(f"诊断告警 {alert_id}", context)

        # 如果有关联分析结果,附加到结果中
        if correlation_result:
            result.metadata["correlation_summary"] = correlation_result.summary
            result.metadata["alert_chain_length"] = len(correlation_result.correlation_chain)

        return result

    async def diagnose_instance(self, instance_id: str, context: dict) -> AgentResponse:
        """诊断指定实例"""
        context["instance_id"] = instance_id
        return await self.process(f"诊断实例 {instance_id}", context)

    async def diagnose_alert_chain(
        self,
        alert_ids: list[str],
        context: dict,
        mock_client=None,
    ) -> AgentResponse:
        """
        诊断告警链(多个告警联合诊断)

        Args:
            alert_ids: 告警ID列表
            context: 上下文
            mock_client: Mock客户端

        Returns:
            AgentResponse: 诊断结果
        """
        if not alert_ids:
            return AgentResponse(
                success=False,
                content="没有提供告警ID",
                metadata={"agent": self.name},
            )

        # 选择第一个作为主告警
        primary_alert_id = alert_ids[0]

        # 获取所有告警
        all_alerts = []
        if mock_client:
            try:
                all_alerts = await mock_client.get_alerts(status="active")
            except Exception:
                pass

        # 查找包含指定告警的列表
        alert_map = {a["alert_id"]: a for a in all_alerts}
        target_alerts = [alert_map.get(aid) for aid in alert_ids if aid in alert_map]
        target_alerts = [a for a in target_alerts if a]  # 过滤None

        if len(target_alerts) < len(alert_ids):
            missing = set(alert_ids) - {a["alert_id"] for a in target_alerts}
            context["warning"] = f"部分告警未找到: {missing}"

        # 执行关联分析
        correlation_result = None
        if target_alerts:
            correlator = self._get_correlator()
            correlation_result = await correlator.correlate_alerts(
                primary_alert_id=primary_alert_id,
                all_alerts=target_alerts,
                mock_client=mock_client,
            )

        # 更新context中的诊断路径信息
        if correlation_result:
            context["diagnostic_path"] = correlation_result.diagnostic_path
            context["alert_info"] = {
                "primary_alert_id": primary_alert_id,
                "diagnostic_path": correlation_result.diagnostic_path,
                "root_cause": correlation_result.root_cause,
                "confidence": correlation_result.confidence,
                "chain_length": len(correlation_result.correlation_chain),
            }

        # 构造诊断Prompt
        chain_info = ""
        if correlation_result:
            chain_info = f"""
=== 告警关联分析 ===
关联告警数: {len(correlation_result.correlation_chain)}
诊断路径: {' -> '.join(correlation_result.diagnostic_path)}
根因: {correlation_result.root_cause}
置信度: {correlation_result.confidence}
摘要: {correlation_result.summary}

关联详情:
"""
            for node in correlation_result.correlation_chain:
                chain_info += f"  - [{node.alert_id}] {node.alert_name} ({node.role.value}, 置信度:{node.confidence})\n"

        prompt = f"""请分析以下告警链:

主告警: {primary_alert_id}
关联告警: {', '.join(alert_ids)}

{chain_info}

请进行联合诊断,给出:
1. 根因分析(最可能的根本原因)
2. 告警链解释(A导致B,B导致C)
3. 处置建议
"""

        # LLM分析
        result_content = await self.think(prompt)

        return AgentResponse(
            success=True,
            content=result_content,
            metadata={
                "agent": self.name,
                "primary_alert_id": primary_alert_id,
                "alert_count": len(alert_ids),
                "correlation": {
                    "root_cause": correlation_result.root_cause if correlation_result else None,
                    "confidence": correlation_result.confidence if correlation_result else None,
                    "chain_length": len(correlation_result.correlation_chain) if correlation_result else 0,
                } if correlation_result else None,
            },
        )


class DiagnosticResultFormatter:
    """
    诊断结果格式化器
    将诊断结果格式化为友好的输出
    """

    @staticmethod
    def format_correlation_result(result: CorrelationResult) -> str:
        """格式化关联分析结果"""
        lines = [
            "=" * 60,
            "告警关联推理结果",
            "=" * 60,
            f"主告警: {result.primary_alert_id}",
            f"诊断路径: {' → '.join(result.diagnostic_path)}",
            f"根因: {result.root_cause}",
            f"置信度: {result.confidence:.0%}",
            "",
            "关联链详情:",
        ]

        for node in result.correlation_chain:
            role_emoji = {
                AlertRole.ROOT_CAUSE: "🔴",
                AlertRole.SYMPTOM: "🔵",
                AlertRole.CONTRIBUTING: "🟡",
                AlertRole.UNKNOWN: "⚪",
            }.get(node.role, "⚪")

            lines.append(
                f"  {role_emoji} [{node.alert_id}] {node.alert_name}"
            )
            lines.append(f"      类型: {node.alert_type}, 严重度: {node.severity}")
            lines.append(f"      实例: {node.instance_name} ({node.instance_id})")
            lines.append(f"      置信度: {node.confidence:.0%}")
            if node.related_alerts:
                lines.append(f"      关联: {', '.join(node.related_alerts)}")
            lines.append("")

        if result.links:
            lines.append("关联关系:")
            for link in result.links:
                lines.append(
                    f"  {link.from_alert} --[{link.link_type}:{link.confidence:.0%}]--> {link.to_alert}"
                )
                lines.append(f"    原因: {link.reason}")

        lines.append("")
        lines.append(f"摘要: {result.summary}")
        lines.append("=" * 60)

        return "\n".join(lines)

    @staticmethod
    def format_diagnostic_message(result: CorrelationResult, llm_analysis: str) -> str:
        """格式化完整的诊断消息"""
        correlation_section = DiagnosticResultFormatter.format_correlation_result(result)

        return f"""{correlation_section}

=== LLM分析结论 ===
{llm_analysis}
"""


# ==================== 便捷函数 ====================

async def diagnose_with_correlation(
    alert_id: str,
    mock_client,
    instance_id: str = None,
) -> tuple[CorrelationResult, str]:
    """
    带关联推理的诊断(便捷函数)

    Args:
        alert_id: 告警ID
        mock_client: Mock Javis客户端
        instance_id: 实例ID(可选)

    Returns:
        tuple: (关联分析结果, LLM分析内容)
    """
    # 获取关联分析结果
    correlator = get_mock_alert_correlator()

    all_alerts = await mock_client.get_alerts(
        instance_id=instance_id,
        status="active",
    )

    correlation_result = await correlator.correlate_alerts(
        primary_alert_id=alert_id,
        all_alerts=all_alerts,
        mock_client=mock_client,
    )

    # 格式化关联结果
    correlation_text = DiagnosticResultFormatter.format_correlation_result(correlation_result)

    # 后续可调用LLM进行进一步分析
    return correlation_result, correlation_text
