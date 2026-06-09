"""GPT Image 2 图片生成插件。"""
from src.plugin_system.base.plugin_metadata import PluginMetadata

__plugin_meta__ = PluginMetadata(
    usage="plugin",
    name="gpt_image_2_plugin",
    version="1.0.2",
    author="MoFox",
    description="基于 OpenAI GPT Image 2 /images/generations 接口的图片生成插件",
)
