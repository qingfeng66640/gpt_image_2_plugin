"""GPT Image 2 文生图 + 图生图命令组件。"""

from __future__ import annotations

import asyncio
import random
import re

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_image, send_text
from src.app.plugin_system.api.stream_api import get_stream
from src.app.plugin_system.base import BaseCommand
from src.core.components.types import PermissionLevel
from src.kernel.concurrency import get_task_manager

from ..services.image_service import GptImage2Service
from ..utils.image_utils import ImageUtils

logger = get_logger("gpt_image_2_plugin.command")

DEFAULT_COMMAND_USER_ID = "command_user"

_last_used: dict[str, int] = {}


def pick(templates: list[str], key: str = "") -> str:
    """随机选择一个回复模板，避免同一个键重复上一次的模板。"""
    if not templates:
        return ""
    if len(templates) == 1:
        return templates[0]
    last_idx = _last_used.get(key, -1)
    available = [i for i in range(len(templates)) if i != last_idx]
    new_idx = random.choice(available)
    if key:
        _last_used[key] = new_idx
    return templates[new_idx]


def humanize_error(error: str) -> str:
    """将技术错误转换为简短的聊天消息。"""
    error_str = str(error).lower()
    if "statuscode 401" in error_str:
        return "API Key 认证失败 (StatusCode 401)，中转站拒绝了请求"
    if "statuscode 403" in error_str:
        return "没有权限访问上游接口 (StatusCode 403)"
    if "statuscode 429" in error_str or "rate limit" in error_str:
        return "请求太频繁了，服务器让我歇一会儿"
    if "relayerror" in error_str and "bad_response_status_code" in error_str:
        return "上游接口返回了错误状态，可能是 API Key 或模型不可用"
    if "relayerror" in error_str:
        return "中转站报错了，可能上游接口有问题"
    if "中转站报" in error_str:
        return error_str  # 已经是解析器输出的可读格式
    if "429" in error_str:
        return "请求太频繁了，服务器让我歇一会儿"
    if "401" in error_str or "unauthorized" in error_str:
        return "认证失败了，可能是 API Key 的问题"
    if "403" in error_str or "forbidden" in error_str:
        return "没有权限访问这个接口"
    if "timeout" in error_str or "timed out" in error_str:
        return "请求超时了，网络不太稳定"
    if "connection" in error_str or "connect" in error_str:
        return "网络连接出了问题"
    if "proxy" in error_str:
        return "代理配置可能有问题"
    if len(error_str) > 80:
        return "遇到了一些技术问题，稍后再试试吧"
    return str(error)


MISSING_PROMPT_HINTS = [
    "想让我画什么呀？比如：/gpt_image draw 夕阳下的海边小屋",
    "还没告诉我要生成什么图片呢",
    "给我一个提示词吧，我来生成图片",
]

UNSUPPORTED_SIZE_HINTS = [
    "{size} 这个尺寸不符合 gpt-image-2 约束，试试 1024x1024、1536x1024 或 1024x1536",
    "这个画幅不太行，宽高要是 16 的倍数，比例也要在 1:3 到 3:1 之间",
]

START_DRAWING_HINTS = [
    "收到，开始生成图片",
    "提示词收到了，我来画",
    "开始调用 GPT Image 2 生图，稍等一下",
]

DRAW_SUCCESS_HINTS = [
    "图片生成好了",
    "完成，看看效果如何",
    "生成好了，希望你喜欢",
]

GENERATE_ERROR_HINTS = [
    "生成失败了，{error}",
    "图片没生成出来，{error}",
    "出了点问题，{error}",
]

MISSING_EDIT_PROMPT_HINTS = [
    "想怎么改这张图？比如：/gpt_image edit 把背景换成星空",
    "告诉我编辑需求吧，比如换背景、改风格、调色调",
]

START_EDITING_HINTS = [
    "收到，开始编辑图片",
    "编辑指令收到了，我来处理",
    "开始调用 GPT Image 2 图生图，稍等一下",
]

EDIT_SUCCESS_HINTS = [
    "图片编辑好了",
    "完成，看看改得怎么样",
    "编辑好了，希望你喜欢",
]

