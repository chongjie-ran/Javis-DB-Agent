# MCP/TeamCoordinator 测试用例设计

> 创建: 2026-04-12 | 负责人: 真理 | 状态: 设计完成待实现

## 背景

MCP (Model Context Protocol) 是 V3.2 核心特性，实现 tools/list + tools/call + JSON Schema 规范。
TeamCoordinator 是 V3.2 P2 计划，让 Orchestrator Agent 支持动态委派子任务。

## MCP 协议测试用例

### 1. tools/list 接口测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| MCP-001 | 列出所有可用工具 | - | 返回非空工具列表 | P0 |
| MCP-002 | 工具列表包含必要字段 | - | name, description, inputSchema | P0 |
| MCP-003 | inputSchema 是有效JSON Schema | - | type/object + required + properties | P0 |
| MCP-004 | 空工具注册 | 无工具 | 返回空列表 [] | P1 |
| MCP-005 | 重复工具名 | 注册同名工具 | 覆盖或报错 (依设计) | P1 |

### 2. tools/call 接口测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| MCP-006 | 正常调用工具 | tool=bash, args={command:"echo hi"} | {content:[{type:"text",text:"hi"}]} | P0 |
| MCP-007 | 调用不存在的工具 | tool=nonexistent | error: tool not found | P0 |
| MCP-008 | 缺少必填参数 | tool=bash, args={} | error: missing required arg | P0 |
| MCP-009 | 参数类型错误 | tool=bash, args={command:123} | error: type mismatch | P1 |
| MCP-010 | 工具执行超时 | slow tool | error: timeout | P1 |
| MCP-011 | 工具抛出异常 | failing tool | error: internal error | P1 |

### 3. 工具注册测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| MCP-012 | 注册bash工具 | name=bash, handler | tools/list包含 | P0 |
| MCP-013 | 注册无效schema工具 | invalid JSON Schema | error: invalid schema | P1 |
| MCP-014 | 动态注册/注销工具 | register + unregister | 工具列表动态更新 | P2 |

## TeamCoordinator 测试用例

### 1. 任务委派测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| TC-001 | 正常创建子任务 | task=代码审查 | task_id + status=pending | P0 |
| TC-002 | 委派给指定Agent | agent=悟通 | 任务分配到目标 | P0 |
| TC-003 | 任务状态同步 | 子任务完成 | 主任务感知状态变化 | P0 |
| TC-004 | 并发委派多个任务 | 5个并发任务 | 全部正确分配 | P1 |
| TC-005 | 目标Agent不存在 | agent=nonexistent | error: agent not found | P1 |

### 2. 任务依赖测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| TC-006 | 任务依赖链 | B depends on A | B在A完成后执行 | P0 |
| TC-007 | 循环依赖检测 | A→B→C→A | error: circular dependency | P0 |
| TC-008 | 缺失依赖任务 | dep on nonexistent | error: missing dep | P1 |

### 3. 错误恢复测试

| 用例ID | 描述 | 输入 | 预期 | 优先级 |
|--------|------|------|------|--------|
| TC-009 | Agent失联 | agent goes offline | 任务重分配或超时 | P1 |
| TC-010 | 子任务失败 | subtask fails | 父任务感知失败状态 | P0 |
| TC-011 | 断点续传 | coordinator restart | 恢复进行中任务 | P2 |
