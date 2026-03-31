# V2.1 Round 2 — 测试报告

**测试者**: 真显
**执行时间**: 2026-03-31
**轮次**: V2.1 Round 2

---

## 执行摘要

| 项目 | 结果 |
|------|------|
| 测试文件 | `tests/v2.0/test_v21_verification.py` |
| 总测试数 | 22 |
| 通过 | 22 |
| 失败 | 0 |
| 跳过 | 0 |
| 通过率 | **100%** |

### 回归测试
| 测试文件 | 通过 | 跳过 | 失败 |
|----------|------|------|------|
| `test_security_layer.py` | 39 | 8 | 0 |

---

## Bug修复验证

### 1. UNION注入Bug修复 ✅

| SQL | 预期 | 实际 | 状态 |
|-----|------|------|------|
| `SELECT 1 UNION SELECT password FROM users` | 拒绝 | 拒绝 (blocked_reason: 检测到UNION注入) | ✅ |
| `SELECT 1 UNION ALL SELECT 2 FROM users` | 放行 | 放行 (risk=L2) | ✅ |
| `SELECT 1 UNION SELECT 2 UNION SELECT 3 FROM users` | 拒绝 | 拒绝 (blocked_reason: 检测到UNION注入) | ✅ |

**修复方式**: 在 `sql_guard.py` 中使用 `union_count > union_all_count` 判断，区分安全的 `UNION ALL` 和危险的 `UNION`。

---

### 2. is_read_only()扩展 ✅

| SQL | 预期 | 实际 | 状态 |
|-----|------|------|------|
| `EXPLAIN SELECT * FROM orders` | 只读 | 只读=True | ✅ |
| `VACUUM orders` | 只读 | 只读=True | ✅ |
| `ANALYZE orders` | 只读 | 只读=True | ✅ |
| `EXPLAIN ANALYZE SELECT * FROM orders` | 非只读 | 非只读=False | ✅ |
| `SET work_mem = '256MB'` | 非只读 | 非只读=False | ✅ |

**修复方式**:
1. 在 `ast_parser.py` 的 `is_read_only()` 中添加 `exp.Analyze` 到 `readonly_types` 元组，使 `ANALYZE orders` 识别为只读
2. 调整 `is_read_only()` 中的 `non_readonly` 检查优先级（先检查非只读模式）
3. 在 `sql_guard.py` 中调整校验顺序，非只读命令（如 `EXPLAIN ANALYZE`）跳过白名单

---

### 3. 白名单正则改进 ✅

| SQL | 预期 | 实际 | 状态 |
|-----|------|------|------|
| `SELECT * FROM public.orders` | 匹配白名单 L1 | 放行 L1 | ✅ |
| `SELECT * FROM "User"` | 匹配白名单 L1 | 放行 L1 | ✅ |
| `SELECT * FROM schema.table WHERE id = 1` | 匹配白名单 L1 | 放行 L1 | ✅ |

**修复方式**: 白名单正则 `[\w\"\`\.]+` 原生支持 `schema.table` 格式（`.` 在字符类中）和带引号表名（如 `"User"`）。

---

### 4. pg_explain正则 ✅

| SQL | 预期 | 实际 | 状态 |
|-----|------|------|------|
| `EXPLAIN SELECT * FROM orders` | 匹配 L1 | 放行 L1 | ✅ |
| `EXPLAIN (ANALYZE) SELECT * FROM orders` | 匹配 L1 | 放行 L1 | ✅ |
| `EXPLAIN (FORMAT JSON) SELECT * FROM orders` | 匹配 L1 | 放行 L1 | ✅ |
| `EXPLAIN ANALYZE SELECT * FROM orders` | 非只读 L2 | 放行 L2 | ✅ |

**修复方式**: 正则 `EXPLAIN(\s+\([^)]*\))?\s+.+` 不强制要求 `FORMAT`，可选的 `(\s+\([^)]*\))?` 支持 `(ANALYZE)`、`(FORMAT JSON)` 等各种选项。

---

## 代码修改摘要

### `src/security/sql_guard/ast_parser.py`

```python
# 修复1: 添加 exp.Analyze 到只读类型
readonly_types = (
    exp.Select,
    exp.Show,
    exp.Subquery,
    exp.Table,
    exp.Analyze,  # ANALYZE orders (PostgreSQL statistics collection)
)

# 修复2: 调整非只读检查优先级（先检查非只读）
if isinstance(ast_node, exp.Command):
    cmd_upper = sql.strip().upper()
    non_readonly = {"EXPLAIN ANALYZE", "SET", "RESET"}
    if any(cmd_upper.startswith(n) for n in non_readonly):
        return False  # 先排除非只读
    readonly_commands = {"EXPLAIN", "VACUUM", "ANALYZE"}
    if any(cmd_upper.startswith(c) for c in readonly_commands):
        return True
```

### `src/security/sql_guard/sql_guard.py`

```python
# 修复3: 调整校验顺序，非只读命令跳过白名单
cmd_upper = sql_stripped.upper()
non_readonly_patterns = ("EXPLAIN ANALYZE", "SET ", "RESET ")
if not any(cmd_upper.startswith(p) for p in non_readonly_patterns):
    is_whitelisted, matched_template = self.template_registry.is_whitelisted(...)
    if is_whitelisted and matched_template:
        return SQLGuardResult(...)  # 白名单L0/L1
```

---

## 回归测试结果

```
tests/v2.0/test_security_layer.py
================== 39 passed, 8 skipped, 1 warning in 50.05s ===================
```

所有现有测试无回归。

---

## 建议

✅ **V2.1 Round 2 修复验证通过，建议合并到主分支**

---

*报告生成: 真显 | 2026-03-31*
