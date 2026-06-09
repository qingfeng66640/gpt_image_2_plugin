"""GPT Image 2 /images/generations API 服务。"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import aiohttp

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.base.service import BaseService
from src.kernel.concurrency import get_task_manager

if TYPE_CHECKING:
    from src.core.components.base.plugin import BasePlugin

    from ..config import GptImage2Config

logger = get_logger("gpt_image_2_plugin.service")

ImageResult = tuple[bool, str, Optional[str]]
ImageTaskFactory = Callable[[], Awaitable[ImageResult]]

DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
ROTATE_KEY_STATUS_CODES = {401, 403, 429}
AUTH_STATUS_CODES = {401, 403}
SUPPORTED_QUALITIES = {"auto", "low", "medium", "high"}
SUPPORTED_OUTPUT_FORMATS = {"png", "jpeg", "webp"}
SUPPORTED_BACKGROUNDS = {"auto", "transparent", "opaque"}
SUPPORTED_MODERATIONS = {"auto", "low"}
REDACTED_RESPONSE_KEYS = {"b64_json", "api_key", "authorization", "token"}


class GptImage2Service(BaseService):
    """OpenAI 兼容图片生成服务，支持本地持久化。"""

    service_name: str = "gpt_image_2_generator"
    service_description: str = "GPT Image 2 图片生成服务"
    version: str = "1.0.2"

    _task_queue: asyncio.Queue[tuple[ImageTaskFactory, asyncio.Future[ImageResult]]] = asyncio.Queue()
    _queue_worker_started: bool = False
    _queue_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, plugin: "BasePlugin") -> None:
        """初始化服务。"""
        super().__init__(plugin)
        self.plugin_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.current_key_index = 0
        self.last_request_time = 0.0

        self.api_keys: list[str] = []
        self.request_url = ""
        self.proxy = ""
        self.cooldown = 5
        self.timeout = 120
        self.max_retries = 2
        self.retry_delay = 10

        self.model = DEFAULT_MODEL
        self.default_size = DEFAULT_SIZE
        self.quality = "auto"
        self.output_format = "png"
        self.background = "auto"
        self.moderation = "auto"
        self.output_compression = 100
        self.n = 1
        self.character_prompt = ""

        self.temp_dir = Path()
        self.command_images_dir = Path()

    async def initialize(self) -> None:
        """加载配置、创建目录并启动队列处理器。"""
        cfg: GptImage2Config = self.plugin.config  # type: ignore[assignment]

        self.api_keys = list(cfg.api.api_keys)
        self.request_url = cfg.api.request_url.strip()
        self.proxy = cfg.api.proxy.strip()
        self.cooldown = cfg.api.cooldown
        self.timeout = cfg.api.timeout
        self.max_retries = cfg.api.max_retries
        self.retry_delay = cfg.api.retry_delay

        self.model = cfg.generation.model.strip() or DEFAULT_MODEL
        self.default_size = self._normalize_config_size(cfg.generation.default_size)
        self.quality = self._pick_allowed(cfg.generation.quality, SUPPORTED_QUALITIES, "auto")
        self.output_format = self._pick_allowed(cfg.generation.output_format, SUPPORTED_OUTPUT_FORMATS, "png")
        self.background = self._pick_allowed(cfg.generation.background, SUPPORTED_BACKGROUNDS, "auto")
        self.moderation = self._pick_allowed(cfg.generation.moderation, SUPPORTED_MODERATIONS, "auto")
        self.output_compression = max(0, min(100, cfg.generation.output_compression))
        self.n = max(1, min(10, cfg.generation.n))
        self.character_prompt = cfg.generation.character_prompt

        self.temp_dir = self.plugin_dir / cfg.advanced.temp_dir
        self.command_images_dir = self.plugin_dir / cfg.advanced.command_images_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.command_images_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_keys:
            logger.warning("未配置 API Key，GPT Image 2 生图功能将不可用")
        if not self.request_url:
            logger.warning("未配置 request_url，GPT Image 2 生图功能将不可用")

        await self._start_queue_worker()
        logger.info("GPT Image 2 图片生成服务初始化完成")

    async def cleanup(self) -> None:
        """清理服务资源。"""
        return None

    async def _start_queue_worker(self) -> None:
        """启动共享队列处理器（仅一次）。"""
        async with GptImage2Service._queue_lock:
            if not GptImage2Service._queue_worker_started:
                GptImage2Service._queue_worker_started = True
                get_task_manager().create_task(
                    self._queue_worker(),
                    name="gpt_image_2_queue_worker",
                    daemon=True,
                )
                logger.info("GPT Image 2 全局生图任务队列已启动")

    @classmethod
    async def _queue_worker(cls) -> None:
        """串行处理图片任务。"""
        while True:
            task_func = None
            result_future: asyncio.Future[ImageResult] | None = None
            try:
                task_func, result_future = await cls._task_queue.get()
                result = await task_func()
                if not result_future.done():
                    result_future.set_result(result)
            except Exception as e:
                logger.error(f"队列处理器捕获异常: {e}", exc_info=True)
                if result_future is not None and not result_future.done():
                    result_future.set_exception(e)
            finally:
                if task_func is not None:
                    cls._task_queue.task_done()
                await asyncio.sleep(0.01)

    async def _enqueue_task(self, task_func: ImageTaskFactory) -> ImageResult:
        """将任务入队并等待结果。"""
        result_future: asyncio.Future[ImageResult] = asyncio.get_event_loop().create_future()
        await GptImage2Service._task_queue.put((task_func, result_future))
        logger.info(f"生图任务已入队，当前队列长度: {GptImage2Service._task_queue.qsize()}")
        try:
            return await result_future
        except asyncio.CancelledError:
            logger.warning("生图任务等待者已取消，后台队列任务会继续执行到结束")
            raise

    def _get_current_api_key(self) -> Optional[str]:
        """返回当前 API 密钥。"""
        if not self.api_keys:
            return None
        return self.api_keys[self.current_key_index]

    def _rotate_api_key(self) -> None:
        """如果存在多个 API 密钥，切换到下一个。"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"切换到 API Key {self.current_key_index + 1}/{len(self.api_keys)}")

    def check_cooldown(self) -> tuple[bool, int]:
        """检查当前是否可以发送请求。"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.cooldown:
            return False, int(self.cooldown - elapsed)
        return True, 0

    async def generate_image(
        self,
        prompt: str,
        user_id: str,
        size: str | None = None,
        *,
        from_command: bool = False,
    ) -> ImageResult:
        """通过队列生成一张图片。"""

        async def task() -> ImageResult:
            return await self._generate_image_internal(
                prompt=prompt,
                user_id=user_id,
                size=size,
                from_command=from_command,
            )

        return await self._enqueue_task(task)

    async def _generate_image_internal(
        self,
        prompt: str,
        user_id: str,
        size: str | None = None,
        *,
        from_command: bool = False,
    ) -> ImageResult:
        """立即生成一张图片。"""
        if not prompt.strip():
            return False, "提示词不能为空", None

        is_ready, wait_time = self.check_cooldown()
        if not is_ready:
            logger.info(f"请求冷却中，等待 {wait_time} 秒")
            await asyncio.sleep(wait_time)

        api_key = self._get_current_api_key()
        if not api_key:
            return False, "API Key 没配置，联系管理员看看", None
        if not self.request_url:
            return False, "请求 URL 没配置，联系管理员看看", None

        self.last_request_time = time.time()
        payload = self.construct_payload(prompt=prompt, user_id=user_id, size=size)
        logger.info(f"GPT Image 2 请求 payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

        return await self._submit_generation(
            payload=payload,
            api_key=api_key,
            from_command=from_command,
        )

    def construct_payload(self, prompt: str, user_id: str, size: str | None = None) -> dict[str, Any]:
        """构建 GPT 图片模型的 /images/generations 请求体。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": self.n,
            "size": self._normalize_config_size(size or self.default_size),
            "quality": self.quality,
            "output_format": self.output_format,
            "background": self.background,
            "moderation": self.moderation,
        }

        if self.output_format in {"jpeg", "webp"}:
            payload["output_compression"] = self.output_compression

        if user_id:
            payload["user"] = str(user_id)

        return payload

    async def _submit_generation(
        self,
        payload: dict[str, Any],
        api_key: str,
        *,
        from_command: bool = False,
    ) -> ImageResult:
        """提交生成请求并保存返回的 base64 图片。"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        connector = aiohttp.TCPConnector() if self.proxy else None
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for attempt in range(self.max_retries + 1):
                try:
                    request_kwargs: dict[str, Any] = {"json": payload, "headers": headers}
                    if self.proxy:
                        request_kwargs["proxy"] = self.proxy

                    logger.info(
                        f"开始请求 GPT Image 2: attempt={attempt + 1}/{self.max_retries + 1}, "
                        f"url={self.request_url}, timeout={self.timeout}s"
                    )
                    async with session.post(self.request_url, **request_kwargs) as resp:
                        body_text = await resp.text()
                        logger.info(f"GPT Image 2 接口响应状态: {resp.status}")
                        if resp.status in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                            logger.warning(
                                f"请求失败 ({resp.status})，响应预览: {self._response_preview(body_text)[:500]}，"
                                f"{self.retry_delay} 秒后重试 ({attempt + 1}/{self.max_retries})"
                            )
                            await asyncio.sleep(self.retry_delay)
                            continue

                        if resp.status not in (200, 201):
                            if resp.status in ROTATE_KEY_STATUS_CODES:
                                self._rotate_api_key()
                            logger.error(f"请求失败 ({resp.status})，响应: {self._response_preview(body_text)}")
                            return False, self._format_error(resp.status, body_text), None

                        return await self._handle_generation_response(
                            body_text,
                            from_command=from_command,
                        )
                except asyncio.TimeoutError:
                    if attempt < self.max_retries:
                        logger.warning(
                            f"请求超时，{self.retry_delay} 秒后重试 "
                            f"({attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(self.retry_delay)
                        continue
                    logger.error(f"请求超时，已达到最大重试次数: timeout={self.timeout}s")
                    return False, "请求超时了，网络不太好", None
                except Exception as e:
                    logger.error(f"请求异常: {e}", exc_info=True)
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    return False, f"网络出问题了：{e}", None

        return False, "未知错误", None

    async def _handle_generation_response(
        self,
        body_text: str,
        *,
        from_command: bool = False,
    ) -> ImageResult:
        """解析 JSON 响应并保存返回的第一张图片。"""
        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            logger.error(f"接口返回非 JSON 内容: {body_text[:500]}")
            return False, "接口返回格式不是 JSON", None

        if not isinstance(data, dict):
            logger.error(f"接口返回 JSON 不是对象: {self._response_preview(data)}")
            return False, "接口返回格式不符合图片生成接口", None

        error_message = self._extract_error_message(data)
        if error_message:
            if self._is_auth_error(data, error_message):
                self._rotate_api_key()
            logger.error(f"接口返回错误响应: {self._response_preview(data)}")
            return False, f"接口返回错误: {error_message}", None

        images = data.get("data")
        if not isinstance(images, list) or not images:
            logger.error(f"接口返回缺少 data 图片列表: {self._response_preview(data)}")
            return False, "接口返回中没有 data 图片列表，详见日志中的响应预览", None

        first = images[0]
        if not isinstance(first, dict):
            return False, "接口返回的图片数据格式不正确", None

        b64_json = first.get("b64_json")
        if not isinstance(b64_json, str) or not b64_json.strip():
            return False, "接口没有返回 b64_json；GPT 图片模型应返回 base64 图片", None

        if len(images) > 1:
            logger.info(f"接口返回 {len(images)} 张图片，当前插件只发送第一张")

        return await self._save_image_from_base64(b64_json, from_command=from_command)

    async def _save_image_from_base64(
        self,
        b64_json: str,
        *,
        from_command: bool = False,
    ) -> ImageResult:
        """解码 base64 图片内容并保存到本地。"""
        try:
            if "," in b64_json and b64_json.lstrip().startswith("data:"):
                b64_json = b64_json.split(",", 1)[1]

            image_data = base64.b64decode(b64_json, validate=True)
        except (binascii.Error, ValueError) as e:
            return False, f"图片 base64 解码失败: {e}", None

        if not image_data:
            return False, "图片数据为空", None

        save_dir = self.command_images_dir if from_command else self.temp_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        extension = self._extension_for_bytes(image_data) or self._extension_for_format(self.output_format)
        filepath = save_dir / f"{uuid.uuid4()}.{extension}"

        try:
            with open(filepath, "wb") as f:
                f.write(image_data)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"保存图片失败: {e}", exc_info=True)
            return False, f"保存图片失败: {e}", None

        logger.info(f"图片已保存: {filepath}")
        return True, "图片生成成功", str(filepath)

    def _format_error(self, status: int, body_text: str) -> str:
        """将 API 错误 JSON 转换为简短消息。"""
        try:
            data = json.loads(body_text)
            if isinstance(data, dict):
                message = self._extract_error_message(data)
                if message:
                    return f"请求失败了 ({status}): {message}"
        except json.JSONDecodeError:
            pass
        preview = body_text[:500]
        logger.error(f"请求失败 ({status})，非 JSON 响应: {preview}")
        return f"请求失败了 ({status}): {preview}"

    def _extract_error_message(self, data: dict[str, Any]) -> str | None:
        """从响应对象中提取常见的 OpenAI 兼容和中转站错误字段。"""
        # OpenAI 风格错误对象（同时匹配 "error" 和 "Err"）
        for err_key in ("error", "Err"):
            error = data.get(err_key)
            if isinstance(error, dict):
                message = self._first_string(
                    error,
                    ("message", "msg", "detail", "code", "type"),
                )
                if message:
                    return message
            if isinstance(error, str) and error.strip():
                return error.strip()

        # 中转站风格错误 (RelayError / StatusCode)
        relay_error = data.get("RelayError")
        if isinstance(relay_error, dict):
            relay_type = self._first_string(relay_error, ("type", "message", "code"))
            status_code = data.get("StatusCode")
            if isinstance(status_code, int) and status_code >= 400:
                prefix = f"中转站报 StatusCode {status_code}"
                if relay_type:
                    return f"{prefix} (RelayError: {relay_type})"
                return prefix
            if relay_type:
                return f"中转站报错: {relay_type}"

        # 顶级 StatusCode 作为错误指示（响应体中的非 2xx）
        status_code = data.get("StatusCode")
        if isinstance(status_code, int) and status_code >= 400:
            return f"中转站报 StatusCode {status_code}"

        # 通用消息字段
        message = self._first_string(
            data,
            ("message", "msg", "detail", "error_message", "errmsg"),
        )
        if message:
            code = data.get("code") or data.get("status")
            if code is not None:
                return f"{code}: {message}"
            return message
        return None

    def _is_auth_error(self, data: dict[str, Any], error_message: str) -> bool:
        """检查中转站/API 错误是否表示认证问题。"""
        status_code = data.get("StatusCode")
        if isinstance(status_code, int) and status_code in AUTH_STATUS_CODES:
            return True

        body_code = data.get("code")
        if isinstance(body_code, (int, str)):
            try:
                if int(body_code) in AUTH_STATUS_CODES:
                    return True
            except (ValueError, TypeError):
                pass

        error_lower = error_message.lower()
        auth_keywords = ("401", "403", "unauthorized", "forbidden", "authentication", "invalid api key")
        return any(kw in error_lower for kw in auth_keywords)

    @staticmethod
    def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        """返回给定键名中第一个非空字符串值。"""
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _response_preview(self, data: Any) -> str:
        """返回用于诊断的简短、已脱敏的响应预览。"""
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                return data[:1000]
            return self._response_preview(parsed)
        redacted = self._redact_response(data)
        try:
            return json.dumps(redacted, ensure_ascii=False)[:1000]
        except TypeError:
            return repr(redacted)[:1000]

    def _redact_response(self, value: Any) -> Any:
        """在响应预览中脱敏大型图片负载和敏感字段。"""
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                key_lower = str(key).lower()
                if key_lower in REDACTED_RESPONSE_KEYS:
                    result[key] = "<redacted>"
                else:
                    result[key] = self._redact_response(item)
            return result
        if isinstance(value, list):
            return [self._redact_response(item) for item in value[:3]]
        if isinstance(value, str) and len(value) > 300:
            return value[:300] + "...<truncated>"
        return value

    def _normalize_config_size(self, size: str) -> str:
        """返回有效的 GPT Image 2 尺寸或安全默认值。"""
        normalized = (size or "").strip().lower().replace("×", "x").replace("*", "x")
        if normalized == "auto":
            return "auto"
        if self.is_supported_size(normalized):
            return normalized
        logger.warning(f"尺寸 {size!r} 不符合 gpt-image-2 约束，回退到 {DEFAULT_SIZE}")
        return DEFAULT_SIZE

    @staticmethod
    def is_supported_size(size: str) -> bool:
        """根据 API 文档验证 GPT Image 2 尺寸约束。"""
        try:
            width_text, height_text = size.lower().split("x", 1)
            width = int(width_text.strip())
            height = int(height_text.strip())
        except (ValueError, AttributeError):
            return False

        if width <= 0 or height <= 0:
            return False
        if width % 16 != 0 or height % 16 != 0:
            return False
        if width > 3840 or height > 2160:
            return False
        ratio = width / height
        return (1 / 3) <= ratio <= 3

    @staticmethod
    def _pick_allowed(value: str, allowed: set[str], default: str) -> str:
        """选择允许的小写值，否则返回默认值。"""
        normalized = (value or "").strip().lower()
        if normalized in allowed:
            return normalized
        logger.warning(f"配置值 {value!r} 不支持，回退到 {default}")
        return default

    @staticmethod
    def _extension_for_format(output_format: str) -> str:
        """将 API 输出格式映射为文件扩展名。"""
        return "jpg" if output_format == "jpeg" else output_format

    @staticmethod
    def _extension_for_bytes(image_data: bytes) -> str | None:
        """根据魔数推断文件扩展名。"""
        if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if image_data.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if image_data.startswith(b"RIFF") and image_data[8:12] == b"WEBP":
            return "webp"
        return None
