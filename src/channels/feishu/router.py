"""飞书Webhook路由

提供FastAPI路由用于接收飞书Webhook回调。
支持Webhook模式和混合模式（WebSocket+Webhook）。
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from src.channels.feishu.feishu_channel import get_feishu_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["飞书"])


class WebhookResponse(BaseModel):
    """Webhook响应"""
    code: int = 0
    msg: str = "success"


@router.post("/webhook", response_model=WebhookResponse)
async def feishu_webhook(
    request: Request,
    x_feishu_encryption_token: Optional[str] = Header(None, alias="X-Feishu-Encryption-Token"),
    x_feishu_signature: Optional[str] = Header(None, alias="X-Feishu-Signature"),
):
    """
    飞书Webhook回调入口

    处理飞书服务器推送的事件通知。

    Headers:
    - X-Feishu-Encryption-Token: 加密Token
    - X-Feishu-Signature: 签名

    Body:
    飞书事件payload，参考:
    https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
    """
    channel = get_feishu_channel()
    if not channel:
        raise HTTPException(status_code=500, detail="飞书通道未启动")

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"解析请求体失败: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    headers = {
        "X-Feishu-Encryption-Token": x_feishu_encryption_token or "",
        "X-Feishu-Signature": x_feishu_signature or "",
    }

    try:
        result = await channel._handler.handle_webhook(body, headers)
        return WebhookResponse(code=result.get("code", 0), msg=result.get("msg", "success"))
    except Exception as e:
        logger.error(f"处理Webhook失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def feishu_status():
    """获取飞书通道状态"""
    channel = get_feishu_channel()
    if not channel:
        return {
            "running": False,
            "message": "飞书通道未启动",
        }

    status = channel.get_status()
    return {
        "running": status.running,
        "mode": status.mode,
        "account_id": status.account_id,
        "error": status.error,
        "last_start_at": status.last_start_at,
        "last_stop_at": status.last_stop_at,
    }


@router.get("/stats")
async def feishu_stats():
    """获取飞书通道统计"""
    channel = get_feishu_channel()
    if not channel:
        return {"error": "飞书通道未启动"}

    return channel.get_stats()


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    chat_id: str
    text: str
    msg_type: str = "text"  # text/post/interactive
    reply_message_id: Optional[str] = None


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    message_id: str
    success: bool


@router.post("/send", response_model=SendMessageResponse)
async def send_feishu_message(request: SendMessageRequest):
    """主动发送消息到飞书"""
    channel = get_feishu_channel()
    if not channel:
        raise HTTPException(status_code=500, detail="飞书通道未启动")

    try:
        message_id = await channel.send_message(
            chat_id=request.chat_id,
            text=request.text,
            msg_type=request.msg_type,
            reply_message_id=request.reply_message_id,
        )
        return SendMessageResponse(
            message_id=message_id or "",
            success=bool(message_id),
        )
    except Exception as e:
        logger.error(f"发送消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class AlertRequest(BaseModel):
    """发送告警请求"""
    chat_id: str
    title: str
    level: str = "info"  # critical/warning/info
    content: str = ""


@router.post("/alert", response_model=SendMessageResponse)
async def send_feishu_alert(request: AlertRequest):
    """发送告警通知到飞书"""
    channel = get_feishu_channel()
    if not channel:
        raise HTTPException(status_code=500, detail="飞书通道未启动")

    try:
        message_id = await channel.send_alert(
            chat_id=request.chat_id,
            title=request.title,
            level=request.level,
            content=request.content,
        )
        return SendMessageResponse(
            message_id=message_id or "",
            success=bool(message_id),
        )
    except Exception as e:
        logger.error(f"发送告警失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
