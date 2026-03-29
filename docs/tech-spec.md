# Javis-DB-Agent 技术方案

> 版本：v1.0 | 日期：2026-03-28 | 状态：初稿

---

## 1. 技术栈选型

### 1.1 LLM层
| 项目 | 选择 | 理由 |
|------|------|------|
| 模型 | Qwen3.5 (Ollama) | 本地运行，适配64GB显存 |
| API | Ollama REST API | 简单易用，本地部署 |
| 推理优化 | GPU加速 | 64GB显存支持 |

### 1.2 核心框架
| 组件 | 选择 | 理由 |
|------|------|------|
| 编排框架 | LangChain/LangGraph | 多Agent协同成熟方案 |
| 或自研 | 轻量级Agent框架 | 更贴合运维场景 |
| Web服务 | FastAPI | 高性能、易扩展 |
| 异步任务 | Celery + Redis | 定时任务、异步执行 |
| 数据库 | SQLite/PostgreSQL | 配置存储、审计日志 |

### 1.3 工具层
| 组件 | 选择 | 理由 |
|------|------|------|
| 工具定义 | Pydantic + JSON Schema | 参数校验、结构化 |
| 数据库连接 | DB-API 2.0 / SQLAlchemy | 统一数据库访问 |
| API客户端 | httpx | 异步HTTP |

### 1.4 安全
| 组件 | 选择 | 理由 |
|------|------|------|
| 权限控制 | RBAC模型 | 运维场景成熟 |
| SQL护栏 | SQL子集+白名单 | 安全可控 |
| 审计存储 | 结构化日志+ES | 可追溯、可分析 |

### 1.5 知识库
| 组件 | 选择 | 理由 |
|------|------|------|
| 知识存储 | 向量数据库 (Milvus/Chroma) | 语义检索 |
| 知识结构 | Markdown + JSON | 便于维护 |
| 知识图谱 | NetworkX + Neo4j | 关系统建模 |

---

## 2. 项目结构

```
Javis-DB-Agent/
├── src/
│   ├── __init__.py
│   ├── main.py                 # 应用入口
│   ├── config.py               # 配置管理
│   ├── gateway/               # Gateway核心
│   │   ├── __init__.py
│   │   ├── session.py         # 会话管理
│   │   ├── tool_registry.py   # 工具注册
│   │   ├── policy_engine.py    # 策略引擎
│   │   └── audit.py           # 审计日志
│   ├── agents/                # Agent实现
│   │   ├── __init__.py
│   │   ├── base.py            # Agent基类
│   │   ├── orchestrator.py    # 编排Agent
│   │   ├── diagnostic.py       # 诊断Agent
│   │   ├── risk.py            # 风险Agent
│   │   ├── sql_analyzer.py    # SQL分析Agent
│   │   ├── inspector.py        # 巡检Agent
│   │   └── reporter.py         # 报告Agent
│   ├── tools/                 # 工具集
│   │   ├── __init__.py
│   │   ├── base.py            # 工具基类
│   │   ├── query_tools.py     # 查询类工具
│   │   ├── analysis_tools.py   # 分析类工具
│   │   └── action_tools.py    # 执行类工具
│   ├── knowledge/             # 知识层
│   │   ├── __init__.py
│   │   ├── kb.py              # 知识库管理
│   │   ├── alert_rules.py     # 告警规则
│   │   ├── sop.py             # SOP管理
│   │   └── cases.py           # 案例库
│   ├── llm/                   # LLM交互
│   │   ├── __init__.py
│   │   ├── ollama_client.py   # Ollama客户端
│   │   └── prompt_manager.py  # Prompt管理
│   └── api/                   # API层
│       ├── __init__.py
│       ├── routes.py          # 路由
│       └── schemas.py         # 请求/响应模型
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_tools.py
│   └── test_integration.py
├── configs/
│   ├── config.yaml           # 主配置
│   ├── prompts.yaml          # Prompt模板
│   └── tools.yaml            # 工具定义
├── scripts/
│   ├── init_db.py            # 数据库初始化
│   └── load_knowledge.py     # 知识导入
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   └── tech-spec.md
└── requirements.txt
```

