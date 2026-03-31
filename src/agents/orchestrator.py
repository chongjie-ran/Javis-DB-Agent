"""统一编排Agent - 任务分解与多Agent协同"""
import asyncio
import json
import logging
from typing import Optional, AsyncIterator
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.base import BaseAgent, AgentResponse
from src.agents.diagnostic import DiagnosticAgent
from src.agents.risk import RiskAgent
from src.agents.sql_analyzer import SQLAnalyzerAgent
from src.agents.inspector import InspectorAgent
from src.agents.reporter import ReporterAgent
from src.agents.session_analyzer_agent import SessionAnalyzerAgent
from src.agents.capacity_agent import CapacityAgent
from src.agents.alert_agent import AlertAgent
from src.agents.backup_agent import BackupAgent
from src.agents.performance_agent import PerformanceAgent

logger = logging.getLogger(__name__)


class Intent(Enum):
    """用户意图"""
    DIAGNOSE = "diagnose"           # 告警诊断
    SQL_ANALYZE = "sql_analyze"    # SQL分析
    ANALYZE_SESSION = "analyze_session"  # 会话分析
    DETECT_DEADLOCK = "detect_deadlock"  # 死锁检测
    SUGGEST_INDEX = "suggest_index"  # 索引建议
    INSPECT = "inspect"            # 健康巡检
    REPORT = "report"              # 报告生成
    RISK_ASSESS = "risk_assess"    # 风险评估
    ANALYZE_CAPACITY = "analyze_capacity"  # 容量分析
    PREDICT_GROWTH = "predict_growth"      # 增长预测
    CAPACITY_REPORT = "capacity_report"    # 容量报告
    ANALYZE_ALERT = "analyze_alert"        # 告警分析 (Round 15)
    DEDUPLICATE_ALERTS = "deduplicate_alerts"  # 告警去重 (Round 15)
    ROOT_CAUSE = "root_cause"            # 根因分析 (Round 15)
    PREDICTIVE_ALERT = "predictive_alert"  # 预测性告警 (Round 15)
    ANALYZE_BACKUP = "analyze_backup"      # 备份分析 (V1.4)
    ANALYZE_PERFORMANCE = "analyze_performance"  # 性能分析 (V1.4)
    GENERAL = "general"            # 通用问答


