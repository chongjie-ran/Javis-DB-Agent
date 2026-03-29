# Javis-DB-Agent 第四轮迭代准备报告

> 版本：v1.0 | 日期：2026-03-28 | 组织者：道衍

---

## 一、第四轮迭代背景

### 1.1 第三轮成果
- ✅ 告警关联推理链（15+因果规则，603行代码）
- ✅ Mock API增强（超时/限流/级联故障模拟）
- ✅ Session持久化（SQLite+TTL，605行代码）
- ✅ 189个测试全通过

### 1.2 第三轮遗留问题
- ❌ 知识库仍为70%，参数/容量知识缺失
- ❌ 真实Javis API对接为0%
- ❌ 端到端场景测试缺失
- ❌ 性能基线未验证

---

## 二、第四轮迭代目标

### 2.1 P0任务

| 任务 | 负责人 | 目标 |
|------|--------|------|
| Javis-DB-Agent API文档研究与Mock数据升级 | 悟通 | 深入研究Javis API，完善Mock数据格式 |
| 认证模块框架设计 | 悟通 | 预留OAuth2.0认证接口 |
| 端到端测试场景设计 | 真显 | 设计完整用户旅程测试用例 |
| 端到端测试执行 | 真显 | 执行端到端测试，修复发现的问题 |

### 2.2 成功标准

| 标准 | 目标 |
|------|------|
| Mock API数据质量 | 提升至真实zCloud的60%相似度 |
| 端到端测试覆盖率 | ≥5个完整用户旅程 |
| 测试通过率 | ≥95% |
| 性能基线 | 建立30秒响应时间基准 |

---

## 三、详细任务分解

### 3.1 悟通任务：Javis-DB-Agent API研究与Mock升级

#### Day 1-2: Javis-DB-Agent API文档研究

**任务**:
1. 研究Javis API的认证机制（OAuth2.0/Token刷新）
2. 分析真实告警数据格式（字段结构、嵌套关系）
3. 了解API的QPS限制和错误码
4. 整理Javis API接口清单

**输出**:
- `docs/javis-db-api-research.md` - API研究文档
- `docs/javis-db-auth-design.md` - 认证机制设计草案

#### Day 3: Mock数据升级

**任务**:
1. 基于研究结果，升级Mock告警数据格式
2. 增加更多真实场景的Mock数据（嵌套字段、自定义字段）
3. 实现QPS限制模拟器
4. 完善错误码映射

**输出**:
- 升级后的 `mock_javis_api/` 数据结构
- QPS限制模拟器

#### Day 4-5: 认证模块框架

**任务**:
1. 设计认证模块接口（预留OAuth2.0位置）
2. 实现Token刷新机制框架
3. 在Mock客户端中预留真实API切换开关

**输出**:
- `src/mock_api/auth_framework.py` - 认证框架
- `src/mock_api/javis_client.py` - 支持真实/Mock切换

### 3.2 真显任务：端到端测试

#### Day 1-2: 端到端测试设计

**任务**:
1. 设计5个完整用户旅程测试场景
2. 建立性能基线测试用例
3. 设计大规模告警处理测试

**输出**:
- `tests/round4/test_e2e_scenarios.py` - 端到端测试用例
- `tests/round4/test_performance_baseline.py` - 性能基线测试

#### Day 3-4: 端到端测试执行

**任务**:
1. 执行端到端测试用例
2. 发现并记录问题
3. 协同悟通修复问题

**输出**:
- 测试执行报告
- 缺陷列表

#### Day 5-7: 性能基线验证

**任务**:
1. 执行性能基线测试
2. 验证30秒响应时间目标
3. 优化性能瓶颈

**输出**:
- 性能基线报告
- 性能优化建议

---

## 四、端到端测试场景设计

### 4.1 场景1：告警诊断完整旅程

