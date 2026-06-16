"""GPT Image 2 图片操作的共享 Action 辅助类。"""

from __future__ import annotations

import asyncio
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

    async def generate_and_send_edit(
        self,
        source_image_b64: str,
        prompt: str,
        size: str = "1024x1024",
    ) -> tuple[bool, str]:
        """图生图：用来源图片 + 编辑指令生成并发送编辑后的图片。"""
        service = self.get_service()
        if not service:
            return False, "图片生成服务不可用"

        user_id = self.chat_stream.context.triggering_user_id or ""
        final_size = self._parse_size(size, default=service.default_size)

        try:
            success, msg, image_path = await service.edit_image(
                source_image_base64=source_image_b64,
                prompt=prompt,
                user_id=str(user_id),
                size=final_size,
            )
            if success and image_path:
                return await self.read_and_send_image(
                    image_path, success_message="[内部：已发送编辑后的图片]"
                )
            logger.error(f"图片编辑失败: {msg}")
            return False, f"图片编辑失败: {msg}"
        except Exception as e:
            logger.error(f"图片编辑异常: {e}", exc_info=True)
            return False, f"图片编辑失败: {e}"

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
        normalized = (size or "").strip().lower().replace("\u00d7", "x").replace("*", "x")
        if normalized == "auto":
            return "auto"
        if service and service.is_supported_size(normalized):
            return normalized

        fallback = (default or "1024x1024").strip().lower()
        if fallback == "auto" or (service and service.is_supported_size(fallback)):
            logger.warning(f"尺寸 {size!r} 无效，使用默认值 {fallback}")
            return fallback
        return "1024x1024"

    async def _get_last_image_from_context(self, delay: float | None = None) -> str | None:
        """等待延迟后从聊天上下文获取最近一张用户发送的图片 base64。

        延迟是为了给框架足够时间完成图片下载和消息处理，
        避免用户图片尚未到达就被 Action 取上下文。
        延迟默认从插件配置 advanced.context_delay 读取。
        """
        if delay is None:
            cfg = getattr(self.plugin, "config", None)
            delay = getattr(getattr(cfg, "advanced", None), "context_delay", 1.5)
        await asyncio.sleep(delay)
        messages = (
            list(self.chat_stream.context.history_messages)
            + list(self.chat_stream.context.unread_messages)
        )
        for msg in reversed(messages):
            media = msg.content.get("media", []) if isinstance(msg.content, dict) else []
            media = media or msg.extra.get("media", [])
            for m in media:
                if m.get("type") == "image" and m.get("data"):
                    logger.info(f"从上下文找到图片: message_id={msg.message_id}")
                    return m["data"]  # 已是 "base64|xxx" 格式
        return None
