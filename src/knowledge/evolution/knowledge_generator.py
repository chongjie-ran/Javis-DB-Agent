"""Knowledge Generator - LLM-powered knowledge generation from coverage gaps

Generates alert rules, SOPs, and cases from identified coverage gaps
using the LLM (Ollama).
"""
import json
import structlog
import uuid
from typing import Dict, Any, List, Optional

logger = structlog.get_logger()

# System prompts for different knowledge types
ALERT_RULE_GENERATION_PROMPT = """你是一个数据库运维专家。根据以下覆盖度缺口信息，生成一个告警规则。

覆盖度缺口:
- 实体类型: {entity_type}
- 资源类型: {resource_type}
- 观测点: {observation_point}
- 描述: {description}

请生成一个JSON格式的告警规则，包含以下字段:
- name: 告警名称（中文，简短描述性）
- condition: 告警条件（使用可执行的表达式，如 cpu_utilization > 80）
- severity: 严重程度（critical/warning/info）
- recommendation: 处置建议（简短，1-2句话）

只返回JSON，不要有其他文字。"""

SOP_GENERATION_PROMPT = """你是一个数据库运维专家。根据以下告警规则，生成一个标准操作程序(SOP)。

告警规则信息:
- 名称: {alert_name}
- 条件: {condition}
- 严重程度: {severity}
- 处置建议: {recommendation}

请生成一个JSON格式的SOP，包含以下字段:
- title: SOP标题（中文，简短）
- steps: 处理步骤列表，每个步骤包含:
  - step: 步骤序号（从1开始）
  - action: 具体操作描述
  - command_hint: 可能的命令提示（可选）

只返回JSON，不要有其他文字。"""

CASE_GENERATION_PROMPT = """你是一个数据库运维专家。基于以下场景信息，生成一个故障案例。

场景信息:
- 实体类型: {entity_type}
- 资源类型: {resource_type}
- 症状: {symptoms}
- 根因: {root_cause}
- 解决方案: {solution}

请生成一个JSON格式的案例，包含以下字段:
- title: 案例标题（中文，描述性）
- symptoms: 症状描述（JSON对象）
- root_cause: 根因分析
- solution: 解决方案
- outcome: 处理结果

只返回JSON，不要有其他文字。"""


