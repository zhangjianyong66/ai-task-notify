# 重要约定

## 配置来源与安全

- 配置优先级固定为“进程环境变量 > 脚本目录下 `.env` > 代码默认值”，由 `get_config` 实现。
- `.env.example` 是配置键的版本化来源；新增、重命名或删除环境变量时必须同步更新它。
- `.env`、webhook、机器人密钥、SMTP 密码和真实收件人属于敏感信息，不得提交或复制到测试夹具、文档和调试输出。
- `NOTIFY_CHANNELS` 大小写不敏感，解析时去除空格，并按用户配置顺序调度。

## 通知渠道

当前支持 `wecom`、`feishu`、`dingtalk`、`email`，注册表位于 `notify.py` 的 `CHANNEL_HANDLERS`。

新增或修改渠道时同时检查：

1. 渠道函数保持 `(env, title, content) -> bool`。
2. 缺少必需配置时返回 `False`，不要抛出导致全局中断的异常。
3. 在 `CHANNEL_HANDLERS` 注册稳定的小写名称。
4. 在 `.env.example` 增加无敏感值配置说明。
5. 在 `test_notify.py` 覆盖多渠道并存、失败隔离和结果字典。
6. 如果响应成功条件不同，按各平台返回协议判断，不只检查 HTTP 200。

`send_notification` 的核心契约是：每个已识别渠道都独立尝试，结果按渠道名记录为布尔值，一个渠道异常不能阻止后续渠道。

## 输入事件协议

- 命令行第一个参数是 JSON 时，按 Codex/Codex wrapper 方式处理。
- 无有效命令行 JSON 且 stdin 非 TTY 时，按 Claude Code 或 Kimi hook JSON 处理。
- Codex 原生来源只接受 `agent-turn-complete`。
- `codex-hook` 来源只接受 `approval-required`。
- `codex-wrapper` 来源只接受 `question-required` 和 `upstream-response-failed`。
- Kimi `Stop` 且 `stop_hook_active=true` 时必须跳过，防止 stop hook 循环。
- 未知来源仍可生成通用通知，但已知来源的非目标事件应尽早忽略。

事件字段可能来自外部 CLI 日志或 hook，展示前使用默认值和截断：命令默认最多 300 字符、问题最多 500 字符、通知正文和 JSON 块也有限制。新增字段时避免把无限长度或敏感原始内容直接发送到通知渠道。

## Wrapper 兼容性

- 审批只使用 Codex 原生 `PermissionRequest` hook；wrapper 不得恢复审批日志解析。
- 提问和最终失败仍依赖 Codex TUI 日志明确标记；修改解析器时必须覆盖字段顺序变化、合法/非法 JSON、空问题、中间重试和最终 `Turn error:`。
- 日志轮转通过设备号与 inode 识别；日志截断时重置读取位置；首次启动只回放末尾 `STARTUP_READ_BYTES`，避免扫描全部历史。
- 去重只在当前 wrapper 进程内有效，并使用有界缓存。去重键变更必须保持同一提问或最终失败不会在一次会话内重复通知。
- 通知子进程的 stdout/stderr 被丢弃，wrapper 自身只在启动通知失败、日志读取失败等情况下向 stderr 报告；不得让通知错误改变真实 Codex 的退出码。
- Codex command hook 的 `async` handler 当前不会执行；hook 适配器必须自行后台启动 `notify.py` 后快速退出。

## 文档与事实来源

- 行为事实优先级：当前源码和测试 > `.env.example`/`AGENTS.md` > README 和历史发布资产。
- README 可用于了解支持渠道和一般安装思路，但其中的 Python 版本、下载 URL 与 hook 示例路径可能过时；实现或部署前必须与源码核对。
- 发现新的目录、环境、部署或运行约定时，除更新本规范外，还应按根目录要求同步更新 `AGENTS.md`。
- Git 提交信息使用中文描述，推荐 Conventional Commits，例如 `docs(spec): 补全项目基础规范`。