---

## 3. 核心模块设计

### 3.1 Tool定义规范

```python
from pydantic import BaseModel, Field
from enum import Enum

class RiskLevel(Enum):
    L1_READ = 1      # 只读分析
    L2_DIAGNOSE = 2  # 自动诊断
    L3_LOW_RISK = 3  # 低风险执行
    L4_MEDIUM = 4    # 中风险执行
    L5_HIGH = 5      # 高风险/禁止

class ToolParam(BaseModel):
    """工具参数定义"""
    name: str
    type: str
    description: str
    required: bool = True
    constraints: dict = {}  # 参数约束

class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    category: str  # query/analysis/action
    risk_level: RiskLevel
    params: list[ToolParam]
    auth_required: list[str] = []
    pre_check: str = ""  # 执行前检查
    post_check: str = "" # 执行后检查
```

### 3.2 Agent基类

```python
from abc import ABC, abstractmethod
from typing import Any

class BaseAgent(ABC):
    """Agent基类"""
    name: str
    description: str
    tools: list[str]  # 可用工具列表
    system_prompt: str
    
    @abstractmethod
    async def process(self, goal: str, context: dict) -> dict:
        """处理任务"""
        pass
    
    async def think(self, prompt: str) -> str:
        """LLM推理"""
        # 调用Ollama
        pass
    
    async def call_tool(self, tool_name: str, params: dict) -> Any:
        """调用工具"""
        # 通过ToolRegistry调用
        pass
```

### 3.3 编排Agent流程

```python
class OrchestratorAgent(BaseAgent):
    """统一编排Agent"""
    
    async def process(self, goal: str, context: dict) -> dict:
        # 1. 意图识别
        intent = await self.recognize_intent(goal)
        
        # 2. 选择专业Agent
        selected_agents = self.select_agents(intent)
        
        # 3. 构建执行计划
        plan = self.build_plan(selected_agents, context)
        
        # 4. 调度执行
        results = await self.execute_plan(plan)
        
        # 5. 汇总结果
        return self.aggregate_results(results)
```

### 3.4 安全策略引擎

```python
class PolicyEngine:
    """策略引擎"""
    
    def __init__(self):
        self.rules = []
    
    def check(self, user: str, action: str, tool: str, params: dict) -> bool:
        """安全检查"""
        # 1. 检查用户权限
        # 2. 检查动作级别
        # 3. 检查工具风险
        # 4. 检查参数约束
        pass
    
    def get_approval_required(self, action: str, risk_level: int) -> bool:
        """是否需要审批"""
        pass
```

---

## 4. API设计

### 4.1 核心接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/chat | 对话交互 |
| POST | /api/v1/diagnose | 告警诊断 |
| POST | /api/v1/analyze/sql | SQL分析 |
| POST | /api/v1/inspect | 巡检执行 |
| GET | /api/v1/health | 健康检查 |
| GET | /api/v1/tools | 工具列表 |
| GET | /api/v1/audit/logs | 审计日志 |

### 4.2 请求/响应示例

```json
// POST /api/v1/diagnose
// Request
{
  "alert_id": "ALT-20260328-001",
  "instance_id": "INS-001",
  "context": {}
}

// Response
{
  "code": 0,
  "message": "success",
  "data": {
    "diagnosis": {
      "alert_type": "锁等待超时",
      "root_cause": "SQL-2026-001 长时间持有锁",
      "confidence": 0.85,
      "next_steps": [
        "查看会话详情",
        "分析阻塞链",
        "评估kill session风险"
      ]
    },
    "risk": {
      "level": "L3",
      "can_auto_handle": false,
      "approval_required": true
    }
  }
}
```

---

## 5. LLM交互设计

### 5.1 System Prompt模板

