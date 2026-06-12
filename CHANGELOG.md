# GPT Image 2 Plugin 更新日志

## 2026-06-12 - 兼容 Neo-MoFox 1.2.0-rc

### 修复
- **[破坏性更新适配]** 为所有 Action 组件添加必需的 `associated_types` 字段
  - `GptImageDrawAction`: 添加 `associated_types: list[str] = ["image"]`
  - `GptImageSelfieAction`: 添加 `associated_types: list[str] = ["image"]`

### 背景
Neo-MoFox 1.2.0-rc 版本强化了 `associated_types` 校验功能，所有 action 和 agent 组件必须显式声明 `associated_types` 列表，否则核心不会加载该组件。

### 影响
- 修复了插件在 1.2.0-rc 版本下启动失败的问题
- 错误信息：`Action 'gpt_image_draw' 的 associated_types 必须是非空 list`

### 技术细节
根据框架更新公告第2条破坏性更新，`associated_types` 用于声明 action/agent 组件支持的消息类型。本插件生成和发送图片，因此声明为 `["image"]`。

这个字段配合 adapter 的 `format_info.accept_format` 进行匹配，确保只有支持图片格式的 adapter 才能使用这些 action。
