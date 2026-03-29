# Javis-DB-Agent Agent项目商用路线图

> 版本: v2.0 | 更新日期: 2026-03-29 | 定义者: Chongjie

---

## 🏁 商用标准（Chongjie定义）

zCloud必须完成以下所有功能才能称为**商用产品**：

| 功能模块 | 子功能 | 状态 | 产出 |
|----------|--------|------|------|
| **1. Agent交互入口** | Web界面/API网关/用户认证 | ✅ R12完成 | dashboard增强、流式响应、Agent切换 |
| **2. 消息通道对接** | | | |
| | 2.1 企业微信(wecom)通道 | ✅ R13完成 | 32个测试，4个API端点 |
| | 2.2 飞书(feishu)通道 | ✅ R14完成 | 29个测试，支持WS+Webhook |
| | 2.3 邮箱(Email)通道 | ✅ R15完成 | 37个测试，命令格式支持 |
| **3. 网络传输安全** | | | |
| | 3.1 传输加密(TLS) | ❌ 未开始 | - |
| | 3.2 API鉴权机制 | ❌ 未开始 | - |
| | 3.3 敏感数据脱敏 | ❌ 未开始 | - |

---

## ✅ 已完成

### R1-R11: 核心引擎

| 功能 | 说明 |
|------|------|
| 核心诊断引擎 | 实例→告警→会话→锁→慢SQL链路 |
| 策略引擎 | PolicyEngine + 7级权限控制 |
| 审批流程 | L5双人审批 + 审批Gate |
| 审计日志 | 哈希链防篡改 |
| 监控告警 | Prometheus metrics端点 |
| 分布式支持 | Redis多节点会话共享 |
| 版本管理 | 策略版本历史 |
| API客户端工厂 | Mock/Real模式切换 |
| OAuth2认证 | access_token + refresh_token |
| 测试覆盖 | 542用例 / 99.8%通过率 |

### R12: Agent交互入口

| 功能 | 产出 |
|------|------|
| Web Dashboard增强 | dashboard.html (983行) |
| 流式响应 | SSE事件(chunk/done/error/thinking) |
| Agent切换器 | 6个Agent可切换 |
| 会话管理 | localStorage持久化 |
| Markdown渲染 | 代码块/表格/列表/粗体 |
| 中断生成 | AbortController支持 |
| 思考动画 | 三点波浪动画 |

### R13: 企业微信通道

| 功能 | 产出 |
|------|------|
| 消息接收 | XML解析、AES解密、签名验证 |
| 消息发送 | 文本/Markdown、企业应用API |
| 会话管理 | user_id/chat_id → session_id映射 |
| 告警推送 | critical/warning/info三级卡片 |
| API端点 | /api/v1/channels/wecom/callback, send, alert, sessions |
| 测试覆盖 | 32个测试用例 |

### R14: 飞书通道

| 功能 | 产出 |
|------|------|
| 消息接收 | WebSocket长连接 + Webhook HTTP回调 |
| 消息发送 | 文本/富文本/交互卡片/流式卡片 |
| 会话管理 | chat_id+user_id → session_id映射，线程隔离 |
| 消息去重 | 滑动窗口TTL(可配置) |
| 权限控制 | allow_from_all / 白名单 |
| 告警通知 | 三色卡片(critical/warning/info) |
| 测试覆盖 | 29个测试用例 |

### R15: 邮箱通道

| 功能 | 产出 |
|------|------|
| 消息接收 | IMAP轮询 |
| 消息发送 | SMTP发送、HTML邮件、附件 |
| 命令解析 | [诊断]/[状态]/[报告]/[巡检]/[风险]/[sql] |
| 会话管理 | Message-ID线程映射，SQLite持久化 |
| 权限控制 | 白名单过滤 |
| 测试覆盖 | 37个测试用例 |

---

## ❌ 未开始

### 3. 网络传输安全

#### 3.1 传输加密(TLS)
- 所有API通信必须使用HTTPS/TLS 1.2+
- 内部服务间通信加密
- 证书管理机制

#### 3.2 API鉴权机制
- API Key / JWT Token 管理
- 权限分级（管理员/操作员/只读）
- 调用频率限制(Rate Limiting)

#### 3.3 敏感数据脱敏
- 日志中的敏感信息（密码、IP、数据库名）脱敏
- 告警通知中的敏感数据过滤
- 审计日志中的敏感操作脱敏

---

## 📋 后续迭代计划

| 阶段 | 任务 | 目标 |
|------|------|------|
| **R16** | 网络传输安全 | TLS + API鉴权 + 数据脱敏 |
| **R17** | 完整端到端测试 | 全链路集成测试 |
| **Beta** | 内部测试 | 种子用户反馈 |

---

## 🎯 当前里程碑

- **R15完成**（2026-03-29）：交互入口+3个消息通道全部就绪
- **Beta发布**：需完成R16网络安全
- **商用发布**：所有功能就绪 + 安全审计通过

---

## 📊 Git提交记录

```
aeed48d Channel: 邮箱(Email)消息通道对接
e893227 Channel: 企业微信(wecom)消息通道对接
10527e6 Channel: 飞书(feishu)消息通道对接
e06be0d Round 12: Agent交互入口（参考OpenClaw webchat标准）
1131c40 Round 11 Fix: R1 asyncio + R2 OAuth2 refresh_token
c7aa82a Round 11: 真实环境验证
34517ee Round 10: 可观测性、多节点部署、策略版本管理
```

---

*本文件由SC根据Chongjie指示创建并更新。*
