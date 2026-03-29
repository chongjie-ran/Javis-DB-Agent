"""企业微信回调路由

接收企微回调推送的消息，转发给WecomChannel处理
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Header, Query
from fastapi.responses import PlainTextResponse
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/channels/wecom", tags=["企微通道"])


@router.get("/callback")
async def wecom_callback_verify(
    msg_signature: str = Query(..., description="消息签名"),
    timestamp: str = Query(..., description="时间戳"),
    nonce: str = Query(..., description="随机数"),
    echostr: Optional[str] = Query(None, description="加密的echostr"),
):
    """
    企微回调URL验证（首次配置回调URL时调用一次）

    GET请求用于URL验证（回调模式初始化）
    """
    from src.channels.wecom.message_handler import get_wecom_handler

    handler = get_wecom_handler()

    # 如果提供了echostr，说明启用了加密模式
    if echostr:
        try:
            decrypted = handler.decrypt_message(echostr)
            import base64
            echostr_decoded = base64.b64decode(decrypted).decode("utf-8")
            return PlainTextResponse(content=echostr_decoded)
        except Exception as e:
            logger.error(f"[WecomCallback] Verify decrypt error: {e}")
            raise HTTPException(status_code=400, detail="Decrypt error")

    # URL验证：返回success
    # 注意：首次配置时，企微会发送GET请求验证URL有效性
    # 企微要求在接收到消息后立即返回echostr内容以证明URL有效
    return PlainTextResponse(content="success")


@router.post("/callback")
async def wecom_callback(
    request: Request,
    msg_signature: str = Query(..., description="消息签名"),
    timestamp: str = Query(..., description="时间戳"),
    nonce: str = Query(..., description="随机数"),
    encrypt_type: Optional[str] = Query(None, description="加密类型"),
):
    """
    企微回调消息接收

    POST请求接收企微推送的消息事件
    支持两种模式：
    - plaintext: 明文模式（推荐开发测试使用）
    - aes: AES加密模式（生产环境使用）
    """
    from src.channels.wecom.message_handler import get_wecom_handler
    from src.channels.wecom.wecom_channel import get_wecom_channel

    body = await request.body()
    headers = dict(request.headers)
    handler = get_wecom_handler()

    logger.info(
        f"[WecomCallback] Received callback: encrypt_type={encrypt_type}, "
        f"body_len={len(body)}, sig={msg_signature[:10]}..."
    )

    # 如果启用了加密，需要解密
    if encrypt_type == "aes":
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(body)
            encrypt_node = root.find("Encrypt")
            if encrypt_node is not None:
                encrypted_xml = encrypt_node.text
                body_str = handler.decrypt_message(encrypted_xml)
                body = body_str.encode("utf-8")
        except Exception as e:
            logger.error(f"[WecomCallback] AES decrypt error: {e}")
            raise HTTPException(status_code=400, detail="Decrypt error")
    elif encrypt_type is None or encrypt_type == "":
        # 明文模式，无需处理
        pass

    # 转发给WecomChannel处理
    try:
        channel = get_wecom_channel()
        channel_msg = await channel.handle_callback(body, headers)
        logger.info(
            f"[WecomCallback] Processed: msg_id={channel_msg.message_id}, "
            f"user={channel_msg.user_id}, session={channel_msg.session_id}"
        )
    except ValueError as e:
        logger.warning(f"[WecomCallback] Parse error (ignored): {e}")
    except Exception as e:
        logger.error(f"[WecomCallback] Process error: {e}", exc_info=True)

    # 企微要求立即返回"success"以确认收到
    return PlainTextResponse(content="success")


@router.post("/send")
async def wecom_send_message(
    chatid: str,
    content: str,
    chat_type: int = 1,
    msgtype: str = "text",
    session_id: Optional[str] = None,
):
    """
    主动发送企微消息

    用于Agent主动向用户发消息（如告警通知）

    Args:
        chatid: 接收方userid（单聊）或群ID（群聊）
        content: 消息内容
        chat_type: 1=单聊, 2=群聊
        msgtype: 消息类型
        session_id: 可选，用于确定发送目标

    Returns:
        {"success": true, "errcode": 0, ...}
    """
    from src.channels.wecom.wecom_channel import get_wecom_channel

    try:
        channel = get_wecom_channel()
        result = await channel.send(
            user_id=chatid,
            content=content,
            session_id=session_id,
            chat_type=chat_type,
            msgtype=msgtype,
            is_group=(chat_type == 2),
        )
        return {
            "success": result.success,
            "errcode": 0 if result.success else -1,
            "errmsg": result.error,
            "data": result.data,
        }
    except Exception as e:
        logger.error(f"[WecomSend] Error: {e}")
        return {"success": False, "errcode": -1, "errmsg": str(e)}


@router.post("/alert")
async def wecom_push_alert(
    content: str,
    alert_level: str = "warning",
    target: Optional[str] = None,
):
    """
    推送告警到企微

    Args:
        content: 告警内容
        alert_level: critical/warning/info
        target: 可选，指定目标会话

    Returns:
        {"success": true, ...}
    """
    from src.channels.wecom.wecom_channel import get_wecom_channel

    try:
        channel = get_wecom_channel()
        result = await channel.push_alert(content, alert_level, target)
        return {
            "success": result.success,
            "errmsg": result.error,
            "data": result.data,
        }
    except Exception as e:
        logger.error(f"[WecomAlert] Error: {e}")
        return {"success": False, "errmsg": str(e)}


@router.get("/sessions")
async def wecom_list_sessions():
    """
    列出企微通道的活跃会话映射

    Returns:
        {"sessions": [{"channel_key": "...", "session_id": "..."}]}
    """
    from src.channels.wecom.message_handler import get_wecom_handler

    handler = get_wecom_handler()
    sessions = handler.get_all_sessions()
    return {
        "count": len(sessions),
        "sessions": [
            {"channel_key": k, "session_id": v}
            for k, v in sessions.items()
        ],
    }


@router.delete("/sessions/{channel_key}")
async def wecom_delete_session(channel_key: str):
    """
    删除企微会话映射

    Args:
        channel_key: 格式 "user:{userid}" 或 "group:{chatid}"
    """
    from src.channels.wecom.message_handler import get_wecom_handler

    handler = get_wecom_handler()
    sessions = handler.get_all_sessions()

    if channel_key in sessions:
        del sessions[channel_key]
        return {"success": True, "message": f"Deleted {channel_key}"}
    else:
        raise HTTPException(status_code=404, detail=f"Session not found: {channel_key}")
