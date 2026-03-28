#!/usr/bin/env python3
"""
Ollama推理质量验证脚本
验证zCloud智能体在真实Ollama上的推理质量
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.ollama_client import OllamaClient


class OllamaQualityValidator:
    """Ollama推理质量验证器"""
    
    def __init__(self):
        self.client = OllamaClient()
        self.results = []
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("zCloud 智能体 Ollama 推理质量验证")
        print("=" * 60)
        
        # 1. 健康检查
        await self.test_ollama_health()
        
        # 2. 告警诊断推理
        await self.test_alert_diagnosis()
        
        # 3. 根因分析推理
        await self.test_root_cause_analysis()
        
        # 4. 工具选择准确性
        await self.test_tool_selection()
        
        # 5. 上下文利用
        await self.test_context_usage()
        
        # 输出汇总
        self.print_summary()
    
    async def test_ollama_health(self):
        """测试1：Ollama健康检查"""
        print("\n[测试1] Ollama健康检查")
        print("-" * 40)
        
        healthy = await self.client.health_check()
        models = await self.client.list_models()
        
        print(f"  Ollama状态: {'✓ 正常' if healthy else '✗ 异常'}")
        print(f"  可用模型数: {len(models)}")
        for m in models:
            print(f"    - {m['name']} ({m['size']/1024/1024/1024:.1f}GB)")
        
        self.results.append({
            "test": "健康检查",
            "passed": healthy,
            "detail": f"模型数: {len(models)}"
        })
    
    async def test_alert_diagnosis(self):
        """测试2：告警诊断推理"""
        print("\n[测试2] 告警诊断推理")
        print("-" * 40)
        
        system_prompt = """你是一个专业的数据库运维智能助手。
角色：你是一个诊断Agent，负责分析数据库告警并给出排查建议。
安全原则：永远不直接输出SQL或shell命令，所有操作通过工具调用。
"""
        
        user_prompt = """告警信息：
- 告警ID: ALT-20260328-001
- 告警类型: LOCK_WAIT_TIMEOUT（锁等待超时）
- 告警消息: 实例发生锁等待超时，当前等待时间120秒
- 实例ID: INS-001
- 严重程度: warning

请分析这个告警，给出：
1. 可能的原因（至少3条）
2. 推荐的排查步骤（按优先级排序）
3. 是否可以自动处置（风险评估）
"""
        
        try:
            response = await self.client.complete(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3
            )
            print(f"  响应长度: {len(response)} 字符")
            print(f"  响应预览:\n{response[:500]}...")
            
            # 检查响应质量
            has_causes = len(response) > 100
            has_steps = "步骤" in response or "排查" in response
            
            self.results.append({
                "test": "告警诊断推理",
                "passed": has_causes and has_steps,
                "detail": f"响应{len(response)}字符，包含原因和步骤" if has_causes and has_steps else "响应过短或缺少关键信息"
            })
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            self.results.append({
                "test": "告警诊断推理",
                "passed": False,
                "detail": str(e)
            })
    
    async def test_root_cause_analysis(self):
        """测试3：根因分析推理"""
        print("\n[测试3] 根因分析推理")
        print("-" * 40)
        
        system_prompt = """你是一个专业的数据库诊断Agent。
你的职责是分析数据库问题的根因，给出结构化的诊断报告。
输出格式要求：JSON格式，包含 root_cause, confidence, evidence, next_steps 字段。
"""
        
        user_prompt = """场景：某订单系统突然响应缓慢，数据库连接数接近上限。

上下文信息：
- 实例状态: running, CPU 45%, 内存 68%
- 当前连接数: 480/500（接近上限）
- 活跃会话: 3个
- 锁等待会话: 15个
- 告警: LOCK_WAIT_TIMEOUT（触发中）
- 最近变更: 无

请分析根因，给出JSON格式的诊断报告：
{
  "root_cause": "...",
  "confidence": 0.85,
  "evidence": ["...", "..."],
  "next_steps": ["...", "..."]
}
"""
        
        try:
            response = await self.client.complete(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.2,
                format="json"
            )
            print(f"  响应长度: {len(response)} 字符")
            print(f"  响应预览: {response[:300]}...")
            
            # 尝试解析JSON
            try:
                data = json.loads(response)
                has_root_cause = "root_cause" in data
                has_confidence = "confidence" in data
                
                self.results.append({
                    "test": "根因分析推理",
                    "passed": has_root_cause and has_confidence,
                    "detail": f"JSON解析成功，置信度: {data.get('confidence', 'N/A')}"
                })
            except json.JSONDecodeError:
                self.results.append({
                    "test": "根因分析推理",
                    "passed": len(response) > 50,
                    "detail": "JSON解析失败，但有响应"
                })
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            self.results.append({
                "test": "根因分析推理",
                "passed": False,
                "detail": str(e)
            })
    
    async def test_tool_selection(self):
        """测试4：工具选择准确性"""
        print("\n[测试4] 工具选择准确性")
        print("-" * 40)
        
        system_prompt = """你是一个数据库运维Agent。
