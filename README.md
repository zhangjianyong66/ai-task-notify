# ai-task-notify

为 Claude Code、Kimi CLI 和 Codex CLI 发送任务完成、审批等待、用户提问等待及上游失败通知。通知渠道支持企业微信、飞书、钉钉和邮件，全部使用 Python 标准库实现。

## 环境要求

- Python 3.10+
- 已配置的群机器人 Webhook 或 SMTP 账号
- Codex 原生 hooks 需要 Codex CLI 0.144.5+

## Codex 一键配置

Linux + Bash 用户推荐从仓库根目录运行统一入口：

```bash
./setup.sh install
```

向导会配置通知渠道、Codex `notify`、`PermissionRequest` hook、wrapper shim 和 Bash PATH。已有完整 `.env` 默认复用；敏感字段使用隐藏输入，配置文件权限固定为 `0600`。安装器不会安装或升级 Python、Codex、Node/npm，也不会使用 `sudo`。

常用命令：

```bash
./setup.sh install --dry-run
./setup.sh install --non-interactive
./setup.sh install --non-interactive --migrate
./setup.sh check
./setup.sh uninstall --dry-run
./setup.sh uninstall
```

- `--dry-run` 只显示计划，不写文件、不创建备份、不采集凭据、不发送通知。
- `--non-interactive` 只使用已有 `.env` 或进程环境变量，缺少字段或存在冲突时在写入前失败。
- 每个用户只维护一个激活仓库副本；无人值守迁移必须显式加 `--migrate`，且不会复制旧仓库的 `.env`。
- `check` 始终只读且不发送通知。
- 卸载默认保留 `.env`、普通备份及用户后来修改的冲突项。

安装状态位于 `${XDG_STATE_HOME:-$HOME/.local/state}/ai-task-notify/install-state.json`。安装完成表示自动配置成功；新增 hook 仍需用户进入 Codex `/hooks` 页面审核并信任，这属于安装后的人工安全步骤，不影响安装成功码。

以下手工配置章节保留用于排障和理解接入结构。

## 配置通知渠道

复制配置模板：

```bash
cp .env.example .env
```

编辑 `.env`，在 `NOTIFY_CHANNELS` 中按发送顺序填写渠道：

```dotenv
NOTIFY_CHANNELS=wecom,feishu,dingtalk,email
```

仅填写启用渠道所需的字段。`.env` 包含敏感信息，已经由 `.gitignore` 忽略，不应提交到 Git。

## Codex 通知架构

Codex 0.144.5+ 使用三个入口，避免重复通知：

| 事件 | 入口 | 说明 |
| --- | --- | --- |
| 任务完成 | Codex 原生 `notify` | 唯一的完成通知入口 |
| 审批等待 | 原生 `PermissionRequest` hook | 使用结构化 hook JSON，不依赖日志文本 |
| 用户提问等待 | `codex-wrapper.py` | 补充原生 hooks 尚未提供的事件 |
| 上游最终失败 | `codex-wrapper.py` | 只通知最终 `Turn error:`，忽略中间重试 |

### 1. 配置完成通知和日志

编辑用户级 `~/.codex/config.toml`：

```toml
notify = ["python3", "/absolute/path/to/ai-task-notify/notify.py"]
log_dir = "/home/your-user/.codex/log"
```

显式设置 `log_dir` 才会生成 wrapper 使用的明文 `codex-tui.log`。完成通知不要再配置 `Stop` hook，否则可能重复发送。

### 2. 配置审批通知

创建或合并用户级 `~/.codex/hooks.json`：

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/ai-task-notify/codex-hook.py",
            "timeout": 5,
            "statusMessage": "Sending approval notification"
          }
        ]
      }
    ]
  }
}
```

省略 `matcher` 表示覆盖所有受支持的审批工具。不要配置 handler 的 `async` 字段：当前 Codex 会跳过这类 handler；`codex-hook.py` 会自行后台启动通知并立即退出。

非托管 hook 新增或修改后，必须进入 Codex CLI 的 `/hooks` 页面审核并信任，未信任时 Codex 会跳过它。

如果当前 `approval_policy = "never"`，正常会话通常不会产生 `PermissionRequest`，但可以保留 hook 供其他 profile 使用。

### 3. 让 wrapper 成为默认 Codex 入口

推荐创建独立 PATH 目录，不覆盖 npm 管理的官方入口：

```bash
mkdir -p ~/.local/codex-wrapper-bin
ln -s /absolute/path/to/ai-task-notify/codex-wrapper.py ~/.local/codex-wrapper-bin/codex
chmod +x /absolute/path/to/ai-task-notify/codex-wrapper.py
```

在 Bash 启动配置中把 shim 目录放在 `~/.local/bin` 前面：

```bash
export PATH="$HOME/.local/codex-wrapper-bin:$PATH"
```

打开新 shell 后验证：

```bash
command -v codex
codex --version
~/.local/bin/codex --version
```

`codex` 应指向 wrapper shim；`~/.local/bin/codex` 保持为官方入口，可在 wrapper 或日志解析出现问题时直接绕过。

wrapper 支持以下覆盖项：

- `CODEX_WRAPPER_REAL_CODEX`：显式指定真实 Codex
- `CODEX_WRAPPER_LOG_PATH`：覆盖 `codex-tui.log` 路径
- `CODEX_WRAPPER_NOTIFY_SCRIPT`：覆盖通知脚本路径

## Claude Code

在 Claude Code 的用户设置中配置 `Stop` hook，并使用仓库内 `notify.py` 的绝对路径：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/ai-task-notify/notify.py"
          }
        ]
      }
    ]
  }
}
```

## Kimi CLI

Kimi 的 `Stop` 和 `Notification` hook 通过 stdin 向 `notify.py` 传入 JSON。命令同样应使用 `notify.py` 的绝对路径。`stop_hook_active=true` 的二次 Stop 事件会自动跳过，防止循环。

## 测试

```bash
python3 -m unittest test_setup_config.py test_codex_wrapper.py test_notify.py test_codex_hook.py
python3 -m py_compile setup_config.py codex-wrapper.py codex-hook.py notify.py test_setup_config.py test_codex_wrapper.py test_codex_hook.py test_notify.py
bash -n setup.sh
python3 codex-wrapper.py --version
```

测试使用 mock 和隔离样本，不访问真实 webhook、SMTP、Codex 会话或用户日志。

## 安全与故障处理

- 上游失败通知会移除 URL 查询参数并遮盖 Authorization、Bearer Token、API key、密码和疑似长密钥。
- hook 和 wrapper 不发送完整请求头、响应体、模型上下文或完整工具参数。
- 通知进程后台启动，网络或 SMTP 超时不会阻断 Codex，也不会改变真实 Codex 的退出码。
- wrapper 只兼容 Codex 0.144.5+ 的当前日志标记；升级后如果格式变化，会向 stderr 输出一次诊断并继续运行 Codex。
- 没有持久队列，机器立即关闭时可能丢失尚未完成的通知。

## 回滚

- 直接运行 `~/.local/bin/codex` 绕过 wrapper。
- 从 PATH 中移除 `~/.local/codex-wrapper-bin` 可恢复官方 Codex 为默认入口。
- 从 `~/.codex/hooks.json` 移除或禁用 `PermissionRequest` hook 可停用审批通知。
- 原生 `notify` 可以独立保留；停用 wrapper 后也可按需移除 `log_dir`。
