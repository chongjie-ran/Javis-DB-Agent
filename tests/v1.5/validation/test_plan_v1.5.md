# V1.5 测试验证计划

> 版本: v1.5 | 创建日期: 2026-03-30 | 项目: Javis-DB-Agent
> 测试目标: V1.4 所有功能在真实环境中的功能验证与问题发现

---

## 一、测试环境准备

### 1.1 环境清单

| 环境 | 配置 | 用途 | 启动方式 |
|------|------|------|----------|
| MySQL Test | localhost:3307, root/test123 | 基础功能测试 | `docker-compose -f docker-compose.mysql.yml up mysql` |
| MySQL Perf | localhost:3308, root/perf123 | 性能分析测试 | `docker-compose -f docker-compose.mysql.yml up mysql_perf` |
| PostgreSQL Test | localhost:5432 (待配置) | PG功能测试 | 需单独部署 |
| Mock API | localhost:18080 | 开发调试 | `python -m mock_javis_api` |
| Real API | javis-db.example.com | 真实API集成测试 | use_mock=false |
| Javis Agent | localhost:8000 | 端到端测试 | `docker-compose up -d` |

### 1.2 前置条件检查

```bash
# 检查Docker环境
docker ps | grep mysql

# 检查Ollama服务
curl http://localhost:11434/api/version

# 检查Mock API
curl http://localhost:18080/health

# 检查.env配置（API Key / OAuth2）
cat ~/.openclaw/workspace/.env | grep JAVIS

# 检查测试数据库数据
mysql -h localhost -P 3307 -uroot -ptest123 -e "SHOW DATABASES;"
```

---

## 二、测试用例统计

| 类别 | P0用例数 | P1用例数 | P2用例数 | 小计 |
|------|----------|----------|----------|------|
| BackupAgent | 10 | 5 | 1 | 16 |
| PerformanceAgent | 9 | 3 | 0 | 12 |
| Intent路由 | 8 | 7 | 0 | 15 |
| 认证鉴权 | 7 | 3 | 0 | 10 |
| 多租户隔离 | 5 | 2 | 0 | 7 |
| 端到端 | 6 | 4 | 0 | 10 |
| **合计** | **45** | **24** | **1** | **70** |

---

## 三、测试轮次安排

### Round 1: 核心功能测试 (BackupAgent + PerformanceAgent)

**执行时间**: ~60分钟
**执行方式**: `pytest tests/v1.5/validation/ -k "BAK-0 or PERF-0" -v`

#### 1.1 BackupAgent 基础功能 (BAK-001 ~ BAK-010)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| BAK-001 | MySQL备份状态 | `pytest -k BAK-001` | 返回db_type=MySQL, backup_enabled字段 |
| BAK-002 | PG备份状态 | `pytest -k BAK-002` | 返回backup_method=pg_basebackup+WAL |
| BAK-003 | MySQL备份历史 | `pytest -k BAK-003` | 返回limit=3条记录 |
| BAK-004 | PG备份历史 | `pytest -k BAK-004` | 返回limit=7条记录 |
| BAK-005 | 触发MySQL备份 | `pytest -k BAK-005` | 返回backup_id, status非空 |
| BAK-006 | 触发PG备份 | `pytest -k BAK-006` | 返回backup_id |
| BAK-007 | MySQL恢复时间估算 | `pytest -k BAK-007` | 返回estimated_minutes |
| BAK-008 | PG恢复时间估算 | `pytest -k BAK-008` | 返回estimated_minutes |
| BAK-009 | MySQL策略建议 | `pytest -k BAK-009` | 返回backup_method, retention, schedule |
| BAK-010 | PG策略建议 | `pytest -k BAK-010` | 返回策略建议列表 |

