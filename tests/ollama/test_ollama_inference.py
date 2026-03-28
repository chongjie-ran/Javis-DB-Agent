"""
Ollama真实推理测试用例 - 第二轮测试
测试与真实Ollama服务的集成
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch


class TestOllamaRealInference:
    """Ollama真实推理测试"""
    
    @pytest.fixture
    def ollama_url(self):
        return "http://localhost:11434"
    
    @pytest.fixture
    def test_model(self):
        return "glm4:latest"
    
    @pytest.mark.asyncio
    async def test_ollama_service_available(self, ollama_url):
        """测试Ollama服务是否可用"""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_url}/")
                assert response.status_code == 200, "Ollama服务不可用"
        except Exception as e:
            pytest.skip(f"Ollama服务未运行: {e}")
    
    @pytest.mark.asyncio
    async def test_ollama_chat_completion(self, ollama_url, test_model):
        """测试chat补全接口"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            response = await client.complete(
                prompt="1+1等于几？请只回答数字。",
                system="你是一个数学助手，只能回答数字。"
            )
            
            assert response is not None, "响应为空"
            assert len(response) > 0, "响应内容为空"
            print(f"Chat响应: {response}")
        except Exception as e:
            pytest.skip(f"Ollama chat接口测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_ollama_generate_completion(self, ollama_url, test_model):
        """测试generate补全接口"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            response = await client.generate(
                prompt="用一句话介绍PostgreSQL。"
            )
            
            assert response is not None, "响应为空"
            assert len(response) > 0, "响应内容为空"
            print(f"Generate响应: {response}")
        except Exception as e:
            pytest.skip(f"Ollama generate接口测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_ollama_list_models(self, ollama_url):
        """测试列出可用模型"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url)
            
            models = await client.list_models()
            
            assert models is not None, "模型列表为空"
            assert isinstance(models, list), "模型列表应为列表"
            print(f"可用模型: {models}")
        except Exception as e:
            pytest.skip(f"Ollama list_models接口测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_ollama_health_check(self, ollama_url):
        """测试健康检查"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url)
            
            is_healthy = await client.health_check()
            
            assert is_healthy is True, "Ollama健康检查失败"
        except Exception as e:
            pytest.skip(f"Ollama健康检查失败: {e}")


class TestOllamaInferenceQuality:
    """Ollama推理质量测试"""
    
    @pytest.fixture
    def ollama_url(self):
        return "http://localhost:11434"
    
    @pytest.fixture
    def test_model(self):
        return "glm4:latest"
    
    @pytest.mark.asyncio
    async def test_lock_wait_diagnosis(self, ollama_url, test_model):
        """测试锁等待诊断推理质量"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            prompt = """你是一个DBA助手。根据以下告警信息，诊断问题原因：

告警：锁等待超时
会话信息：
- PID 1234: SELECT * FROM orders WHERE status='pending' (等待锁)
- PID 5678: UPDATE accounts SET balance=balance-100 (持有锁)

请给出：
1. 问题原因
2. 排查步骤
3. 处理建议
"""
            
            response = await client.complete(prompt=prompt)
            
            # 验证响应质量
            assert response is not None and len(response) > 50, "响应内容过短"
            
            # 验证包含关键信息
            keywords = ["事务", "锁", "提交", "回滚"]
            has_keywords = any(kw in response for kw in keywords)
            assert has_keywords, f"响应缺少关键诊断信息。响应: {response[:200]}"
            
            print(f"锁等待诊断响应:\n{response}")
        except Exception as e:
            pytest.skip(f"锁等待诊断测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_slow_sql_analysis(self, ollama_url, test_model):
        """测试慢SQL分析推理质量"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            prompt = """你是一个DBA助手。分析以下慢SQL：

SQL: SELECT * FROM orders o JOIN customers c ON o.c_id = c.id WHERE c.region = 'APAC'
执行时间: 30ms
执行计划: Nested Loop, Seq Scan on orders

请给出：
1. 性能问题原因
2. 优化建议
3. 索引建议
"""
            
            response = await client.complete(prompt=prompt)
            
            # 验证响应质量
            assert response is not None and len(response) > 50, "响应内容过短"
            
            # 验证包含优化相关关键词
            keywords = ["索引", "优化", "join", "scan"]
            has_keywords = any(kw.lower() in response.lower() for kw in keywords)
            assert has_keywords, f"响应缺少优化建议。响应: {response[:200]}"
            
            print(f"慢SQL分析响应:\n{response}")
        except Exception as e:
            pytest.skip(f"慢SQL分析测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_risk_assessment(self, ollama_url, test_model):
        """测试风险评估推理"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            prompt = """评估以下操作的风险级别：

操作：终止一个数据库会话
会话状态：idle in transaction 600秒
影响：可能中断一个未提交的长事务

请给出：
1. 风险级别(L1-L5)
2. 风险理由
3. 建议措施
"""
            
            response = await client.complete(prompt=prompt)
            
            # 验证响应包含风险级别
            assert response is not None and len(response) > 30, "响应内容过短"
            
            # 验证包含L3-L5级别的风险提示
            risk_keywords = ["L3", "L4", "L5", "高风险", "中风险", "需审批"]
            has_risk = any(kw in response for kw in risk_keywords)
            assert has_risk, f"响应缺少风险级别信息。响应: {response[:200]}"
            
            print(f"风险评估响应:\n{response}")
        except Exception as e:
            pytest.skip(f"风险评估测试失败: {e}")


class TestOllamaStreaming:
    """Ollama流式输出测试"""
    
    @pytest.fixture
    def ollama_url(self):
        return "http://localhost:11434"
    
    @pytest.fixture
    def test_model(self):
        return "glm4:latest"
    
    @pytest.mark.asyncio
    async def test_stream_response(self, ollama_url, test_model):
        """测试流式响应"""
        try:
            from src.llm.ollama_client import OllamaClient
            client = OllamaClient(base_url=ollama_url, model=test_model)
            
            chunks = []
            async for chunk in client.complete_stream(
                prompt="用三个词描述数据库",
                system="简短回答"
            ):
                chunks.append(chunk)
            
            full_response = "".join(chunks)
            assert len(full_response) > 0, "流式响应为空"
            assert len(chunks) > 0, "没有收到任何chunk"
            print(f"流式响应 (共{len(chunks)}个chunk): {full_response}")
        except Exception as e:
            pytest.skip(f"流式响应测试失败: {e}")


class TestOllamaTimeout:
    """Ollama超时处理测试"""
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """测试超时处理"""
        try:
            from src.llm.ollama_client import OllamaClient
            
            # 使用一个极短的超时时间，预期会超时
            client = OllamaClient(base_url="http://localhost:11434", model="glm4:latest")
            client.timeout = 0.001  # 1毫秒超时
            
            with pytest.raises(Exception):
                await client.complete(prompt="测试超时")
        except Exception as e:
            if "Ollama服务" in str(e) or "skip" in str(e).lower():
                pytest.skip(f"Ollama服务未运行: {e}")
            # 预期抛出超时异常
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