# ------------------------------------------------------------
# 意图识别示例库 - v1.3 语义路由增强
# 每个意图包含多个同义表达，用于语义相似度匹配
# ------------------------------------------------------------
INTENT_EXAMPLES: dict[Intent, list[str]] = {
    Intent.DIAGNOSE: [
        "告警诊断", "诊断告警", "帮我看看这个告警", "告警是什么原因",
        "这个警报怎么处理", "告警根因分析", "告警排查", "告警问题定位",
    ],
    Intent.SQL_ANALYZE: [
        "分析SQL", "SQL性能分析", "慢SQL查询", "这个SQL有没有问题",
        "SQL改写", "优化SQL", "执行计划分析", "查看SQL性能",
    ],
    Intent.ANALYZE_SESSION: [
        "会话分析", "连接池状态", "当前会话", "活跃会话", "查看会话",
        "会话详情", "连接情况", "会话列表",
    ],
    Intent.DETECT_DEADLOCK: [
        "死锁检测", "检查死锁", "有没有死锁", "查看死锁情况",
        "死锁排查", "检测死锁",
    ],
    Intent.SUGGEST_INDEX: [
        "索引建议", "创建索引", "加索引", "建议加什么索引",
        "索引优化", "索引推荐",
    ],
    Intent.INSPECT: [
        "健康巡检", "巡检", "检查状态", "MySQL instances", "有哪些实例",
        "实例列表", "查看实例", "实例健康检查", "数据库实例", "实例状态",
        "健康检查", "巡检报告", "系统状态", "show me all databases",
        "所有mysql数据库", "mysql数据库列表", "列出所有数据库",
    ],
    Intent.REPORT: [
        "生成报告", "报告", "报告生成", "生成巡检报告", "分析报告",
        "运维报告", "汇总报告",
    ],
    Intent.RISK_ASSESS: [
        "风险评估", "评估风险", "风险分析", "有没有风险", "风险等级",
        "风险点", "安全隐患",
    ],
    Intent.ANALYZE_CAPACITY: [
        "容量分析", "存储分析", "磁盘空间", "容量使用情况", "存储容量",
        "容量监控", "磁盘使用率",
    ],
    Intent.PREDICT_GROWTH: [
        "增长预测", "容量预测", "未来增长", "趋势预测", "存储增长趋势",
        "容量增长预测",
    ],
    Intent.CAPACITY_REPORT: [
        "容量报告", "存储报告", "容量报表", "容量统计",
        "容量使用报告", "存储空间报告",
    ],
    Intent.ANALYZE_ALERT: [
        "告警分析", "告警详情", "查看告警", "告警内容", "告警上下文",
        "这条告警什么意思", "告警解释",
    ],
    Intent.DEDUPLICATE_ALERTS: [
        "告警去重", "合并告警", "告警压缩", "去除重复告警",
        "重复告警太多", "告警太多怎么办",
    ],
    Intent.ROOT_CAUSE: [
        "根因分析", "找到根本原因", "根本原因是什么", "为什么会发生",
        "告警根因", "问题根因",
    ],
    Intent.PREDICTIVE_ALERT: [
        "预测性告警", "提前预警", "趋势告警", "预测告警",
        "未来可能出现的告警", "预警",
    ],
    Intent.ANALYZE_BACKUP: [
        "备份状态怎么样", "检查一下今天的备份", "上次备份成功了吗",
        "最近有没有备份失败的", "备份策略需要调整吗", "恢复演练一下",
        "备份列表", "备份历史", "查看备份", "备份详情", "备份恢复",
        "备份告警", "备份异常", "备份失败", "RTO多少", "RPO多少",
    ],
    Intent.ANALYZE_PERFORMANCE: [
        "帮我分析一下性能", "哪些SQL最慢", "执行计划看看", "参数需要调优吗",
        "TopSQL是哪些", "慢SQL分析", "性能报告", "性能瓶颈", "CPU使用率高",
        "内存占用分析", "连接数爆了", "QPS多少", "TPS多少", "吞吐量怎么样",
        "性能趋势", "负载情况",
    ],
    Intent.GENERAL: [
        "你好", "帮我", "问一下", "请问", "怎么样", "是什么",
    ],
}


# ------------------------------------------------------------
# v1.3 Round 2: 意图样本自演化收集器
# ------------------------------------------------------------
@dataclass
class IntentExampleFeedback:
    """用户反馈记录"""
    user_input: str
    recognized_intent: Intent
    user_accepted: bool  # 用户是否接受了识别结果
    corrected_intent: Optional[Intent] = None  # 用户纠正后的意图
    timestamp: str = ""