```
用户: "INS-001的CPU告警是怎么回事？"
系统: 
  1. 接收用户输入
  2. 调用Orchestrator识别意图
  3. 调用DiagnosticAgent诊断告警
  4. 使用AlertCorrelator查找关联告警
  5. 使用知识库检索相关SOP
  6. 生成诊断报告
验证: 
  - 响应时间 < 30秒
  - 报告包含根因分析
  - 报告包含关联告警
```

### 4.2 场景2：会话恢复与上下文

```
用户: [新建会话] "查询INS-001状态"
用户: [新建会话] "这个实例最近有什么告警？"
系统: 识别为同一用户，复用上下文
验证:
  - 无需重新认证
  - 历史上下文可访问
```

### 4.3 场景3：错误注入与降级

```
触发: 错误注入（模拟Javis API超时）
用户: "查询INS-001状态"
系统: 
  1. 检测到API超时
  2. 触发重试机制
  3. 重试失败后返回降级响应
验证:
  - 用户收到友好错误提示
  - 审计日志记录错误
```

### 4.4 场景4：批量告警关联分析

```
输入: 10个活跃告警
系统:
  1. 调用AlertCorrelator分析关联
  2. 构建告警链
  3. 识别根因
  4. 生成告警收敛建议
验证:
  - 正确识别根因告警
  - 告警链完整
  - 收敛建议合理
```

### 4.5 场景5：工单创建与审批

```
用户: "帮我创建一个重启实例的工单"
系统:
  1. RiskAssessmentAgent评估风险
  2. 确认为L3风险，需要审批
  3. 生成审批请求
  4. 等待审批
  5. 审批通过后执行
验证:
  - 风险评估正确
  - 审批流程触发
  - 执行结果反馈
```

---

## 五、Mock数据升级规格

### 5.1 告警数据格式升级

**目标**: 从简单格式升级到接近真实格式

```python
# 当前Mock格式（简化）
{
    "alert_id": "ALT-001",
    "alert_type": "CPU_HIGH",
    "severity": "warning",
    "message": "CPU使用率超过80%"
}

# 目标Mock格式（接近真实）
{
    "alert_id": "ALT-001",
    "alert_type": "CPU_HIGH",
    "severity": "warning",
    "message": "CPU使用率超过80%",
    "instance_id": "INS-001",
    "instance_name": "生产主库",
    "occurred_at": "2026-03-28T10:00:00Z",
    "metric_value": 85.5,
    "threshold": 80.0,
    "unit": "%",
    "custom_fields": {
        "host_ip": "192.168.1.100",
        "region": "华东-上海",
        "cluster": "prod-cluster-01"
    },
    "nested_alerts": [],
    "annotations": {
        "first_occurrence": "2026-03-28T09:00:00Z",
        "acknowledged_by": None,
        "resolved_at": None
    }
}
```

### 5.2 QPS限制模拟器

```python
class QPSLimiter:
    """QPS限制模拟器"""
    def __init__(self, max_qps: int = 100):
        self.max_qps = max_qps
        self.window = 1.0  # 1秒窗口
        self.requests = []
    
    def should_limit(self) -> bool:
        """判断是否应该限流"""
        now = time.time()
        self.requests = [r for r in self.requests if now - r < self.window]
        if len(self.requests) >= self.max_qps:
            return True
        self.requests.append(now)
        return False
```

---

## 六、验收标准

| 验收项 | 标准 | 负责人 |
|--------|------|--------|
| Javis-DB-Agent API研究文档 | 包含认证机制、接口清单、QPS限制 | 悟通 |
| Mock数据升级 | 告警格式接近真实，字段完整 | 悟通 |
| 认证框架 | 预留OAuth2.0接口 | 悟通 |
| 端到端测试设计 | 5个完整用户旅程 | 真显 |
| 端到端测试执行 | ≥95%通过率 | 真显 |
| 性能基线 | 30秒响应时间基准建立 | 真显 |

---

*道衍 - 第四轮迭代准备完成，授权执行*
