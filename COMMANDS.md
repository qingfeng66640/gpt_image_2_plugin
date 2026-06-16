# GPT Image 2 命令

## `/gpt_image`

通过配置的 `/images/generations` 接口生成图片。命令会立即返回，图片生成和发送在后台继续执行。

示例：

```text
/gpt_image draw 夕阳下的海边小屋，电影感光影，细节丰富
/gpt_image 横图 一座未来城市的夜景，霓虹灯，雨后街道
/gpt_image 竖图 精致人物插画，清晰面部，柔和光影
/gpt_image 1536x864 A cinematic fantasy landscape with floating islands
/gpt_image auto 一只穿宇航服的猫，海报风格
```

支持的画幅别名：

- `方图` / `square` -> `1024x1024`
- `横图` / `landscape` -> `1536x1024`
- `竖图` / `portrait` -> `1024x1536`
- `auto` -> 由接口自动选择

自定义尺寸要求：

- 格式为 `WIDTHxHEIGHT`
- 宽高必须为 16 的倍数
- 宽高比必须在 `1:3` 到 `3:1` 之间
- 最大边界按接口文档约束为 `3840x2160`
