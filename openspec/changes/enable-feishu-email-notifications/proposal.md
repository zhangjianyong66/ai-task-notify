## Why

当前项目已经具备飞书和邮件通知通道，但缺少明确的变更契约来约束“同时通知邮箱和飞书”的配置、行为和验证方式。需要把多渠道通知作为可测试能力沉淀下来，避免后续调整时破坏并行发送语义。

## What Changes

- 明确支持通过 `NOTIFY_CHANNELS=feishu,email` 同时启用飞书和邮件通知。
- 明确多渠道发送时应逐个尝试所有已启用渠道，单个渠道失败不应阻止其他渠道发送。
- 补充邮件与飞书同时启用所需配置项和验证方式。
- 增加针对多渠道调度行为的测试覆盖。

## Capabilities

### New Capabilities

- `multi-channel-notifications`: 定义通知脚本同时启用多个渠道时的配置、发送和失败隔离行为。

### Modified Capabilities

- 无。

## Impact

- 影响 `notify.py` 的通知渠道配置解析、调度行为或相关测试覆盖。
- 影响 `.env.example`、`README.md` 等配置文档中关于飞书和邮件同时启用的说明。
- 不引入新的第三方依赖，不改变现有命令行入口。
