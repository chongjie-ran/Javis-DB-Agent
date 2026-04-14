"""
AutoMemory 测试
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.memory.auto_memory import AutoMemory, Correction
from src.memory.memory_manager import MemoryManager


class MockMemoryManager:
    """Mock MemoryManager for testing"""
    def __init__(self):
        self.saved = []

    async def save(self, content: str, memory_type: str, tags: list = None):
        # Simple record-like object with expected attributes
        class SavedRecord:
            def __init__(self, content, memory_type, tags):
                self.content = content
                self.memory_type = memory_type
                self.tags = tags
        self.saved.append(SavedRecord(content, memory_type, tags or []))

    def search(self, keyword, case_sensitive=False):
        return []


class TestAutoMemory:
    """AutoMemory测试"""

    def test_record_correction(self):
        """记录纠正"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        am.record_correction("原始结论", "正确结论", "原因")
        
        assert len(am._session_corrections) == 1
        assert am._session_corrections[0].original_action == "原始结论"
        assert am._session_corrections[0].correction == "正确结论"

    def test_should_remember_false_for_code(self):
        """绝对不记：代码语法"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        assert am.should_remember("def hello(): print('hi')") is False
        assert am.should_remember("class MyClass: pass") is False
        assert am.should_remember("import os") is False

    def test_should_remember_false_for_git(self):
        """绝对不记：Git命令"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        assert am.should_remember("git commit -m 'fix'") is False
        assert am.should_remember("git push origin main") is False

    def test_should_remember_false_for_debug(self):
        """绝对不记：调试代码"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        assert am.should_remember("print(result)") is False
        assert am.should_remember("logger.debug('debug')") is False

    def test_should_remember_false_for_short(self):
        """绝对不记：太短的内容"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        assert am.should_remember("ok") is False  # length < 3
        assert am.should_remember("a") is False  # length < 3

    def test_should_remember_true_for_valid(self):
        """应该记忆：有效的学习内容"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        assert am.should_remember("每次调用前需要检查参数有效性") is True
        assert am.should_remember("这个文件位置不对，应该在configs目录下") is True

    def test_extract_memory_type_feedback(self):
        """推断类型：默认feedback"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        corr = Correction("做错了", "应该这样做", reason="原因")
        assert am.extract_memory_type(corr) == "feedback"

    def test_extract_memory_type_pattern(self):
        """推断类型：pattern"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        corr = Correction("每次都错", "这是规律", reason="总是要先验证")
        assert am.extract_memory_type(corr) == "pattern"

    def test_extract_memory_type_reference(self):
        """推断类型：reference"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        corr = Correction("在哪里", "在src/api/routes.py文件里", reason=None)
        assert am.extract_memory_type(corr) == "reference"

    def test_consolidate_session(self):
        """会话整合"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        am.record_correction("原来的做法是错的", "应该用正确的方式来做", "原因")
        am.record_correction("def foo():", "def bar():", "函数名错了")  # 不应记忆
        
        count = am.consolidate_session()
        
        assert count == 1
        assert len(mm.saved) == 1
        assert mm.saved[0].memory_type == "feedback"

    def test_get_learnings(self):
        """获取学习点"""
        mm = MockMemoryManager()
        am = AutoMemory(mm)
        
        learnings = am.get_learnings("当前任务", limit=3)
        assert isinstance(learnings, list)
        assert len(learnings) <= 3
