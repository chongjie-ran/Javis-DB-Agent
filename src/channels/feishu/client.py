"""飞书API客户端

封装飞书开放平台API，支持：
- 获取tenant_access_token
- 发送消息（文本、卡片、Markdown）
- 上传媒体文件
- 获取用户信息
"""
import time
import httpx
import json
import logging
from typing import Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FeishuMessageResult:
    """消息发送结果"""
    message_id: str
    chat_id: str
    code: int = 0
    msg: str = "success"


class FeishuAPIError(Exception):
    """飞书API异常"""
    def __init__(self, code: int, msg: str, data: Any = None):
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(f"Feishu API Error [{code}]: {msg}")


class FeishuClient:
    """
    飞书API客户端

    文档: https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM
    """

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self._tenant_token: Optional[str] = None
        self._token_expires_at: float = 0

    # ==================== Token管理 ====================

    async def get_tenant_access_token(self) -> str:
        """获取tenant_access_token（自动续期）"""
        # 检查是否过期（提前5分钟刷新）
        if self._tenant_token and time.time() < self._token_expires_at - 300:
            return self._tenant_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
            )
            data = resp.json()

        if data.get("code") != 0:
            raise FeishuAPIError(
                code=data.get("code", -1),
                msg=data.get("msg", "获取token失败"),
            )

        self._tenant_token = data["tenant_access_token"]
        # token有效期2小时
        self._token_expires_at = time.time() + 7200

        return self._tenant_token

    def _headers(self, token: str) -> dict:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _post(
        self,
        path: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """POST请求"""
        token = await self.get_tenant_access_token()
        url = f"{self.BASE_URL}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url,
                json=data,
                params=params,
                headers=self._headers(token),
            )
            result = resp.json()

        if result.get("code") != 0:
            raise FeishuAPIError(
                code=result.get("code", -1),
                msg=result.get("msg", "请求失败"),
                data=result,
            )

        return result

    async def _get(
        self,
        path: str,
        params: Optional[dict] = None,
    ) -> dict:
        """GET请求"""
        token = await self.get_tenant_access_token()
        url = f"{self.BASE_URL}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                url,
                params=params,
                headers=self._headers(token),
            )
            result = resp.json()

        if result.get("code") != 0:
            raise FeishuAPIError(
                code=result.get("code", -1),
                msg=result.get("msg", "请求失败"),
                data=result,
            )

        return result

    # ==================== 消息发送 ====================

    async def send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: dict,
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """
        发送消息

        Args:
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型 (open_id/user_id/union_id/chat_id)
            msg_type: 消息类型 (text/post/interactive/image/file/media/audio)
            content: 消息内容（JSON）
            reply_message_id: 回复的消息ID
            reply_in_thread: 是否在线程中回复

        Returns:
            FeishuMessageResult
        """
        path = "/im/v1/messages"
        params = {"receive_id_type": receive_id_type}

        if reply_message_id:
            path = f"/im/v1/messages/{reply_message_id}/reply"
            params["reply_in_thread"] = reply_in_thread

        data = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content) if isinstance(content, dict) else content,
        }

        result = await self._post(path, data=data, params=params)

        msg_data = result.get("data", {})
        return FeishuMessageResult(
            message_id=msg_data.get("message_id", ""),
            chat_id=msg_data.get("chat_id", ""),
            code=result.get("code", 0),
            msg=result.get("msg", "success"),
        )

    async def send_text(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        text: str = "",
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """发送文本消息"""
        content = {"text": text}
        return await self.send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content=content,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    async def send_post(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        post_content: Optional[dict] = None,
        text: str = "",
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """
        发送富文本消息（post类型，支持Markdown）

        post_content格式:
        {
            "zh_cn": {
                "title": "标题",
                "content": [
                    [{"tag": "text", "text": "文本"}],
                    [{"tag": "at", "text": "@用户", "user_id": "user_id"}],
                    [{"tag": "link", "text": "链接", "href": "https://..."}],
                ]
            }
        }
        """
        if post_content:
            content = post_content
        else:
            # 默认使用md标签支持Markdown
            content = {
                "zh_cn": {
                    "content": [[{"tag": "md", "text": text}]],
                }
            }

        return await self.send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="post",
            content=content,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    async def send_interactive(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        card: Optional[dict] = None,
        card_content: Optional[dict] = None,
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """
        发送卡片消息

        card: 卡片JSON对象（CardKit v2格式）
        card_content: 等同于card，为兼容而提供
        """
        card_data = card or card_content
        return await self.send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="interactive",
            content=card_data,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    async def update_message(
        self,
        message_id: str,
        msg_type: str,
        content: dict,
    ) -> bool:
        """
        更新消息（仅支持更新卡片消息）

        Returns:
            是否更新成功
        """
        path = f"/im/v1/messages/{message_id}"
        data = {
            "msg_type": msg_type,
            "content": json.dumps(content) if isinstance(content, dict) else content,
        }

        token = await self.get_tenant_access_token()
        url = f"{self.BASE_URL}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.patch(
                url,
                json=data,
                headers=self._headers(token),
            )
            result = resp.json()

        return result.get("code") == 0

    # ==================== 媒体文件 ====================

    async def upload_media(
        self,
        file_path: str,
        file_name: str,
        file_type: str = "message_file",
    ) -> Optional[str]:
        """
        上传媒体文件，获取file_key

        Args:
            file_path: 文件路径
            file_name: 文件名
            file_type: 文件类型 (message_file/message_image/message_audio/message_video)

        Returns:
            file_key 或 None
        """
        import mimetypes
        import os

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        url = f"{self.BASE_URL}/im/v1/files"

        token = await self.get_tenant_access_token()

        file_size = os.path.getsize(file_path)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    url,
                    data={
                        "file_name": file_name,
                        "file_type": file_type,
                        "file_size": str(file_size),
                    },
                    files={"file": (file_name, f, mime_type)},
                    headers={"Authorization": f"Bearer {token}"},
                )
            result = resp.json()

        if result.get("code") != 0:
            raise FeishuAPIError(
                code=result.get("code", -1),
                msg=result.get("msg", "上传失败"),
            )

        return result.get("data", {}).get("file_key")

    async def download_media(self, message_id: str, file_key: str) -> bytes:
        """下载媒体文件内容"""
        path = f"/im/v1/messages/{message_id}/resources/{file_key}"

        token = await self.get_tenant_access_token()
        url = f"{self.BASE_URL}{path}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                url,
                headers=self._headers(token),
            )

        if resp.status_code != 200:
            raise FeishuAPIError(
                code=resp.status_code,
                msg=f"下载失败: HTTP {resp.status_code}",
            )

        return resp.content

    # ==================== 用户信息 ====================

    async def get_user_info(self, user_id: str) -> Optional[dict]:
        """获取用户信息"""
        result = await self._get(
            "/contact/v3/users/" + user_id,
            params={"user_id_type": "open_id"},
        )
        return result.get("data", {}).get("user")

    async def get_bot_info(self) -> Optional[dict]:
        """获取Bot信息"""
        result = await self._get("/bot/v3/info")
        return result.get("data")

    # ==================== 群组信息 ====================

    async def get_chat_info(self, chat_id: str) -> Optional[dict]:
        """获取群组信息"""
        result = await self._get(f"/im/v1/chats/{chat_id}")
        return result.get("data")

    # ==================== Webhook事件验证 ====================

    @staticmethod
    def verify_webhook(
        body: dict,
        headers: dict,
        verify_token: str,
        encrypt_key: Optional[str] = None,
    ) -> bool:
        """
        验证Webhook请求

        文档: https://open.feishu.cn/document/ukTMukTMukTM/ucDOz4yN4QjLxADMT
        """
        # 解密（如果启用加密）
        if encrypt_key:
            import base64
            from cryptography.hazmat.primitives.cipher import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend

            encrypted = body.get("encrypt", "")
            if encrypted:
                key = encrypt_key.encode()[:32].ljust(32, b"\0")
                iv = base64.b64decode(body.get("encrypt", ""))[:16]
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
                decryptor = cipher.decryptor()
                decrypted = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
                # 移除PKCS7填充
                pad_len = decrypted[-1]
                decrypted = decrypted[:-pad_len]
                body = json.loads(decrypted)

        # 验证Token
        token = headers.get("X-Feishu-Encryption-Token", "")
        return token == verify_token


# ==================== 工厂函数 ====================

_clients: dict[str, FeishuClient] = {}


def get_feishu_client(app_id: str, app_secret: str) -> FeishuClient:
    """获取或创建FeishuClient实例"""
    key = f"{app_id}"
    if key not in _clients:
        _clients[key] = FeishuClient(app_id=app_id, app_secret=app_secret)
    return _clients[key]


def reset_feishu_clients():
    """重置所有客户端（用于测试）"""
    _clients.clear()
