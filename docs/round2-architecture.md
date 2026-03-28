# zCloudNewAgentProject 第二轮架构调整

> 版本：v2.0 | 日期：2026-03-28 | 状态：执行中

---

## 1. 第一轮不足分析

### 1.1 知识库严重不足
- ❌ 告警规则仅有3条，远不足以覆盖zCloud常见告警场景
- ❌ SOP库仅有2个，缺少完整覆盖
- ❌ 案例库为空，无法进行案例推理
- ❌ 运维知识库（基础知识）缺失

**影响**：Agent推理质量低，知识匹配命中不足

### 1.2 缺失关键工具（6个）
| 缺失工具 | 影响场景 | 优先级 |
|----------|----------|--------|
| query_disk_usage | 容量不足处理 | P0 |
| query_parameters | 参数与配置风险 | P0 |
| query_top_sql | 慢SQL/锁分析 | P0 |
| query_ha_status | 复制/HA状态 | P0 |
| get_inspection_result | 巡检与健康治理 | P1 |
| query_config_deviation | 参数与配置风险 | P1 |

### 1.3 zCloud API未Mock
- ❌ 无zCloud API接口定义
- ❌ 所有工具使用硬编码模拟数据
- ❌ 无法验证真实API适配性

### 1.4 Ollama未验证
- ❌ config.yaml配置`glm4:latest`，tech-spec说`qwen3.5`
- ❌ 未用真实Ollama测试推理质量
- ❌ 未确认64GB显存下的模型选择

---

## 2. 第二轮架构调整

### 2.1 知识库结构（完整设计）

```
knowledge/
├── alert_rules.yaml       # 告警规则库（扩展至15+条）
├── basics/                # 运维基础知识
│   ├── oracle基础知识.md
│   └── postgresql基础知识.md
├── sop/                   # SOP/Runbook库（扩展至8+个）
│   ├── 慢SQL分析.md
│   ├── lock_wait排查.md
│   ├── 巡检标准流程.md
│   ├── 性能瓶颈排查.md
│   ├── 主从延迟诊断.md
│   ├── 连接数打满处理.md
│   ├── 容量不足处理.md
│   └── HA切换处理.md
└── cases/                 # 历史案例库（新建，3+案例）
    ├── 2026-01-锁等待故障.md
    ├── 2026-02-慢SQL风暴.md
    └── 2026-03-主从延迟.md
```

### 2.2 告警规则扩展（15条核心规则）

| 告警代码 | 名称 | 风险级别 |
|----------|------|----------|
| LOCK_WAIT_TIMEOUT | 锁等待超时 | L3 |
| SLOW_QUERY_DETECTED | 慢SQL告警 | L2 |
| REPLICATION_LAG | 主从延迟告警 | L3 |
| CPU_USAGE_HIGH | CPU使用率过高 | L2 |
| MEMORY_USAGE_HIGH | 内存使用率过高 | L3 |
| DISK_USAGE_HIGH | 磁盘使用率过高 | L3 |
| DISK_IO_HIGH | 磁盘IO过高 | L2 |
| CONNECTION_FULL | 连接数打满 | L4 |
| SESSION_LEAK | 会话泄漏 | L3 |
| BACKUP_FAILED | 备份失败 | L3 |
| HA_SWITCH_TRIGGERED | HA切换触发 | L4 |
| ARCHIVE_AREA_FULL | 归档空间满 | L4 |
| LOG_SWITCH_FREQUENT | 日志切换频繁 | L2 |
| PARAMETER_CHANGED | 参数变更 | L3 |
| SLOW_DISK_WRITE | 磁盘写入慢 | L2 |

### 2.3 工具层扩展（新增6个）

```python
# 6个缺失工具
MissingTool = {
    "query_disk_usage":      "查询磁盘/表空间使用率",
    "query_parameters":     "查询数据库参数配置",
    "query_top_sql":        "查询Top SQL（CPU/IO/逻辑读）",
    "query_ha_status":       "查询HA/主备状态",
    "get_inspection_result": "获取巡检结果",
    "query_config_deviation": "查询配置偏差"
}
```

### 2.4 zCloud API Mock接口设计

```
mock_zcloud_api/
├── server.py              # Mock API Server (FastAPI)
├── routers/
│   ├── instances.py       # /api/v1/instances
│   ├── alerts.py          # /api/v1/alerts
│   ├── sessions.py        # /api/v1/sessions
│   ├── locks.py           # /api/v1/locks
│   ├── sqls.py            # /api/v1/sqls
│   ├── replication.py     # /api/v1/replication
│   ├── parameters.py      # /api/v1/parameters
│   ├── capacity.py        # /api/v1/capacity
│   ├── inspection.py      # /api/v1/inspection
│   └── workorders.py       # /api/v1/workorders
└── mock_data/
    └── fixtures.yaml      # Mock数据
```

**Mock接口清单（12个）**：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/instances/{id}` | GET | 实例状态 |
| `/api/v1/alerts/{id}` | GET | 告警详情 |
| `/api/v1/sessions` | GET | 会话列表 |
| `/api/v1/locks` | GET | 锁等待 |
| `/api/v1/sqls/slow` | GET | 慢SQL |
| `/api/v1/sqls/top` | GET | Top SQL |
| `/api/v1/sqls/{id}/plan` | GET | 执行计划 |
| `/api/v1/replication` | GET | 复制状态 |
| `/api/v1/parameters` | GET | 参数配置 |
| `/api/v1/capacity/disk` | GET | 磁盘/表空间 |
| `/api/v1/inspection/{task_id}` | GET | 巡检结果 |
| `/api/v1/workorders` | POST | 创建工单 |

---

## 3. Ollama验证方案

### 3.1 可用模型确认
```
glm4:latest (5.4GB, Q4_0, 9.4B) ← 当前配置
qwen3:30b-a3b (18.6GB) ← tech-spec目标
```

### 3.2 验证测试用例
1. **告警诊断推理**：输入告警，验证知识匹配准确性
2. **根因分析质量**：验证诊断置信度和路径合理性
3. **工具调用准确性**：验证Agent是否正确选择工具
4. **上下文利用**：验证Agent能否结合平台数据推理

---

## 4. 执行分工

| 执行方 | 任务 |
|--------|------|
| 悟通 | 知识库扩展（告警规则+SOP+案例）+ 6个缺失工具实现 + zCloud Mock API |
| 真显 | 测试用例准备 + Mock数据准备 + 验证测试 |

---

*状态：执行中，待悟通和真显接手*
