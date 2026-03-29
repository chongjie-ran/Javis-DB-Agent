# Javis-DB-Agent 第二轮执行计划

> 版本：v1.0 | 日期：2026-03-28 | 状态：待执行

---

## 第二轮任务清单

### 任务A：知识库内容补充 ✅ 已完成

| 文件 | 状态 | 说明 |
|------|------|------|
| `knowledge/alert_rules.yaml` | ✅ 已扩展 | 15条告警规则（原有3条） |
| `knowledge/sop/巡检标准流程.md` | ✅ 已新增 | 完整巡检SOP |
| `knowledge/sop/性能瓶颈排查.md` | ✅ 已新增 | 性能诊断SOP |
| `knowledge/sop/主从延迟诊断.md` | ✅ 已新增 | 主从延迟处理SOP |
| `knowledge/sop/连接数打满处理.md` | ✅ 已新增 | 连接数问题SOP |
| `knowledge/sop/容量不足处理.md` | ✅ 已新增 | 容量管理SOP |
| `knowledge/sop/HA切换处理.md` | ✅ 已新增 | HA切换SOP |
| `knowledge/cases/2026-01-15-锁等待故障.md` | ✅ 已新增 | 案例1 |
| `knowledge/cases/2026-02-20-慢SQL风暴.md` | ✅ 已新增 | 案例2 |
| `knowledge/cases/2026-03-10-主从延迟.md` | ✅ 已新增 | 案例3 |

### 任务B：接入真实Ollama验证 ✅ 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| Ollama健康检查 | ✅ 通过 | glm4:latest, qwen3:30b-a3b 可用 |
| 推理质量测试 | ✅ 通过 | 基本推理能力验证通过 |
| 验证脚本 | ✅ 已创建 | `scripts/verify_ollama.py` |

### 任务C：补充6个缺失工具 ✅ 已完成

| 工具名 | 状态 | 说明 |
|--------|------|------|
| query_disk_usage | ✅ 已实现 | 磁盘/表空间使用率 |
| query_parameters | ✅ 已实现 | 数据库参数配置 |
| query_top_sql | ✅ 已实现 | Top SQL查询 |
| query_ha_status | ✅ 已实现 | HA/主备状态 |
| get_inspection_result | ✅ 已实现 | 巡检结果获取 |
| query_config_deviation | ✅ 已实现 | 配置偏差查询 |

### 任务D：Mock Javis-DB-Agent API接口 ✅ 已完成

| 组件 | 状态 | 说明 |
|------|------|------|
| `mock_javis_api/server.py` | ✅ 已创建 | FastAPI主服务 |
| `mock_javis_api/routers/instances.py` | ✅ | /api/v1/instances |
| `mock_javis_api/routers/alerts.py` | ✅ | /api/v1/alerts |
| `mock_javis_api/routers/sessions.py` | ✅ | /api/v1/sessions |
| `mock_javis_api/routers/locks.py` | ✅ | /api/v1/locks |
| `mock_javis_api/routers/sqls.py` | ✅ | /api/v1/sqls |
| `mock_javis_api/routers/replication.py` | ✅ | /api/v1/replication |
| `mock_javis_api/routers/parameters.py` | ✅ | /api/v1/parameters |
| `mock_javis_api/routers/capacity.py` | ✅ | /api/v1/capacity |
| `mock_javis_api/routers/inspection.py` | ✅ | /api/v1/inspection |
| `mock_javis_api/routers/workorders.py` | ✅ | /api/v1/workorders |
| `mock_javis_api/models.py` | ✅ | Pydantic模型+Mock数据 |

---

## 悟通执行清单（续）

### E. Mock API Server 启动验证

```bash
cd ~/SWproject/Javis-DB-Agent
# 启动Mock API Server
python3 -m uvicorn mock_javis_api.server:app --host 0.0.0.0 --port 18080

# 测试接口
curl http://localhost:18080/health
curl http://localhost:18080/api/v1/instances/INS-001
```

### F. Agent与Mock API集成

1. 更新 `src/config.py`，添加 `javis_api_base_url`
2. 创建 `src/tools/javis_client.py`，封装Mock API调用
3. 修改现有工具，从Mock API获取数据（而非硬编码）
4. 测试告警诊断场景：`python3 scripts/verify_ollama.py`

