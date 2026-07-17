# AI Task Notify 项目规范

本目录是当前单包 Python 项目的开发规范入口。项目没有前端、数据库、Web 服务或独立构建层，不按通用全栈模板拆分规范。

## 规范索引

| 文档 | 内容 |
| --- | --- |
| [目录结构](./directory-structure.md) | 根目录文件职责、配置与流程目录边界 |
| [开发与测试命令](./development-and-testing.md) | 运行环境、验证命令和测试约定 |
| [代码风格](./code-style.md) | Python 命名、结构、错误处理和测试风格 |
| [部署方式](./deployment.md) | 本地脚本部署、通知配置和 Codex wrapper 接入 |
| [重要约定](./important-conventions.md) | 配置优先级、事件协议、渠道扩展和兼容性约束 |

## 开发前检查

- 确认改动属于 `notify.py`、`codex-wrapper.py`、测试、配置示例或文档中的哪一类。
- 修改通知渠道前，先阅读 [重要约定](./important-conventions.md) 中的渠道注册和失败隔离规则。
- 修改 Codex 日志解析或进程包装前，先阅读 [部署方式](./deployment.md) 和 wrapper 兼容性约定。
- 不读取、提交或在输出中展示真实 `.env` 内容；配置字段以 `.env.example` 为准。
- 先检查 `git status --short`，保留用户已有的未提交改动。

## 质量检查

- 执行 `python3 -m unittest test_codex_wrapper.py test_notify.py`。
- 执行 `python3 -m py_compile codex-wrapper.py notify.py test_codex_wrapper.py test_notify.py`。
- wrapper 相关改动额外执行 `python3 codex-wrapper.py --version`。
- 确认测试不访问真实 webhook、SMTP 或用户的 Codex 日志。
- 确认 `.env`、凭据、真实 webhook 和邮箱密码未进入版本控制。

参考证据：`notify.py`、`codex-wrapper.py`、`test_notify.py`、`test_codex_wrapper.py`、`.env.example`、`AGENTS.md`。