#### 1.2 PerformanceAgent 基础功能 (PERF-001 ~ PERF-010)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| PERF-001 | MySQL TopSQL | `pytest -k PERF-001` | 返回sql, execution_count, avg_time |
| PERF-002 | PG TopSQL | `pytest -k PERF-002` | 返回TopSQL列表 |
| PERF-003 | TopSQL自定义数量 | `pytest -k PERF-003` | 返回limit=10条 |
| PERF-004 | MySQL执行计划 | `pytest -k PERF-004` | 返回analysis, estimated_cost |
| PERF-005 | PG执行计划 | `pytest -k PERF-005` | 返回执行计划 |
| PERF-006 | MySQL参数调优 | `pytest -k PERF-006` | 返回参数建议列表 |
| PERF-007 | PG参数调优 | `pytest -k PERF-007` | 返回参数建议列表 |
| PERF-008 | MySQL完整分析 | `pytest -k PERF-008` | 返回综合报告(backup+performance+capacity) |
| PERF-009 | PG完整分析 | `pytest -k PERF-009` | 返回综合报告 |
| PERF-010 | 无慢SQL场景 | `pytest -k PERF-010` | 返回空列表或提示 |

#### 1.3 Round 1 输出

- ✅ 全部通过的用例 → 进入Round 3
- ❌ 失败的用例 → 记录BUG → 进入Round 4

---

### Round 2: 认证与安全测试

**执行时间**: ~45分钟
**执行方式**: `pytest tests/v1.5/validation/ -k "AUTH-0 or TENANT-0" -v`

#### 2.1 认证鉴权 (AUTH-001 ~ AUTH-010)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| AUTH-001 | 正确API Key | `pytest -k AUTH-001` | 返回200 |
| AUTH-002 | 错误API Key | `pytest -k AUTH-002` | 返回401 |
| AUTH-003 | OAuth2获取Token | `pytest -k AUTH-003` | 返回有效access_token |
| AUTH-004 | OAuth2刷新Token | `pytest -k AUTH-004` | 返回新access_token |
| AUTH-005 | 过期Token | `pytest -k AUTH-005` | 返回401 |
| AUTH-006 | 无认证访问 | `pytest -k AUTH-006` | 返回401 |
| AUTH-007 | Token过期自动刷新 | `pytest -k AUTH-007` | 自动刷新成功 |
| AUTH-008 | API Key+OAuth2混合 | `pytest -k AUTH-008` | API Key优先 |
| AUTH-009 | Scope权限控制 | `pytest -k AUTH-009` | 返回403 |
| AUTH-010 | 认证日志审计 | `pytest -k AUTH-010` | 日志包含完整字段 |

#### 2.2 多租户隔离 (TENANT-001 ~ TENANT-007)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| TENANT-001 | 租户A数据访问 | `pytest -k TENANT-001` | 仅返回租户A数据 |
| TENANT-002 | 租户B隔离 | `pytest -k TENANT-002` | 无权访问租户A数据 |
| TENANT-003 | 租户A备份 | `pytest -k TENANT-003` | 仅返回租户A备份 |
| TENANT-004 | 租户B性能 | `pytest -k TENANT-004` | 仅返回租户B性能 |
| TENANT-005 | 跨租户数据泄露 | `pytest -k TENANT-005` | 返回403或空 |
| TENANT-006 | 租户会话隔离 | `pytest -k TENANT-006` | 正确拒绝 |
| TENANT-007 | 租户配额管理 | `pytest -k TENANT-007` | 返回配额超限 |

#### 2.3 Round 2 输出

- ✅ 全部通过 → 进入Round 3
- ❌ 安全问题 → **立即上报**, 修复后重新验证

---

### Round 3: 集成测试

**执行时间**: ~90分钟
**执行方式**: `pytest tests/v1.5/validation/ -k "ROUTE-0 or E2E-0" -v`

