# Codex 原生 Hooks 通知接入实施计划

## 1. 完善通知事件模型

- [ ] 在 `notify.py` 增加错误摘要脱敏与截断纯函数。
- [ ] 改进 `agent-turn-complete` 格式，展示线程、轮次、目录、用户输入摘要和最后回复。
- [ ] 增加 `codex-hook/approval-required` 与 `codex-wrapper/upstream-response-failed` 格式。
- [ ] 增加后台启动 `notify.py` 的标准库辅助函数，启动失败返回可诊断结果。

## 2. 接入 PermissionRequest hook

- [ ] 新增 `codex-hook.py`，读取 stdin JSON，只接受 `PermissionRequest`。
- [ ] 将 hook 字段转换为内部审批事件，并异步调用 `notify.py`。
- [ ] 对无效 JSON、非目标事件和缺失字段安全跳过，不输出会破坏 hook 协议的 stdout。
- [ ] 提供无机器密钥的用户级 hook 示例配置。

## 3. 精简并增强 wrapper

- [ ] 删除审批日志解析和相关分支，审批只走原生 hook。
- [ ] 重写提问工具解析，使 `thread_id` 字段顺序变化不影响 JSON 提取。
- [ ] 增加 `Turn error:` 最终失败解析、错误分类、HTTP 状态提取和脱敏。
- [ ] 忽略可恢复重试日志，只对最终失败发送一次告警。
- [ ] 将通知调用改为后台异步启动，避免阻塞日志监听。
- [ ] 将去重缓存改为有界结构，覆盖提问和失败事件。
- [ ] 增加日志不存在、不可读和已知标记无法解析时的一次性诊断。
- [ ] 保持真实 Codex 参数、环境和退出码透明透传。

## 4. 增加测试

- [ ] 为 Codex 完成、审批、提问和上游失败消息格式增加测试。
- [ ] 为 Bearer、API key、URL 查询参数和长密钥脱敏增加测试。
- [ ] 为 hook stdin 合法/非法/非目标事件转换增加测试。
- [ ] 为提问日志字段前后顺序、无效 JSON和空问题增加解析测试。
- [ ] 为最终失败类别、HTTP 状态、忽略中间重试和去重键增加测试。
- [ ] 为异步子进程启动使用 mock，禁止真实网络和真实 Codex 会话。

## 5. 更新文档与项目知识

- [ ] 更新 `README.md` 的 Codex 0.144.5+ 架构、配置示例、hook 信任、shim、绕过和回滚说明。
- [ ] 更新 `.trellis/spec/project/` 中的部署、事件协议、wrapper 兼容和测试约定。
- [ ] 更新根目录 `AGENTS.md`，记录显式 `log_dir`、用户级 hook、默认 shim、真实 Codex 路径和验证命令。
- [ ] 检查 `.env.example`；仅在出现新环境变量时修改。

## 6. 配置当前机器

- [ ] 在 `~/.codex/config.toml` 增加显式 `log_dir`，保持 `notify` 和 `approval_policy = "never"` 不变。
- [ ] 创建或合并 `~/.codex/hooks.json` 的全局 `PermissionRequest` hook，不覆盖其他用户 hook。
- [ ] 创建 `~/.local/codex-wrapper-bin/codex` shim，不覆盖 npm 管理的官方入口。
- [ ] 在 Bash 启动配置中将 shim 目录置于 PATH 前部，保持重复执行幂等。
- [ ] 提醒用户进入 Codex `/hooks` 审核并信任新增 hook；在 `never` 策略下不强制制造真实审批。

## 7. 验证门禁

- [ ] `python3 -m unittest test_codex_wrapper.py test_notify.py test_codex_hook.py`
- [ ] `python3 -m py_compile codex-wrapper.py codex-hook.py notify.py test_codex_wrapper.py test_codex_hook.py test_notify.py`
- [ ] `python3 codex-wrapper.py --version` 返回 `codex-cli 0.144.5`。
- [ ] 新 shell 中 `command -v codex` 指向独立 shim，`~/.local/bin/codex --version` 仍可直接运行。
- [ ] 启动一次 wrapper Codex 后确认显式日志创建；不读取或展示真实敏感日志内容。
- [ ] 使用隔离 JSON 样本验证审批、提问、失败事件只启动一次通知，不发送真实 webhook/邮件。
- [ ] `git diff --check` 通过，工作区不包含 `.env`、凭据或生成缓存。

## 风险与回滚点

- 日志格式变化：解析器只匹配明确标记，失败时报警并继续 Codex；回滚为直接使用官方入口。
- hook 未信任：`/hooks` 审核前审批通知不运行，但完成通知和 wrapper 仍可工作。
- shim 路径失效：直接运行 `~/.local/bin/codex`，修复 PATH 或项目绝对路径。
- 通知网络超时：异步子进程隔离，不能拖慢 Codex；无持久队列意味着关机时允许丢失通知。
