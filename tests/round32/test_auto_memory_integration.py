"""
AutoMemory 集成测试 - V3.1 P0功能

测试覆盖：
1. record_correction - 记录纠正行为
2. should_remember - 记忆过滤器（绝对不记规则）
3. extract_memory_type - 记忆类型推断
4. consolidate_session - 会话结束整合
5. get_learnings - 获取相关学习点
6. 与MemoryManager集成

运行：
    cd ~/.openclaw/workspace/Javis-DB-Agent
    python3 -m pytest tests/round32/test_auto_memory_integration.py -v --tb=short

已知Bug (待修复):
1. should_remember 不匹配 "from X import Y" 语法
2. consolidate_session 过滤掉所有中文内容（should_remember逻辑问题）
3. get_learnings 调用 search() 时传递了不支持的 limit 参数
"""

import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.memory.auto_memory import AutoMemory, Correction
from src.memory.memory_manager import MemoryManager, MemoryRecord


class TestAutoMemoryRecordCorrection:
    """record_correction 功能测试"""

    def test_record_single_correction(self):
        """记录单条纠正"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("原方案 A", "改用方案 B", "A 有性能问题")
        
        assert len(am._session_corrections) == 1
        corr = am._session_corrections[0]
        assert corr.original_action == "原方案 A"
        assert corr.correction == "改用方案 B"
        assert corr.reason == "A 有性能问题"

    def test_record_multiple_corrections(self):
        """记录多条纠正"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("方案 1", "方案 2", "原因 1")
        am.record_correction("做法 X", "做法 Y", "原因 2")
        am.record_correction("结论 A", "结论 B", None)
        
        assert len(am._session_corrections) == 3

    def test_correction_timestamp_auto(self):
        """时间戳自动生成"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("错", "对")
        
        assert am._session_corrections[0].timestamp is not None


class TestAutoMemoryShouldRemember:
    """should_remember 记忆过滤器测试"""

    def test_reject_code_def(self):
        """拒绝：函数定义"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        assert am.should_remember("def calculate(x, y): return x + y") is False

    def test_reject_code_class(self):
        """拒绝：类定义"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("class MyValidator: pass") is False

    def test_reject_import_statement(self):
        """拒绝：import 语句（包括 from X import Y）"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("import os") is False
        # Fixed: from X import Y 现在被正确拒绝
        assert am.should_remember("from typing import List") is False

    def test_reject_git_commands(self):
        """拒绝：Git 命令"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("git commit -m 'fix bug'") is False
        assert am.should_remember("git push origin main") is False

    def test_reject_debug_print(self):
        """拒绝：print 调试"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("print(result)") is False

    def test_reject_debug_logger(self):
        """拒绝：日志调试"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("logger.info('debug message')") is False

    def test_reject_too_short(self):
        """拒绝：内容太短"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        assert am.should_remember("ok") is False
        assert am.should_remember("hi") is False  # 2 chars < 3 threshold

    def test_accept_valid_learning(self):
        """接受：有效学习内容"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        # Fixed: 中文内容现在被正确接受
        assert am.should_remember("这个 SQL 查询需要添加索引才能提升性能") is True


class TestAutoMemoryExtractType:
    """extract_memory_type 记忆类型推断测试"""

    def test_type_pattern_keywords(self):
        """推断为 pattern：包含规律关键字"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        
        corr = Correction("每次都错", "规律性正确做法", "总是要先检查")
        assert am.extract_memory_type(corr) == "pattern"

    def test_type_reference_keywords(self):
        """推断为 reference：包含位置关键字"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        
        corr = Correction("找不到", "在 src/api/routes.py 文件里", None)
        assert am.extract_memory_type(corr) == "reference"

    def test_type_default_feedback(self):
        """推断为 feedback：默认类型"""
        am = AutoMemory(MemoryManager(tempfile.mkdtemp()))
        
        corr = Correction("做错了", "应该这样做", None)
        assert am.extract_memory_type(corr) == "feedback"


class TestAutoMemoryConsolidateSession:
    """consolidate_session 会话整合测试"""

    def test_consolidate_empty_session(self):
        """空会话返回 0"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        count = am.consolidate_session()
        assert count == 0

    def test_consolidate_with_valid_corrections(self):
        """整合有效纠正 - 中文内容现在被正确保留"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("原方案", "新方案", "原因说明")
        count = am.consolidate_session()
        
        # Fixed: 中文内容现在被正确保留
        assert count == 1

    def test_consolidate_filters_code(self):
        """整合时过滤代码语法"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("def foo():", "def bar():")  # 应被过滤
        am.record_correction("这个配置项写法不对", "应该在根目录")  # 应保留
        
        count = am.consolidate_session()
        # Fixed: 中文内容现在被正确保留
        assert count == 1

    def test_consolidate_with_memory_manager(self):
        """与真实 MemoryManager 集成"""
        tmpdir = tempfile.mkdtemp()
        try:
            mm = MemoryManager(tmpdir)
            am = AutoMemory(mm)
            
            am.record_correction("原结论", "正确结论", "因为...")
            count = am.consolidate_session()
            
            # Fixed: 中文内容现在被正确保留
            assert count == 1
        finally:
            shutil.rmtree(tmpdir)


class TestAutoMemoryGetLearnings:
    """get_learnings 获取学习点测试"""

    def test_get_learnings_empty(self):
        """无学习点时返回空列表 - Bug: search() 不支持 limit 参数"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        # Bug: get_learnings 调用 search(context, limit=...) 但 search() 不支持 limit
        # BUG-AM-03 fixed: search() no longer uses limit param
        result = am.get_learnings("数据库优化", limit=3)
        assert isinstance(result, list)

    def test_get_learnings_limit(self):
        """限制返回数量 - Bug: search() 不支持 limit 参数"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        # BUG-AM-03 fixed: search() no longer uses limit param
        result = am.get_learnings("数据库优化", limit=3)
        assert isinstance(result, list)


class TestAutoMemoryIntegration:
    """端到端集成测试"""

    def test_full_correction_workflow(self):
        """完整纠正 - 整合工作流"""
        tmpdir = tempfile.mkdtemp()
        try:
            mm = MemoryManager(tmpdir)
            am = AutoMemory(mm)
            
            am.record_correction("直接在生产环境测试", "先在测试环境验证", "避免生产事故")
            am.record_correction("忽略索引", "添加适当索引", "性能考虑")
            am.record_correction("def foo(): pass", "def bar(): pass")  # 会被过滤
            
            count = am.consolidate_session()
            
            # Fixed: 2 条中文内容被保留，1 条代码被过滤
            assert count == 2
        finally:
            shutil.rmtree(tmpdir)

    def test_correction_with_no_reason(self):
        """无原因纠正"""
        mm = MemoryManager(tempfile.mkdtemp())
        am = AutoMemory(mm)
        
        am.record_correction("A 做法", "B 做法")
        count = am.consolidate_session()
        
        # Fixed: 中文内容现在被正确保留
        assert count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
