# MEMORY.md - 真理的长期记忆

## 关于本 workspace
- 2026-04-12 初始化完成
- 由 Chongjie (崇洁) 创建，拥有并使用

## 关于 Chongjie
- IT行业，GMT+8 Asia/Shanghai
- 运营多个AI Agent协同工作
- 当前项目：Javis-DB V3.3

## 项目经验
- 2026-04-12: 完成 Javis-DB V3.3 P0 功能测试验证
  - 40/40 测试通过
  - 覆盖: retry_executor, resource_guard, session persistence
  - Commit: ca07ed8

## Agent 协作关系
| Agent | 角色 |
|-------|------|
| 悟通 | P0 实现 (错误恢复/资源保护) |
| 悟空 | P0 实现 (会话持久化) |
| 真显 | P1 测试搭档 |
| 道衍 | P2 评审 |
| 道奇 | P2 评审 |

## 教训
- 测试fixture中 lambda 在 nonlocal 场景下有闭包问题，用具名函数更可靠
- ConversationMessage 用 `.blocks` 不是 `.content`
- ResourceMonitor 是单例，测试前需清理 `_snapshots`
