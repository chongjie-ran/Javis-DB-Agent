"""流式对话API路由 - 支持SSE流式响应（基于现有handle_chat增强）"""
import asyncio
import json
import time
import uuid
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from src.api.schemas import ChatRequest
from src.api.auth import get_auth_manager

router = APIRouter(prefix="/api/v1/chat", tags=["流式对话"])


def _get_user_from_token(authorization: str = Header(None)) -> dict:
    """验证token并返回用户信息（可选）"""
    if not authorization:
        return {"user_id": "anonymous", "username": "anonymous", "role": "guest"}
    try:
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        auth = get_auth_manager()
        payload = auth.verify_token(token)
        if payload:
            return payload
        return {"user_id": "anonymous", "username": "anonymous", "role": "guest"}
    except Exception:
        return {"user_id": "anonymous", "username": "anonymous", "role": "guest"}


async def _stream_text(text: str, delay: float = 0.015):
    """将文本内容按小块yield，模拟打字机效果"""
    words = text.split()
    buffer = ""
    for word in words:
        buffer += word + " "
        if len(buffer) >= 8 or word.endswith(("\n", "。", "！", "？", ".", "!", "?")):
            yield buffer
            buffer = ""
            await asyncio.sleep(delay)
    if buffer:
        yield buffer
        await asyncio.sleep(delay)


async def _stream_chat(request: ChatRequest, user_info: dict):
    """生成流式聊天气泡的SSE响应"""
    from src.agents.orchestrator import OrchestratorAgent
    from src.agents.diagnostic import DiagnosticAgent
    from src.agents.risk import RiskAgent
    from src.agents.sql_analyzer import SQLAnalyzerAgent
    from src.agents.inspector import InspectorAgent
    from src.agents.reporter import ReporterAgent
    from src.gateway.session import get_session_manager

    session_id = request.session_id or f"dash-{uuid.uuid4().hex[:8]}"
    user_id = request.user_id or user_info.get("sub") or user_info.get("user_id", "anonymous")
    requested_agent = request.agent  # 前端指定的Agent

    # 发送session_id
    yield f"event: session\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

    # 发送thinking状态
    yield f"event: thinking\ndata: {json.dumps({'thinking': True, 'message': '🤖 正在思考...'}, ensure_ascii=False)}\n\n"

    try:
        session_mgr = get_session_manager()

        # 获取或创建会话
        session = session_mgr.get_session(session_id)
        if not session:
            session = session_mgr.create_session(user_id)

        context = {
            "session_id": session.session_id,
            "user_id": user_id,
            "extra_info": str(request.context or {}),
        }

        # ── 创建数据库连接器并加入 context ──────────────────────────────
        # InspectorAgent 等需要直连数据库查询真实数据
        try:
            from src.db.direct_postgres_connector import DirectPostgresConnector
            context["pg_connector"] = DirectPostgresConnector(
                host="localhost",
                port=5432,
                user="chongjieran",
                password="",
                database="postgres",
            )
        except Exception as e:
            print(f"[chat_stream] 创建 PG 连接器失败: {e}")
            context["pg_connector"] = None

        try:
            from src.db.mysql_adapter import MySQLConnector
            context["mysql_connector"] = MySQLConnector(
                host="127.0.0.1",
                port=3306,
                username="root",
                password="root",
            )
        except Exception as e:
            print(f"[chat_stream] 创建 MySQL 连接器失败: {e}")
            context["mysql_connector"] = None

        # 兼容旧字段名（postgres_tools.py 用 db_connector）
        context["db_connector"] = context.get("pg_connector")

        # 根据选择的Agent路由到对应的Agent
        agent_map = {
            "diagnostic": DiagnosticAgent(),
            "risk": RiskAgent(),
            "sql_analyzer": SQLAnalyzerAgent(),
            "inspector": InspectorAgent(),
            "reporter": ReporterAgent(),
        }
        
        # 调用Agent（非流式，但返回完整结果）
        active_agent_name = "orchestrator"
        if requested_agent and requested_agent in agent_map:
            # 直接调用指定的Agent
            active_agent = agent_map[requested_agent]
            active_agent_name = requested_agent
            if hasattr(active_agent, 'handle_chat'):
                response = await active_agent.handle_chat(request.message, context)
            else:
                # Agent没有handle_chat方法，使用编排Agent
                orch = OrchestratorAgent()
                response = await orch.handle_chat(request.message, context)
                active_agent_name = "orchestrator"
        else:
            # 使用编排Agent（默认智能路由）
            orch = OrchestratorAgent()
            response = await orch.handle_chat(request.message, context)

        # thinking结束
        yield f"event: thinking\ndata: {json.dumps({'thinking': False}, ensure_ascii=False)}\n\n"

        # 流式发送响应文本（打字机效果）
        full_content = response.content
        async for chunk in _stream_text(full_content):
            yield f"event: chunk\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        # 记录到会话
        session.add_message("user", request.message)
        session.add_message("assistant", full_content)
        session_mgr.save_session(session)

        # 发送完成信号
        yield f"event: done\ndata: {json.dumps({'content': full_content, 'agent': response.metadata.get('agent', active_agent_name)}, ensure_ascii=False)}\n\n"

        # ── 清理数据库连接 ────────────────────────────────────────────────
        try:
            if context.get("pg_connector"):
                await context["pg_connector"].close()
            if context.get("mysql_connector"):
                await context["mysql_connector"].close()
        except Exception:
            pass

    except Exception as e:
        # 清理连接（即使出错也要清理）
        try:
            if context.get("pg_connector"):
                await context["pg_connector"].close()
            if context.get("mysql_connector"):
                await context["mysql_connector"].close()
        except Exception:
            pass
        yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest, authorization: str = Header(None)):
    """
    流式对话接口 - SSE

    支持Bearer token认证（可选）
    事件流:
    - session: 发送session_id
    - thinking: 思考状态变化
    - chunk: 文本片段（打字机效果）
    - done: 完成
    - error: 错误
    """
    user_info = _get_user_from_token(authorization)
    return StreamingResponse(
        _stream_chat(request, user_info),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    """获取会话历史"""
    from src.gateway.session import get_session_manager
    session_mgr = get_session_manager()
    session = session_mgr.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    history = []
    for msg in session.messages:
        history.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp,
        })

    return {"session_id": session_id, "messages": history, "count": len(history)}