class KnowledgeGenerator:
    """LLM-powered knowledge generator

    Generates alert rules, SOPs, and cases from coverage gaps
    using the Ollama LLM client.
    """

    def __init__(self, llm_client: Any):
        """
        Initialize KnowledgeGenerator

        Args:
            llm_client: OllamaClient or compatible LLM client
        """
        self._llm = llm_client

    async def generate_alert_rule(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an alert rule from a coverage gap

        Args:
            gap: Coverage gap dict with entity_type, resource_type,
                observation_point, description

        Returns:
            Alert rule dict with id, name, condition, severity, etc.
        """
        entity_type = gap.get("entity_type", "")
        resource_type = gap.get("resource_type", "")
        observation_point = gap.get("observation_point", "")
        description = gap.get("description", "")

        # Build metric name from observation point
        metric_name = observation_point.split(".")[-1] if observation_point else resource_type.split(".")[-1]

        prompt = ALERT_RULE_GENERATION_PROMPT.format(
            entity_type=entity_type,
            resource_type=resource_type,
            observation_point=observation_point,
            description=description,
        )

        try:
            response = await self._llm.complete(prompt)
            # Try to parse JSON from response
            rule_data = self._parse_json_response(response)
            if rule_data:
                rule_data["id"] = f"evolve-{uuid.uuid4().hex[:8]}"
                rule_data["entity_type"] = entity_type
                rule_data["resource_type"] = resource_type
                rule_data["observation_point"] = observation_point
                rule_data["enabled"] = 1
                logger.info("alert_rule.generated", gap=gap, rule_id=rule_data["id"])
                return rule_data
        except Exception as e:
            logger.warning("alert_rule.generation_failed", gap=gap, error=str(e))

        # Fallback: generate a basic rule without LLM
        return self._fallback_alert_rule(gap, metric_name)

    async def generate_sop(self, alert_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an SOP for an alert rule

        Args:
            alert_rule: Alert rule dict

        Returns:
            SOP dict with id, title, alert_rule_id, steps
        """
        alert_name = alert_rule.get("name", "")
        condition = alert_rule.get("condition", "")
        severity = alert_rule.get("severity", "warning")
        recommendation = alert_rule.get("recommendation", "")

        prompt = SOP_GENERATION_PROMPT.format(
            alert_name=alert_name,
            condition=condition,
            severity=severity,
            recommendation=recommendation,
        )

        try:
            response = await self._llm.complete(prompt)
            sop_data = self._parse_json_response(response)
            if sop_data:
                sop_data["id"] = f"evolve-sop-{uuid.uuid4().hex[:8]}"
                sop_data["alert_rule_id"] = alert_rule.get("id")
                sop_data["enabled"] = 1
                logger.info("sop.generated", alert_rule_id=alert_rule.get("id"), sop_id=sop_data["id"])
                return sop_data
        except Exception as e:
            logger.warning("sop.generation_failed", alert_rule_id=alert_rule.get("id"), error=str(e))

        # Fallback SOP
        return self._fallback_sop(alert_rule)

    async def generate_case(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a case from a scenario

        Args:
            scenario: Scenario dict with entity_type, resource_type,
                symptoms, root_cause, solution

        Returns:
            Case dict with id, title, symptoms, root_cause, solution, outcome
        """
        entity_type = scenario.get("entity_type", "")
        resource_type = scenario.get("resource_type", "")
        symptoms = scenario.get("symptoms", {})
        root_cause = scenario.get("root_cause", "")
        solution = scenario.get("solution", "")

        prompt = CASE_GENERATION_PROMPT.format(
            entity_type=entity_type,
            resource_type=resource_type,
            symptoms=json.dumps(symptoms, ensure_ascii=False),
            root_cause=root_cause,
            solution=solution,
        )

        try:
            response = await self._llm.complete(prompt)
            case_data = self._parse_json_response(response)
            if case_data:
                case_data["id"] = f"evolve-case-{uuid.uuid4().hex[:8]}"
                case_data["alert_rule_id"] = scenario.get("alert_rule_id")
                logger.info("case.generated", scenario=scenario, case_id=case_data["id"])
                return case_data
        except Exception as e:
            logger.warning("case.generation_failed", scenario=scenario, error=str(e))

        # Fallback case
        return self._fallback_case(scenario)

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response

        Handles cases where LLM wraps JSON in markdown code blocks
        or includes extra text.
        """
        text = response.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        for marker in ["```json", "```"]:
            if marker in text:
                try:
                    # Get content between marker and closing marker
                    parts = text.split(marker)
                    if len(parts) >= 3:
                        content = parts[1].strip()
                    else:
                        content = parts[1].strip()
                    # Remove closing ``` if present
                    if content.endswith("```"):
                        content = content[:-3].strip()
                    return json.loads(content)
                except (json.JSONDecodeError, IndexError):
                    continue

        # Try finding JSON object pattern
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

        return None

    def _fallback_alert_rule(self, gap: Dict[str, Any], metric_name: str) -> Dict[str, Any]:
        """Generate a fallback alert rule without LLM"""
        entity_type = gap.get("entity_type", "")
        resource_type = gap.get("resource_type", "")

        # Build name from resource/observation point
        parts = (resource_type or entity_type).split(".")
        name = parts[-1] if parts else "Unknown"
        name = f"{name}监控告警"

        # Infer severity from metric type
        severity = "warning"
        if "error" in metric_name or "fault" in metric_name:
            severity = "critical"
        elif "latency" in metric_name or "utilization" in metric_name:
            severity = "warning"
        else:
            severity = "info"

        return {
            "id": f"evolve-{uuid.uuid4().hex[:8]}",
            "name": name,
            "condition": f"{metric_name} > threshold",
            "severity": severity,
            "entity_type": entity_type,
            "resource_type": resource_type,
            "observation_point": gap.get("observation_point"),
            "recommendation": f"检查{resource_type}的{metric_name}指标",
            "enabled": 1,
            "metadata": {"generated_by": "evolution_fallback", "gap_id": f"gap-{uuid.uuid4().hex[:8]}"}
        }

    def _fallback_sop(self, alert_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a fallback SOP without LLM"""
        name = alert_rule.get("name", "告警处理")
        resource_type = alert_rule.get("resource_type", "")

        return {
            "id": f"evolve-sop-{uuid.uuid4().hex[:8]}",
            "title": f"{name}标准处理流程",
            "alert_rule_id": alert_rule.get("id"),
            "steps": [
                {"step": 1, "action": f"登录{resource_type}所在主机", "command_hint": "ssh user@host"},
                {"step": 2, "action": "查看告警相关指标", "command_hint": "查看监控面板"},
                {"step": 3, "action": "分析告警原因", "command_hint": "检查日志和指标"},
                {"step": 4, "action": "执行处置操作", "command_hint": "根据分析结果"},
                {"step": 5, "action": "验证处置效果", "command_hint": "确认告警消除"},
            ],
            "enabled": 1,
            "metadata": {"generated_by": "evolution_fallback"}
        }

    def _fallback_case(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a fallback case without LLM"""
        entity_type = scenario.get("entity_type", "")
        resource_type = scenario.get("resource_type", "")
        root_cause = scenario.get("root_cause", "待分析")
        solution = scenario.get("solution", "待确认")

        return {
            "id": f"evolve-case-{uuid.uuid4().hex[:8]}",
            "title": f"{resource_type}故障案例",
            "alert_rule_id": scenario.get("alert_rule_id"),
            "symptoms": scenario.get("symptoms", {}),
            "root_cause": root_cause,
            "solution": solution,
            "outcome": "待验证",
            "metadata": {"generated_by": "evolution_fallback"}
        }
