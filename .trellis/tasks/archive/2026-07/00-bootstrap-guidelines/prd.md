# 补全项目开发规范

## 目标

基于仓库当前源码、测试、配置和运行方式，建立可供后续 AI 开发任务直接使用的 Trellis 项目规范，避免沿用不适用于本项目的通用全栈模板。

## 已确认的项目事实

- 项目是单仓库、单包 Python 脚本项目，没有前端、数据库、Web 服务或独立构建层。
- 核心运行文件是 `notify.py` 和 `codex-wrapper.py`。
- 测试使用 Python 标准库 `unittest`，位于根目录的 `test_notify.py` 和 `test_codex_wrapper.py`。
- 通知配置来自进程环境变量和脚本目录下的 `.env`，可提交字段模板位于 `.env.example`。
- 本机部署依赖 Codex 用户配置、可选 wrapper 和固定脚本路径，相关约定记录在 `AGENTS.md`。

## 规范范围

项目规范统一放在 `.trellis/spec/project/`，不创建虚构的 backend/frontend 分层：

- `index.md`：规范入口、开发前检查和质量检查。
- `directory-structure.md`：目录与文件职责、新文件放置规则。
- `development-and-testing.md`：Python 基线、测试命令和副作用隔离。
- `code-style.md`：Python 风格、职责边界、错误处理和测试风格。
- `deployment.md`：通知配置、Codex 原生通知、wrapper 和本机部署方式。
- `important-conventions.md`：配置优先级、通知渠道契约、事件协议和兼容性约束。

## 编写要求

- 规范必须来自真实源码、测试、配置或项目文档，不写通用占位建议。
- 每个重要约定应给出对应文件、函数、测试或运行配置作为证据。
- 明确记录不适用的模板层和应避免的反模式。
- `index.md` 必须与最终规范文件集合一致。
- 新发现且可复用的目录、环境、部署和运行约定同步维护到根目录 `AGENTS.md`。

## 验收标准

- [x] `.trellis/spec/project/` 覆盖目录结构、开发测试、代码风格、部署和重要约定。
- [x] 规范包含来自 `notify.py`、`codex-wrapper.py`、测试、`.env.example` 和 `AGENTS.md` 的真实示例或路径引用。
- [x] 已移除不适用于本项目的 backend/frontend/database 模板假设。
- [x] 规范中没有占位文本或待补充章节。
- [x] `index.md` 中的规范链接全部有效。
- [x] `python3 -m unittest test_codex_wrapper.py test_notify.py` 通过。
- [x] `python3 -m py_compile codex-wrapper.py notify.py test_codex_wrapper.py test_notify.py` 通过。

## 完成记录

项目规范已随提交 `2e14481` 写入。本次收尾重新核对了规范内容、索引链接和项目验证命令，满足归档条件。
