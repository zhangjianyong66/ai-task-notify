# 部署方式

## 部署模型

本项目不是常驻 Web 服务，也没有容器镜像、安装包构建或 systemd 配置。当前部署方式是把仓库保留在本机固定路径，通过 AI CLI 的 hook/notify 配置调用 Python 脚本。

运行依赖：

- Python 3.10+。
- 访问企业微信、飞书、钉钉 webhook 或 SMTP 的网络能力。
- 使用 wrapper 时需要本机已安装真实 Codex CLI，并存在 Codex TUI 日志。
- Codex 原生 hooks 正式支持基线为 0.144.5+。

## 一键配置入口

Linux + Bash 推荐使用 `./setup.sh install`，诊断使用 `./setup.sh check`，恢复首次接管前状态使用 `./setup.sh uninstall`。内部实现为纯标准库 `setup_config.py`。

- `install/check/uninstall` 支持任务设计中定义的非交互、迁移和 dry-run 选项；凭据不作为命令行参数。
- 状态清单位于 `${XDG_STATE_HOME:-$HOME/.local/state}/ai-task-notify/install-state.json`，不保存通知凭据正文。
- `CODEX_HOME` 优先于默认 `~/.codex`；wrapper 日志路径优先级为 `CODEX_WRAPPER_LOG_PATH > CODEX_HOME > HOME`。
- 自动配置成功后只提示用户进入 `/hooks` 审核，不探测或绕过 Codex 的人工信任状态。
- 安装器不安装依赖、不使用 `sudo`；修改前备份、原子替换并在失败时回滚。

### 一键配置契约

#### 1. Scope / Trigger

触发条件：需要在 Linux + Bash 用户环境中安装、诊断、迁移或卸载本项目的 Codex 通知接入。

#### 2. Signatures

```text
./setup.sh install [--non-interactive] [--migrate] [--dry-run]
./setup.sh check
./setup.sh uninstall [--non-interactive] [--dry-run]
```

#### 3. Contracts

- `CODEX_HOME` 优先于 `$HOME/.codex`；`XDG_STATE_HOME` 优先于 `$HOME/.local/state`。
- `.env` 只持久化文件中已有值或交互输入值；进程环境变量只参与有效配置校验和测试通知，不反向写入文件。
- 状态清单记录 `schema`、`repo_path`、受管路径、摘要和恢复备份引用，不保存通知凭据正文。
- 成功安装后提示 `/hooks` 人工审核；不读取或写入 Codex 信任状态。

#### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 缺少渠道必填字段 | 写入前返回 `1`，只输出字段名 |
| Codex 不存在或低于 `0.144.5` | 返回 `1`，不安装或升级依赖 |
| 非交互存在迁移/路径冲突 | 未显式 `--migrate` 或有冲突时返回 `1` |
| 候选 TOML/JSON/Bash 校验失败 | 返回 `1`，原文件保持不变 |
| `--dry-run` | 只输出计划，不创建状态、备份、临时文件或通知 |
| 卸载发现用户后改项 | 完成无冲突项，保留冲突并返回 `1` |

#### 5. Good / Base / Bad Cases

- Good：临时 `HOME` 中 fake Codex 返回 `0.145.0`，连续安装保持配置和 hook 幂等。
- Base：已有完整 `.env` 直接复用，敏感字段回车保留，未知键和注释继续存在。
- Bad：把 webhook、密码或进程环境凭据拼入命令行、状态清单或计划输出。

#### 6. Tests Required

- `test_setup_config.py` 使用临时 HOME、CODEX_HOME、XDG 状态目录和 fake Codex。
- 断言安装、重装、dry-run、检查、卸载、恢复、冲突、权限和进程环境不落盘。
- `test_codex_wrapper.py` 断言 `CODEX_WRAPPER_LOG_PATH > CODEX_HOME > HOME`。

#### 7. Wrong vs Correct

错误：安装器把进程环境中的 `WECOM_WEBHOOK_URL` 自动复制到项目 `.env`。

正确：环境变量参与当前次校验和通知发送，但 `.env` 只由已有文件内容或用户交互输入更新。

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
