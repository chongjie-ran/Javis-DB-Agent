# Javis-DB-Agent V3.0.0 (2026-04-02)

## 重大新功能

### Phase 0: Hook生命周期系统
- 新增 `src/hooks/` 目录
- 8个Hook点：before_iteration, before_execute_tools, after_execute_tools, before_llm, on_stream, after_llm, after_iteration, on_error, on_complete
- CompositeHook支持组合+错误隔离

### Phase 1: AgentRunner重构
- 新增 `src/agents/agent_runner.py`
- AgentRunSpec规格定义
- InstructionSelfContainValidator指令自包含验证

### Phase 2: 双层记忆系统
- 新增 `src/memory/` 目录
- HISTORY.md短期记忆（事件日志）
- MEMORY.md长期记忆（结构化事实）
- TokenMonitor token监控

### Phase 3: 对抗性验证系统
- 新增 `src/validation/` 目录
- ValidatorRegistry验证器注册表
- BreakingValidator打破声明
- AdversarialValidationHook对抗性验证Hook

### Phase 4: 自我合理化防护
- 新增 `src/hooks/self_justification_guard.py`
- 19个信号词检测
- 9种防护动作
- 开发者特有信号支持

### Phase 5: TaskScheduler
- 新增 `src/scheduler/` 目录
- 任务分类：READ_ONLY/WRITE_SAME_FILE/WRITE_DIFF_FILE/VERIFY
- FileLockManager文件锁
- 死锁预防（按路径排序）

### Phase 6: Subagent双模式
- 新增 `src/subagent/` 目录
- ExploreSpec探索模式（5分钟/只读/30k token）
- ExecuteSpec执行模式（60分钟/可写/100k token）
- SubagentFactory工厂

## 架构改进
- AgentLoop解耦为AgentRunner+Hook
- 向后兼容：现有Agent业务逻辑保持不变
- 扩展方式：从修改核心代码改为Hook注入

## 测试改进
- 新增V3.0相关测试用例
- 所有Phase保持向后兼容

---

# 历史版本

## V2.7 (2026-04-01)
- Webhook审批通知
- HMAC-SHA256签名
- IP白名单
- Replay防护

## V2.6.1 (2026-04-01)
- Token TTL机制
- Hook MODIFY动作
- 后台自动清理

## V2.6 (2026-04-01)
- Hook事件驱动
- 并行Agent引擎
- SafetyGuardRail
- 可观测性框架
