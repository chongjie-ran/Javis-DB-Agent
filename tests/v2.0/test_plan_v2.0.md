# V2.0 测试计划

> 版本：v1.0  
> 日期：2026-03-30  
> 项目路径：`/Users/chongjieran/SWproject/Javis-DB-Agent/`  
> 状态：**规划中**（待V2.0模块实现后启动）

---

## 一、测试目标

验证V2.0三个P0方向的完整功能：
- **P0-1**：安全治理层增强（SQL护栏 + SOP执行器 + 执行回流验证）
- **P0-2**：知识层增强（知识图谱 + 案例库 + RAG检索 + 推理链路）
- **P0-3**：感知层增强（拓扑感知 + 配置感知 + zCloud API对接）

---

## 二、测试范围

### 2.1 模块覆盖

| 模块 | 测试文件 | 用例数 | 负责人 |
|------|---------|--------|--------|
| P0-1 SQL护栏 | `test_security_layer.py` | 30 | 待定 |
| P0-1 SOP执行器 | `test_security_layer.py` | 5 | 待定 |
| P0-1 执行回流 | `test_security_layer.py` | 6 | 待定 |
| P0-1 权限审批 | `test_security_layer.py` | 6 | 待定 |
| P0-2 知识图谱 | `test_knowledge_layer.py` | 17 | 待定 |
| P0-2 案例库 | `test_knowledge_layer.py` | 7 | 待定 |
| P0-2 RAG检索 | `test_knowledge_layer.py` | 9 | 待定 |
| P0-2 推理链路 | `test_knowledge_layer.py` | 8 | 待定 |
| P0-3 拓扑感知 | `test_perception_layer.py` | 10 | 待定 |
| P0-3 配置感知 | `test_perception_layer.py` | 9 | 待定 |
| P0-3 API对接 | `test_perception_layer.py` | 10 | 待定 |
| 集成测试 | `test_integration.py` | 16 | 待定 |
| **合计** | **4个文件** | **~120+用例** | |

### 2.2 排除范围

- V2.0阶段不包含的Agent开发（变更管理Agent、配置风险Agent、HA诊断Agent）
- 阶段三自治场景
- V1.5 DFX框架已覆盖的功能回归（仅做Smoke测试）

---

## 三、测试轮次安排

### 第一轮：基础验证（Week 1-2）

**目标**：验证测试框架本身可用，Mock fixture正常工作

**前置条件**：
- `tests/v2.0/conftest.py` 中的Mock fixture可用
- pytest能正常收集测试用例

**测试内容**：
```
pytest tests/v2.0/ --collect-only    # 验证用例收集
pytest tests/v2.0/ -k "happy" -v    # 验证Happy path用例
```

**通过标准**：
- 用例收集>100个
- Happy path用例可执行（不报ImportError）

**验收标准**：
- [ ] pytest可正常加载V2.0测试
- [ ] Mock fixture无语法错误
- [ ] 测试标记（markers）正确注册

---

### 第二轮：Mock层测试（Week 2-3）

**目标**：基于Mock fixture完成所有P0用例

**前置条件**：
- V2.0模块代码框架已创建（接口已定义）
- Mock fixture实现完整

**测试执行**：
```bash
# P0-1安全层
pytest tests/v2.0/test_security_layer.py -v

# P0-2知识层
pytest tests/v2.0/test_knowledge_layer.py -v

# P0-3感知层
pytest tests/v2.0/test_perception_layer.py -v
```

**通过标准**：
- 所有Happy path用例通过
- Edge cases用例按预期处理
- Error cases用例正确拦截/拒绝

**验收标准**：
- [ ] SQL护栏可正确识别安全/危险SQL
- [ ] SOP执行器步骤执行正确
- [ ] 执行回流偏差检测正确
- [ ] 知识图谱增删改查正常
- [ ] 案例库检索/推荐正常
- [ ] RAG混合检索正常
- [ ] 推理链路置信度计算正确
- [ ] 拓扑/配置感知Mock正常

---

### 第三轮：真实数据库测试（Week 3-4）

**目标**：使用真实MySQL/PG环境验证

**前置条件**：
- MySQL测试实例可用
- PostgreSQL测试实例可用
- 测试数据已准备

