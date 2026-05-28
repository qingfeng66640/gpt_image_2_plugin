"""GPT Image 2 插件的图片文件辅助工具。"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("gpt_image_2_plugin.utils")


class ImageUtils:
    """小型图片辅助方法集合。"""

    @staticmethod
    def read_image_as_base64(image_path: str) -> tuple[bool, str, Optional[str]]:
        """将图片文件读取为 base64 字符串。"""
        try:
            if not os.path.exists(image_path):
                return False, f"图片文件不存在: {image_path}", None

            file_size = os.path.getsize(image_path)
            if file_size == 0:
                return False, "图片文件为空", None

            with open(image_path, "rb") as f:
                image_data = f.read()

            image_base64 = base64.b64encode(image_data).decode("utf-8")
            logger.info(f"读取图片成功: {image_path}, {file_size} bytes")
            return True, "图片读取成功", image_base64
        except Exception as e:
            logger.error(f"读取图片失败: {e}", exc_info=True)
            return False, f"读取图片失败: {e}", None

    @staticmethod
    def cleanup_temp_file(file_path: str, *, keep_file: bool = True) -> None:
        """可选择性地删除临时图片文件。"""
        if keep_file:
            logger.info(f"图片文件已保留: {file_path}")
            return

        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"已删除临时图片: {file_path}")
        except Exception as e:
            logger.warning(f"删除临时图片失败: {e}")
