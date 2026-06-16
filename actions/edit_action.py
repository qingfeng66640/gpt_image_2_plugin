"""GPT Image 2 图生图编辑 Action。"""

from __future__ import annotations

from typing import Annotated

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.types import ChatType

from .base_image_action import BaseGptImageAction

logger = get_logger("gpt_image_2_plugin.edit_action")


class GptImageEditAction(BaseGptImageAction):
    """根据用户指令编辑聊天上下文中的最近一张图片。"""

    action_name: str = "gpt_image_edit"
    action_description: str = (
        "编辑/修改聊天中最近一张图片。当用户发送一张图片并附带编辑需求时使用。\n\n"
        "【使用场景】\n"
        "- 用户发了图片说\"把背景换成星空\"、\"给我换个发型\"、\"把色调调暖\"等\n"
        "- 用户想对刚发的图片做局部修改、风格转换、滤镜效果等\n\n"
        "【参数要求】\n"
        "- edit_instruction 用中文或英文描述你想要的编辑效果，要具体清晰\n"
        "- 尺寸建议：方图 1024x1024，横图 1536x1024，竖图 1024x1536\n"
        "- gpt-image-2 支持自定义 WIDTHxHEIGHT，但宽高必须是 16 的倍数，宽高比在 1:3 到 3:1 之间"
    )
    primary_action: bool = False
    chat_type: ChatType = ChatType.ALL
    associated_types: list[str] = ["image"]

    async def execute(
        self,
        edit_instruction: Annotated[
            str,
            "图片编辑指令。描述要对图片做什么修改，如\"把背景换成星空\"、\"增加柔和的暖色调滤镜\"、\"把人物服装改成古装\"",
        ],
        size: Annotated[
            str,
            "编辑后输出图片的尺寸。可用 auto、1024x1024、1536x1024、1024x1536，或符合 gpt-image-2 约束的 WIDTHxHEIGHT。",
        ] = "1024x1024",
    ) -> tuple[bool, str]:
        """执行图生图编辑。"""
        if not edit_instruction.strip():
            return False, "你想怎么改这张图？告诉我具体的编辑需求"

        source_b64 = await self._get_last_image_from_context()
        if not source_b64:
            return False, "没找到可以编辑的图片。先发一张图片，再告诉我怎么改"

        logger.info(f"GPT Image 2 图生图 - size={size}, instruction={edit_instruction[:80]}")
        return await self.generate_and_send_edit(
            source_image_b64=source_b64,
            prompt=edit_instruction.strip(),
            size=size,
        )