**环境准备**：
```bash
# MySQL
export TEST_MYSQL_HOST=localhost
export TEST_MYSQL_PORT=3306
export TEST_MYSQL_USER=root
export TEST_MYSQL_PASSWORD=
export TEST_MYSQL_DATABASE=test

# PostgreSQL
export TEST_PG_HOST=localhost
export TEST_PG_PORT=5432
export TEST_PG_USER=javis_test
export TEST_PG_PASSWORD=javis_test123
export TEST_PG_DATABASE=postgres
```

**测试执行**：
```bash
# MySQL环境
pytest tests/v2.0/ -m mysql -v

# PostgreSQL环境
pytest tests/v2.0/ -m pg -v
```

**通过标准**：
- MySQL用例>80%通过
- PostgreSQL用例>80%通过

**验收标准**：
- [ ] 拓扑发现（pg_stat_replication / SHOW SLAVE STATUS）正常
- [ ] 配置采集（pg_settings / SHOW GLOBAL VARIABLES）正常
- [ ] SQL护栏在真实DB上验证通过

---

### 第四轮：真实API测试（Week 4-5，可选）

**目标**：zCloud平台API对接验证

**前置条件**：
- zCloud测试环境可用
- API凭证已配置

**环境准备**：
```bash
export TEST_ZCOULD_API_URL=https://zcloud-test.enmotech.com/api
export TEST_ZCLOUD_API_KEY=your-test-api-key
```

**测试执行**：
```bash
pytest tests/v2.0/ -m real_api -v
```

**通过标准**：
- zCloud API健康检查通过
- 告警/拓扑/配置API返回正常

**验收标准**：
- [ ] zCloud API认证正常
- [ ] 告警获取接口正常
- [ ] 拓扑获取接口正常
- [ ] API降级（Mock）机制正常

---

### 第五轮：集成测试 + 回归（Week 5-6）

**目标**：三层协同 + V1.5回归

**测试执行**：
```bash
# 集成测试
pytest tests/v2.0/test_integration.py -v

# 完整回归（排除slow）
pytest tests/v2.0/ -m "not slow" -v
```

**通过标准**：
- 集成测试用例>90%通过
- V1.5回归>95%通过

**验收标准**：
- [ ] SQL护栏+编排Agent协同正常
- [ ] 知识图谱+诊断Agent协同正常
- [ ] 拓扑/配置+诊断Agent协同正常
- [ ] 完整执行闭环（SOP→审批→执行→验证）正常
- [ ] V1.5 BackupAgent功能正常
- [ ] V1.5 PolicyEngine正常
- [ ] V1.5 审计链正常

---

## 四、环境准备

### 4.1 测试数据库

| 数据库 | 版本 | 用途 | 端口 | 账号 |
|--------|------|------|------|------|
| PostgreSQL | 15+ | P0-1/P0-2/P0-3测试 | 5432 | javis_test/javis_test123 |
| MySQL | 8.0+ | P0-1/P0-2/P0-3测试 | 3306 | root/(无密码) |

**DDL脚本**：`tests/v2.0/setup_v2.0_test_env.sql`（待创建）

### 4.2 Python依赖

```bash
pip install pytest pytest-asyncio pytest-timeout
pip install psycopg2-binary pymysql
pip install requests
```

### 4.3 zCloud API（可选）

| 环境 | URL | 说明 |
|------|-----|------|
| 测试环境 | `http://localhost:8080` | Mock或真实 |
| 正式环境 | `https://zcloud.enmotech.com/api` | 仅限授权测试 |

---

## 五、验收标准

### 5.1 功能验收

| 模块 | 指标 | 目标值 |
|------|------|--------|
| SQL护栏 | 危险SQL拦截率 | ≥99% |
| SQL护栏 | 误报率 | ≤5% |
| SOP执行器 | 步骤执行成功率 | ≥95% |
| 执行回流 | 偏差检测率 | ≥90% |
| 知识图谱 | 节点增删改查成功率 | ≥98% |
| 案例库 | 相似案例Top5准确率 | ≥80% |
| RAG检索 | 混合检索Top10准确率 | ≥75% |
| 推理链路 | 置信度计算误差 | ≤10% |
| 拓扑感知 | 集群拓扑发现率 | ≥95% |
| 配置感知 | 参数采集完整率 | ≥95% |

### 5.2 性能验收

| 指标 | 目标值 |
|------|--------|
| SQL护栏单次验证 | <50ms |
| 知识图谱路径查询（5层） | <500ms |
| RAG混合检索Top10 | <1s |
| 20并发诊断压力测试 | <30s |
| 100次策略检查 | <5s |

