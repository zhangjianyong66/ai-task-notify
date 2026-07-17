# Codex 原生 Hooks 通知接入设计

## 设计目标

将 Codex 通知拆分为三个职责清晰的事件入口：官方 `notify` 负责完成通知，官方 `PermissionRequest` hook 负责审批通知，精简 wrapper 仅负责官方 hooks 未覆盖的结构化提问和上游最终失败告警。所有入口最终复用 `notify.py` 的渠道调度和消息格式化。

本任务的交付物相互依赖同一事件协议、通知入口与部署配置，不拆分父子任务。

## 架构边界

```text
Codex agent-turn-complete
        │ 官方 notify（Codex 异步启动）
        ▼
    notify.py ───────────────► 企业微信 / 飞书 / 钉钉 / 邮件

Codex PermissionRequest
        │ 用户级全局 hook，stdin JSON
        ▼
  codex-hook.py
        │ 后台启动 notify.py 后立即退出
        └────────────────────► 同一通知渠道

Codex TUI info log
  ├─ ToolCall: request_user_input / AskUserQuestion
  └─ Turn error: ...（仅最终失败）
        │
        ▼
  codex-wrapper.py
        │ 后台启动 notify.py，不等待网络结果
        └────────────────────► 同一通知渠道
```

## 事件职责

### 完成通知

- 保留用户级 `notify = ["python3", ".../notify.py"]`。
- 只接受 `type = "agent-turn-complete"`。
- 使用 `thread-id`、`turn-id`、`cwd`、`input-messages` 和 `last-assistant-message` 生成结构化内容，不再只展示原始 JSON。
- 不配置 `Stop` 完成通知，避免重复和同步 hook 阻塞。

### 审批通知

- 新增轻量 `codex-hook.py`，从 stdin 读取 Codex hook JSON。
- 只处理 `hook_event_name = "PermissionRequest"`，转换为内部 `source = "codex-hook"`、`type = "approval-required"`。
- 允许的字段包括 `session_id`、`turn_id`、`cwd`、`tool_name`、`tool_input.command` 和 `tool_input.description`。
- 适配器通过后台子进程调用 `notify.py`，自身不输出内容并以 0 退出，避免改变审批流程。
- hook 放在用户级 `~/.codex/hooks.json`；项目现有 Trellis hooks 保持不变。
- 非托管 hook 仍需用户在 `/hooks` 中审核并信任。

### 提问通知

- wrapper 不再解析审批日志，只保留内置提问工具。
- 解析 `ToolCall: request_user_input` 和兼容名称 `AskUserQuestion`。
- 不依赖 `thread_id` 位于 JSON 前或后；先定位工具标记，再用 JSON 解码器提取第一个完整对象，并从整行提取线程/轮次字段。
- 提取首个问题、选项和问题数量，保留现有截断限制。
- 已知标记出现但 JSON 无法解析时只输出一次兼容性警告。

### 上游最终失败告警

- 不通知 `stream disconnected - retrying...` 等中间重试日志。
- 仅解析 `Turn error: ...` 最终失败标记。
- 按受控关键词映射错误类别：HTTP/连接失败、响应流连接失败、响应流断开、重试耗尽、认证失败、限流/额度、其他上游错误。
- 尝试提取 HTTP 状态码、线程和轮次标识；缺少字段时使用安全默认值。
- 同一 wrapper 进程内按线程、轮次、错误类别和摘要去重；使用有界缓存避免长会话无限增长。
- 已知 `Turn error:` 标记出现但无法形成有效摘要时输出一次兼容性警告。

## 脱敏策略

在通知格式化前统一处理可能包含敏感信息的错误摘要：

- 限制长度约 300 字符并折叠多余空白。
- 遮盖 `Authorization`、`Bearer`、API key、token、secret、password 等键值。
- 移除 URL 查询参数，只保留 scheme、host 和 path 或直接用占位符替代查询部分。
- 遮盖疑似长密钥字符串。
- 不转发完整上游响应体、请求头、完整提示词或模型上下文。

脱敏函数保持纯函数，使用代表性输入做单元测试。

## 异步发送

- 在 `notify.py` 提供可复用的后台启动辅助函数，供 `codex-hook.py` 和 wrapper 调用。
- 使用参数列表启动 Python，不拼接 shell 命令。
- stdin/stdout/stderr 指向空设备并创建独立会话，调用方不等待通知完成。
- 启动失败写入调用方 `stderr`，不改变真实 Codex 的退出码。
- 不增加持久队列；机器立即关闭时允许丢失尚未完成的通知。

## 日志与诊断

- 用户级 Codex 配置显式设置 `log_dir = "/home/zhangjianyong/.codex/log"`，使 0.144.5 创建 `codex-tui.log`。
- wrapper 保留 inode/截断/轮转处理。
- 日志启动后一段合理时间仍不存在时输出一次说明，指出需要显式 `log_dir`。
- 日志无法读取时节流输出错误，避免轮询刷屏。
- 兼容基线是 0.144.5+；升级 Codex 后通过固定日志样本单元测试和手工会话验证解析器。

## 部署设计

- 创建 `~/.local/codex-wrapper-bin/codex`，指向仓库内可执行的 `codex-wrapper.py`。
- 在 Bash 启动配置中把该目录放在 `~/.local/bin` 前面。
- wrapper 解析自身真实路径后跳过 shim，继续找到 `~/.local/bin/codex` 0.144.5。
- 紧急绕过命令为 `~/.local/bin/codex`。
- 不使用 `/usr/local/bin/codex` 0.137.0 作为真实目标。

## 兼容与回滚

- 旧版 Codex 只尽力运行完成通知，不保证 hooks 和日志事件。
- 回滚时从 PATH 中移除 wrapper shim 目录或直接调用官方入口。
- 可禁用/移除用户级 `PermissionRequest` hook；`notify` 可独立继续工作。
- `log_dir` 可保留用于诊断，也可在停用 wrapper 后移除。
- 所有通知失败都不得终止 Codex 或改变其退出码。

## 安全说明

- 不在仓库、测试、文档或告警中写入真实 webhook、SMTP 密码、模型供应商凭据或 MCP 密钥。
- 当前用户级 Codex 配置中的既有敏感值不在本任务中复制或展示；凭据轮换属于独立安全操作。
