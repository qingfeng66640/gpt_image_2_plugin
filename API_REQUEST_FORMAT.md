# GPT Image 2 请求格式

插件只适配图片生成接口：

```http
POST /images/generations
Content-Type: application/json
Authorization: Bearer <api_key>
```

默认完整 URL：

```text
https://api.openai.com/v1/images/generations
```

可通过以下配置覆盖完整 URL：

```text
config/plugins/gpt_image_2_plugin/config.toml
```

请求体示例：

```json
{
  "model": "gpt-image-2",
  "prompt": "A cinematic fantasy landscape",
  "n": 1,
  "size": "1536x1024",
  "quality": "auto",
  "output_format": "png",
  "background": "auto",
  "moderation": "auto",
  "user": "command_user"
}
```

`output_compression` 只会在 `output_format` 为 `jpeg` 或 `webp` 时发送。

响应要求：

```json
{
  "data": [
    {
      "b64_json": "..."
    }
  ]
}
```

插件会读取第一张图片，保存到本地，再通过消息 API 发送。

不要把 `api.request_url` 配置为：

- `/v1/chat/completions`：聊天接口，要求 `messages`
- `/v1/responses`：Responses API，要求 `input`
