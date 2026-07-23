# Codex 一键配置技术设计

## 设计目标

提供一个面向 Linux + Bash 用户的统一入口 `./setup.sh`，安全完成通知渠道、Codex 原生通知、审批 hook、wrapper shim 和 PATH 的安装、诊断与卸载。配置过程必须幂等、可预演、可回滚，并保留用户未受管的配置。

本任务的命令入口、配置适配器、状态模型和测试共同构成一个不可分割的安装生命周期，因此不拆分父子任务。

## 命令契约

```text
./setup.sh install [--non-interactive] [--migrate] [--dry-run]
./setup.sh check
./setup.sh uninstall [--non-interactive] [--dry-run]
```

- `setup.sh` 是唯一公开入口，只定位仓库、检查 `python3` 并把参数原样交给内部 Python 实现。
- `install` 默认运行交互向导；重复执行用于检查、升级和修复受管配置。
- `install --non-interactive` 只消费已有 `.env` 或进程环境，不接受任何凭据参数。
- `--migrate` 只对非交互安装有意义，授权把当前激活副本迁移到本仓库路径。
- `check` 始终只读、无网络访问，以逐项状态和退出码表达健康度。
- `uninstall` 默认先展示计划并要求确认；`--non-interactive` 是明确的执行授权。
- `--dry-run` 只生成变更计划，不写文件、不备份、不采集凭据、不联网。
- 参数组合或未知参数不合法时返回 `2`；配置或运行失败返回 `1`；成功返回 `0`。

## 文件边界

```text
setup.sh              # 稳定 shell 入口，不承载配置合并逻辑
setup_config.py       # 发现、规划、交互、事务、检查和卸载
test_setup_config.py  # 纯函数、临时 HOME、CLI 与事务测试
codex-wrapper.py      # 补充识别 CODEX_HOME 的日志路径
test_codex_wrapper.py # CODEX_HOME 路径优先级测试
```

`notify.py` 继续作为渠道配置与发送能力的唯一来源。安装器复用其 `load_env`、`get_config`、`get_enabled_channels`、`CHANNEL_HANDLERS` 和 `send_notification`，不复制渠道发送实现。

## 路径解析

- 仓库路径：以 `setup_config.py` 的真实路径为准，统一 `resolve()`。
- Codex 配置目录：优先使用 `CODEX_HOME`，否则使用 `$HOME/.codex`。
- Codex 日志：`$CODEX_HOME/log/codex-tui.log`；同步修改 wrapper，使其遵循相同优先级，`CODEX_WRAPPER_LOG_PATH` 仍最高。
- shim：`$HOME/.local/codex-wrapper-bin/codex`，保持官方 Codex 入口不被覆盖。
- shell 配置：`$HOME/.bashrc`。
- 状态目录：`${XDG_STATE_HOME:-$HOME/.local/state}/ai-task-notify/`，目录权限 `0700`。
- 状态清单：状态目录下 `install-state.json`，权限 `0600`。
- 备份：状态目录下按事务时间戳分组，目录 `0700`、文件 `0600`。

## 安装数据流

```text
环境与依赖发现
      ↓
读取 .env / TOML / hooks JSON / .bashrc / 状态清单
      ↓
校验通知字段、Codex 版本和真实入口
      ↓
生成完整变更计划并识别冲突
      ↓
交互解决冲突或非交互提前失败
      ↓
dry-run: 输出计划后结束
      ↓
备份 → 临时写入 → 格式校验 → 原子替换
      ↓
写入状态清单并提交事务
      ↓
可选且再次确认的真实测试通知
```

所有冲突必须在首次持久化写入前解决。可选测试通知发生在配置事务提交后；发送失败不撤销已经正确写入的本地配置，但命令返回 `1` 并逐渠道报告结果。

## 通知渠道向导

- 支持现有 `wecom`、`feishu`、`dingtalk`、`email`，允许多选并保持用户选择顺序。
- 必填字段表由安装模块集中定义，并与 `.env.example`、`notify.py` 的当前契约一致。
- webhook、签名密钥和 SMTP 密码使用 `getpass`；主机、端口、用户和邮件地址可使用普通输入。
- 已有完整 `.env` 默认复用。选择重新配置时只显示字段的“已配置/缺失”状态；敏感字段回车表示保留。
- 更新 `.env` 时只改动已知键对应行，保留注释、未知键和未启用渠道凭据；新增键按模板顺序追加。
- 进程环境优先于 `.env`。环境中已有的值可用于本次校验，但不会被反向复制到 `.env`。
- 实际生成或修改 `.env` 后强制权限 `0600`。状态清单不保存任何通知配置值。

## Codex 依赖发现

- 沿 PATH 查找名为 `codex` 的可执行文件，解析真实路径并排除目标 wrapper 自身和 shim。
- 执行候选的 `--version`，要求版本不低于 `0.144.5`；多候选时报告最终选择路径。
- 不调用 Codex 的安装或更新命令，不调用 npm 或 `sudo`。
- 官方入口路径不写死；必要时在状态与诊断输出中记录或展示路径。

## 配置适配器

### `config.toml`

只管理顶层 `notify` 与 `log_dir`：

- 采用有边界的顶层键文本编辑器，保留其余原文和注释。
- 新值使用确定性的单行 TOML 表达；首次安装后可做精确幂等比较。
- 相关键使用不受支持的多行或复杂写法时视为冲突，不猜测、不整文件重写。
- 写入前验证现有配置，写入候选后使用真实 Codex 的 `--strict-config --version` 在隔离 `CODEX_HOME` 中校验；Python 3.11+ 可额外用 `tomllib` 做语法预检，但不得提高项目的 Python 3.10 基线。

