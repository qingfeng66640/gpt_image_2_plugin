"""GPT Image 2 自拍 Action。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.types import ChatType

from .base_image_action import BaseGptImageAction

if TYPE_CHECKING:
    from ..services.image_service import GptImage2Service

logger = get_logger("gpt_image_2_plugin.selfie_action")


class GptImageSelfieAction(BaseGptImageAction):
    """生成 Bot 配置角色的图片。"""

    action_name: str = "gpt_image_selfie"
    action_description: str = (
        "生成【你自己】的照片或形象图发给用户。仅当用户想看你的照片、自拍、样子、外观、头像时使用。\n\n"
        "【提示词要求】\n"
        "- 配置文件中已有你的角色特征，参数中不要重复基础外观，只补充场景、姿势、情绪、风格。\n"
        "- scene_description、pose_or_action、mood 可以使用中文或英文。\n"
        "- 不要使用负面提示词、Vibe、采样器、steps、seed 等旧接口概念。"
    )
    primary_action: bool = False
    chat_type: ChatType = ChatType.ALL

    async def execute(
        self,
        scene_description: Annotated[str, "场景、环境、时间、光线、服装或风格描述。"],
        pose_or_action: Annotated[str, "姿势、动作、表情、视线方向等描述。"],
        size: Annotated[str, "图片尺寸，自拍通常用 1024x1536 或 1024x1024。"] = "1024x1536",
        mood: Annotated[str, "情绪氛围描述，可留空。"] = "",
    ) -> tuple[bool, str]:
        """执行自拍图片生成。"""
        service = self.get_service()
        if not service:
            return False, "图片生成服务不可用"

        prompt = self._build_selfie_prompt(service, scene_description, pose_or_action, mood)
        logger.info(f"GPT Image 2 自拍 - size={size}, prompt={prompt}")
        return await self.generate_and_send_image(
            prompt=prompt,
            size=size,
            success_message="[内部：已发送你的照片]",
            error_prefix="拍照失败",
        )

    def _build_selfie_prompt(
        self,
        service: "GptImage2Service",
        scene_description: str,
        pose_or_action: str,
        mood: str,
    ) -> str:
        """根据配置的角色特征构建自拍提示词。"""
        character = service.character_prompt.strip() or "a friendly digital assistant"
        prompt_parts = [
            f"Create a high-quality image of this character: {character}.",
            f"Scene and style: {scene_description.strip()}.",
            f"Pose, action, and expression: {pose_or_action.strip()}.",
        ]
        if mood.strip():
            prompt_parts.append(f"Mood: {mood.strip()}.")
        prompt_parts.append("Use coherent anatomy, polished lighting, and a clean composition.")
        return " ".join(prompt_parts)
