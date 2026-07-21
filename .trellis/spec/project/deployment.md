# 部署方式

## 部署模型

本项目不是常驻 Web 服务，也没有容器镜像、安装包构建或 systemd 配置。当前部署方式是把仓库保留在本机固定路径，通过 AI CLI 的 hook/notify 配置调用 Python 脚本。

运行依赖：

- Python 3.10+。
- 访问企业微信、飞书、钉钉 webhook 或 SMTP 的网络能力。
- 使用 wrapper 时需要本机已安装真实 Codex CLI，并存在 Codex TUI 日志。
- Codex 原生 hooks 正式支持基线为 0.144.5+。

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

当前机器还显式配置：

```toml
log_dir = "/home/zhangjianyong/.codex/log"
```

显式 `log_dir` 会启用 `codex-tui.log`，供 wrapper 补齐提问和最终失败事件。

## Codex 审批 hook

用户级 `~/.codex/hooks.json` 配置全局 `PermissionRequest`，命令指向项目内 `codex-hook.py`。该适配器不返回审批决定，后台启动通知后以 0 退出。非托管 hook 修改后必须由用户在 `/hooks` 中审核并信任。

不要为 hook handler 配置 `async`；Codex 0.144.5 会跳过该 handler。

## Codex wrapper

`codex-wrapper.py` 用于捕获 Codex 原生完成通知和审批 hook 之外的结构化提问与上游最终失败：

- 默认从 `PATH` 查找真实 `codex`，并跳过与 wrapper 自身解析到同一路径的候选，防止递归。
- `CODEX_WRAPPER_REAL_CODEX` 可显式指定真实 Codex。
- `CODEX_WRAPPER_LOG_PATH` 可覆盖默认日志 `~/.codex/log/codex-tui.log`。
- `CODEX_WRAPPER_NOTIFY_SCRIPT` 可覆盖默认同目录 `notify.py`。
- wrapper 将所有 CLI 参数和环境传给真实 Codex，并返回其退出码。

当前机器使用独立 shim：

```bash
/home/zhangjianyong/.local/codex-wrapper-bin/codex
```

该符号链接指向项目内 `codex-wrapper.py`，`~/.bashrc` 会去重并强制将 shim 目录放在 PATH 前部，`~/.profile` 仅在 `~/.local/bin` 尚未存在于 PATH 时添加它，避免登录 shell 覆盖 wrapper 顺序。wrapper 会跳过解析后指向自身的候选，继续找到 `~/.local/bin/codex` 0.144.6。紧急绕过直接调用 `~/.local/bin/codex`；不使用 `/usr/local/bin/codex` 0.137.0。

## Claude Code 与 Kimi

- Claude Code Stop hook 和 Kimi hook 通过 stdin 向 `notify.py` 传 JSON。
- hook 命令应指向本地 `notify.py` 的绝对路径。
- README 中部分下载链接和 hook 示例路径已不符合当前本地部署，不能直接复制为运行配置；以源码、`.env.example`、`AGENTS.md` 和本规范为准。

## 发布资产

`Aigialosauridae/*.zip` 是仓库中的历史/发布资产，不是 Python 脚本的依赖，也不参与测试。除非任务明确涉及发布包，不解压、不执行、不从中加载代码。