class IntentExampleCollector:
    """
    意图样本自演化收集器
    
    功能：
    1. 收集用户反馈，自动扩展 INTENT_EXAMPLES
    2. 记录用户实际问法，自动归类到对应 Intent
    3. 持久化存储，与知识库自演化闭环对接
    """
    
    # 样本收集存储路径
    STORAGE_PATH = Path(__file__).parent.parent.parent / "data" / "intent_examples.json"
    
    def __init__(self):
        self._feedback_buffer: list[IntentExampleFeedback] = []
        self._pending_additions: dict[Intent, list[str]] = {i: [] for i in Intent}
        self._load_stored_examples()
    
    def _load_stored_examples(self):
        """从持久化存储加载已收集的样本"""
        if self.STORAGE_PATH.exists():
            try:
                with open(self.STORAGE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 合并存储的样本到 INTENT_EXAMPLES
                    for intent_str, examples in data.items():
                        try:
                            intent = Intent(intent_str)
                            for ex in examples:
                                if ex not in INTENT_EXAMPLES[intent]:
                                    INTENT_EXAMPLES[intent].append(ex)
                        except ValueError:
                            pass
            except Exception as e:
                logger.warning(f"加载意图样本失败: {e}")
    
    def record_feedback(
        self,
        user_input: str,
        recognized_intent: Intent,
        user_accepted: bool,
        corrected_intent: Optional[Intent] = None
    ):
        """
        记录用户反馈
        
        Args:
            user_input: 用户原始输入
            recognized_intent: 系统识别的意图
            user_accepted: 用户是否接受
            corrected_intent: 用户纠正后的意图（如果不接受）
        """
        feedback = IntentExampleFeedback(
            user_input=user_input,
            recognized_intent=recognized_intent,
            user_accepted=user_accepted,
            corrected_intent=corrected_intent if not user_accepted else None
        )
        self._feedback_buffer.append(feedback)
        
        # 如果用户纠正了意图，将新样本加入待添加列表
        if not user_accepted and corrected_intent:
            if user_input.strip() and len(user_input.strip()) >= 2:
                self._pending_additions[corrected_intent].append(user_input.strip())
    
    async def auto_learn_from_feedback(self) -> dict[Intent, list[str]]:
        """
        从反馈中自动学习，扩展意图样本
        
        Returns:
            新增的样本字典 {Intent: [新样本列表]}
        """
        new_additions = {}
        
        for intent, examples in self._pending_additions.items():
            if examples:
                # 去重
                unique_examples = list(set(examples))
                # 过滤掉太短或太相似的
                filtered = [e for e in unique_examples if len(e) >= 2]
                if filtered:
                    new_additions[intent] = filtered
                    # 添加到 INTENT_EXAMPLES
                    for ex in filtered:
                        if ex not in INTENT_EXAMPLES[intent]:
                            INTENT_EXAMPLES[intent].append(ex)
        
        # 清空待添加列表
        self._pending_additions = {i: [] for i in Intent}
        
        # 持久化
        if new_additions:
            self._persist_examples()
        
        return new_additions
    
    def _persist_examples(self):
        """持久化意图样本到磁盘"""
        try:
            self.STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            # 读取现有数据
            existing = {}
            if self.STORAGE_PATH.exists():
                with open(self.STORAGE_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            
            # 合并新样本
            for intent, examples in INTENT_EXAMPLES.items():
                intent_key = intent.value
                if intent_key not in existing:
                    existing[intent_key] = []
                # 添加新样本
                for ex in examples:
                    if ex not in existing[intent_key]:
                        existing[intent_key].append(ex)
            
            # 写回
            with open(self.STORAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            
            logger.info(f"意图样本已持久化，共 {len(existing)} 个意图")
        except Exception as e:
            logger.error(f"持久化意图样本失败: {e}")
    
    def get_stats(self) -> dict:
        """获取样本收集统计"""
        return {
            "total_intents": len(INTENT_EXAMPLES),
            "intent_counts": {i.value: len(examples) for i, examples in INTENT_EXAMPLES.items()},
            "pending_learning": {i.value: len(ex) for i, ex in self._pending_additions.items()},
            "feedback_buffer_size": len(self._feedback_buffer),
        }


# 全局实例
_intent_collector: Optional[IntentExampleCollector] = None


def get_intent_collector() -> IntentExampleCollector:
    """获取意图收集器单例"""
    global _intent_collector
    if _intent_collector is None:
        _intent_collector = IntentExampleCollector()
    return _intent_collector


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
3. sql_analyzer: SQL分析Agent - SQL性能分析、索引建议、SQL改写
4. inspector: 巡检Agent - 健康检查
5. reporter: 报告Agent - 报告生成
6. session_analyzer: 会话分析Agent - 会话状态、连接池、死锁检测
7. capacity: 容量管理Agent - 存储分析、增长预测、容量报告、阈值告警
8. alert: 告警专家Agent - 告警分析、去重压缩、根因分析、预测性告警 (Round 15新增)

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
            "session_analyzer": SessionAnalyzerAgent(),
            "capacity": CapacityAgent(),
            "alert": AlertAgent(),
            "backup": BackupAgent(),
            "performance": PerformanceAgent(),
        }
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agent_registry.get(name)

    # ------------------------------------------------------------
    # v1.3 Round 2 语义路由增强
    # ------------------------------------------------------------
    # 相似度阈值：超过此值则使用语义匹配结果
    SEMANTIC_SIMILARITY_THRESHOLD = 0.75
    # LLM fallback 阈值：当 embedding 不可用时，使用 LLM 语义匹配
    LLM_FALLBACK_THRESHOLD = 0.6

    async def _semantic_intent_recognize(self, goal: str) -> tuple[Intent, float]:
        """
        语义意图识别 - v1.3 Round 2 增强
        
        使用 EmbeddingService 计算用户输入与各意图示例的余弦相似度，
        选择相似度最高的意图。如果 Ollama embedding 不可用，降级到纯 LLM 语义匹配。
        
        Fallback 策略：
        1. 尝试 EmbeddingService 语义向量匹配
        2. 如果 Ollama 不可用或模型缺失，降级到 LLM 语义匹配
        3. LLM 匹配也失败时，返回 GENERAL
        
        Args:
            goal: 用户输入
            
        Returns:
            (匹配到的Intent, 相似度分数)
        """
        # Step 1: 尝试 EmbeddingService 语义向量匹配
        try:
            from src.knowledge.vector.embedding_service import EmbeddingService
            
            embed_service = EmbeddingService()
            best_intent: Optional[Intent] = None
            best_score = 0.0

            for intent, examples in INTENT_EXAMPLES.items():
                for example in examples:
                    try:
                        score = await embed_service.compute_similarity(goal, example)
                        if score > best_score:
                            best_score = score
                            best_intent = intent
                    except Exception:
                        # 单个相似度计算失败，跳过继续
                        continue

            await embed_service.close()

            if best_intent and best_score >= self.SEMANTIC_SIMILARITY_THRESHOLD:
                return best_intent, best_score
            
            # 语义匹配分数不足，尝试 LLM fallback
            if best_score > 0:
                llm_intent, llm_score = await self._llm_semantic_match(goal, best_intent, best_score)
                if llm_score >= self.LLM_FALLBACK_THRESHOLD:
                    return llm_intent, llm_score
            
            # 降级到 GENERAL
            return Intent.GENERAL, best_score
            
        except ImportError:
            # EmbeddingService 不可用，降级到 LLM 语义匹配
            logger.warning("EmbeddingService 不可用，降级到 LLM 语义匹配")
            return await self._llm_semantic_match(goal, Intent.GENERAL, 0.0)
        except Exception as e:
            # 其他错误，降级到 LLM 语义匹配
            logger.warning(f"Embedding 语义匹配失败: {e}，降级到 LLM 语义匹配")
            return await self._llm_semantic_match(goal, Intent.GENERAL, 0.0)
    
    async def _llm_semantic_match(
        self, 
        goal: str, 
        hint_intent: Optional[Intent] = None,
        hint_score: float = 0.0
    ) -> tuple[Intent, float]:
        """
        LLM 语义匹配 - Ollama embedding 不可用时的降级方案
        
        使用 LLM 直接判断用户意图，不依赖 embedding 模型。
        
        Args:
            goal: 用户输入
            hint_intent: embedding 匹配给出的候选意图
            hint_score: embedding 匹配的分数
            
        Returns:
            (匹配到的Intent, 置信度分数)
        """
        # 构建提示，包含各意图的示例（v1.3 Round 3 增强）
        intent_examples_text = ""
        intent_descriptions = {
            Intent.DIAGNOSE: "告警诊断、根因分析、故障排查",
            Intent.SQL_ANALYZE: "SQL性能分析、慢查询优化、执行计划分析",
            Intent.ANALYZE_SESSION: "会话状态、连接池、死锁检测",
            Intent.DETECT_DEADLOCK: "死锁检测",
            Intent.SUGGEST_INDEX: "索引建议",
            Intent.INSPECT: "健康巡检、查看实例列表、数据库列表、健康检查",
            Intent.REPORT: "报告生成",
            Intent.RISK_ASSESS: "风险评估",
            Intent.ANALYZE_CAPACITY: "容量分析、存储分析",
            Intent.PREDICT_GROWTH: "增长预测、容量预测",
            Intent.CAPACITY_REPORT: "容量报告",
            Intent.ANALYZE_ALERT: "告警分析、告警详情",
            Intent.DEDUPLICATE_ALERTS: "告警去重、合并告警",
            Intent.ROOT_CAUSE: "根因分析",
            Intent.PREDICTIVE_ALERT: "预测性告警、提前预警",
            Intent.ANALYZE_BACKUP: "备份分析、备份状态、恢复演练",
            Intent.ANALYZE_PERFORMANCE: "性能分析、TopSQL、执行计划",
            Intent.GENERAL: "通用问答",
        }
        
        for intent, examples in INTENT_EXAMPLES.items():
            examples_str = ", ".join([f'"{e}"' for e in examples[:5]])
            desc = intent_descriptions.get(intent, "")
            intent_examples_text += f"- {intent.value}: {desc}。示例：{examples_str}\n"
        
        hint_section = ""
        if hint_intent and hint_score > 0:
            hint_section = f"\n\n参考信息：语义向量匹配初步识别为「{hint_intent.value}」（分数 {hint_score:.2f}），请综合判断。"
        
        # v1.3 Round 3 增强：更精确的 Prompt
        prompt = f"""你是专业的数据库运维意图识别助手。

任务：根据用户输入，从以下意图列表中选择最匹配的一个。

用户输入：{goal}{hint_section}

可用意图：
{intent_examples_text}

识别规则：
1. "MySQL instances"、"show me all databases"、"列出所有数据库"、"有哪些实例" → inspect
2. "告警诊断"、"帮我看看这个告警"、"告警根因分析" → diagnose
3. "SQL分析"、"慢SQL查询"、"执行计划分析" → sql_analyze
4. "会话分析"、"连接池状态"、"当前会话" → analyze_session
5. "容量分析"、"存储空间"、"磁盘使用率" → analyze_capacity
6. "告警分析"、"这条告警什么意思"、"告警详情" → analyze_alert
7. "备份状态怎么样"、"检查备份"、"恢复演练" → analyze_backup
8. "哪些SQL最慢"、"TopSQL"、"执行计划看看"、"性能分析" → analyze_performance

请直接输出意图名称（只输出英文，不要输出其他内容）。如果都不匹配，输出 "general"："""
        
        try:
            result = await self.think(prompt)
            result = result.strip().lower()
            
            # 解析 LLM 返回结果
            for intent in Intent:
                if intent.value in result:
                    # LLM 匹配有较高置信度
                    return intent, 0.85
            
            return Intent.GENERAL, 0.5
        except Exception as e:
            logger.error(f"LLM 语义匹配失败: {e}")
            return Intent.GENERAL, 0.0

    def _build_conversation_history(self, context: dict, max_turns: int = 3) -> str:
        """
        从context中提取对话历史，v1.3 上下文融合
        
        Args:
            context: 上下文字典
            max_turns: 最多保留的对话轮数
            
        Returns:
            格式化后的对话历史字符串
        """
        history = context.get("conversation_history", [])
        if not history:
            return ""
        
        # 只保留最近 max_turns 轮
        recent = history[-max_turns:] if len(history) > max_turns else history
        
        parts = []
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if content:
                parts.append(f"{'用户' if role == 'user' else '助手'}: {content}")
        
        return "\n".join(parts)
    
    def _build_system_prompt(self) -> str:
        return self.system_prompt
    
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """处理用户目标"""
        # 1. 识别意图（带上下文，用于语义路由和上下文融合）
        intent = await self._recognize_intent(goal, context)
        
        # 2. 选择Agent
        selected_agents = self._select_agents(intent, goal)
        
        # 3. 构建执行计划
        plan = self._build_plan(selected_agents, goal, context)
        
        # 4. 执行计划
        results = await self._execute_plan(plan, context)
        
        # 5. 汇总结果
        aggregated = self._aggregate_results(results, intent)
        
        # 6. Fallback: 当没有Agent被选中时，直接用LLM回答（不再返回"未找到相关信息"）
        if not selected_agents or (not results and intent == Intent.GENERAL):
            llm_prompt = f"""你是一个专业的数据库运维智能助手。请回答用户的问题。

用户问题：{goal}

请用专业的数据库运维知识回答，如果涉及具体实例请说明需要连接数据库才能获取实时数据。
"""
            try:
                llm_response = await self.think(llm_prompt)
                if llm_response and llm_response.strip():
                    aggregated = {"content": llm_response}
            except Exception:
                # LLM fallback 也失败，保持原有 aggregated
                pass
        
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
    
    async def _recognize_intent(self, goal: str, context: Optional[dict] = None) -> Intent:
        """
        识别用户意图 - v1.3 Round 2 语义路由增强
        
        策略：
        1. 先尝试语义向量相似度匹配（快且泛化能力强）
        2. 向量匹配失败/不足时，使用 LLM 语义匹配 fallback
        3. LLM 结果仍然无法匹配时，返回 GENERAL
        
        样本自演化：
        - 记录用户反馈到 IntentExampleCollector
        - 自动学习用户实际问法
        """
        # Step 1: 语义向量匹配（v1.3新增）
        semantic_intent, semantic_score = await self._semantic_intent_recognize(goal)
        if semantic_score >= self.SEMANTIC_SIMILARITY_THRESHOLD:
            # 语义匹配成功，记录反馈供自演化使用
            self._record_intent_feedback(goal, semantic_intent, semantic_score)
            return semantic_intent
        
        # Step 2: 语义匹配分数不足，降级到 LLM 意图识别
        # 融入对话历史上下文（v1.3新增）
        history_text = ""
        if context:
            history_text = self._build_conversation_history(context)
        
        history_section = f"\n\n近期对话历史（供参考）：\n{history_text}\n" if history_text else ""
        
        prompt = f"""请识别以下用户目标的意图类型：

目标：{goal}{history_section}

可选意图：
- diagnose: 告警诊断、根因分析
- sql_analyze: SQL分析、慢SQL分析
- analyze_session: 会话分析、连接池分析
- detect_deadlock: 死锁检测
- suggest_index: 索引建议
- inspect: 健康巡检、状态检查（包括查看实例列表、数据库列表等）
- report: 报告生成
- risk_assess: 风险评估
- analyze_alert: 告警分析、告警详情分析 (Round 15)
- deduplicate_alerts: 告警去重、告警压缩 (Round 15)
- root_cause: 根因分析、定位根本原因 (Round 15)
- predictive_alert: 预测性告警、趋势预测预警 (Round 15)
- analyze_backup: 备份分析、备份状态查询、恢复演练 (V1.4)
- analyze_performance: 性能分析、TopSQL、执行计划 (V1.4)
- general: 通用问答

请只输出意图名称（如：diagnose）。
语义匹配分数 {semantic_score:.2f} 低于阈值 {self.SEMANTIC_SIMILARITY_THRESHOLD}，请结合上下文综合判断。
"""
        result = await self.think(prompt)
        result = result.strip().lower()
        
        for intent in Intent:
            if intent.value in result:
                # LLM 匹配成功，记录反馈
                self._record_intent_feedback(goal, intent, 0.85)
                return intent
        return Intent.GENERAL
    
    def _record_intent_feedback(self, user_input: str, intent: Intent, confidence: float):
        """
        记录意图识别反馈，供样本自演化使用
        
        Args:
            user_input: 用户原始输入
            intent: 识别出的意图
            confidence: 置信度分数
        """
        try:
            collector = get_intent_collector()
            # 这里记录的是系统识别结果，用户接受与否需要后续外部反馈
            collector.record_feedback(
                user_input=user_input,
                recognized_intent=intent,
                user_accepted=True  # 暂时假设用户接受，后续可通过外部反馈修正
            )
        except Exception as e:
            logger.debug(f"记录意图反馈失败: {e}")
    
    def _select_agents(self, intent: Intent, goal: str) -> list[BaseAgent]:
        """
        选择合适的Agent - v1.3 Round 2 语义工具选择增强
        
        根据意图和用户输入语义选择合适的Agent工具。
        工具选择的语义匹配独立于意图识别。
        
        策略：
        1. 基础映射：根据意图类型选择默认Agent
        2. 语义微调：根据用户输入中的关键词语义微调Agent组合
        3. 上下文感知：结合上下文中的额外信息调整选择
        
        Args:
            intent: 识别的用户意图
            goal: 用户原始输入
            
        Returns:
            选中的Agent列表
        """
        # 基础Agent映射
        mapping = {
            Intent.DIAGNOSE: ["diagnostic", "risk"],
            Intent.SQL_ANALYZE: ["sql_analyzer", "risk"],
            Intent.ANALYZE_SESSION: ["session_analyzer"],
            Intent.DETECT_DEADLOCK: ["session_analyzer", "risk"],
            Intent.SUGGEST_INDEX: ["sql_analyzer"],
            Intent.INSPECT: ["inspector"],
            Intent.REPORT: ["reporter"],
            Intent.RISK_ASSESS: ["risk"],
            Intent.ANALYZE_CAPACITY: ["capacity"],
            Intent.PREDICT_GROWTH: ["capacity"],
            Intent.CAPACITY_REPORT: ["capacity"],
            Intent.ANALYZE_ALERT: ["alert"],
            Intent.DEDUPLICATE_ALERTS: ["alert"],
            Intent.ROOT_CAUSE: ["alert", "diagnostic"],
            Intent.PREDICTIVE_ALERT: ["alert"],
            Intent.ANALYZE_BACKUP: ["backup"],
            Intent.ANALYZE_PERFORMANCE: ["performance"],
            Intent.GENERAL: [],
        }
        
        agent_names = mapping.get(intent, ["diagnostic"])
        selected = [self._agent_registry[name] for name in agent_names if name in self._agent_registry]
        
        # 语义工具选择微调
        selected = self._semantic_tool_fine_tune(intent, goal, selected)
        
        return selected
    
    def _semantic_tool_fine_tune(
        self, 
        intent: Intent, 
        goal: str, 
        base_agents: list[BaseAgent]
    ) -> list[BaseAgent]:
        """
        语义工具选择微调 - v1.3 Round 2 新增
        
        根据用户输入中的语义关键词，对Agent组合进行微调。
        这个方法是意图识别之外独立的语义工具选择逻辑。
        
        Args:
            intent: 已识别的意图
            goal: 用户原始输入
            base_agents: 基于意图选择的默认Agent列表
            
        Returns:
            微调后的Agent列表
        """
        goal_lower = goal.lower()
        selected_names = {a.name for a in base_agents}
        
        # 语义关键词 -> 需要添加的Agent
        semantic_additions = {
            # 健康检查 + 风险评估
            "风险": {"add": ["risk"]},
            "安全": {"add": ["risk"]},
            "隐患": {"add": ["risk"]},
            # 会话分析 + 死锁检测
            "连接": {"add": ["session_analyzer"]},
            "阻塞": {"add": ["session_analyzer"]},
            "锁等待": {"add": ["session_analyzer"]},
            # SQL分析 + 索引建议
            "索引": {"add": ["sql_analyzer"]},
            "慢查询": {"add": ["sql_analyzer"]},
            "优化": {"add": ["sql_analyzer"]},
            # 容量分析 + 报告
            "容量": {"add": ["capacity"]},
            "存储": {"add": ["capacity"]},
            "磁盘": {"add": ["capacity"]},
            # 告警分析 + 诊断
            "告警详情": {"add": ["alert"]},
            "告警解释": {"add": ["alert"]},
            "根因": {"add": ["diagnostic"]},
            # V1.4 备份分析
            "备份": {"add": ["backup"]},
            "恢复": {"add": ["backup"]},
            "RTO": {"add": ["backup"]},
            "RPO": {"add": ["backup"]},
            # V1.4 性能分析
            "性能": {"add": ["performance"]},
            "TopSQL": {"add": ["performance"]},
            "慢SQL": {"add": ["performance"]},
            "执行计划": {"add": ["performance"]},
            "调优": {"add": ["performance"]},
        }
        
        for keyword, action in semantic_additions.items():
            if keyword in goal_lower:
                for agent_name in action.get("add", []):
                    if agent_name in self._agent_registry:
                        selected_names.add(agent_name)
        
        # 语义关键词 -> 需要移除的Agent（互斥）
        semantic_removals = {
            "只巡检": ["risk", "diagnostic", "alert"],
            "只要报告": ["risk", "diagnostic", "alert", "session_analyzer", "sql_analyzer"],
            "只看风险": ["inspector", "reporter", "session_analyzer"],
        }
        
        for keyword, agents_to_remove in semantic_removals.items():
            if keyword in goal_lower:
                selected_names -= set(agents_to_remove)
        
        # 根据微调结果返回Agent列表
        final_agents = [
            self._agent_registry[name] 
            for name in selected_names 
            if name in self._agent_registry
        ]
        
        # 保持顺序：诊断 -> 风险 -> 专业Agent
        priority_order = ["diagnostic", "risk", "alert", "capacity", "sql_analyzer", 
                         "session_analyzer", "inspector", "reporter"]
        final_agents.sort(key=lambda a: priority_order.index(a.name) if a.name in priority_order else 99)
        
        return final_agents
    
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

    async def handle_chat_stream(self, user_input: str, context: dict) -> AsyncIterator[dict]:
        """
        流式处理对话，yield 事件字典:
        - {"type": "thinking", "content": "正在分析..."}
        - {"type": "content", "content": "token"}
        - {"type": "done", "agent": "orchestrator", "content": "完整回复"}
        """
        import time
        start = time.time()

        # 1. 识别意图（快速，不流式）
        yield {"type": "thinking", "content": "🤔 正在理解你的问题..."}
        try:
            intent = await self._recognize_intent(user_input, context)
            intent_label = {
                "diagnose": "告警诊断",
                "sql_analyze": "SQL分析",
                "analyze_session": "会话分析",
                "detect_deadlock": "死锁检测",
                "suggest_index": "索引建议",
                "inspect": "健康巡检",
                "report": "报告生成",
                "risk_assess": "风险评估",
                "analyze_capacity": "容量分析",
                "predict_growth": "增长预测",
                "capacity_report": "容量报告",
                "analyze_alert": "告警分析",
                "deduplicate_alerts": "告警去重",
                "root_cause": "根因分析",
                "predictive_alert": "预测性告警",
                "analyze_backup": "备份分析",
                "analyze_performance": "性能分析",
                "general": "通用问答",
            }.get(intent.value, "通用问答")
            yield {"type": "thinking", "content": f"📋 识别为「{intent_label}」任务，准备调用专业Agent..."}
        except Exception as e:
            intent = None
            yield {"type": "thinking", "content": "⚠️ 意图识别跳过，直接开始生成回复..."}

        # 2. 选择Agent
        if intent:
            try:
                selected = self._select_agents(intent, user_input)
                if selected:
                    names = " → ".join([a.name for a in selected])
                    yield {"type": "thinking", "content": f"🔧 调度Agent: {names}"}
            except Exception:
                pass

        # 3. 构建Plan（快速）
        try:
            if intent and hasattr(self, '_select_agents') and intent:
                plan = self._build_plan(selected if 'selected' in dir() else [], user_input, context)
                if plan:
                    yield {"type": "thinking", "content": f"📝 执行计划（共{len(plan)}步）..."}
        except Exception:
            pass

        # 4. 流式生成回复
        yield {"type": "thinking", "content": "✨ 正在生成回复..."}
        full_response = ""

        try:
            async for token in self.think_stream(user_input):
                full_response += token
                yield {"type": "content", "content": token}
        except Exception as e:
            # Fallback: 非流式
            try:
                response = await self._process_direct(user_input, context)
                full_response = response.content or str(response)
                yield {"type": "content", "content": full_response}
            except Exception as e2:
                full_response = f"处理出错: {e2}"
                yield {"type": "content", "content": full_response}

        # 5. 完成
        yield {
            "type": "done",
            "agent": self.name,
            "content": full_response,
            "execution_time_ms": int((time.time() - start) * 1000),
        }
    
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