#### 3.1 意图路由 (ROUTE-001 ~ ROUTE-015)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| ROUTE-001 | 备份查询路由 | `pytest -k ROUTE-001` | intent=ANALYZE_BACKUP |
| ROUTE-002 | 性能查询路由 | `pytest -k ROUTE-002` | intent=ANALYZE_PERFORMANCE |
| ROUTE-003 | 混合查询路由 | `pytest -k ROUTE-003` | 同时触发两个Agent |
| ROUTE-004 | MySQL备份意图 | `pytest -k ROUTE-004` | intent=ANALYZE_BACKUP |
| ROUTE-005 | PG性能意图 | `pytest -k ROUTE-005` | intent=ANALYZE_PERFORMANCE |
| ROUTE-006 | 模糊意图-备份 | `pytest -k ROUTE-006` | intent=ANALYZE_BACKUP |
| ROUTE-007 | 模糊意图-性能 | `pytest -k ROUTE-007` | intent=ANALYZE_PERFORMANCE |
| ROUTE-008 | 异常意图兜底 | `pytest -k ROUTE-008` | 降级到GENERAL |
| ROUTE-009 | 告警诊断路由 | `pytest -k ROUTE-009` | intent=DIAGNOSE |
| ROUTE-010 | SQL分析路由 | `pytest -k ROUTE-010` | intent=SQL_ANALYZE |
| ROUTE-011 | 容量分析路由 | `pytest -k ROUTE-011` | intent=ANALYZE_CAPACITY |
| ROUTE-012 | 健康巡检路由 | `pytest -k ROUTE-012` | intent=INSPECT |
| ROUTE-013 | 会话分析路由 | `pytest -k ROUTE-013` | intent=ANALYZE_SESSION |
| ROUTE-014 | 风险评估路由 | `pytest -k ROUTE-014` | intent=RISK_ASSESS |
| ROUTE-015 | 多Agent协同 | `pytest -k ROUTE-015` | 触发多Agent |

#### 3.2 端到端场景 (E2E-001 ~ E2E-010)

| 用例ID | 场景 | 执行命令 | 通过标准 |
|--------|------|----------|----------|
| E2E-001 | MySQL完整巡检 | `pytest -k E2E-001` | 返回综合报告 |
| E2E-002 | PG完整巡检 | `pytest -k E2E-002` | 返回综合报告 |
| E2E-003 | 备份恢复演练 | `pytest -k E2E-003` | 备份成功+时间估算 |
| E2E-004 | 多轮对话 | `pytest -k E2E-004` | 上下文保持 |
| E2E-005 | Agent降级 | `pytest -k E2E-005` | 优雅降级 |
| E2E-006 | LLM+工具混合 | `pytest -k E2E-006` | 意图+工具正确 |
| E2E-007 | Real API MySQL | `pytest -k E2E-007` | 真实MySQL数据 |
| E2E-008 | Real API PG | `pytest -k E2E-008` | 真实PG数据 |
| E2E-009 | Mock/Real切换 | `pytest -k E2E-009` | 模式正确切换 |
| E2E-010 | 会话持久化 | `pytest -k E2E-010` | 会话恢复 |

#### 3.3 Round 3 输出

- ✅ 全部通过 → 进入V1.5 Release
- ❌ 发现问题 → 进入Round 4

---

### Round 4: 问题修复验证

**执行时间**: ~60分钟
**执行方式**: 针对性回归测试

#### 4.1 BUG修复验证

| BUG编号 | 描述 | 对应用例 | 验证方式 |
|---------|------|----------|----------|
| BUG-001 | [Round 1发现的BUG] | 对应失败的用例 | 重新执行该用例 |
| BUG-002 | [Round 2发现的BUG] | 对应失败的用例 | 重新执行 |
| BUG-003 | [Round 3发现的BUG] | 对应失败的用例 | 重新执行 |

#### 4.2 回归测试

```bash
# 执行Round 1-3中失败的用例
pytest tests/v1.5/validation/ -k "failed_cases" -v

# 执行关键P0用例全量回归
pytest tests/v1.5/validation/ -k "P0" -v
```

#### 4.3 性能基准验证

| 指标 | 基准 | 实际值 | 状态 |
|------|------|--------|------|
| BackupAgent响应时间 | <2s | 待测 | - |
| PerformanceAgent响应时间 | <3s | 待测 | - |
| 意图路由准确率 | >95% | 待测 | - |
| API认证响应时间 | <500ms | 待测 | - |

---

## 四、执行脚本

### 4.1 一键执行所有测试

