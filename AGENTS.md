# 项目说明

- 本项目提供 AI 任务通知脚本，核心文件是 `notify.py`、`codex-hook.py` 和 `codex-wrapper.py`。
- `notify.py` 通过 `.env` 读取通知渠道配置，支持企业微信、飞书、钉钉和邮件。
- `codex-hook.py` 接收 Codex 原生 `PermissionRequest` hook JSON，并在不改变审批结果的前提下后台启动通知。
- `codex-wrapper.py` 用于包装本机 `codex` CLI：启动真实 `codex`，同时监听 Codex TUI 日志中的用户提问和上游最终失败事件并调用 `notify.py` 发通知。

## Codex Wrapper 运行约定

- Codex 原生任务完成通知已配置在 `~/.codex/config.toml`：`notify = ["python3", "/home/zhangjianyong/project/ai-task-notify/notify.py"]`。
- 用户级 Codex 配置已显式设置 `log_dir = "/home/zhangjianyong/.codex/log"`，wrapper 使用其中的 `codex-tui.log`。
- 用户级 `~/.codex/hooks.json` 已配置全局 `PermissionRequest` hook，命令指向项目内 `codex-hook.py`；新增或修改后必须在 Codex `/hooks` 中审核并信任。
- 当前 `approval_policy = "never"` 保持不变，默认 profile 通常不会产生审批事件。
- 默认真实 `codex` 从当前 `PATH` 中自动发现，并会跳过 wrapper 自身，避免递归调用。
- 如需指定真实 `codex`，设置环境变量 `CODEX_WRAPPER_REAL_CODEX`。
- 默认日志路径是 `~/.codex/log/codex-tui.log`，可用 `CODEX_WRAPPER_LOG_PATH` 覆盖。
- 默认通知脚本是项目内的 `notify.py`，可用 `CODEX_WRAPPER_NOTIFY_SCRIPT` 覆盖。
- 新 Bash shell 中默认 `codex` 路径是 `/home/zhangjianyong/.local/codex-wrapper-bin/codex`，该 shim 是指向项目 `codex-wrapper.py` 的符号链接。
- 当前官方 Codex 入口是 `/home/zhangjianyong/.local/bin/codex`，版本为 0.144.5，可作为紧急绕过通道；`/usr/local/bin/codex` 0.137.0 不作为真实目标。
- 验证 wrapper 可用：`python3 codex-wrapper.py --version`。
- wrapper shim 目录通过 `~/.bashrc` 放在 PATH 前部；当前已启动 shell 不会自动刷新，验证时使用新 shell 或重新加载配置。
- 回滚或故障绕过：直接运行 `/home/zhangjianyong/.local/bin/codex`，或从 PATH 中移除 `~/.local/codex-wrapper-bin`。
- Codex 0.144.5 的 handler `async` 选项不会执行对应 hook；审批 hook 必须由 `codex-hook.py` 自行后台启动通知后快速退出。

## 测试

- 使用标准库测试：`python3 -m unittest test_codex_wrapper.py test_notify.py test_codex_hook.py`。
- 单独验证通知调度测试：`python3 -m unittest test_notify.py`。
- 语法检查：`python3 -m py_compile codex-wrapper.py codex-hook.py notify.py test_codex_wrapper.py test_codex_hook.py test_notify.py`。
<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
