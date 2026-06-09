# GPT Image 2 Plugin

基于 OpenAI 兼容 `/images/generations` 接口的图片生成插件，独立于旧版 `image_generator_plugin-neo`。

## 能力

- `/gpt_image` 命令文生图
- LLM Action 触发文生图
- 基于 `character_prompt` 的 Bot 自拍 Action
- 自定义完整请求 URL
- API Key 轮换
- 全局串行队列、冷却、重试、超时控制
- 生成图片本地保存

## 正确接口

插件发送的是图片生成 payload，必须使用图片生成接口：

```text
https://api.openai.com/v1/images/generations
```

如果使用中转站，也必须是中转站的 `/v1/images/generations` 路径，例如：

```text
https://example.com/v1/images/generations
```

不要配置成 `/v1/chat/completions` 或 `/v1/responses`。这两个接口分别要求 `messages` 和 `input` 字段，不接受本插件的图片生成 payload。

## 配置

配置文件：

```text
config/plugins/gpt_image_2_plugin/config.toml
```

最小配置：

```toml
[plugin]
enabled = true

[api]
api_keys = ["YOUR_OPENAI_API_KEY"]
request_url = "https://api.openai.com/v1/images/generations"

[generation]
model = "gpt-image-2"
default_size = "1024x1024"
```

## 本地保存

- 命令生成图片：`plugins/gpt_image_2_plugin/command_images/`
- Action 生成图片：`plugins/gpt_image_2_plugin/temp_images/`

当前插件默认保留生成文件，不会在发送后删除。

## 生产行为

`/gpt_image` 不会阻塞消息事件处理器。命令收到后会立即提交后台任务，图片生成完成后再异步发送，避免被事件总线短超时取消。

## Neo-MoFox 1.2.0-rc 兼容性

插件的两个 LLM Action 已显式声明 `associated_types = ["image"]`。在 1.2.0-rc 及之后版本中，核心会根据当前适配器写入消息 `extra.format_info.accept_format` 的内容过滤 Action；如果适配器未声明支持 `image`，自然语言触发的画图/自拍 Action 将不会加载到本轮可用工具中。

本插件不实现 adapter，也不构造 `Envelope`，因此 `format_info.accept_format` 需要由当前使用的 adapter 提供。NapCat adapter 改名为 OneBot adapter 不影响本插件源码，但运行环境需要迁移对应 adapter 配置。

关键日志：

- `后台生图任务已提交`
- `开始请求 GPT Image 2`
- `GPT Image 2 接口响应状态`
- `图片已保存`
- `后台生图图片发送结果`