可用工具列表：
1. query_instance_status - 查询实例状态
2. query_session - 查询会话信息
3. query_lock - 查询锁等待
4. query_slow_sql - 查询慢SQL
5. query_replication - 查询复制状态
6. query_disk_usage - 查询磁盘使用率
7. query_parameters - 查询参数配置
8. send_notification - 发送通知
9. create_work_order - 创建工单

原则：只选择一个最合适的工具，不要选择多个。
"""
        
        scenarios = [
            {
                "scenario": "我想查看当前数据库的磁盘使用情况",
                "expected_tool": "query_disk_usage"
            },
            {
                "scenario": "发现有锁等待问题，想查看锁的详细信息",
                "expected_tool": "query_lock"
            },
            {
                "scenario": "需要给DBA发一条告警通知",
                "expected_tool": "send_notification"
            },
        ]
        
        passed = 0
        for s in scenarios:
            prompt = f"用户需求：{s['scenario']}\n\n请选择最合适的工具（只输出工具名称）："
            try:
                response = await self.client.complete(
                    prompt=prompt,
                    system=system_prompt,
                    temperature=0.1
                )
                response_clean = response.strip().lower()
                is_correct = s["expected_tool"].lower() in response_clean
                
                status = "✓" if is_correct else "✗"
                print(f"  {status} 场景: {s['scenario'][:30]}...")
                print(f"     期望: {s['expected_tool']}, 实际: {response_clean[:30]}")
                
                if is_correct:
                    passed += 1
            except Exception as e:
                print(f"  ✗ 错误: {e}")
        
        self.results.append({
            "test": "工具选择准确性",
            "passed": passed >= 2,
            "detail": f"{passed}/{len(scenarios)} 正确"
        })
    
    async def test_context_usage(self):
        """测试5：上下文利用"""
        print("\n[测试5] 上下文利用")
        print("-" * 40)
        
        system_prompt = """你是一个数据库诊断Agent。
你会收到数据库的上下文信息，请结合上下文进行分析，不要凭空猜测。
"""
        
        user_prompt = """上下文信息：
- 实例ID: INS-001
- 实例名称: PROD-ORDER-DB
- CPU使用率: 92%（严重偏高）
- 内存使用率: 85%
- 当前活跃会话: 50个
- Top SQL: 一条UPDATE语句执行了30分钟未完成
- 锁等待: 10个会话等待

问题：CPU使用率突然飙升到92%，请分析原因。
"""
        
        try:
            response = await self.client.complete(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3
            )
            print(f"  响应长度: {len(response)} 字符")
            
            # 检查是否正确利用了上下文
            uses_context = all(keyword in response for keyword in ["UPDATE", "30", "CPU"])
            
            print(f"  响应预览: {response[:400]}...")
            
            self.results.append({
                "test": "上下文利用",
                "passed": uses_context and len(response) > 100,
                "detail": f"{'正确利用上下文' if uses_context else '未充分结合上下文'}，响应{len(response)}字符"
            })
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            self.results.append({
                "test": "上下文利用",
                "passed": False,
                "detail": str(e)
            })
    
    def print_summary(self):
        """打印测试汇总"""
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        
        passed_count = sum(1 for r in self.results if r["passed"])
        total_count = len(self.results)
        
        for r in self.results:
            status = "✓ PASS" if r["passed"] else "✗ FAIL"
            print(f"  {status} | {r['test']:20s} | {r['detail']}")
        
        print("-" * 60)
        print(f"  通过率: {passed_count}/{total_count} ({passed_count/total_count*100:.0f}%)")
        
        if passed_count == total_count:
            print("  结论: ✨ Ollama推理质量合格，可用于生产")
        elif passed_count >= total_count * 0.6:
            print("  结论: ⚠️ Ollama推理质量基本可用，建议优化")
        else:
            print("  结论: ✗ Ollama推理质量不达标，需优化后使用")


async def main():
    validator = OllamaQualityValidator()
    await validator.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