### `hooks.json`

- 使用标准库 `json` 解析和序列化，验证根结构及 `hooks.PermissionRequest` 类型。
- 只新增或更新命令指向当前 `codex-hook.py` 的 handler group；其他事件、group、matcher 和 handler 语义保持不变。
- 等价 handler 不重复添加；其他 ai-task-notify 路径属于迁移或冲突；其他产品的 PermissionRequest hook 可并存。
- JSON 格式可能统一为两空格缩进，但键顺序和所有未知字段保留。

### wrapper shim 与 Bash PATH

- shim 是指向当前仓库 `codex-wrapper.py` 的符号链接；非符号链接或指向其他产品时属于冲突。
- `~/.bashrc` 新增唯一带起止标记的受管区块。区块把 shim 目录去重后放到 PATH 首位。
- 已有未标记但行为等价的 PATH 配置视为外部配置并保持不变，不重复写入，也不在卸载时删除。
- 候选 `.bashrc` 使用 `bash -n` 校验。安装器不 `source` 文件，也不尝试改变父进程环境。

## 计划、冲突与迁移

每个配置目标产生 `unchanged`、`create`、`update`、`remove`、`restore` 或 `conflict` 计划项。输出只能展示配置类型、动作和安全路径，不能显示通知字段值或任意旧命令的完整参数。

- 交互安装逐项确认冲突替换；拒绝任一冲突时不执行任何写入。
- 非交互安装遇到冲突直接失败。
- 状态清单中存在不同 `repo_path` 时视为迁移：交互模式要求确认，非交互模式要求 `--migrate`。
- 迁移统一更新 notify、hook 和 shim 的绝对路径，不读取或复制旧仓库 `.env`。
- 每个用户只维护一个激活状态清单。

## 事务与状态模型

安装器先计算完整计划，再创建事务：

1. 对即将修改的现有文件和链接保存权限受控的快照，并记录原始存在性、模式和摘要。
2. 在目标同目录创建临时文件，设置目标权限、刷新并原子替换。
3. 文件级候选先完成 TOML、JSON 或 Bash 校验。
4. 任一步失败，按逆序恢复本次快照并移除本次新建项。
5. 全部目标成功后，最后原子写入状态清单，事务才算提交。

状态清单使用版本化 JSON schema，记录激活仓库、受管目标、当前受管值摘要、原始快照引用和最新成功事务，不嵌入 `.env` 值或旧配置正文。重复安装保留首次接管前的恢复基线，不能把已经受管的值覆盖成新的“原始值”。

## 检查与卸载

`check` 静态检查：

- Linux、Bash、Python 3.10+、真实 Codex 与版本。
- `.env` 权限、启用渠道名称和必填字段完整性，只输出字段名与状态。
- `notify`、`log_dir`、PermissionRequest handler、shim 目标、wrapper 可执行权限。
- Bash 受管区块或已生效的等价 PATH，并用新 Bash 解析 `codex` 首个入口。
- 状态清单 schema、激活仓库与受管值摘要。

hook 信任仅输出后续 `/hooks` 提示，不检查内部哈希，也不影响成功状态。`check` 不读取 Codex TUI 日志、不发送通知。

`uninstall` 根据状态清单生成逆向计划。当前值仍等于受管值时恢复首次安装前的键、handler、链接或受管区块；当前值已变化时标记冲突并保留。无冲突项完成后更新状态；存在保留冲突时返回 `1`。`.env`、普通备份和未标记的外部 PATH 配置默认保留。

## 安全与故障边界

- 安装输出、异常和测试夹具不得包含真实 webhook、签名密钥、SMTP 密码或收件人。
- 不用 shell 字符串拼接执行 Codex 或 Python；子进程一律使用参数列表。
- 不绕过 hook trust，不修改审批策略，不使用 root 权限。
- 备份和状态目录拒绝宽松权限；符号链接目标在修改前解析并验证。
- 通知测试必须由用户明确确认，`dry-run`、`check` 和非交互安装永不联网。

## 测试策略

- 所有文件变更测试使用临时 HOME、临时 `CODEX_HOME`、fake Codex 和 fake 输入，不访问真实用户配置。
- 覆盖全新安装、重复安装、修复、交互冲突拒绝/接受、非交互冲突、迁移授权、dry-run、事务中途失败与回滚。
- 覆盖已有 JSON hook 并存、非法 JSON、TOML 复杂目标键拒绝、Bash 受管区块和未标记等价配置。
- 覆盖 `.env` 注释与未知键保留、多个渠道、缺字段、敏感输入不回显、不输出值、权限 `0600`。
- 覆盖卸载恢复、安装后用户修改冲突、状态清单损坏和无状态卸载。
- 网络测试只注入 fake `CHANNEL_HANDLERS`；真实 webhook、SMTP、Codex 会话和用户日志均禁止访问。

## 兼容与取舍

- 保持 Python 3.10+ 和纯标准库；不引入通用 TOML 写入依赖，因此只管理两个已知顶层键，并对复杂写法安全失败。
- MVP 只支持 Linux + Bash 与 Codex；Claude Code、Kimi、macOS、Windows、Zsh、Fish 留待独立任务。
- hook 信任属于 Codex 用户交互边界；脚本只提示，不尝试把人工安全决策自动化。
