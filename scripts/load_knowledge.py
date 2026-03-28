#!/usr/bin/env python3
"""知识库导入脚本"""
import os
import yaml
from datetime import datetime

KNOWLEDGE_DIR = "knowledge"
SOP_DIR = "knowledge/sop"
CASES_DIR = "knowledge/cases"


def ensure_knowledge_dirs():
    """确保知识库目录存在"""
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    os.makedirs(SOP_DIR, exist_ok=True)
    os.makedirs(CASES_DIR, exist_ok=True)
    print("✓ 知识库目录已创建")


def create_sample_alert_rules():
    """创建示例告警规则"""
    rules = [
        {
            "alert_code": "LOCK_WAIT_TIMEOUT",
            "name": "锁等待超时",
            "description": "实例发生锁等待超时",
            "severity": "warning",
            "symptoms": [
                "等待时间超过阈值",
                "会话处于Waiting状态",
                "业务请求响应缓慢"
            ],
            "possible_causes": [
                "长事务持有锁",
                "未提交事务",
                "锁冲突"
            ],
            "check_steps": [
                "查询锁等待链: SELECT * FROM v$lock WHERE block > 0",
                "分析持有锁的SQL",
                "评估影响范围"
            ],
            "resolution": [
                "确认是否可以kill session",
                "联系应用负责人",
                "评估事务回滚影响"
            ],
            "risk_level": "L3"
        },
        {
            "alert_code": "SLOW_QUERY_DETECTED",
            "name": "慢SQL告警",
            "description": "检测到执行时间过长的SQL",
            "severity": "info",
            "symptoms": [
                "SQL执行时间超过阈值",
                "系统响应变慢"
            ],
            "possible_causes": [
                "SQL缺少索引",
                "统计信息过期",
                "执行计划不当"
            ],
            "check_steps": [
                "查看SQL执行计划",
                "检查相关表索引",
                "分析表数据量"
            ],
            "resolution": [
                "添加合适索引",
                "重写SQL",
                "更新统计信息"
            ],
            "risk_level": "L2"
        },
        {
            "alert_code": "REPLICATION_LAG",
            "name": "主从延迟告警",
            "description": "主从复制延迟超过阈值",
            "severity": "warning",
            "symptoms": [
                "从库延迟超过阈值",
                "数据同步不一致"
            ],
            "possible_causes": [
                "从库负载过高",
                "网络延迟",
                "大事务同步"
            ],
            "check_steps": [
                "检查从库负载",
                "查看网络状态",
                "分析binlog应用情况"
            ],
            "resolution": [
                "优化从库性能",
                "调整复制架构",
                "拆分大事务"
            ],
            "risk_level": "L3"
        }
    ]
    
    output_path = os.path.join(KNOWLEDGE_DIR, "alert_rules.yaml")
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump({"alert_rules": rules}, f, allow_unicode=True, default_flow_style=False)
    
    print(f"✓ 告警规则已创建: {output_path}")


def create_sample_sop():
    """创建示例SOP"""
    sops = {
        "lock_wait排查": """# 锁等待排查标准流程

## 1. 确认告警
- 收到锁等待超时告警
- 记录告警时间和实例ID

## 2. 收集信息
- 查询锁等待链
- 查看阻塞者和被阻塞者
- 分析相关SQL

## 3. 评估影响
- 评估阻塞的会话数
- 评估对业务的影响
- 判断是否可以自动处理

## 4. 处理决策
- L3及以下：可考虑自动处理
- L4及以上：必须人工审批

## 5. 处理执行
- 联系应用负责人
- 或执行kill session
- 验证处理结果

## 6. 记录归档
- 记录处理过程
- 更新知识库案例
""",
        "慢SQL分析": """# 慢SQL分析标准流程

## 1. 收集SQL信息
- 获取SQL文本和SQL ID
- 查看执行计划
- 分析执行统计

## 2. 判断优化方向
- 索引优化
- SQL改写
- 统计信息更新
- 参数调整

## 3. 风险评估
- 评估优化风险
- 确定回滚方案

## 4. 实施优化
- 在测试环境验证
- 生产环境灰度实施

## 5. 效果验证
- 对比优化前后性能
- 持续监控
"""
    }
    
    os.makedirs(SOP_DIR, exist_ok=True)
    for name, content in sops.items():
        filepath = os.path.join(SOP_DIR, f"{name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✓ SOP已创建: {filepath}")


if __name__ == "__main__":
    print("=" * 50)
    print("zCloudNewAgentProject 知识库初始化")
    print("=" * 50)
    ensure_knowledge_dirs()
    create_sample_alert_rules()
    create_sample_sop()
    print("=" * 50)
    print("知识库初始化完成！")
    print("=" * 50)