```yaml
system_prompt: |
  你是一个专业的数据库运维智能助手。
  
  角色定义：
  - 你是{{agent_name}}，负责{{agent_description}}
  - 你通过工具与数据库交互，不能直接执行SQL
  
  安全原则：
  - 永远不直接输出SQL或shell命令
  - 所有操作必须通过工具调用
  - 遵循最小权限原则
  
  工具调用原则：
  - 选择合适的工具
  - 传递受限的参数
  - 检查执行结果
```

### 5.2 Tool Calling格式

```json
{
  "tool_calls": [
    {
      "tool": "query_session",
      "params": {
        "instance_id": "INS-001",
        "limit": 10
      }
    }
  ]
}
```

---

## 6. 知识库设计

### 6.1 知识分类

| 类型 | 存储格式 | 检索方式 |
|------|----------|----------|
| 运维知识 | Markdown | 全文搜索 |
| 告警规则 | JSON | 精确匹配 |
| SOP | Markdown + JSON | 关键词 |
| 案例 | Markdown | 语义向量 |
| 知识图谱 | Neo4j | 图查询 |

### 6.2 知识入库示例

```yaml
# alert_rule_example.yaml
- alert_code: ALT_LOCK_WAIT
  name: 锁等待超时
  description: 实例发生锁等待超时
  severity: warning
  symptoms:
    - 等待时间超过阈值
    - 会话处于Waiting状态
  possible_causes:
    - 长事务持有锁
    - 未提交事务
    - 锁冲突
  check_steps:
    - 查询锁等待链
    - 分析持有锁的SQL
    - 评估影响范围
  resolution:
    - 确认是否可以kill session
    - 联系应用负责人
    - 评估事务回滚影响
```

---

## 7. 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                      本地部署                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐      │
│  │   FastAPI   │   │   Celery    │   │   Redis     │      │
│  │   Gateway   │   │   Worker    │   │   Broker    │      │
│  └─────────────┘   └─────────────┘   └─────────────┘      │
│         ↓                                              │      │
│  ┌─────────────────────────────────────────────────┐  │      │
│  │              Agent Core                          │  │      │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │  │      │
│  │  │编排Agent│ │诊断Agent│ │风险Agent│ │SQL分析 │   │  │      │
│  │  └────────┘ └────────┘ └────────┘ └────────┘   │  │      │
│  └─────────────────────────────────────────────────┘  │      │
│         ↓                                              │      │
│  ┌─────────────────────────────────────────────────┐  │      │
│  │              Tool Executor                       │  │      │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐      │  │      │
│  │  │QueryTools│ │AnalysisTools│ │ActionTools│      │  │      │
│  │  └───────────┘ └───────────┘ └───────────┘      │  │      │
│  └─────────────────────────────────────────────────┘  │      │
│         ↓                                              │      │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐      │
│  │   SQLite    │   │   Chroma    │   │   Ollama    │      │
│  │  (配置/审计) │   │  (向量库)   │   │  (LLM)     │      │
│  └─────────────┘   └─────────────┘   └─────────────┘      │
│                                                        GPU │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 实施计划

### 第一阶段（1-2周）
- [ ] 项目结构搭建
- [ ] Gateway核心实现
- [ ] Ollama集成
- [ ] 基础Tool框架

### 第二阶段（2-3周）
- [ ] 编排Agent实现
- [ ] 诊断Agent实现
- [ ] SQL分析Agent实现
- [ ] 告警诊断场景

### 第三阶段（3-4周）
- [ ] 巡检Agent实现
- [ ] 报告Agent实现
- [ ] 知识库集成
- [ ] 安全策略完善

### 第四阶段（4-5周）
- [ ] API开发
- [ ] 前端界面
- [ ] 集成测试
- [ ] 文档完善

---

## 9. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| LLM推理质量 | 高 | 优化Prompt、知识增强、结果校验 |
| 工具安全 | 高 | 严格参数约束、多层安全校验 |
| 性能瓶颈 | 中 | 缓存优化、异步处理、增量加载 |
| 知识覆盖不足 | 中 | 持续沉淀、案例积累 |

---

*文档状态：初稿，待评审*
