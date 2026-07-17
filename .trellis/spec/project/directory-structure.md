# 目录结构

## 当前结构

```text
ai-task-notify/
├── notify.py                 # 通知入口、渠道实现、消息格式化与输入解析
├── codex-hook.py             # Codex PermissionRequest hook 适配器
├── codex-wrapper.py          # Codex CLI 包装器和 TUI 日志监听
├── test_notify.py            # 通知配置与多渠道调度测试
├── test_codex_hook.py        # Codex hook 转换与无阻断行为测试
├── test_codex_wrapper.py     # wrapper 路径发现和配置测试
├── .env.example              # 可提交的通知配置字段模板
├── .env                      # 本机私密配置，已由 .gitignore 忽略
├── README.md                 # 面向使用者的通用安装和渠道说明
├── AGENTS.md                 # 当前机器运行约定与 AI 项目说明
├── Aigialosauridae/          # 历史/发布压缩包，不参与 Python 运行时
├── .trellis/                 # Trellis 工作流、任务、规范与会话数据
├── .agents/                  # 项目级 AI 技能
└── .codex/                   # 项目级 Codex 配置、hook 和代理定义
```

## 文件职责

- `notify.py` 是通知业务的唯一运行入口。配置加载、HTTP/SMTP 发送、渠道注册、消息格式化和 CLI/stdin 输入解析都在此文件中。
- `codex-hook.py` 只负责把 `PermissionRequest` stdin JSON 转换为受控审批事件并后台启动 `notify.py`，不得返回审批决定。
- `codex-wrapper.py` 只负责查找并启动真实 Codex、监听 `~/.codex/log/codex-tui.log`、解析提问和最终失败事件，再调用 `notify.py`。不要把具体渠道发送逻辑复制到 hook 或 wrapper。
- 测试与被测脚本同处根目录，命名为 `test_<模块>.py`。两个 Codex 脚本文件名包含连字符，因此测试通过 `importlib.util.spec_from_file_location` 加载。
- `.env.example` 只列配置键和无敏感值示例；真实 `.env` 不提交。
- `.trellis/`、`.agents/` 和 `.codex/` 是研发流程与工具配置，不是通知脚本的运行依赖。

## 新文件放置规则

- 当前项目规模下，通知入口和 wrapper 继续放在根目录，不创建虚构的 `frontend/`、`backend/`、`database/` 或 `src/` 层。
- 为现有脚本补测试时，继续使用根目录 `test_*.py`。
- 新增通知渠道通常直接扩展 `notify.py`、`.env.example` 和 `test_notify.py`；只有出现可独立复用且职责明确的模块时才拆文件。
- 发布压缩包只放入 `Aigialosauridae/`；不得从压缩包导入代码，也不得把其中二进制视为测试或运行依赖。
- 项目工作流知识写入 `.trellis/spec/project/`；机器特定且下次会复用的运行约定同步维护在根目录 `AGENTS.md`。

## 不适用的结构

项目目前没有包管理清单、第三方依赖文件、数据库迁移、Web 路由、前端组件、Dockerfile、systemd 单元或 CI 配置。规范不得假设这些设施存在。
