"""GPT Image 2 图片操作的共享 Action 辅助类。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_image
from src.core.components.base.action import BaseAction

from ..utils.image_utils import ImageUtils

if TYPE_CHECKING:
    from ..services.image_service import GptImage2Service

logger = get_logger("gpt_image_2_plugin.base_image_action")


class BaseGptImageAction(BaseAction):
    """GPT Image 2 Action 基类。"""

    def get_service(self) -> Optional["GptImage2Service"]:
        """返回插件图片服务实例。"""
        service = getattr(self.plugin, "image_service", None)
        if not service:
            logger.error("无法获取 GPT Image 2 图片生成服务")
        return service

    async def generate_and_send_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        *,
        success_message: str = "[内部：已发送图片]",
        error_prefix: str = "生成失败",
    ) -> tuple[bool, str]:
        """生成图片并发送到当前聊天流。"""
        service = self.get_service()
        if not service:
            return False, "图片生成服务不可用"

        user_id = self.chat_stream.context.triggering_user_id or ""
        final_size = self._parse_size(size, default=service.default_size)

        try:
            success, msg, image_path = await service.generate_image(
                prompt=prompt,
                user_id=str(user_id),
                size=final_size,
            )
            if success and image_path:
                return await self.read_and_send_image(image_path, success_message=success_message)
            logger.error(f"图片生成失败: {msg}")
            return False, f"{error_prefix}: {msg}"
        except Exception as e:
            logger.error(f"图片生成异常: {e}", exc_info=True)
            return False, f"{error_prefix}: {e}"

    async def read_and_send_image(
        self,
        image_path: str,
        *,
        success_message: str = "[内部：已发送图片]",
    ) -> tuple[bool, str]:
        """读取已保存的图片并发送。"""
        success, msg, image_base64 = ImageUtils.read_image_as_base64(image_path)
        if not success or not image_base64:
            return False, msg

        try:
            await send_image(image_base64, stream_id=self.chat_stream.stream_id)
            ImageUtils.cleanup_temp_file(image_path, keep_file=True)
            return True, success_message
        except Exception as e:
            logger.error(f"发送图片失败: {e}", exc_info=True)
            return False, f"发送图片失败: {e}"

    def _parse_size(self, size: str, default: str = "1024x1024") -> str:
        """解析并验证 GPT Image 2 尺寸字符串。"""
        service = self.get_service()
        normalized = (size or "").strip().lower().replace("×", "x").replace("*", "x")
        if normalized == "auto":
            return "auto"
        if service and service.is_supported_size(normalized):
            return normalized

        fallback = (default or "1024x1024").strip().lower()
        if fallback == "auto" or (service and service.is_supported_size(fallback)):
            logger.warning(f"尺寸 {size!r} 无效，使用默认值 {fallback}")
            return fallback
        return "1024x1024"
