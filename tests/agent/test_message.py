"""Message模型测试 - V3.3-P2 Bug-1修复验证
测试message_id幂等性和跨持久化
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
import time
from src.gateway.persistent_session import Message


class TestMessageIdempotency:
    """message_id幂等性测试"""
    
    def test_message_id_generated_once(self):
        """同一Message对象多次to_dict()应产生相同的message_id"""
        msg = Message(role="user", content="hello")
        id1 = msg.to_dict()["message_id"]
        id2 = msg.to_dict()["message_id"]
        id3 = msg.to_dict()["message_id"]
        
        assert id1 == id2 == id3, f"message_id不一致: {id1}, {id2}, {id3}"
    
    def test_different_messages_have_different_ids(self):
        """不同Message对象应有不同的message_id"""
        msg1 = Message(role="user", content="hello")
        msg2 = Message(role="user", content="world")
        
        assert msg1._message_id != msg2._message_id


class TestMessagePersistence:
    """message_id跨持久化测试"""
    
    def test_from_dict_preserves_message_id(self):
        """从dict恢复Message时，message_id应被保留"""
        original = Message(role="user", content="test message")
        original_id = original._message_id
        
        # 模拟持久化/恢复
        data = original.to_dict()
        restored = Message.from_dict(data)
        
        assert restored._message_id == original_id, \
            f"message_id未保留: 原始={original_id}, 恢复={restored._message_id}"
    
    def test_from_dict_preserves_message_id_across_multiple_cycles(self):
        """多次持久化/恢复循环后message_id仍应保持一致"""
        msg = Message(role="assistant", content="response")
        original_id = msg._message_id
        
        for i in range(5):
            data = msg.to_dict()
            msg = Message.from_dict(data)
        
        assert msg._message_id == original_id, \
            f"多次循环后message_id丢失: 原始={original_id}, 当前={msg._message_id}"
    
    def test_to_dict_from_dict_roundtrip(self):
        """完整的to_dict/from_dict往返测试"""
        original = Message(
            role="user",
            content="测试内容",
            tool_calls=[{"name": "test", "args": {}}],
            tool_call_id="call_123",
            timestamp=1234567890.0
        )
        
        # 往返
        data = original.to_dict()
        restored = Message.from_dict(data)
        
        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.tool_calls == original.tool_calls
        assert restored.tool_call_id == original.tool_call_id
        assert abs(restored.timestamp - original.timestamp) < 0.001
        assert restored._message_id == original._message_id


class TestMessageEdgeCases:
    """边界情况测试"""
    
    def test_from_dict_with_no_message_id(self):
        """从没有message_id的dict恢复应生成新的message_id"""
        data = {
            "role": "user",
            "content": "test",
            "tool_calls": "",
            "tool_call_id": "",
            "timestamp": time.time(),
        }
        
        msg = Message.from_dict(data)
        assert msg._message_id is not None
        assert len(msg._message_id) > 0
    
    def test_from_dict_with_empty_message_id(self):
        """从message_id为空字符串的dict恢复应生成新的message_id"""
        data = {
            "role": "user",
            "content": "test",
            "tool_calls": "",
            "tool_call_id": "",
            "timestamp": time.time(),
            "message_id": "",
        }
        
        msg = Message.from_dict(data)
        assert msg._message_id is not None
        assert len(msg._message_id) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
