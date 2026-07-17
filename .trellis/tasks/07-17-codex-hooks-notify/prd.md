# 优化 Codex 原生 Hooks 通知接入

## Goal

利用 Codex CLI 0.144.5 已稳定支持的生命周期 hooks，降低通知方案对 TUI 文本日志和正则解析的依赖，同时可靠保留任务完成、审批等待、结构化提问等待和上游接口最终失败告警。

用户价值是减少 Codex 升级后的静默失效风险，并继续复用企业微信、飞书、钉钉和邮件多渠道通知。

## Background

- 当前 npm 最新版和本机安装版均为 `@openai/codex 0.144.5`，`hooks` 状态为 Stable 且默认启用。
- `notify.py` 已支持四种通知渠道、多渠道顺序调度和单渠道失败隔离。
- Codex 官方 `notify` 当前只发送 `agent-turn-complete`，但载荷已包含 `thread-id`、`turn-id`、`cwd`、`input-messages` 和 `last-assistant-message`，并通过独立子进程启动。
- 官方 `PermissionRequest` hook 提供结构化审批事件；官方 hooks 没有等待内置 `request_user_input` 回答或上游模型请求失败的专用事件。
- `Stop` 只在正常停止路径执行，上游请求最终失败不会触发；command hook 本身是同步的。
- Codex app-server 有结构化失败事件，但实现完整 app-server 客户端超出本任务范围。
- Codex 0.144.5 的 `codex_core=info` 日志包含提问工具调用和最终 `Turn error: ...`，但该文本格式不是稳定 hook 协议。
- 新版 Codex 只有显式配置 `log_dir` 才创建 `codex-tui.log`；本机当前没有该文件，因此现有 wrapper 没有可靠日志输入。
- 本机 `~/.local/bin/codex` 是 0.144.5，`/usr/local/bin/codex` 是 0.137.0。
- 当前用户级 `approval_policy = "never"`，默认 profile 通常不会产生审批事件。
- 现有 8 个单元测试、语法检查和 wrapper 透传验证通过，但关键日志解析缺少直接测试。

## Requirements

### 事件来源

- 采用“官方事件优先、日志兼容补缺”的混合架构。
- 保留官方 `notify` 作为完成通知唯一入口，不使用 `Stop` 发送完成通知。
- 使用用户级全局 `PermissionRequest` hook 发送审批通知，删除 wrapper 的审批日志解析。
- wrapper 仅监听官方 hooks 尚未覆盖的结构化提问和上游最终失败。
- 不实现完整 Codex app-server 客户端。

### 上游失败告警

- 仅在重试耗尽、回复最终中断时通知；可恢复的中间重试不单独推送。
- 至少区分 HTTP/连接失败、响应流连接失败、响应流断开、重试耗尽、认证失败、限流/额度和其他上游错误。
- 通知保留可可靠提取的 HTTP 状态码、工作目录、线程/轮次标识、重试耗尽状态和最多约 300 字符摘要。
- 只发送脱敏摘要；不得发送完整响应体、完整提示词、模型上下文、请求头、认证信息或带查询参数的完整 URL。
- 同一 wrapper 进程内需要有界去重或节流，避免通知风暴。

### 执行与兼容

- 审批、提问和最终失败事件由 hook/wrapper 快速转换后，通过后台子进程异步调用 `notify.py`，不等待 webhook 或 SMTP。
- 不引入常驻服务、持久消息队列、数据库或第三方 Python 依赖；机器立即关闭时允许丢失尚未完成的通知。
- hook、日志和通知失败不得阻断 Codex、改变审批结果或改变真实 Codex 退出码。
- 正式兼容基线是 Codex CLI 0.144.5+；旧版仅尽力兼容，不维护旧日志格式分支。
- 日志长期不存在、不可读，或出现已知事件标记但无法解析时，wrapper 必须向 `stderr` 输出一次明确诊断并继续运行。
- 保持现有四种渠道、配置优先级、内容截断和失败隔离行为兼容。

### 部署

- 用户级全局 hook 覆盖当前机器所有项目和会产生 `PermissionRequest` 的 profile；项目现有 Trellis hooks 保持不变。
- 保持当前 `approval_policy = "never"`，不为验证永久修改审批策略。
- 用户级 Codex 配置显式设置 `log_dir`，为 wrapper 提供日志。
- 通过独立 PATH shim 目录让 wrapper 成为默认终端 `codex`，不得覆盖 npm 管理的 `~/.local/bin/codex`。
- 官方 `~/.local/bin/codex` 必须作为紧急绕过通道；0.137.0 的 `/usr/local/bin/codex` 不作为真实目标。
- 非托管 hook 需要通过 Codex `/hooks` 审核和信任。
- 其他机器不自动配置，需要按文档重复安装 hook、`log_dir` 和 shim。

### 文档与安全

- 文档说明 hooks 能力边界、配置位置、信任审核、shim、版本基线、验证和回滚。
- 新发现的本机运行约定同步更新根目录 `AGENTS.md` 和项目规范。
- 不读取、提交或在输出中展示真实 `.env`、webhook、SMTP 密码、模型供应商凭据或 MCP 密钥。

## Acceptance Criteria

- [ ] `agent-turn-complete` 只通过 `notify` 发送一次，并展示线程、轮次、目录、用户输入摘要和最后回复。
- [ ] `PermissionRequest` 使用用户级原生 hook 转换为审批通知，wrapper 不再解析审批日志。
- [ ] `request_user_input` 和 `AskUserQuestion` 的代表性日志顺序变化仍可解析，非法样本安全跳过并报警。
- [ ] `Turn error:` 最终失败可分类、提取可用状态并发送一次脱敏告警；中间重试不发送。
- [ ] Bearer Token、API key、URL 查询参数和疑似长密钥不会出现在格式化告警中。
- [ ] 异步通知启动失败可诊断，但不会阻断 hook、wrapper 或真实 Codex。
- [ ] 日志缺失、不可读和已知标记解析失败都有一次性诊断，不会轮询刷屏。
- [ ] 用户级 `PermissionRequest` hook、显式 `log_dir` 和独立 PATH shim 可验证，官方 `~/.local/bin/codex` 仍可绕过。
- [ ] 新增解析、格式化、脱敏、hook 和异步启动测试，不访问真实 webhook、SMTP、Codex 会话或用户日志。
- [ ] 完整单元测试、语法检查、wrapper 版本透传、shim 路径和 `git diff --check` 全部通过。
- [ ] `README.md`、相关项目规范和 `AGENTS.md` 与最终实现一致，且不包含真实凭据。

## Out of Scope

- 新增通知渠道。
- 完整 Codex app-server 客户端。
- 通用策略、审计或可观测平台。
- 常驻通知服务或持久队列。
- 修改模型供应商、模型选择、无关 MCP 配置或当前审批策略。
- 为 0.144.5 之前的 Codex 维护专用 hooks/日志兼容实现。
- 自动配置其他机器或自动信任非托管 hook。
