"""SSE流式Hook - 将on_stream chunks转为SSE事件 (V3.2)"""
import json
from typing import AsyncIterator
from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext


class SSEStreamHook(AgentHook):
    """on_stream时yield SSE格式事件，替代手动的_stream_text()"""

    name: str = "sse_stream"
    priority: int = 5

    def __init__(self):
        self._chunks = []

    def on_stream(self, ctx: AgentHookContext, chunk: str) -> AgentHookContext:
        self._chunks.append(chunk)
        return ctx

    def get_sse_chunks(self) -> list[str]:
        return list(self._chunks)

    def clear(self):
        self._chunks.clear()
