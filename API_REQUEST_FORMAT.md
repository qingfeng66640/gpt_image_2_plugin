# GPT Image 2 请求格式

插件使用两类接口：文生图 `/images/generations`（JSON）与图生图 `/images/edits`（multipart）。
下面先说明文生图接口：

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

## 图生图 /images/edits

`/gpt_image edit` 与 `gpt_image_edit` Action 把聊天中的最近一张图片作为输入，
请求发往 `api.request_url` 中 `/generations` 被替换为 `/edits` 的地址，且必须是
**multipart/form-data**（官方 edits 协议要求上传图片文件；发送 JSON 会被上游拒绝，
中转站通常只返回 `bad_response_status_code` 这类包装错误，看不到真实原因）：

```http
POST /images/edits
Content-Type: multipart/form-data; boundary=...
Authorization: Bearer <api_key>
```

字段：`image`（文件，按源图魔数决定 filename 与 Content-Type）、`model`、`prompt`、
`n`、`size`、`quality`、`output_format`、`background`、`moderation`、
`output_compression`（仅 jpeg/webp）、`user`。

响应格式与 `/images/generations` 相同。图生图耗时明显高于文生图（实测单张低质量
编辑可达 200 秒以上），`api.timeout` 建议不低于 300。

不要把 `api.request_url` 配置为：

- `/v1/chat/completions`：聊天接口，要求 `messages`
- `/v1/responses`：Responses API，要求 `input`