### 5.3 回归验收

| 模块 | 回归覆盖率 | 目标值 |
|------|-----------|--------|
| V1.5 BackupAgent | 基础功能回归 | 100% |
| V1.5 PolicyEngine | 权限检查回归 | 100% |
| V1.5 审计链 | 哈希链验证回归 | 100% |
| V1.5 向量存储 | 检索回归 | 100% |

---

## 六、回归策略

### 6.1 自动化回归

每次代码提交自动触发：
```bash
# CI/CD配置（待集成）
pytest tests/v2.0/ -m "not slow and not real_api" -v
```

### 6.2 回归测试集

| 优先级 | 用例数 | 执行频率 | 运行环境 |
|--------|--------|---------|---------|
| P0核心 | ~50个 | 每次提交 | CI |
| P1扩展 | ~40个 | 每日 | CI |
| P2边界 | ~30个 | 每周 | 手动 |
| 集成 | ~16个 | 每周 | 手动 |

### 6.3 回归判定规则

- **通过**：所有P0用例通过 + P1用例通过≥80%
- **降级**：P0通过但P1<80% → 发布前需修复
- **失败**：P0失败 → 阻断发布

---

## 七、测试数据

### 7.1 测试SQL样本

| 类型 | SQL | 预期行为 |
|------|-----|---------|
| 安全SELECT | `SELECT id,name FROM users WHERE status=1` | L0-L2，允许 |
| 危险TRUNCATE | `TRUNCATE TABLE users` | 拦截 |
| 危险DROP | `DROP TABLE backup_logs` | 拦截 |
| 无WHERE DELETE | `DELETE FROM logs` | 拦截 |
| 带WHERE DELETE | `DELETE FROM logs WHERE created_at<'2026-01-01'` | L2-L3，审批 |
| UNION注入 | `SELECT * FROM users UNION SELECT * FROM passwords` | 拦截 |

### 7.2 知识图谱样本

| 节点ID | 类型 | 名称 |
|--------|------|------|
| FAULT-lock | fault_pattern | 锁等待超时 |
| ROOT-long-txn | root_cause | 长事务持有锁 |
| ACTION-kill | action | Kill会话 |

**关系**：`FAULT-lock --caused_by--> ROOT-long-txn --resolvable_by--> ACTION-kill`

### 7.3 拓扑样本

```json
{
  "cluster_id": "CLS-TEST-001",
  "nodes": [
    {"node_id": "N1", "role": "primary", "status": "up"},
    {"node_id": "N2", "role": "replica", "status": "up"},
    {"node_id": "N3", "role": "replica", "status": "down"}
  ]
}
```

---

## 八、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| zCloud API不可用 | P0-3部分测试无法真实验证 | 使用Mock降级，每次测试优先尝试真实API |
| PG/MySQL测试环境不稳定 | 测试结果波动 | 使用容器化环境，测试前健康检查 |
| V2.0模块实现延迟 | 测试无法真实运行 | 先用Mock层验证逻辑，待实现后切换 |
| 测试数据污染 | 历史测试数据影响新测试 | 每个测试前使用独立数据，测试后清理 |
| 性能测试环境不一致 | 性能指标不可比 | 使用固定规格CI环境，记录baseline |

---

## 九、交付物

| 交付物 | 路径 | 状态 |
|--------|------|------|
| 测试框架配置 | `tests/v2.0/conftest.py` | ✅ 已创建 |
| P0-1安全层测试 | `tests/v2.0/test_security_layer.py` | ✅ 已创建 |
| P0-2知识层测试 | `tests/v2.0/test_knowledge_layer.py` | ✅ 已创建 |
| P0-3感知层测试 | `tests/v2.0/test_perception_layer.py` | ✅ 已创建 |
| 集成测试 | `tests/v2.0/test_integration.py` | ✅ 已创建 |
| 测试用例CSV | `tests/v2.0/test_cases_v2.0.csv` | ✅ 已创建 |
| 测试计划文档 | `tests/v2.0/test_plan_v2.0.md` | ✅ 已创建 |
| 环境配置脚本 | `tests/v2.0/setup_v2.0_test_env.sql` | ⏳ 待创建 |
| 测试报告模板 | `tests/v2.0/test_report_template.md` | ⏳ 待创建 |

---

*本文档由SC团队Agent设计 | 日期：2026-03-30*
