# zCloudNewAgentProject 第三轮测试准备报告

> 版本：v1.0 | 日期：2026-03-28 | 测试者：真显

---

## 一、测试准备完成状态

| 测试文件 | 测试用例数 | 覆盖内容 | 状态 |
|----------|------------|----------|------|
| `test_alert_chain_reasoning.py` | 34 | 告警关联推理链 | ✅ 完成 |
| `test_mock_api_enhanced.py` | 29 | Mock API增强 | ✅ 完成 |
| `test_session_persistence.py` | 25 | Session持久化 | ✅ 完成 |
| **合计** | **88** | 三大测试领域 | ✅ |

---

## 二、测试用例详情

### 2.1 告警关联推理链测试 (32用例)

**文件**: `tests/round3/test_alert_chain_reasoning.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| TestAlertChainDataStructures | 2 | 告警节点结构、告警链结构 |
| TestAlertCorrelationRules | 4 | CPU↔Lock、Lock↔Session、复制延迟↔慢SQL、磁盘满↔备份失败 |
| TestSingleHopReasoning | 2 | 单跳推理逻辑 |
| TestTwoHopReasoning | 3 | 两跳推理链、置信度传递 |
| TestParallelAlertReasoning | 2 | 并行告警、多链交叉 |
| TestAlertChainReasoningLogic | 4 | 关联查找、链构建、根因识别、链长度限制 |
| TestAlertChainConfidenceCalculation | 3 | 概率乘法、并行合并、阈值过滤 |
| TestAlertChainIntegration | 2 | 端到端诊断流程、告警优先级 |
| TestAlertChainKnowledgeBase | 1 | 知识规则匹配 |

**核心测试场景**:
- ✅ A告警→B告警→C告警的两跳推理链
- ✅ CPU高→锁等待→会话泄漏因果链
- ✅ 磁盘满→备份失败→HA切换链路
- ✅ 置信度在链中的传递和衰减
- ✅ 根因告警识别和定位

### 2.2 Mock API增强测试 (28用例)

**文件**: `tests/round3/test_mock_api_enhanced.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| TestMockAPITimeoutScenarios | 5 | 慢响应超时、连接超时、超时错误格式、异步超时、重试策略 |
| TestMockAPIRateLimiting | 5 | 429响应、剩余次数、重置时间、响应头解析、自适应限流 |
| TestMockAPICascadeFailures | 5 | DB故障、故障传播、熔断器、部分降级、故障转移 |
| TestMockAPIErrorHandling | 8 | 400/401/403/404/500/502/503错误格式、错误码映射 |
| TestMockAPIResilience | 4 | 舱壁隔离、指数退避、死信队列、优雅降级 |
| TestMockAPIHealthCheck | 3 | 健康/降级/不健康检查 |
| TestMockAPIIntegration | 2 | 端到端恢复、熔断器集成 |

**核心测试场景**:
- ✅ 超时场景模拟（读超时、连接超时、总超时）
- ✅ 限流响应 (429 Too Many Requests)
- ✅ 级联故障传播（DB→Session→Lock→Alert）
- ✅ 熔断器模式（closed→open→half-open）
- ✅ 指数退避重试策略
- ✅ 优雅降级等级

### 2.3 Session持久化测试 (26用例)

**文件**: `tests/round3/test_session_persistence.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| TestSessionDataModel | 4 | Session基本结构、消息、上下文、元数据 |
| TestSessionSerialization | 4 | JSON序列化、Pickle序列化、消息列表、嵌套对象 |
| TestSessionPersistenceStorage | 3 | 文件存储、二进制存储、并发安全 |
| TestSessionRecovery | 5 | 基本恢复、消息历史、上下文、重启恢复、部分数据 |
| TestSessionExpiration | 4 | TTL计算、过期检测、自动清理、优雅过期 |
| TestMultiSessionIsolation | 4 | 用户多会话、上下文隔离、泄露防护、ID唯一性 |
| TestSessionContextOperations | 4 | 设置获取、更新、合并、删除 |
| TestSessionIntegration | 2 | 完整生命周期、超时后恢复 |

**核心测试场景**:
- ✅ Session数据结构完整序列化
- ✅ 重启后消息历史恢复
- ✅ 上下文（context）完整恢复
- ✅ 多会话隔离和数据安全
- ✅ Session过期和自动清理
- ✅ 优雅过期和摘要保留

---

## 三、运行方式

### 运行全部第三轮测试
```bash
cd ~/SWproject/zCloudNewAgentProject
python3 -m pytest tests/round3/ -v
```

### 运行单个测试文件
```bash
# 告警链推理测试
python3 -m pytest tests/round3/test_alert_chain_reasoning.py -v

# Mock API增强测试
python3 -m pytest tests/round3/test_mock_api_enhanced.py -v

# Session持久化测试
python3 -m pytest tests/round3/test_session_persistence.py -v
```

### 带详细输出
```bash
python3 -m pytest tests/round3/ -v -s --tb=long
```

---

## 四、依赖项

### Mock API Server (18080端口)
```bash
# 启动Mock API Server
cd ~/SWproject/zCloudNewAgentProject
python3 -m uvicorn mock_zcloud_api.server:app --host 0.0.0.0 --port 18080

# 验证运行
curl http://localhost:18080/health
```

### Ollama (可选)
```bash
# 用于需要真实LLM推理的测试
ollama serve
```

---

## 五、预期结果

### 86个测试用例应全部通过

| 测试领域 | 用例数 | 预期通过 |
|----------|--------|----------|
| 告警链推理 | 34 | 34 ✅ |
| Mock API增强 | 29 | 29 ✅ |
| Session持久化 | 25 | 25 ✅ |
| **总计** | **88** | **88** |

---

## 六、待悟通开发的功能

第三轮测试验证依赖以下功能实现：

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 告警关联推理引擎 | P0 | 待开发 |
| 推理链置信度计算 | P0 | 待开发 |
| Mock API超时端点 | P1 | 待开发 |
| Mock API限流端点 | P1 | 待开发 |
| Mock API级联故障 | P1 | 待开发 |
| Session持久化存储 | P0 | 待开发 |
| Session过期管理 | P1 | 待开发 |
| 熔断器实现 | P2 | 待开发 |

---

## 七、测试覆盖率

### 第三轮新增覆盖

| 领域 | 覆盖模块 | 覆盖率目标 |
|------|----------|------------|
| 告警链推理 | 推理链构建、置信度计算、规则匹配 | 80%+ |
| Mock API | 超时、限流、级联故障、熔断器 | 75%+ |
| Session持久化 | 序列化、恢复、过期管理、隔离 | 85%+ |

---

## 八、已知限制

1. **Mock API Server**: 部分测试需要Mock API Server运行在18080端口
2. **真实LLM**: 推理质量测试需要Ollama服务
3. **持久化存储**: 测试使用临时文件，真实存储待实现
4. **端到端测试**: 待Agent完整实现后补充

---

*真显 - 第三轮测试准备完成，等待悟通通知核心功能完成后开始执行测试*
