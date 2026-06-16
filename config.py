"""GPT Image 2 插件的配置。"""

from __future__ import annotations

from typing import ClassVar

from src.core.components.base.config import BaseConfig, Field, SectionBase, config_section


class GptImage2Config(BaseConfig):
    """GPT Image 2 插件配置。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "GPT Image 2 图片生成插件配置"

    @config_section("plugin")
    class PluginSection(SectionBase):
        """插件开关。"""

        enabled: bool = Field(default=False, description="是否启用插件")

    @config_section("components")
    class ComponentsSection(SectionBase):
        """组件开关。"""

        action_enabled: bool = Field(
            default=True,
            description="是否启用 Action 组件（LLM Tool Calling 生图）",
        )
        command_enabled: bool = Field(
            default=True,
            description="是否启用 Command 组件（/gpt_image 命令）",
        )
        command_permission_level: str = Field(
            default="owner",
            description=(
                "/gpt_image 命令的最低权限级别。"
                "可选值：user、operator、owner。"
                "设为 user 时普通用户也能使用生图命令"
            ),
        )

    @config_section("api")
    class ApiSection(SectionBase):
        """API 连接设置。"""

        api_keys: list[str] = Field(
            default_factory=list,
            description="OpenAI API Keys 列表（支持多个，会自动轮换）",
        )
        request_url: str = Field(
            default="https://api.openai.com/v1/images/generations",
            description="完整请求 URL，可改为兼容 OpenAI 的自定义中转地址",
        )
        proxy: str = Field(
            default="",
            description="代理地址（如 http://127.0.0.1:7890），留空则不使用代理",
        )
        cooldown: int = Field(default=5, description="两次请求之间的冷却时间（秒）")
        timeout: int = Field(default=120, description="单次请求超时时间（秒）")
        max_retries: int = Field(default=2, description="遇到 429/5xx 时的最大重试次数")
        retry_delay: int = Field(default=10, description="重试等待时间（秒）")

    @config_section("generation")
    class GenerationSection(SectionBase):
        """默认图片生成参数。"""

        model: str = Field(default="gpt-image-2", description="图片生成模型")
        default_size: str = Field(
            default="1024x1024",
            description=(
                "默认图片尺寸。gpt-image-2 支持 auto 或 WIDTHxHEIGHT；"
                "宽高需为 16 的倍数，宽高比需在 1:3 到 3:1 之间"
            ),
        )
        quality: str = Field(
            default="auto",
            description="输出质量：auto、low、medium、high",
        )
        output_format: str = Field(
            default="png",
            description="输出格式：png、jpeg、webp",
        )
        background: str = Field(
            default="auto",
            description="背景：auto、transparent、opaque",
        )
        moderation: str = Field(default="auto", description="审核级别：auto、low")
        output_compression: int = Field(
            default=100,
            description="jpeg/webp 输出压缩等级 0-100；png 时不会发送该参数",
        )
        n: int = Field(
            default=1,
            description="生成图片数量。当前插件只发送第一张，建议保持 1",
        )
        character_prompt: str = Field(
            default="a friendly anime-style digital assistant with pink hair, blue eyes, elf ears",
            description="自拍功能的角色特征锚定，用于生成 Bot 自己的照片",
        )

    @config_section("advanced")
    class AdvancedSection(SectionBase):
        """存储与行为设置。"""

        temp_dir: str = Field(default="temp_images", description="Action 临时图片目录")
        command_images_dir: str = Field(
            default="command_images",
            description="命令生成图片保存目录",
        )
        context_delay: float = Field(
            default=1.5,
            description="图生图从上下文获取图片前的等待时间（秒），给框架时间完成图片下载和消息处理",
        )

    @config_section("prompt")
    class PromptSection(SectionBase):
        """提示词自定义。"""

        custom_instructions: str = Field(
            default="",
            description="追加到两个 action 描述末尾的自定义触发/提示词说明",
        )

    plugin: PluginSection = Field(default_factory=PluginSection)
    components: ComponentsSection = Field(default_factory=ComponentsSection)
    api: ApiSection = Field(default_factory=ApiSection)
    generation: GenerationSection = Field(default_factory=GenerationSection)
    advanced: AdvancedSection = Field(default_factory=AdvancedSection)
    prompt: PromptSection = Field(default_factory=PromptSection)
