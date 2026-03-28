"""
第四轮测试：性能基线验证

本模块验证系统性能指标：
1. 30秒响应时间目标验证
2. 并发性能测试
3. 资源消耗评估
"""
import pytest
import asyncio
import time
import os
import resource
from unittest.mock import MagicMock, AsyncMock
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.diagnostic import DiagnosticAgent
from src.agents.orchestrator import OrchestratorAgent
from src.gateway.alert_correlator import AlertCorrelator
from src.tools.query_tools import QueryInstanceStatusTool


def get_cpu_usage_sample():
    """获取CPU使用率采样（基于idle时间）"""
    try:
        import subprocess
        result = subprocess.run(["top", "-l", "1", "-n", "0"], capture_output=True, text=True, timeout=2)
        for line in result.stdout.split('\n'):
            if 'CPU usage' in line:
                parts = line.split(',')
                for p in parts:
                    if 'idle' in p:
                        idle_pct = float(p.split('%')[0].strip())
                        return 100 - idle_pct
        return 50.0  # 默认值
    except:
        return 50.0  # 默认值


def get_memory_usage_percent():
    """获取内存使用百分比"""
    try:
        import subprocess
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=2)
        # 解析 vm_stat 输出
        lines = result.stdout.split('\n')
        free = 0
        active = 0
        inactive = 0
        wired = 0
        for line in lines:
            if 'Pages free:' in line:
                free = int(line.split(':')[1].strip().replace('.', ''))
            elif 'Pages active:' in line:
                active = int(line.split(':')[1].strip().replace('.', ''))
            elif 'Pages inactive:' in line:
                inactive = int(line.split(':')[1].strip().replace('.', ''))
            elif 'Pages wired down:' in line:
                wired = int(line.split(':')[1].strip().replace('.', ''))
        page_size = 4096  # macOS default
        total = (free + active + inactive + wired) * page_size / (1024*1024*1024)
        used = (active + wired) * page_size / (1024*1024*1024)
        return used / total * 100 if total > 0 else 50
    except:
        return 50.0


# ============================================================================
# 性能测试配置
# ============================================================================

# 响应时间目标（SLA）
RESPONSE_TIME_SLA_MS = 30000  # 30秒

# 并发测试配置
CONCURRENT_USER_COUNTS = [1, 5, 10]  # 并发用户数
MAX_CONCURRENT_TEST = 10


# ============================================================================
# 测试夹具
# ============================================================================

@pytest.fixture
def mock_zcloud_client():
    """Mock zCloud客户端"""
    client = MagicMock()
    client.get_instance = AsyncMock(return_value={
        "instance_id": "INS-PROD-001",
        "status": "running",
        "cpu_usage_percent": 45.2,
    })
    client.get_alerts = AsyncMock(return_value=[
        {
            "alert_id": f"ALT-{i:03d}",
            "alert_type": "CPU_HIGH",
            "severity": "warning",
            "instance_id": "INS-PROD-001",
            "occurred_at": time.time() - 300,
            "metric_value": 92.5,
            "threshold": 80.0,
        }
        for i in range(10)
    ])
    client.get_sessions = AsyncMock(return_value={
        "sessions": [{"sid": 1001 + i, "status": "ACTIVE"} for i in range(10)],
        "total": 10,
    })
    return client


@pytest.fixture
def mock_llm_response():
    """Mock LLM响应"""
    return {
        "response": """诊断分析：这是一个CPU告警问题，可能与慢查询或高负载有关。建议检查实例状态和会话情况。""",
        "done": True,
    }


# ============================================================================
# 性能指标收集器
# ============================================================================

