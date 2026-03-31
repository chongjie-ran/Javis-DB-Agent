# SOP YAML 格式

## 概述
SOP（Standard Operating Procedure）标准操作规程，支持YAML格式定义。

## 文件位置
`knowledge/sop_yaml/*.yaml`

## 格式示例
```yaml
sop_id: slow_sql_diagnosis
name: 慢SQL诊断
description: 诊断和优化慢SQL
version: "1.0"
steps:
  - step_id: step_1
    name: 查找慢SQL
    action: find_slow_queries
    params:
      instance_id: "{instance_id}"
      limit: 10
    timeout_seconds: 30
    risk_level: L1
```

## 字段说明
| 字段 | 必填 | 说明 |
|------|------|------|
| sop_id | 是 | SOP唯一标识 |
| name | 是 | SOP名称 |
| steps | 是 | 步骤列表 |
| step_id | 是 | 步骤唯一标识 |
| action | 是 | 执行的动作 |
| params | 否 | 动作参数 |
| risk_level | 否 | L1-L5 |
| require_approval | 否 | 是否需要审批 |
