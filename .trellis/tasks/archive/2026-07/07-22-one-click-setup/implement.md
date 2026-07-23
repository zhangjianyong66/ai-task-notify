# Codex 一键配置实施计划

## 1. 建立统一命令入口

- [x] 新增可执行 `setup.sh`，解析自身目录、检查 `python3` 并把全部参数交给 `setup_config.py`。
- [x] 新增 `setup_config.py` 的 `argparse` 入口，实现 `install`、`check`、`uninstall` 及合法选项组合和退出码。
- [x] 集中实现路径解析，支持 `HOME`、`CODEX_HOME`、`XDG_STATE_HOME` 的隔离测试覆盖。

## 2. 实现发现、校验与变更计划

- [x] 定义通知渠道必填字段、敏感字段和 `.env` 安全状态模型，复用 `notify.py` 的配置优先级。
- [x] 实现真实 Codex 查找、wrapper 排除、版本解析与 `0.144.5+` 校验，不执行安装或更新。
- [x] 为 TOML 顶层键、hooks JSON、shim、Bash 受管区块和安装状态实现只读检查器。
- [x] 建立确定性的计划项模型，先汇总全部 `unchanged/create/update/remove/restore/conflict` 再产生副作用。
- [x] 实现脱敏计划输出；输出只包含动作、字段名和安全路径。

## 3. 实现交互式渠道配置

- [x] 已有有效 `.env` 默认复用；提供显式重新配置选择。
- [x] 支持多渠道选择、普通输入与 `getpass` 敏感输入，回车保留已有敏感值。
- [x] 以行级已知键编辑保留注释、未知键和未启用渠道凭据，并把 `.env` 权限设为 `0600`。
- [x] 实现 `--non-interactive` 的完整性检查，缺字段时只输出字段名并在写入前失败。
- [x] 实现可注入的测试通知调用；只有交互确认后发送，逐渠道报告，失败不回滚本地配置。

## 4. 实现 Codex 与 shell 配置适配器

- [x] 实现 `config.toml` 顶层 `notify`、`log_dir` 的受限保留式编辑；拒绝不支持的复杂目标键。
- [x] 使用隔离 `CODEX_HOME` 和真实 Codex `--strict-config --version` 校验 TOML 候选。
- [x] 使用标准库 JSON 合并 `PermissionRequest` handler，保持其他 hook 语义并防止重复。
- [x] 创建或更新 wrapper shim，保留并报告真实 Codex 绕过入口。
- [x] 管理唯一 Bash PATH 标记区块，识别并保留未标记的等价现有配置，候选执行 `bash -n`。
- [x] 修改 `codex-wrapper.py` 的默认日志路径以识别 `CODEX_HOME`，保留显式 wrapper 环境变量最高优先级。

## 5. 实现事务、状态与迁移

- [x] 在 XDG 状态目录实现 schema 版本化 `install-state.json`，目录 `0700`、文件 `0600`，不保存通知凭据。
- [x] 实现时间戳备份、同目录临时文件、权限设置、刷新和原子替换。
- [x] 实现计划执行失败时的逆序回滚，包括文件、权限、符号链接和本次新建项。
- [x] 保留首次接管前的恢复基线，使重复安装不会改变卸载目标。
- [x] 实现单激活副本检查、交互迁移确认和非交互 `--migrate` 授权，不迁移 `.env`。
- [x] 实现 `install/uninstall --dry-run`，断言不创建状态、备份、临时文件或外部通知。

## 6. 实现检查与卸载

- [x] `check` 覆盖运行环境、通知配置、Codex 配置、hook、shim、PATH、权限和状态清单，保持只读且无网络。
- [x] hook trust 只输出 `/hooks` 后续提示，不读取或写入 Codex 内部信任状态，不影响成功退出码。
- [x] `uninstall` 先生成逆向计划；交互模式默认拒绝，非交互模式视为授权。
- [x] 当前值仍受管时恢复首次安装前状态；安装后被修改的项报告冲突并保留。
- [x] 默认保留 `.env`、备份和外部未标记 PATH；有冲突时完成安全项后返回非零并保留可重试状态。

## 7. 增加测试

- [x] 新增 `test_setup_config.py`，使用临时 HOME、fake Codex、fake 输入和 mock 渠道隔离所有副作用。
- [x] 覆盖新装、幂等重装、修复、冲突、迁移、dry-run、版本不足、非法配置和候选校验失败。
- [x] 覆盖事务中每类写入失败后的完整回滚、备份与状态权限以及首次基线保持。
- [x] 覆盖 `.env` 注释/未知键保留、多渠道必填字段、敏感输入与输出脱敏。
- [x] 覆盖 hooks 并存、TOML 受限编辑、Bash 区块、未标记等价 PATH、shim 冲突与真实入口排除。
- [x] 覆盖卸载恢复和用户后改冲突；测试通知只使用 fake handler。
- [x] 扩展 `test_codex_wrapper.py`，验证 `CODEX_WRAPPER_LOG_PATH > CODEX_HOME > HOME` 的路径优先级。

## 8. 更新文档与项目知识

- [x] README 将 `./setup.sh install` 作为 Codex 推荐安装入口，记录三个子命令、dry-run、无人值守、迁移、人工 `/hooks` 审核和故障绕过。
- [x] 更新 `.trellis/spec/project/` 的目录结构、开发测试、部署和一键配置安全约定。
- [x] 更新根目录 `AGENTS.md` 的安装、检查、卸载、状态目录与验证命令；同步当前 Codex 版本事实。
- [x] `.env.example` 只有在配置键变化时修改，不写入真实值。

## 9. 验证门禁

- [x] `python3 -m unittest test_setup_config.py test_codex_wrapper.py test_notify.py test_codex_hook.py`
- [x] `python3 -m py_compile setup_config.py codex-wrapper.py codex-hook.py notify.py test_setup_config.py test_codex_wrapper.py test_codex_hook.py test_notify.py`
- [x] `bash -n setup.sh`
- [x] 在临时 HOME 中执行 fake Codex 的 `install`、重复 `install`、`check`、`uninstall` 全流程，确认不触碰真实用户配置。
- [x] 在当前机器先运行 `./setup.sh install --dry-run` 和 `./setup.sh check`，不发送真实通知；实际迁移现有配置前再次审阅计划。
- [x] `python3 codex-wrapper.py --version` 能透传真实 Codex 版本。
- [x] `git diff --check` 通过，`git status --short` 不包含 `.env`、凭据、备份、状态清单或缓存。

## 风险与回滚点

- TOML 目标键使用复杂写法：安全拒绝并保留原文件，不退化为整文件重写。
- 用户配置在安装计划生成后并发变化：应用前核对摘要，不一致则中止并回滚。
- hook JSON 格式被规范化：语义保留，变更前备份，卸载按受管节点恢复而非整文件覆盖。
- 仓库移动或删除：状态清单保留激活路径；从新路径使用迁移流程修复，不复制旧凭据。
- 可选通知测试失败：保留已提交的本地安装，返回非零并报告失败渠道。
- 当前机器已有未标记 PATH 配置：识别为外部等价配置，不接管、不重复追加，卸载也不删除。