### G. 知识库加载机制

1. 完善 `src/knowledge/__init__.py`
2. 实现 `src/knowledge/alert_rules.py` - 告警规则加载和匹配
3. 实现 `src/knowledge/sop_loader.py` - SOP加载和检索
4. 实现 `src/knowledge/case_loader.py` - 案例加载和匹配

### H. 测试用例补充

由**真显**负责：
1. 编写6个场景的集成测试用例
2. Mock数据补充（更真实的故障场景）
3. Agent响应质量评估标准

---

## Mock API 测试命令

```bash
# 健康检查
curl -s http://localhost:18080/health | python3 -m json.tool

# 实例详情
curl -s http://localhost:18080/api/v1/instances/INS-001 | python3 -m json.tool

# 告警列表
curl -s http://localhost:18080/api/v1/alerts?instance_id=INS-001 | python3 -m json.tool

# 会话列表
curl -s "http://localhost:18080/api/v1/sessions?instance_id=INS-001&limit=5" | python3 -m json.tool

# 慢SQL
curl -s "http://localhost:18080/api/v1/sqls/slow?instance_id=INS-001&limit=5" | python3 -m json.tool

# Top SQL
curl -s "http://localhost:18080/api/v1/sqls/top?instance_id=INS-001&sort_by=cpu" | python3 -m json.tool

# 磁盘使用率
curl -s http://localhost:18080/api/v1/capacity/disk?instance_id=INS-001 | python3 -m json.tool

# 参数配置
curl -s http://localhost:18080/api/v1/parameters?instance_id=INS-001 | python3 -m json.tool

# HA状态
curl -s http://localhost:18080/api/v1/replication?instance_id=INS-001 | python3 -m json.tool

# 配置偏差
curl -s http://localhost:18080/api/v1/capacity/deviation?instance_id=INS-001 | python3 -m json.tool

# 触发巡检
curl -s -X POST "http://localhost:18080/api/v1/inspection?instance_id=INS-001&inspection_type=quick" | python3 -m json.tool

# 创建工单
curl -s -X POST http://localhost:18080/api/v1/workorders \
  -H "Content-Type: application/json" \
  -d '{"title":"测试工单","description":"这是一个测试工单","priority":"medium","instance_id":"INS-001"}' | python3 -m json.tool
```

---

## 架构调整摘要

### 新增文件

```
knowledge/
├── alert_rules.yaml           # 15条规则（扩展）
├── sop/
│   ├── 巡检标准流程.md        # 新增
│   ├── 性能瓶颈排查.md        # 新增
│   ├── 主从延迟诊断.md        # 新增
│   ├── 连接数打满处理.md      # 新增
│   ├── 容量不足处理.md        # 新增
│   └── HA切换处理.md          # 新增
└── cases/
    ├── 2026-01-15-锁等待故障.md  # 新增
    ├── 2026-02-20-慢SQL风暴.md   # 新增
    └── 2026-03-10-主从延迟.md    # 新增

mock_javis_api/               # 新增目录
├── __init__.py
├── server.py                 # FastAPI主服务
├── models.py                 # 数据模型+Mock数据
└── routers/
    ├── instances.py
    ├── alerts.py
    ├── sessions.py
    ├── locks.py
    ├── sqls.py
    ├── replication.py
    ├── parameters.py
    ├── capacity.py
    ├── inspection.py
    └── workorders.py

scripts/
└── verify_ollama.py          # Ollama验证脚本
```

### 新增工具（6个）

| 工具 | 功能 |
|------|------|
| query_disk_usage | 磁盘/表空间使用率 |
| query_parameters | 数据库参数配置 |
| query_top_sql | Top SQL查询 |
| query_ha_status | HA/主备状态 |
| get_inspection_result | 巡检结果获取 |
| query_config_deviation | 配置偏差查询 |

### 更新文件

- `configs/tools.yaml` - 新增6个工具定义
- `configs/config.yaml` - 新增zCloud Mock API配置
- `src/tools/query_tools.py` - 新增6个工具实现
- `docs/round2-architecture.md` - 第二轮架构调整文档

---

*任务分配：悟通负责实现，真显负责测试*
