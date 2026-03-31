# ApprovalGate API

## 概述
审批网关，支持L4单签/L5双人审批。

## API端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/approvals/pending | 获取待审批列表 |
| GET | /api/v1/approvals/{request_id} | 获取审批详情 |
| POST | /api/v1/approvals/{request_id}/approve | 审批通过 |
| POST | /api/v1/approvals/{request_id}/reject | 审批拒绝 |

## 风险级别
- L4: 单签审批（1人通过即可）
- L5: 双人审批（需2人通过）