```bash
#!/bin/bash
# tests/v1.5/validation/run_all.sh

set -e

cd /Users/chongjieran/SWproject/Javis-DB-Agent

echo "=== V1.5 测试验证开始 ==="
echo "时间: $(date)"

# Round 1: 核心功能
echo ">>> Round 1: 核心功能测试"
pytest tests/v1.5/validation/ -k "BAK-0 or PERF-0" -v --tb=short || echo "Round 1 有失败用例"

# Round 2: 认证与安全
echo ">>> Round 2: 认证与安全测试"
pytest tests/v1.5/validation/ -k "AUTH-0 or TENANT-0" -v --tb=short || echo "Round 2 有失败用例"

# Round 3: 集成测试
echo ">>> Round 3: 集成测试"
pytest tests/v1.5/validation/ -k "ROUTE-0 or E2E-0" -v --tb=short || echo "Round 3 有失败用例"

echo "=== V1.5 测试验证完成 ==="
```

### 4.2 执行特定Round

```bash
# Round 1
pytest tests/v1.5/validation/ -k "BAK-0 or PERF-0" -v

# Round 2
pytest tests/v1.5/validation/ -k "AUTH-0 or TENANT-0" -v

# Round 3
pytest tests/v1.5/validation/ -k "ROUTE-0 or E2E-0" -v

# Round 4 (修复后)
pytest tests/v1.5/validation/ -k "BUG-001 or BUG-002 or BUG-003" -v
```

---

## 五、测试报告模板

### 5.1 Round执行报告格式

```markdown
# V1.5 Round X 测试报告

## 执行信息
- 执行时间: YYYY-MM-DD HH:MM ~ HH:MM
- 执行环境: [环境描述]
- 执行人: SC Agent

## 测试结果汇总
| 用例类别 | 通过 | 失败 | 跳过 | 合计 |
|----------|------|------|------|------|
| BackupAgent | 12 | 2 | 1 | 15 |
| PerformanceAgent | 8 | 0 | 0 | 8 |
| ... | ... | ... | ... | ... |

## 失败用例详情
| 用例ID | 失败原因 | 严重程度 | 修复建议 |
|--------|----------|----------|----------|
| BAK-005 | [原因] | P0 | [建议] |

## 下一步行动
- [ ] 修复BAK-005
- [ ] 重新验证ROUND X
```

### 5.2 最终报告格式

```markdown
# V1.5 最终测试报告

## 测试概览
- 总用例数: 70
- 通过数: XX
- 失败数: XX
- 通过率: XX%

## V1.4功能覆盖
| 功能模块 | 用例数 | 覆盖率 | 状态 |
|----------|--------|--------|------|
| BackupAgent | 16 | 100% | ✅ |
| PerformanceAgent | 12 | 100% | ✅ |
| Intent路由 | 15 | 100% | ✅ |
| 认证鉴权 | 10 | 100% | ✅ |
| 多租户隔离 | 7 | 100% | ✅ |
| 端到端 | 10 | 100% | ✅ |

## 发布建议
- [ ] P0用例全部通过 → 可发布
- [ ] 有P0失败 → 阻塞发布
```

---

## 六、风险与注意事项

### 6.1 已知风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 真实PostgreSQL环境未部署 | PG用例无法执行 | 使用Mock API补充 |
| OAuth2服务器不可用 | AUTH-003~005无法执行 | 使用Mock认证 |
| 网络延迟导致超时 | 测试不稳定 | 增加timeout配置 |
| 测试数据污染 | 隔离性测试失败 | 使用独立测试DB |

### 6.2 注意事项

1. **并发测试**：BAK-015、PERF-011等并发用例需确保测试环境资源充足
2. **数据隔离**：每个租户测试前后清理数据
3. **Token刷新**：AUTH-004、AUTH-007需注意Token有效期
4. **会话持久化**：E2E-010需独立测试环境避免干扰

---

## 七、产出物清单

