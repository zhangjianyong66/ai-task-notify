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
- 当前本机真实 Codex 路径：`/home/zhangjianyong/.nvm/versions/node/v22.22.0/bin/codex`。
- 验证 wrapper 可用：`python3 codex-wrapper.py --version`。
- 当前本机已在 `~/.local/bin/codex` 配置可执行 shim，调用 `/home/zhangjianyong/project/ai-task-notify/codex-wrapper.py`。
- `~/.bashrc` 中设置了 `CODEX_WRAPPER_REAL_CODEX=/home/zhangjianyong/.nvm/versions/node/v22.22.0/bin/codex`，用于避免 shim 递归调用自身。

## 测试

- 使用标准库测试：`python3 -m unittest test_codex_wrapper.py`。
- 语法检查：`python3 -m py_compile codex-wrapper.py notify.py test_codex_wrapper.py`。
