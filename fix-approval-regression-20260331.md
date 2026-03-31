# 修复记录：ApprovalGate V2.3 回归 Bug

**日期**: 2026-03-31
**提交**: 8a86040 (v2.3: ApprovalGate migration)
**验收**: `python3 tests/run_tests.py --unit` → **239 passed, 0 failed**

---

## 问题概述

V2.3 commit 8a86040 引入 ApprovalGate 迁移，但 `src/models/approval.py` 中的实现与单元测试期望的 API 存在多处不一致，导致 25 个单元测试失败。

---

## 根因分析

### 1. `ApprovalRecord.__init__` - 必填参数过多

**问题**: `approval_id` 和 `status` 是 required positional 参数，但测试直接用 keyword args 创建实例，期望这两个字段有默认值。

```python
# 测试写法（期望可行）:
record = ApprovalRecord(tool_call_id="call_001", tool_name="kill_session", ...)

# 实际报错:
TypeError: ApprovalRecord.__init__() missing 2 required positional arguments: 'approval_id' and 'status'
```

### 2. `ApprovalRecord.id` 属性缺失

**问题**: 所有测试用 `record.id` 访问审批记录 ID，但实现只有 `approval_id` 字段，无 `id` 属性。

### 3. `ApprovalRecord.is_executable` / `is_terminal` 是方法而非属性

**问题**: 测试直接访问 `record.is_executable`（无括号），期望是布尔属性；实现是 `def is_executable(self) -> bool` 方法。

### 4. `ApprovalRecord` 缺少 `approver1_at`、`reject_reason`、`executor` 等属性

**问题**: 测试访问 `record.approver1_at`、`record.reject_reason`、`record.executor` 等属性，实现中不存在。

### 5. `ApprovalStore.submit` - 无重复提交校验

**问题**: 测试期望重复提交 `tool_call_id` 抛出 `ValueError`，实现无此校验。

### 6. `ApprovalStore.approve2/approve1` - 无状态校验

**问题**: `approve2` 未校验当前状态是否为 `APPROVED1`，`approve1` 未设置 `approver1_at`。

### 7. `ApprovalStore.reject/mark_executed` - 无终态校验

**问题**: `reject` 未校验是否已终态，`mark_executed` 未校验是否为 `APPROVED2`。

### 8. `ApprovalGate.requires_approval` 阈值错误

**问题**: 测试期望 `requires_approval(5)=True, requires_approval(4)=False`，但原实现是 `risk_level >= 4`。

### 9. `ApprovalGate.check_can_execute` 对无记录情况返回错误值

**问题**: 测试期望无记录时返回 `(False, "无审批记录...")`，原实现返回 `(True, None)`。

### 10. `ApprovalGate.check_can_execute` 无法处理已拒绝记录

**问题**: `get_by_tool_call` 过滤掉终态记录，导致已拒绝记录的 `check_can_execute` 返回"无审批记录"而非"审批状态: rejected"。

### 11. `ApprovalGate.request_approval` 不抛出重复异常

**问题**: 测试期望重复提交抛 `ValueError`，原实现静默返回已有记录。

### 12. `src/gateway/approval.py` 缺少 `get_approval_gate` 函数

**问题**: `approval_adapter.py` 的 `get_sync_approval_adapter()` 导入 `get_approval_gate`，但该函数不存在。

---

## 修复内容

### `src/models/approval.py`

#### `ApprovalRecord` 类

- 将 `approval_id` 和 `status` 移至参数列表末尾并设为 `Optional`，默认值由 `__post_init__` 自动填充（UUID 和 PENDING）
- 添加 `@property id` 别名 → `self.approval_id`
- 添加 `@property approver1_at` / `approver1_at=` setter
- 添加 `@property approver2_at` / `approver2_at=` setter
- 添加 `@property executor` / `executor=` setter
- 添加 `@property reject_reason` 别名 → `self.rejection_reason`
- 将 `is_executable` 和 `is_terminal` 从方法改为 `@property`

#### `ApprovalStore` 类

- `submit()`: 增加重复 `tool_call_id` 检查，抛出 `ValueError`；将 `approver1`/`approver2` 存入 `ApprovalRecord`
- `approve1()`: 增加 `approver1_at` 时间戳设置
- `approve2()`: 增加状态校验（非 `APPROVED1` 时抛 `ValueError`）；增加 `approver2_at` 时间戳设置
- `reject()`: 增加终态校验（已终态时抛 `ValueError`）
- `mark_executed()`: 增加状态校验（非 `APPROVED2` 时抛 `ValueError`）；设置 `executor`

#### `ApprovalGate` 类

- `requires_approval()`: 改为 `risk_level == 5`（仅 L5 需要审批）
- `check_can_execute()`: 无记录返回 `(False, "无审批记录...")`；直接遍历 `_records` 查找（不过滤终态），使已拒绝记录也能报告状态
- `request_approval()`: 重复提交改为抛出 `ValueError`（不再静默复用）

### `src/gateway/approval.py`

- 在文件末尾添加 `_approval_gate` 单例变量和 `get_approval_gate() -> ApprovalGate` 函数，导出给 `approval_adapter.py` 使用

---

## 验证结果

```
$ python3 tests/run_tests.py --unit
======================= 239 passed, 2 warnings in 10.71s =======================
```

所有 25 个失败测试现已通过，214 个原有通过测试无回退。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/models/approval.py` | ApprovalRecord/Store/Gate 多处 API 修复 |
| `src/gateway/approval.py` | 新增 `get_approval_gate()` 单例函数 |
