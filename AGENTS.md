# 项目说明

- 本项目提供 AI 任务通知脚本，核心文件是 `notify.py` 和 `codex-wrapper.py`。
- `notify.py` 通过 `.env` 读取通知渠道配置，支持企业微信、飞书、钉钉和邮件。
- `codex-wrapper.py` 用于包装本机 `codex` CLI：启动真实 `codex`，同时监听 Codex TUI 日志中的审批和用户提问事件并调用 `notify.py` 发通知。

## Codex Wrapper 运行约定

- Codex 原生任务完成通知已配置在 `~/.codex/config.toml`：`notify = ["python3", "/home/zhangjianyong/project/ai-task-notify/notify.py"]`。
- 默认真实 `codex` 从当前 `PATH` 中自动发现，并会跳过 wrapper 自身，避免递归调用。
- 如需指定真实 `codex`，设置环境变量 `CODEX_WRAPPER_REAL_CODEX`。
- 默认日志路径是 `~/.codex/log/codex-tui.log`，可用 `CODEX_WRAPPER_LOG_PATH` 覆盖。
- 默认通知脚本是项目内的 `notify.py`，可用 `CODEX_WRAPPER_NOTIFY_SCRIPT` 覆盖。
- 当前本机 `codex` 命令路径：`/home/zhangjianyong/.local/bin/codex`，该路径是官方 npm Codex 入口的符号链接；另有 `/usr/local/bin/codex` 候选。
- 验证 wrapper 可用：`python3 codex-wrapper.py --version`。
- 当前本机未把 wrapper 安装为 `codex` shim，当前 shell 也未设置 `CODEX_WRAPPER_REAL_CODEX`；需要 wrapper 时直接运行 `python3 /home/zhangjianyong/project/ai-task-notify/codex-wrapper.py`。
- 如果以后重新配置 wrapper shim，必须将 `CODEX_WRAPPER_REAL_CODEX` 指向另一个真实 Codex 可执行文件，避免递归调用自身。

## 测试

- 使用标准库测试：`python3 -m unittest test_codex_wrapper.py test_notify.py`。
- 单独验证通知调度测试：`python3 -m unittest test_notify.py`。
- 语法检查：`python3 -m py_compile codex-wrapper.py notify.py test_codex_wrapper.py test_notify.py`。
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
