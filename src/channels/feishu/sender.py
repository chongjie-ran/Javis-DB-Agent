"""飞书消息发送器

负责将zCloud Agent的响应发送回飞书，支持：
- 文本消息
- 卡片消息（Interactive Card）
- Markdown富文本
- 流式响应（卡片更新）
"""
import json
import logging
from typing import Optional, Any
from src.channels.feishu.client import FeishuClient, FeishuMessageResult
from src.channels.feishu.config import FeishuChannelConfig

logger = logging.getLogger(__name__)


class FeishuSender:
    """
    飞书消息发送器

    将zCloud Agent的响应格式化并发送到飞书。
    支持多种消息类型：文本、卡片、Markdown。
    """

    def __init__(self, client: FeishuClient, config: FeishuChannelConfig):
        self.client = client
        self.config = config

    # ==================== 基础发送 ====================

    async def send_text(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        text: str = "",
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """发送纯文本消息"""
        logger.debug(f"send_text to {receive_id}: {text[:50]}...")
        return await self.client.send_text(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            text=text,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    async def send_markdown(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        markdown: str = "",
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """
        发送Markdown富文本消息

        飞书post类型的md标签支持部分Markdown语法：
        - 粗体 **text**
        - 斜体 *text*
        - 删除线 ~~text~~
        - 代码 `code` 和 ```code block```
        - 链接 [text](url)
        - 换行 \\n
        """
        post_content = {
            "zh_cn": {
                "content": [[{"tag": "md", "text": markdown}]],
            }
        }
        logger.debug(f"send_markdown to {receive_id}: {markdown[:50]}...")
        return await self.client.send_post(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            post_content=post_content,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    async def send_card(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        card: Optional[dict] = None,
        card_content: Optional[dict] = None,
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """
        发送交互式卡片消息

        card: CardKit v2 格式卡片
        """
        card_data = card or card_content
        logger.debug(f"send_card to {receive_id}")
        return await self.client.send_interactive(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            card=card_data,
            reply_message_id=reply_message_id,
            reply_in_thread=reply_in_thread,
        )

    # ==================== 卡片构建器 ====================

    @staticmethod
    def build_text_card(text: str, wide_screen: bool = True) -> dict:
        """构建纯文本卡片"""
        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": wide_screen,
            },
            "body": {
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": text,
                        },
                    }
                ],
            },
        }

    @staticmethod
    def build_markdown_card(markdown: str, wide_screen: bool = True) -> dict:
        """构建Markdown卡片"""
        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": wide_screen,
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": markdown,
                    }
                ],
            },
        }

    @staticmethod
    def build_streaming_card(initial_text: str = "正在思考...") -> dict:
        """构建流式响应卡片（用于流式更新）"""
        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": True,
                "update_multi": True,  # 允许多端更新
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": initial_text,
                    }
                ],
            },
        }

    @staticmethod
    def build_alert_card(
        title: str,
        level: str,
        content: str,
        action_text: Optional[str] = None,
        action_value: Optional[str] = None,
    ) -> dict:
        """
        构建告警通知卡片

        Args:
            title: 告警标题
            level: 告警级别 (critical/warning/info)
            content: 告警内容（支持Markdown）
            action_text: 操作按钮文本
            action_value: 操作按钮值
        """
        # 级别颜色映射
        level_colors = {
            "critical": "#FF3B30",  # 红色
            "warning": "#FF9500",   # 橙色
            "info": "#007AFF",      # 蓝色
        }
        level_color = level_colors.get(level.lower(), "#007AFF")

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"### 🔔 {title}",
                },
            },
            {
                "tag": "hr",
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content,
                },
            },
        ]

        if action_text and action_value:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "lark_md", "content": action_text},
                            "value": action_value,
                            "type": "primary",
                        }
                    ],
                }
            )

        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": True,
            },
            "body": {
                "elements": elements,
            },
        }

    @staticmethod
    def build_agent_response_card(
        response_text: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        构建Agent响应卡片

        Args:
            response_text: Agent响应内容
            metadata: 额外元数据
        """
        # 基础卡片
        elements = [
            {
                "tag": "markdown",
                "content": response_text,
            }
        ]

        # 添加元数据（如果有）
        if metadata:
            meta_parts = []
            if agent := metadata.get("agent"):
                meta_parts.append(f"**Agent**: {agent}")
            if intent := metadata.get("intent"):
                meta_parts.append(f"**Intent**: {intent}")

            if meta_parts:
                elements.append({"tag": "hr"})
                elements.append(
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "lark_md",
                                "content": " | ".join(meta_parts),
                            }
                        ],
                    }
                )

        return {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": True,
            },
            "body": {
                "elements": elements,
            },
        }

    # ==================== 快捷发送 ====================

    async def send_agent_response(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        text: str = "",
        use_card: bool = True,
        metadata: Optional[dict] = None,
        reply_message_id: Optional[str] = None,
        reply_in_thread: bool = False,
    ) -> FeishuMessageResult:
        """发送Agent响应（智能选择格式）"""
        if use_card and self.config.capability_card:
            card = self.build_agent_response_card(text, metadata=metadata)
            return await self.send_card(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                card=card,
                reply_message_id=reply_message_id,
                reply_in_thread=reply_in_thread,
            )
        else:
            return await self.send_markdown(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                markdown=text,
                reply_message_id=reply_message_id,
                reply_in_thread=reply_in_thread,
            )

    async def send_alert_notification(
        self,
        receive_id: str,
        receive_id_type: str = "open_id",
        title: str = "",
        level: str = "info",
        content: str = "",
        reply_message_id: Optional[str] = None,
    ) -> FeishuMessageResult:
        """发送告警通知"""
        card = self.build_alert_card(
            title=title,
            level=level,
            content=content,
        )
        return await self.send_card(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            card=card,
            reply_message_id=reply_message_id,
        )

    # ==================== 流式更新 ====================

    async def update_streaming_card(
        self,
        message_id: str,
        new_content: str,
    ) -> bool:
        """
        更新流式卡片内容

        用于流式响应时逐步更新卡片内容。

        Args:
            message_id: 卡片消息ID
            new_content: 新的Markdown内容

        Returns:
            是否更新成功
        """
        card = self.build_streaming_card(new_content)
        return await self.client.update_message(
            message_id=message_id,
            msg_type="interactive",
            content=card,
        )


# ==================== 工厂函数 ====================

def create_feishu_sender(client: FeishuClient, config: FeishuChannelConfig) -> FeishuSender:
    """创建FeishuSender实例"""
    return FeishuSender(client=client, config=config)
