# 部署方式

## 部署模型

本项目不是常驻 Web 服务，也没有容器镜像、安装包构建或 systemd 配置。当前部署方式是把仓库保留在本机固定路径，通过 AI CLI 的 hook/notify 配置调用 Python 脚本。

运行依赖：

- Python 3.10+。
- 访问企业微信、飞书、钉钉 webhook 或 SMTP 的网络能力。
- 使用 wrapper 时需要本机已安装真实 Codex CLI，并存在 Codex TUI 日志。

## 通知配置

1. 从 `.env.example` 复制本机 `.env`。
2. 在 `NOTIFY_CHANNELS` 中填写逗号分隔的 `wecom`、`feishu`、`dingtalk`、`email`。
3. 只填写启用渠道所需的 webhook、签名密钥或 SMTP 字段。
4. `.env` 必须保持未跟踪；当前根目录 `.gitignore` 已忽略它。

`notify.py` 默认读取与脚本同目录的 `.env`，进程环境变量优先于文件值。部署到其他路径时，应在 hook 中使用 `notify.py` 的绝对路径，避免依赖调用时的当前工作目录。

## Codex 原生完成通知

当前机器的用户级 `~/.codex/config.toml` 配置为：

```toml
notify = ["python3", "/home/zhangjianyong/project/ai-task-notify/notify.py"]
```

该入口处理 Codex 的 `agent-turn-complete` 事件。不要把真实 `.env` 内容写进 Codex 配置。

## Codex wrapper

`codex-wrapper.py` 是可选接入，用于捕获 Codex 原生完成通知之外的提权审批和结构化提问：

- 默认从 `PATH` 查找真实 `codex`，并跳过与 wrapper 自身解析到同一路径的候选，防止递归。
- `CODEX_WRAPPER_REAL_CODEX` 可显式指定真实 Codex。
- `CODEX_WRAPPER_LOG_PATH` 可覆盖默认日志 `~/.codex/log/codex-tui.log`。
- `CODEX_WRAPPER_NOTIFY_SCRIPT` 可覆盖默认同目录 `notify.py`。
- wrapper 将所有 CLI 参数和环境传给真实 Codex，并返回其退出码。

当前机器的 `~/.local/bin/codex` 是官方 npm Codex 入口的符号链接，不是 wrapper shim；当前 shell 也没有设置 `CODEX_WRAPPER_REAL_CODEX`。需要使用 wrapper 时，直接运行：

```bash
python3 /home/zhangjianyong/project/ai-task-notify/codex-wrapper.py <codex 参数>
```

如果以后重新把 wrapper 安装为 `codex` shim，必须显式设置 `CODEX_WRAPPER_REAL_CODEX` 指向另一个真实可执行文件，并验证 `python3 codex-wrapper.py --version`，避免递归启动。

## Claude Code 与 Kimi

- Claude Code Stop hook 和 Kimi hook 通过 stdin 向 `notify.py` 传 JSON。
- hook 命令应指向本地 `notify.py` 的绝对路径。
- README 中部分下载链接和 hook 示例路径已不符合当前本地部署，不能直接复制为运行配置；以源码、`.env.example`、`AGENTS.md` 和本规范为准。

## 发布资产

`Aigialosauridae/*.zip` 是仓库中的历史/发布资产，不是 Python 脚本的依赖，也不参与测试。除非任务明确涉及发布包，不解压、不执行、不从中加载代码。