| 产出物 | 路径 | 说明 |
|--------|------|------|
| 测试用例CSV | `tests/v1.5/validation/test_cases_v1.5.csv` | 70个用例 |
| 测试计划 | `tests/v1.5/validation/test_plan_v1.5.md` | 本文档 |
| Round 1报告 | `tests/v1.5/validation/reports/round1_report.md` | 待生成 |
| Round 2报告 | `tests/v1.5/validation/reports/round2_report.md` | 待生成 |
| Round 3报告 | `tests/v1.5/validation/reports/round3_report.md` | 待生成 |
| Round 4报告 | `tests/v1.5/validation/reports/round4_report.md` | 待生成 |
| 最终报告 | `tests/v1.5/validation/reports/final_report.md` | 待生成 |

---

*最后更新: 2026-03-30*
*版本: v1.5*

---

## 八、DFX深度测试轮次安排

> V1.5.1 新增 - 从DFX维度进行苏格拉底式深入分析

### 8.1 DFX测试维度定义

| 维度 | 名称 | 关注点 |
|------|------|--------|
| F | 功能测试 | 功能完整性、边界条件、错误处理、逆向测试 |
| P | 性能测试 | 响应时间、并发能力、资源占用、极限测试 |
| R | 可靠性测试 | 容错能力、恢复能力、幂等性、超时处理 |
| M | 可维护性测试 | 可观测性、诊断能力、可配置性 |
| S | 安全测试 | 认证授权、SQL注入、数据隔离、敏感信息 |
| A | 审计测试 | 操作记录、审计链、可追溯、合规性 |

### 8.2 DFX测试用例统计

| 类别 | F | P | R | M | S | A | 小计 |
|------|---|---|---|---|---|---|------|
| BackupAgent | 18 | 5 | 5 | 3 | 7 | 3 | 41 |
| PerformanceAgent | 7 | 2 | 2 | 0 | 3 | 1 | 15 |
| Intent路由 | 6 | 0 | 3 | 0 | 3 | 1 | 13 |
| 认证鉴权 | 0 | 0 | 2 | 0 | 6 | 3 | 11 |
| 多租户隔离 | 2 | 0 | 0 | 0 | 4 | 1 | 7 |
| 端到端 | 4 | 3 | 4 | 0 | 1 | 1 | 13 |
| **合计** | **37** | **10** | **16** | **3** | **24** | **10** | **100** |

### 8.3 DFX测试轮次

#### Round 5: DFX-功能测试 (F)

**执行时间**: ~60分钟
**执行方式**: `pytest tests/v1.5/validation/test_cases_dfx.py -k "F" -v`

| 用例ID | 场景 | 通过标准 |
|--------|------|----------|
| BAK-F-001~018 | BackupAgent功能测试 | 18个用例通过 |
| PERF-F-001~017 | PerformanceAgent功能测试 | 15个用例通过 |
| ROUTE-F-001~013 | Intent路由功能测试 | 13个用例通过 |

#### Round 6: DFX-性能测试 (P)

**执行时间**: ~45分钟
**执行方式**: `pytest tests/v1.5/validation/test_cases_dfx.py -k "P" -v --timeout=120`

| 用例ID | 场景 | 通过标准 |
|--------|------|----------|
| BAK-P-001~005 | BackupAgent性能测试 | 响应时间符合预期 |
| PERF-P-001~003 | PerformanceAgent性能测试 | 响应时间符合预期 |
| E2E-P-001~003 | 端到端性能测试 | 真实API响应合理 |

#### Round 7: DFX-可靠性测试 (R)

**执行时间**: ~60分钟
**执行方式**: `pytest tests/v1.5/validation/test_cases_dfx.py -k "R" -v`

| 用例ID | 场景 | 通过标准 |
|--------|------|----------|
| BAK-R-001~009 | BackupAgent可靠性测试 | 容错、恢复、幂等性 |
| PERF-R-001~006 | PerformanceAgent可靠性测试 | 解析容错、权限处理 |
| ROUTE-R-001~005 | Intent路由可靠性测试 | LLM降级、截断处理 |

#### Round 8: DFX-安全测试 (S)

**执行时间**: ~90分钟
**执行方式**: `pytest tests/v1.5/validation/test_cases_dfx.py -k "S" -v`

