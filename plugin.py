"""GPT Image 2 图片生成插件。"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.core.components.base import BasePlugin
from src.core.components.loader import register_plugin
from src.core.components.types import PermissionLevel

from .actions.draw_action import GptImageDrawAction
from .actions.selfie_action import GptImageSelfieAction
from .commands.image_command import GptImageCommand
from .config import GptImage2Config
from .services.image_service import GptImage2Service

logger = get_logger("gpt_image_2_plugin")

_PERMISSION_MAP: dict[str, PermissionLevel] = {
    "user": PermissionLevel.USER,
    "operator": PermissionLevel.OPERATOR,
    "owner": PermissionLevel.OWNER,
}


@register_plugin
class GptImage2Plugin(BasePlugin):
    """OpenAI GPT Image 2 图片生成插件。"""

    plugin_name: str = "gpt_image_2_plugin"
    plugin_description: str = "基于 GPT Image 2 /images/generations 接口的图片生成插件"
    plugin_version: str = "1.0.0"
    config_file_name: str = "config.toml"

    configs = [GptImage2Config]

    def __init__(self, config: GptImage2Config | None = None) -> None:
        """初始化插件并应用配置中的命令权限级别。"""
        super().__init__(config)
        self.image_service: GptImage2Service | None = None
        if isinstance(self.config, GptImage2Config):
            self._apply_command_permission()

    async def on_plugin_loaded(self) -> None:
        """加载后初始化服务并注入提示词元数据。"""
        cfg = self.config
        if not isinstance(cfg, GptImage2Config) or not cfg.plugin.enabled:
            logger.info("GptImage2Plugin 已在配置中禁用")
            return

        try:
            logger.info("初始化 GptImage2Plugin...")
            self.image_service = GptImage2Service(self)
            await self.image_service.initialize()
            logger.info("GptImage2Service 已初始化")
        except Exception as e:
            logger.error(f"GptImage2Plugin 初始化失败: {e}", exc_info=True)
            raise

        character_prompt = cfg.generation.character_prompt.strip()
        if character_prompt:
            GptImageSelfieAction.action_description = (
                GptImageSelfieAction.action_description.rstrip()
                + "\n\n【你的角色特征（已内置，参数中无需重复）】\n"
                + character_prompt
            )

        custom = cfg.prompt.custom_instructions.strip()
        if custom:
            for action_cls in (GptImageDrawAction, GptImageSelfieAction):
                action_cls.action_description = action_cls.action_description.rstrip() + "\n\n" + custom

    async def on_plugin_unloaded(self) -> None:
        """卸载前清理服务资源。"""
        if self.image_service:
            await self.image_service.cleanup()
            logger.info("GptImage2Service 已清理")

    def _apply_command_permission(self) -> None:
        """从配置读取命令权限级别并应用到命令类。"""
        cfg = self.config
        if not isinstance(cfg, GptImage2Config):
            return
        perm_str = cfg.components.command_permission_level.strip().lower()
        level = _PERMISSION_MAP.get(perm_str)
        if level is None:
            logger.warning(
                f"无效的 command_permission_level {perm_str!r}，"
                f"回退到 owner"
            )
            level = PermissionLevel.OWNER
        GptImageCommand.permission_level = level
        logger.info(f"/gpt_image 命令权限级别已设为 {level.to_string()}")

    def get_components(self) -> list[type]:
        """返回启用的组件类列表。"""
        cfg = self.config
        if not isinstance(cfg, GptImage2Config) or not cfg.plugin.enabled:
            return []

        components: list[type] = []
        if cfg.components.action_enabled:
            components.extend([GptImageDrawAction, GptImageSelfieAction])
        if cfg.components.command_enabled:
            components.append(GptImageCommand)
        components.append(GptImage2Service)
        return components