NO_IMAGE_HINTS = [
    "没找到可以编辑的图片，先发一张图片给我再编辑吧",
    "要先发一张图片才行，然后再告诉我怎么改",
]

EDIT_ERROR_HINTS = [
    "编辑失败了，{error}",
    "图片没改出来，{error}",
    "编辑出问题了，{error}",
]

SIZE_ALIASES: dict[str, str] = {
    "方": "1024x1024",
    "方图": "1024x1024",
    "square": "1024x1024",
    "横": "1536x1024",
    "横图": "1536x1024",
    "横版": "1536x1024",
    "landscape": "1536x1024",
    "竖": "1024x1536",
    "竖图": "1024x1536",
    "竖版": "1024x1536",
    "portrait": "1024x1536",
    "auto": "auto",
}

PRESETS: dict[str, dict[str, str]] = {
    "人物": {
        "size": "1024x1536",
        "prefix": "高质量人物插画，清晰面部，精致服装，",
    },
    "风景": {
        "size": "1536x1024",
        "prefix": "高质量风景图，丰富环境细节，电影感光影，",
    },
    "头像": {
        "size": "1024x1024",
        "prefix": "高质量头像，清晰面部，干净背景，",
    },
}


class GptImageCommand(BaseCommand):
    """解析 `/gpt_image` 请求并在后台派发生成任务。

    图片生成可能超过事件总线处理器超时时间，因此命令在后台任务提交后立即返回。
    """

    command_name: str = "gpt_image"
    command_description: str = (
        "GPT Image 2 图片生成 - draw 文生图 / edit 图生图（编辑聊天中最近一张图片）"
    )
    permission_level: PermissionLevel = PermissionLevel.OPERATOR

    def _get_service(self) -> GptImage2Service | None:
        """返回插件服务实例。"""
        return getattr(self.plugin, "image_service", None)

    async def execute(self, message_text: str) -> tuple[bool, str]:  # type: ignore[override]
        """/gpt_image 命令入口。"""
        text = message_text.strip()
        if not text:
            await send_text(pick(MISSING_PROMPT_HINTS, "missing_prompt"), stream_id=self.stream_id)
            return False, "缺少提示词"

        parts = text.split(maxsplit=1)
        sub_cmd = parts[0].lower()
        if sub_cmd == "help":
            return await self._do_help()
        elif sub_cmd == "draw":
            rest = parts[1] if len(parts) > 1 else ""
            return await self._do_draw(rest)
        elif sub_cmd == "edit":
            rest = parts[1] if len(parts) > 1 else ""
            return await self._do_edit(rest)
        else:
            rest = text
            return await self._do_draw(rest)

    async def _do_help(self) -> tuple[bool, str]:
        """/gpt_image help — 显示命令帮助。"""
        help_text = (
            "【GPT Image 2 图片生成命令】\n\n"
            "/gpt_image draw [尺寸] <提示词>\n"
            "  文生图 — 根据文字描述生成图片。\n"
            "  尺寸可选：方/横/竖/1024x1024/1536x1024/1024x1536/auto\n"
            "  预设风格：人物/风景/头像\n"
            "  例：/gpt_image draw 横 夕阳下的海边小屋\n"
            "  例：/gpt_image draw 人物 一位穿汉服的少女在樱花树下\n\n"
            "/gpt_image edit <编辑指令>\n"
            "  图生图 — 对聊天中最近一张图片按指令编辑修改。\n"
            "  需要先发一张图片，再用此命令编辑。\n"
            "  例：/gpt_image edit 把背景换成星空\n"
            "  例：/gpt_image edit 增加暖色调滤镜，提高亮度\n\n"
            "/gpt_image help\n"
            "  显示此帮助信息。"
        )
        await send_text(help_text, stream_id=self.stream_id)
        return True, "帮助已发送"

    async def _do_edit(self, raw_text: str) -> tuple[bool, str]:
        """从聊天上下文取最近一张图片，按编辑指令编辑后发送。"""
        instruction = raw_text.strip()
        if not instruction:
            await send_text(pick(MISSING_EDIT_PROMPT_HINTS, "missing_edit"), stream_id=self.stream_id)
            return False, "缺少编辑指令"

        service = self._get_service()
        if not service:
            await send_text("图片生成服务还没准备好", stream_id=self.stream_id)
            return False, "服务未初始化"

        # 等待框架处理图片（延迟从配置读取，默认 1.5 秒）
        delay = getattr(getattr(self.plugin.config, "advanced", None), "context_delay", 1.5)
        await asyncio.sleep(delay)

        # 从 ChatStream 上下文取最近一张图片
        source_b64 = None
        stream = await get_stream(self.stream_id)
        if stream:
            messages = list(stream.context.history_messages) + list(stream.context.unread_messages)
            for msg in reversed(messages):
                media = msg.content.get("media", []) if isinstance(msg.content, dict) else []
                media = media or msg.extra.get("media", [])
                for m in media:
                    if m.get("type") == "image" and m.get("data"):
                        source_b64 = m["data"]
                        break
                if source_b64:
                    break

        if not source_b64:
            await send_text(pick(NO_IMAGE_HINTS, "no_image"), stream_id=self.stream_id)
            return False, "未找到图片"

        try:
            await send_text(pick(START_EDITING_HINTS, "start_edit"), stream_id=self.stream_id)
            task_info = get_task_manager().create_task(
                self._edit_and_send(
                    service=service,
                    source_image_b64=source_b64,
                    prompt=instruction,
                    stream_id=self.stream_id,
                    message_id=self.message_id,
                ),
                name=f"gpt_image_2_edit_{self.message_id or 'message'}",
            )
            logger.info(f"后台编辑任务已提交: task_id={task_info.task_id}, stream_id={self.stream_id}")
            return True, "编辑任务已提交"
        except Exception as e:
            logger.error(f"执行 /gpt_image edit 时出错: {e}", exc_info=True)
            await send_text(
                pick(EDIT_ERROR_HINTS, "edit_error").format(error=humanize_error(str(e))),
                stream_id=self.stream_id,
            )
            return False, "命令执行异常"

    async def _edit_and_send(
        self,
        *,
        service: GptImage2Service,
        source_image_b64: str,
        prompt: str,
        stream_id: str,
        message_id: str | None,
    ) -> None:
        """在命令事件超时外编辑并发送图片。"""
        try:
            logger.info(f"后台编辑任务开始: stream_id={stream_id}, prompt={prompt[:80]!r}")
            success, message, image_path = await service.edit_image(
                source_image_base64=source_image_b64,
                prompt=prompt,
                user_id=DEFAULT_COMMAND_USER_ID,
            )
            logger.info(f"后台编辑任务完成: success={success}, message={message}, image_path={image_path}")

            if success and image_path:
                ok, msg, image_base64 = ImageUtils.read_image_as_base64(image_path)
                if ok and image_base64:
                    sent = await send_image(image_base64, stream_id=stream_id, reply_to=message_id or None)
                    logger.info(f"后台编辑图片发送结果: sent={sent}")
                    if sent:
                        await send_text(pick(EDIT_SUCCESS_HINTS, "edit_success"), stream_id=stream_id)
                    else:
                        await send_text("图片编辑好了，但是发送失败了，文件已保留", stream_id=stream_id)
                    ImageUtils.cleanup_temp_file(image_path, keep_file=True)
                    return
                logger.error(f"后台编辑读取图片失败: {msg}")
                await send_text(humanize_error(msg), stream_id=stream_id)
                return

            await send_text(
                pick(EDIT_ERROR_HINTS, "edit_error").format(error=humanize_error(message)),
                stream_id=stream_id,
            )
        except Exception as e:
            logger.error(f"后台执行 /gpt_image edit 任务时出错: {e}", exc_info=True)
            await send_text(
                pick(EDIT_ERROR_HINTS, "edit_error").format(error=humanize_error(str(e))),
                stream_id=stream_id,
            )

    async def _do_draw(self, raw_text: str) -> tuple[bool, str]:
        """从命令文本生成图片。"""
        args = raw_text.split() if raw_text.strip() else []
        if not args:
            await send_text(pick(MISSING_PROMPT_HINTS, "missing_prompt"), stream_id=self.stream_id)
            return False, "缺少提示词"

        service = self._get_service()
        if not service:
            await send_text("图片生成服务还没准备好", stream_id=self.stream_id)
            return False, "服务未初始化"

        size = service.default_size
        prompt_start_idx = 0
        prompt_prefix = ""
        first_arg = args[0].lower().replace("×", "x").replace("*", "x")

        if first_arg in PRESETS:
            preset = PRESETS[first_arg]
            size = preset["size"]
            prompt_prefix = preset["prefix"]
            prompt_start_idx = 1
        elif first_arg in SIZE_ALIASES:
            size = SIZE_ALIASES[first_arg]
            prompt_start_idx = 1
        elif "x" in first_arg and re.fullmatch(r"\d+x\d+", first_arg):
            if service.is_supported_size(first_arg):
                size = first_arg
                prompt_start_idx = 1
            else:
                await send_text(
                    pick(UNSUPPORTED_SIZE_HINTS, "unsupported_size").format(size=first_arg),
                    stream_id=self.stream_id,
                )
                return False, "画幅不支持"

        prompt = " ".join(args[prompt_start_idx:]).strip()
        if not prompt:
            await send_text("画幅选好了，但是还没说要画什么", stream_id=self.stream_id)
            return False, "缺少提示词"

        if prompt_prefix:
            prompt = prompt_prefix + prompt

        try:
            await send_text(pick(START_DRAWING_HINTS, "start_draw"), stream_id=self.stream_id)
            task_info = get_task_manager().create_task(
                self._generate_and_send(
                    service=service,
                    prompt=prompt,
                    size=size,
                    stream_id=self.stream_id,
                    message_id=self.message_id,
                ),
                name=f"gpt_image_2_command_{self.message_id or 'message'}",
            )
            logger.info(f"后台生图任务已提交: task_id={task_info.task_id}, stream_id={self.stream_id}")
            return True, "生图任务已提交"
        except Exception as e:
            logger.error(f"执行 /gpt_image 命令时出错: {e}", exc_info=True)
            await send_text(
                pick(GENERATE_ERROR_HINTS, "gen_error").format(error=humanize_error(str(e))),
                stream_id=self.stream_id,
            )
            return False, "命令执行异常"

    async def _generate_and_send(
        self,
        *,
        service: GptImage2Service,
        prompt: str,
        size: str,
        stream_id: str,
        message_id: str | None,
    ) -> None:
        """在命令事件超时外生成并发送图片。"""
        try:
            logger.info(f"后台生图任务开始: stream_id={stream_id}, size={size}, prompt={prompt[:80]!r}")
            success, message, image_path = await service.generate_image(
                prompt=prompt,
                user_id=DEFAULT_COMMAND_USER_ID,
                size=size,
                from_command=True,
            )
            logger.info(f"后台生图任务完成: success={success}, message={message}, image_path={image_path}")

            if success and image_path:
                ok, msg, image_base64 = ImageUtils.read_image_as_base64(image_path)
                if ok and image_base64:
                    sent = await send_image(image_base64, stream_id=stream_id, reply_to=message_id or None)
                    logger.info(f"后台生图图片发送结果: sent={sent}, image_path={image_path}")
                    if sent:
                        await send_text(pick(DRAW_SUCCESS_HINTS, "draw_success"), stream_id=stream_id)
                    else:
                        await send_text("图片生成好了，但是发送失败了，文件已保留", stream_id=stream_id)
                    ImageUtils.cleanup_temp_file(image_path, keep_file=True)
                    return
                logger.error(f"后台生图读取图片失败: {msg}, image_path={image_path}")
                await send_text(humanize_error(msg), stream_id=stream_id)
                return

            await send_text(
                pick(GENERATE_ERROR_HINTS, "gen_error").format(error=humanize_error(message)),
                stream_id=stream_id,
            )
        except Exception as e:
            logger.error(f"后台执行 /gpt_image 生图任务时出错: {e}", exc_info=True)
            await send_text(
                pick(GENERATE_ERROR_HINTS, "gen_error").format(error=humanize_error(str(e))),
                stream_id=stream_id,
            )