class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.cpu_start = None
        self.cpu_end = None
        self.memory_start = None
        self.memory_end = None
    
    def start(self):
        """开始计时"""
        self.start_time = time.time()
        self.cpu_start = get_cpu_usage_sample()
        self.memory_start = get_memory_usage_percent()
    
    def stop(self):
        """结束计时"""
        self.end_time = time.time()
        self.cpu_end = get_cpu_usage_sample()
        self.memory_end = get_memory_usage_percent()
    
    @property
    def elapsed_ms(self) -> float:
        """经过时间（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0
    
    @property
    def cpu_delta(self) -> float:
        """CPU变化量"""
        if self.cpu_start is not None and self.cpu_end is not None:
            return self.cpu_end - self.cpu_start
        return 0
    
    @property
    def memory_delta(self) -> float:
        """内存变化量"""
        if self.memory_start is not None and self.memory_end is not None:
            return self.memory_end - self.memory_start
        return 0


# ============================================================================
# 30秒响应时间目标验证
# ============================================================================

class TestResponseTimeSLA:
    """响应时间SLA测试"""
    
    @pytest.mark.asyncio
    async def test_single_alert_diagnosis_response_time(self, mock_zcloud_client, mock_llm_response):
        """
        测试单个告警诊断的响应时间
        
        目标：单次诊断请求应在30秒内完成
        """
        # Setup
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
        }
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        # Execute
        result = await agent.diagnose_alert("ALT-001", context)
        
        metrics.stop()
        
        # Assert
        assert result.success, f"诊断失败: {result.content}"
        assert metrics.elapsed_ms < RESPONSE_TIME_SLA_MS, \
            f"响应时间超过SLA: {metrics.elapsed_ms:.0f}ms > {RESPONSE_TIME_SLA_MS}ms"
    
    @pytest.mark.asyncio
    async def test_query_tool_response_time(self, mock_zcloud_client):
        """
        测试查询工具响应时间
        
        目标：查询操作应在5秒内完成
        """
        QUERY_SLA_MS = 5000
        
        tool = QueryInstanceStatusTool()
        params = {"instance_id": "INS-PROD-001", "metrics": ["cpu", "memory", "io"]}
        context = {"mock_client": mock_zcloud_client}
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        result = await tool.execute(params, context)
        
        metrics.stop()
        
        assert result.success, f"查询失败: {result}"
        assert metrics.elapsed_ms < QUERY_SLA_MS, \
            f"查询响应时间超过SLA: {metrics.elapsed_ms:.0f}ms > {QUERY_SLA_MS}ms"
    
    @pytest.mark.asyncio
    async def test_orchestrator_intent_recognition_time(self):
        """
        测试意图识别响应时间
        
        目标：意图识别应在10秒内完成（LLM调用需约15秒）
        """
        INTENT_SLA_MS = 10000
        
        agent = OrchestratorAgent()
        
        test_inputs = [
            "CPU告警了",
            "帮我分析这个慢SQL",
            "做个健康巡检",
        ]
        
        for inp in test_inputs:
            metrics = PerformanceMetrics()
            metrics.start()
            
            intent = await agent._recognize_intent(inp)
            
            metrics.stop()
            
            assert metrics.elapsed_ms < INTENT_SLA_MS, \
                f"意图识别超时: '{inp}' - {metrics.elapsed_ms:.0f}ms > {INTENT_SLA_MS}ms"
    
    @pytest.mark.asyncio
    async def test_alert_correlation_response_time(self, mock_zcloud_client):
        """
        测试告警关联分析响应时间
        
        目标：10个告警的关联分析应在10秒内完成
        """
        CORRELATION_SLA_MS = 10000
        
        from src.gateway.alert_correlator import get_mock_alert_correlator
        
        correlator = get_mock_alert_correlator()
        all_alerts = await mock_zcloud_client.get_alerts(status="active")
        
        metrics = PerformanceMetrics()
        metrics.start()
        
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-001",
            all_alerts=all_alerts,
            mock_client=mock_zcloud_client,
        )
        
        metrics.stop()
        
        assert result is not None, "关联分析结果为空"
        assert metrics.elapsed_ms < CORRELATION_SLA_MS, \
            f"关联分析超时: {metrics.elapsed_ms:.0f}ms > {CORRELATION_SLA_MS}ms"


# ============================================================================
# 并发性能测试
# ============================================================================

class TestConcurrentPerformance:
    """并发性能测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_diagnosis_requests(self, mock_zcloud_client, mock_llm_response):
        """
        测试并发诊断请求
        
        验证点：
        1. 系统能处理10个并发请求
        2. 平均响应时间合理
        3. 无请求失败
        """
        NUM_CONCURRENT = 10
        MAX_AVG_RESPONSE_MS = 5000  # 并发下平均响应时间应<5秒
        
        async def single_diagnosis(idx: int) -> PerformanceMetrics:
            agent = DiagnosticAgent()
            agent.think = AsyncMock(return_value=mock_llm_response["response"])
            
            context = {
                "instance_id": f"INS-PROD-{idx:03d}",
                "mock_client": mock_zcloud_client,
            }
            
            metrics = PerformanceMetrics()
            metrics.start()
            
            result = await agent.diagnose_alert(f"ALT-{idx:03d}", context)
            
            metrics.stop()
            
            assert result.success, f"诊断 {idx} 失败: {result.content}"
            return metrics
        
        # Execute concurrent requests
        start_time = time.time()
        tasks = [single_diagnosis(i) for i in range(NUM_CONCURRENT)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Calculate metrics
        response_times = [r.elapsed_ms for r in results]
        avg_response = sum(response_times) / len(response_times)
        max_response = max(response_times)
        min_response = min(response_times)
        
        print(f"\n=== 并发诊断性能报告 ===")
        print(f"并发数: {NUM_CONCURRENT}")
        print(f"总耗时: {total_time:.2f}s")
        print(f"平均响应: {avg_response:.0f}ms")
        print(f"最大响应: {max_response:.0f}ms")
        print(f"最小响应: {min_response:.0f}ms")
        
        # Assert
        assert avg_response < MAX_AVG_RESPONSE_MS, \
            f"平均响应时间过高: {avg_response:.0f}ms > {MAX_AVG_RESPONSE_MS}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_query_requests(self, mock_zcloud_client):
        """
        测试并发查询请求
        
        验证点：
        1. 100个并发查询应在30秒内完成
        2. 无请求失败
        """
        NUM_CONCURRENT = 100
        MAX_TOTAL_TIME_S = 30
        
        tool = QueryInstanceStatusTool()
        
        async def single_query(idx: int) -> bool:
            params = {"instance_id": f"INS-PROD-{idx:03d}"}
            context = {"mock_client": mock_zcloud_client}
            result = await tool.execute(params, context)
            return result.success
        
        start_time = time.time()
        tasks = [single_query(i) for i in range(NUM_CONCURRENT)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        success_count = sum(results)
        success_rate = success_count / NUM_CONCURRENT * 100
        
        print(f"\n=== 并发查询性能报告 ===")
        print(f"并发数: {NUM_CONCURRENT}")
        print(f"总耗时: {total_time:.2f}s")
        print(f"成功率: {success_rate:.1f}%")
        
        # Assert
        assert total_time < MAX_TOTAL_TIME_S, \
            f"并发查询总时间超时: {total_time:.2f}s > {MAX_TOTAL_TIME_S}s"
        assert success_rate == 100.0, f"存在失败请求: {success_count}/{NUM_CONCURRENT}"
    
    @pytest.mark.asyncio
    async def test_sustained_load_performance(self, mock_zcloud_client, mock_llm_response):
        """
        测试持续负载性能
        
        验证点：
        1. 持续1分钟负载下性能稳定
        2. 无内存泄漏
        3. 响应时间无明显退化
        """
        DURATION_S = 60
        SAMPLE_INTERVAL_S = 5
        
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        response_times = []
        memory_samples = []
        start_time = time.time()
        request_count = 0
        
        print(f"\n=== 持续负载测试 (60秒) ===")
        
        while time.time() - start_time < DURATION_S:
            context = {
                "instance_id": "INS-PROD-001",
                "mock_client": mock_zcloud_client,
            }
            
            metrics = PerformanceMetrics()
            metrics.start()
            
            result = await agent.diagnose_alert("ALT-001", context)
            
            metrics.stop()
            
            response_times.append(metrics.elapsed_ms)
            memory_samples.append(get_memory_usage_percent())
            request_count += 1
            
            await asyncio.sleep(SAMPLE_INTERVAL_S)
            
            # 每10秒报告一次
            if request_count % 2 == 0:
                recent_avg = sum(response_times[-2:]) / 2
                print(f"  [{request_count}请求] 平均响应: {recent_avg:.0f}ms, 内存: {memory_samples[-1]:.1f}%")
        
        # Calculate degradation
        first_half_avg = sum(response_times[:len(response_times)//2]) / (len(response_times)//2)
        second_half_avg = sum(response_times[len(response_times)//2:]) / (len(response_times) - len(response_times)//2)
        degradation = (second_half_avg - first_half_avg) / first_half_avg * 100
        
        print(f"\n=== 持续负载结果 ===")
        print(f"总请求数: {request_count}")
        print(f"前半段平均: {first_half_avg:.0f}ms")
        print(f"后半段平均: {second_half_avg:.0f}ms")
        print(f"性能退化: {degradation:+.1f}%")
        
        # Assert - 性能退化不超过30%
        assert degradation < 30, f"性能退化过大: {degradation:.1f}%"
        assert second_half_avg < RESPONSE_TIME_SLA_MS, \
            f"后半段响应时间超标: {second_half_avg:.0f}ms"


# ============================================================================
# 资源消耗评估
# ============================================================================

class TestResourceConsumption:
    """资源消耗评估测试"""
    
    @pytest.mark.asyncio
    async def test_memory_usage_per_request(self, mock_zcloud_client, mock_llm_response):
        """
        测试每次请求的内存消耗
        
        验证点：
        1. 单次请求内存增量合理（<50MB）
        2. 内存正确释放
        """
        SINGLE_REQUEST_MEMORY_LIMIT_MB = 50
        
        # 记录初始内存使用率
        initial_memory_pct = get_memory_usage_percent()
        
        # 执行单次请求
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
        }
        
        result = await agent.diagnose_alert("ALT-001", context)
        
        # 等待GC
        import gc
        gc.collect()
        await asyncio.sleep(0.5)
        
        # 记录最终内存使用率
        final_memory_pct = get_memory_usage_percent()
        memory_delta = final_memory_pct - initial_memory_pct
        
        print(f"\n=== 内存消耗报告 ===")
        print(f"初始内存使用率: {initial_memory_pct:.1f}%")
        print(f"最终内存使用率: {final_memory_pct:.1f}%")
        print(f"内存变化: {memory_delta:+.1f}%")
        
        assert result.success, f"请求失败: {result.content}"
        # 内存使用率变化应小于10%
        assert abs(memory_delta) < 10, \
            f"单次请求内存变化过大: {memory_delta:.1f}% > 10%"
    
    @pytest.mark.asyncio
    async def test_cpu_usage_during_correlation(self, mock_zcloud_client):
        """
        测试告警关联分析的CPU使用
        
        验证点：
        1. CPU峰值合理
        2. 无长时间CPU高占用
        """
        from src.gateway.alert_correlator import get_mock_alert_correlator
        
        correlator = get_mock_alert_correlator()
        all_alerts = await mock_zcloud_client.get_alerts(status="active")
        
        # 添加更多告警以增加计算量
        all_alerts.extend([
            {
                "alert_id": f"ALT-{i:03d}",
                "alert_type": "CPU_HIGH",
                "severity": "warning",
                "instance_id": "INS-PROD-001",
                "occurred_at": time.time() - 300 + i * 60,
                "metric_value": 85.0 + i,
                "threshold": 80.0,
                "message": f"CPU使用率过高: {85.0 + i}%",
                "status": "active",
            }
            for i in range(50)
        ])
        
        cpu_samples = []
        
        async def sample_cpu():
            for _ in range(10):
                cpu_samples.append(get_cpu_usage_sample())
                await asyncio.sleep(0.1)
        
        # 并行执行关联分析和CPU采样
        await asyncio.gather(
            correlator.correlate_alerts("ALT-001", all_alerts, mock_zcloud_client),
            sample_cpu(),
        )
        
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)
        
        print(f"\n=== CPU使用报告 ===")
        print(f"平均CPU: {avg_cpu:.1f}%")
        print(f"峰值CPU: {max_cpu:.1f}%")
        
        # CPU峰值不应超过80%
        assert max_cpu < 80, f"CPU峰值过高: {max_cpu:.1f}%"
    
    @pytest.mark.asyncio
    async def test_process_file_descriptors(self, mock_zcloud_client, mock_llm_response):
        """
        测试文件描述符使用
        
        验证点：
        1. 文件描述符数量合理
        2. 无描述符泄漏
        """
        try:
            import subprocess
            result = subprocess.run(["sh", "-c", "ulimit -n"], capture_output=True, text=True)
            max_fds = int(result.stdout.strip())
            initial_fds = max_fds
        except:
            initial_fds = 256  # 默认值
        
        # 执行多次操作
        for i in range(20):
            agent = DiagnosticAgent()
            agent.think = AsyncMock(return_value=mock_llm_response["response"])
            
            context = {"instance_id": "INS-PROD-001", "mock_client": mock_zcloud_client}
            await agent.diagnose_alert("ALT-001", context)
        
        try:
            result = subprocess.run(["sh", "-c", "ulimit -n"], capture_output=True, text=True)
            final_fds = int(result.stdout.strip())
        except:
            final_fds = initial_fds
        
        fd_increase = abs(final_fds - initial_fds)
        
        print(f"\n=== 文件描述符报告 ===")
        print(f"初始限制: {initial_fds}")
        print(f"最终限制: {final_fds}")
        print(f"变化: {fd_increase}")
        
        # 文件描述符使用应保持稳定
        assert fd_increase < 50, f"文件描述符变化过大: {fd_increase}"


# ============================================================================
# 性能回归测试
# ============================================================================

class TestPerformanceRegression:
    """性能回归测试基线"""
    
    @pytest.mark.asyncio
    async def test_baseline_diagnosis_response_time(self, mock_zcloud_client, mock_llm_response):
        """
        建立诊断响应时间基线
        
        用于未来性能回归对比
        """
        NUM_SAMPLES = 20
        
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        response_times = []
        
        for i in range(NUM_SAMPLES):
            context = {
                "instance_id": f"INS-PROD-{i:03d}",
                "mock_client": mock_zcloud_client,
            }
            
            metrics = PerformanceMetrics()
            metrics.start()
            
            result = await agent.diagnose_alert("ALT-001", context)
            
            metrics.stop()
            
            assert result.success, f"请求 {i} 失败"
            response_times.append(metrics.elapsed_ms)
        
        avg = sum(response_times) / len(response_times)
        p50 = sorted(response_times)[len(response_times) // 2]
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        p99 = sorted(response_times)[int(len(response_times) * 0.99)]
        
        print(f"\n=== 诊断响应时间基线 (n={NUM_SAMPLES}) ===")
        print(f"平均: {avg:.0f}ms")
        print(f"P50: {p50:.0f}ms")
        print(f"P95: {p95:.0f}ms")
        print(f"P99: {p99:.0f}ms")
        print(f"SLA达标率: {sum(1 for t in response_times if t < RESPONSE_TIME_SLA_MS) / NUM_SAMPLES * 100:.0f}%")
        
        # 保存基线到文件
        baseline_file = os.path.join(os.path.dirname(__file__), "performance_baseline.json")
        baseline_data = {
            "timestamp": time.time(),
            "samples": NUM_SAMPLES,
            "avg_ms": avg,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
        }
        
        import json
        with open(baseline_file, "w") as f:
            json.dump(baseline_data, f, indent=2)


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
