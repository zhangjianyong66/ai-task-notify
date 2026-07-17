# Codex 通知集成协议

## Scenario: Codex 0.144.5+ 混合通知入口

### 1. Scope / Trigger

- 触发条件：修改 Codex 完成通知、`PermissionRequest` hook、TUI 日志解析、后台通知进程或用户级部署配置。
- 目标：官方结构化事件优先，日志只补齐官方 hooks 未提供的用户提问和上游最终失败，同时保证通知失败不改变 Codex 行为。
- 正式兼容基线：Codex CLI 0.144.5+；旧版只尽力兼容，不维护专用日志分支。

### 2. Signatures

- 完成通知：`python3 notify.py '<json>'`
- 审批 hook：`python3 codex-hook.py`，从 stdin 读取一个 JSON 对象。
- wrapper：`python3 codex-wrapper.py <全部原始 Codex 参数>`。
- 后台启动函数：`start_background_notification(data: dict, notify_script: Path | str | None = None) -> tuple[bool, str]`。
- hook 转换函数：`parse_permission_request(data: dict) -> dict | None`。
- 日志转换函数：`parse_question_toolcall(line: str) -> dict | None`、`parse_upstream_failure(line: str) -> dict | None`。

### 3. Contracts

事件入口和内部载荷：

| 来源 | `source` | `type` | 必要或常用字段 |
| --- | --- | --- | --- |
| Codex 原生 `notify` | `codex` | `agent-turn-complete` | `thread-id`、`turn-id`、`cwd`、`input-messages`、`last-assistant-message` |
| `PermissionRequest` | `codex-hook` | `approval-required` | `session_id`、`turn_id`、`cwd`、`tool_name`、受控命令或参数字段摘要 |
| TUI 提问日志 | `codex-wrapper` | `question-required` | `thread_id`、`turn_id`、首个问题、选项、问题数量 |
| TUI 最终错误日志 | `codex-wrapper` | `upstream-response-failed` | 错误类别、HTTP 状态、重试耗尽状态、最多 300 字符脱敏摘要 |

边界约定：

- `codex-hook.py` 不返回审批决定、不输出 stdout，并始终以 0 退出；原有审批提示由 Codex 继续处理。
- `tool_input.description` 是可选字段；MCP `tool_input` 只发送参数名摘要，不发送完整参数值。
- wrapper 不解析审批日志；审批只走 `PermissionRequest`。
- `stream disconnected - retrying...` 等中间重试不通知，只有 `Turn error:` 进入最终失败转换。
- 后台通知使用参数列表、空设备和独立会话启动，不等待 webhook/SMTP。
- 配置覆盖项：`CODEX_WRAPPER_REAL_CODEX`、`CODEX_WRAPPER_LOG_PATH`、`CODEX_WRAPPER_NOTIFY_SCRIPT`。
- 用户级配置需要 `log_dir`；用户级 hook 放在 `~/.codex/hooks.json`，修改后由用户在 `/hooks` 信任。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| hook stdin 不是合法 JSON | stderr 输出一次诊断，退出 0，不启动通知 |
| hook 事件不是 `PermissionRequest` | 静默退出 0 |
| 可选描述缺失或 MCP 参数形状不同 | 使用安全默认值或参数名摘要，仍退出 0 |
| 后台进程启动失败 | 调用方 stderr 诊断，不改变 hook 或真实 Codex 退出码 |
| 日志长期不存在 | wrapper 提示显式配置 `log_dir`，只提示一次 |
| 日志读取失败 | 按时间节流诊断，继续轮询 |
| 已知提问/错误标记无法解析 | 一次性兼容性警告，继续 Codex |
| 中间流重试 | 忽略，不发送通知 |
| `Turn error:` 最终失败 | 分类、提取状态、脱敏、进程内有界去重后通知 |

### 5. Good / Base / Bad Cases

- Good：`PermissionRequest` 的 Bash 输入带 `command` 和 `description`，hook 只发送截断摘要并立即返回。
- Base：MCP 审批只有任意 JSON 参数，hook 仅发送 `参数字段: path, mode`，不暴露值。
- Good：提问日志中的 `thread_id` 位于 JSON 前或后，解析结果一致。
- Base：最终错误没有线程、轮次或 HTTP 状态，使用 `N/A` 和 `upstream-error`，仍发送安全摘要。
- Bad：把完整 `tool_input`、响应体、请求头或带查询参数 URL 放进通知。
- Bad：在 hook 配置中使用 `async = true`；Codex 当前会跳过该 handler。

### 6. Tests Required

- `test_codex_hook.py`：合法/非法/非目标事件、可选描述、MCP 参数名摘要、无 stdout、退出 0、只启动一次通知。
- `test_codex_wrapper.py`：提问字段前后顺序、非法 JSON、空问题、错误分类、HTTP 状态、中间重试忽略、有界去重和诊断节流。
- `test_notify.py`：完成/审批/提问/失败格式、Bearer/API key/URL 查询参数/长密钥脱敏、后台进程启动参数和失败结果。
- 全量命令：`python3 -m unittest test_codex_wrapper.py test_notify.py test_codex_hook.py`。
- 断言重点：测试不得访问真实 webhook、SMTP、用户日志或真实 Codex 会话；已知事件格式不得包含原始 JSON 块。

### 7. Wrong vs Correct

#### Wrong

```python
# 审批继续依赖不稳定的 TUI 文本，并同步等待通知网络请求。
approval = parse_exec_command_log(line)
subprocess.run(["python3", "notify.py", json.dumps(approval)])
```

#### Correct

```python
# 审批使用结构化 hook；日志只补齐提问和最终失败。
event = parse_permission_request(hook_json)
ok, error = start_background_notification(event, notify_script)
```

正确实现降低日志格式升级导致的静默失效，并保证通知通道故障不会阻断 Codex。