| 用例ID | 场景 | 通过标准 |
|--------|------|----------|
| BAK-S-001~008 | BackupAgent安全测试 | SQL注入防护、租户隔离 |
| PERF-S-001~005 | PerformanceAgent安全测试 | UNION注入、大SQL限制 |
| ROUTE-S-001~005 | Intent路由安全测试 | 提示注入防护 |
| AUTH-S-001~010 | 认证鉴权安全测试 | Token伪造检测、限流 |
| TENANT-S-001~005 | 多租户安全测试 | 跨租户隔离 |

#### Round 9: DFX-审计测试 (A)

**执行时间**: ~30分钟
**执行方式**: `pytest tests/v1.5/validation/test_cases_dfx.py -k "A" -v`

| 用例ID | 场景 | 通过标准 |
|--------|------|----------|
| BAK-A-001~005 | BackupAgent审计测试 | 审计记录完整 |
| PERF-A-001~004 | PerformanceAgent审计测试 | SQL历史记录 |
| ROUTE-A-001~002 | Intent路由审计测试 | 路由记录完整 |
| AUTH-A-001~005 | 认证鉴权审计测试 | 登录/登出审计 |

### 8.4 DFX测试执行脚本

```bash
#!/bin/bash
# tests/v1.5/validation/run_dfx_tests.sh

set -e
cd /Users/chongjieran/SWproject/Javis-DB-Agent

echo "=== V1.5 DFX深度测试开始 ==="
echo "时间: $(date)"

# Round 5: 功能测试
echo ">>> Round 5: DFX-功能测试 (F)"
pytest tests/v1.5/validation/test_cases_dfx.py -k "F" -v --tb=short || echo "功能测试有失败"

# Round 6: 性能测试
echo ">>> Round 6: DFX-性能测试 (P)"
pytest tests/v1.5/validation/test_cases_dfx.py -k "P" -v --tb=short --timeout=120 || echo "性能测试有失败"

# Round 7: 可靠性测试
echo ">>> Round 7: DFX-可靠性测试 (R)"
pytest tests/v1.5/validation/test_cases_dfx.py -k "R" -v --tb=short || echo "可靠性测试有失败"

# Round 8: 安全测试
echo ">>> Round 8: DFX-安全测试 (S)"
pytest tests/v1.5/validation/test_cases_dfx.py -k "S" -v --tb=short || echo "安全测试有失败"

# Round 9: 审计测试
echo ">>> Round 9: DFX-审计测试 (A)"
pytest tests/v1.5/validation/test_cases_dfx.py -k "A" -v --tb=short || echo "审计测试有失败"

echo "=== V1.5 DFX深度测试完成 ==="
```

### 8.5 DFX测试报告模板

```markdown
# V1.5 DFX测试报告

## 执行信息
- 执行时间: YYYY-MM-DD HH:MM ~ HH:MM
- 执行环境: [环境描述]
- 执行人: SC Agent

## DFX测试结果汇总
| 维度 | 通过 | 失败 | 跳过 | 合计 | 通过率 |
|------|------|------|------|------|--------|
| F-功能 | XX | XX | XX | XX | XX% |
| P-性能 | XX | XX | XX | XX | XX% |
| R-可靠性 | XX | XX | XX | XX | XX% |
| M-可维护性 | XX | XX | XX | XX | XX% |
| S-安全 | XX | XX | XX | XX | XX% |
| A-审计 | XX | XX | XX | XX | XX% |
| **合计** | **XX** | **XX** | **XX** | **100** | **XX%** |

## 失败用例详情
| 用例ID | 维度 | 失败原因 | 严重程度 | 修复建议 |
|--------|------|----------|----------|----------|
| BAK-F-001 | F | [原因] | P0 | [建议] |

## 苏格拉底式深入分析
### 发现的问题
1. [深入分析问题本质]
2. [分析问题根因]

### 改进建议
1. [从DFX角度提出改进]
```

---

*最后更新: 2026-03-30*
*版本: v1.5.1 (DFX深度测试)*
