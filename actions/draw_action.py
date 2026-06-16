"""GPT Image 2 画图 Action。"""

from __future__ import annotations

from typing import Annotated

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.types import ChatType

from .base_image_action import BaseGptImageAction

logger = get_logger("gpt_image_2_plugin.draw_action")


class GptImageDrawAction(BaseGptImageAction):
    """通过 GPT Image 2 为用户生成图片。"""

    action_name: str = "gpt_image_draw"
    action_description: str = (
        "为用户生成一张图片。当用户想要画图、生图、生成壁纸、头像、插画、海报、表情包等视觉内容时使用。\n\n"
        "【提示词要求】\n"
        "- content_description 可以使用中文或英文，但必须描述清楚主体、场景、构图、镜头、光线、风格和细节。\n"
        "- 不要使用 NovelAI 专用参数、负面提示词、采样器、steps、seed、Vibe 等旧接口概念。\n"
        "- 尺寸建议：方图 1024x1024，横图 1536x1024，竖图 1024x1536。\n"
        "- gpt-image-2 支持自定义 WIDTHxHEIGHT，但宽高必须是 16 的倍数，宽高比在 1:3 到 3:1 之间。"
    )
    primary_action: bool = False
    chat_type: ChatType = ChatType.ALL
    associated_types: list[str] = ["image"]

    async def execute(
        self,
        content_description: Annotated[
            str,
            "图片生成提示词。描述主体、场景、构图、光线、风格和重要细节。",
        ],
        size: Annotated[
            str,
            "图片尺寸。可用 auto、1024x1024、1536x1024、1024x1536，或符合 gpt-image-2 约束的 WIDTHxHEIGHT。",
        ] = "1024x1024",
    ) -> tuple[bool, str]:
        """执行图片生成。"""
        if not content_description.strip():
            return False, "画什么呢？请告诉我你想要的图片内容"

        logger.info(f"GPT Image 2 画图 - size={size}, prompt={content_description}")
        return await self.generate_and_send_image(
            prompt=content_description.strip(),
            size=size,
            success_message="[内部：已发送画作]",
            error_prefix="画画失败了",
        )
