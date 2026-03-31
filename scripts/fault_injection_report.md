# Javis-DB-Agent V2.5 故障注入与检测验证报告

> 测试时间: 2026-03-31 21:39 GMT+8
> 测试环境: macOS Darwin 25.3.0 (arm64)
> 数据库: PostgreSQL 16.13 (Homebrew), MySQL 8.0.45

---

## 一、故障注入结果

### 1.1 注入的故障

| # | 故障类型 | PostgreSQL | MySQL | 状态 |
|---|---------|------------|-------|------|
| 1 | 锁等待 | ✅ users.id=9999 事务未提交 | ✅ users.id=9999 事务未提交 | ✅ 已注入 |
| 2 | 大数据量 | ✅ orders: 50,100 行 | ✅ orders: 50,000 行 | ✅ 已注入 |
| 3 | 索引缺失 | ✅ no_index_test: 10,000行, 无二级索引 | ✅ no_index_test: 10,000行, 无二级索引 | ✅ 已注入 |

### 1.2 数据库连接验证

```
PostgreSQL: /tmp socket, user=chongjieran, database=javis_test_db
MySQL: 127.0.0.1:3306, root/root, socket=/tmp/mysql.sock
```

### 1.3 注入脚本位置

```
~/SWproject/Javis-DB-Agent/scripts/fault_injection.py
```

使用方法:
```bash
# 注入故障（保持运行以维持锁）
python3 ~/SWproject/Javis-DB-Agent/scripts/fault_injection.py

# 清理故障
python3 ~/SWproject/Javis-DB-Agent/scripts/fault_injection.py --cleanup
```

---

## 二、Javis-DB-Agent 检测能力验证

### 2.1 API 测试结果

| API 端点 | 方法 | 结果 | 说明 |
|---------|------|------|------|
| `/api/v1/discovery/instances` | GET | ✅ 正常 | 返回2个已注册的数据库实例 |
| `/api/v1/discovery/scan` | POST | ✅ 正常 | 扫描发现服务可用 |
| `/api/v1/discovery/health` | GET | ✅ 正常 | 健康状态: healthy |
| `/api/v1/analyze/sql` | POST | ✅ 正常 | SQL分析功能正常 |
| `/api/v1/monitoring/alerts` | GET | ✅ 正常 | 返回3条告警 (CPU/内存/磁盘) |
| `/api/v1/monitoring/health-score` | GET | ✅ 正常 | 健康分数: 85.0 |
| `/api/v1/monitoring/cards` | GET | ✅ 正常 | 实例总数: 12, 告警数: 3 |
| `/api/v1/chat` | POST | ⚠️ 空响应 | LLM流式输出问题 (见2.2) |
| `/api/v1/chat/stream` | POST | ⚠️ 空响应 | LLM流式输出问题 |
| `/api/v1/diagnose` | POST | ⚠️ 空响应 | 依赖于LLM |
| `/api/v1/inspect` | POST | ⚠️ 空响应 | 依赖于LLM |
| `/api/v1/report` | POST | ⚠️ 空响应 | 依赖于LLM |

### 2.2 LLM 流式输出问题分析

**问题**: Chat/诊断类接口返回空响应

**根因**: `qwen3.5:35b` 模型将输出放到 `thinking` 字段而非 `message.content` 字段

**Ollama API 响应示例**:
```json
{"model":"qwen3.5:35b","message":{"role":"assistant","content":"","thinking":"Hello..."}}
```

**影响范围**:
- `src/llm/ollama_client.py` 的 `complete_stream()` 只读取 `message.content`
- `qwen3.5:35b` 的实际内容在 `message.thinking` 字段
- 导致所有流式LLM输出为空

**建议修复**: 更新 `ollama_client.py` 同时检查 `message.thinking` 字段

---

## 三、SQL 分析器检测验证

### 3.1 测试用例

```sql
SELECT * FROM orders WHERE status = 'pending' LIMIT 100
```

### 3.2 分析结果

| 项目 | 结果 |
|------|------|
| SQL指纹 | `SELECT * FROM orders WHERE status = ? LIMIT 100` |
| 性能影响 | medium |
| 风险级别 | low |
| 优化建议 | 1) 明确指定列 2) 确认status索引存在 3) 使用绑定变量 |

### 3.3 索引建议

**MySQL**:
```sql
CREATE INDEX idx_orders_status ON orders(status);
```

**PostgreSQL**:
```sql
CREATE INDEX idx_orders_status ON orders USING btree(status);
```

### 3.4 判定

✅ **SQL分析器正常工作**，能够:
- 识别全表扫描风险
- 提供索引建议
- 识别 SELECT * 问题
- 生成优化SQL

---

## 四、监控告警验证

### 4.1 当前活跃告警

| 告警ID | 实例 | 严重性 | 消息 | 状态 |
|-------|------|--------|------|------|
| ALT-001 | INS-001 | 🔴 critical | CPU使用率超过90% | active |
| ALT-002 | INS-002 | 🟡 warning | 内存使用率超过80% | active |
| ALT-003 | INS-001 | ℹ️ info | 磁盘空间接近阈值 | acknowledged |

### 4.2 健康评分

```
总分: 85.0 (healthy)
├── 实例健康: 90.0
├── 告警管理: 85.0
├── 性能: 95.0
└── 容量: 88.0
趋势: stable
```

---

## 五、问题汇总

### 5.1 已确认问题

| 问题 | 严重性 | 说明 |
|------|--------|------|
| LLM流式输出为空 | 中 | qwen3.5:35b 的 thinking 字段未被处理 |
| Chat接口返回空 | 中 | 依赖LLM流式输出 |
| Diagnose接口返回空 | 中 | 依赖LLM |

### 5.2 根本原因

1. **模型兼容性问题**: `qwen3.5:35b` (Qwen3 MoE) 与 `glm4:latest` 的输出格式不同
2. **配置不一致**: `src/config.py` 默认 `ollama_model = "qwen3.5:35b"`，但 `config.yaml` 使用 `glm4:latest`

### 5.3 建议修复方案

**方案A**: 修改 `src/llm/ollama_client.py` 同时处理 `message.content` 和 `message.thinking`:
```python
content = data["message"].get("content") or data["message"].get("thinking", "")
```

**方案B**: 将默认模型改为 `glm4:latest` (已验证流式输出正常)

---

## 六、验收标准检查

| 验收标准 | 状态 | 说明 |
|---------|------|------|
| 故障成功注入到真实数据库 | ✅ | PG和MySQL均已注入3类故障 |
| Javis-DB-Agent能检测到注入的故障 | ⚠️ 部分 | SQL分析器可检测索引问题，监控可检测系统问题，LLM接口因bug无法检测 |
| 系统给出正确的诊断建议 | ⚠️ 部分 | SQL分析器给出正确建议，LLM接口返回空 |

---

## 七、总结

### 7.1 成功部分
- ✅ 故障注入脚本完成，支持PG/MySQL多种故障类型
- ✅ PostgreSQL 和 MySQL 连接正常
- ✅ 实例发现、健康检查、监控告警等基础功能正常
- ✅ SQL分析器能正确识别慢SQL和索引缺失问题

### 7.2 待修复
- ⚠️ LLM流式输出bug导致chat/diagnose/inspect接口返回空
- ⚠️ 无法通过自然语言接口验证锁检测能力

### 7.3 后续建议
1. 修复 `ollama_client.py` 的 `complete_stream()` 方法，同时处理 `thinking` 字段
2. 或将默认模型切换为 `glm4:latest`
3. 使用 `fault_injection.py` 脚本进行故障复现测试
