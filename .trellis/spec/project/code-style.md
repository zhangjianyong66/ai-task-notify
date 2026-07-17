# 代码风格

## Python 风格

- 使用 4 空格缩进、`snake_case` 函数和变量名、`UPPER_SNAKE_CASE` 模块常量、`PascalCase` 测试类名。
- 脚本保留 `#!/usr/bin/env python3`，入口函数返回整数退出码，并由 `sys.exit(main())` 退出；参考两个业务脚本的末尾。
- 路径处理优先使用 `pathlib.Path`，用户路径配置调用 `expanduser()`，需要身份比较时调用 `resolve()`。
- 新代码按 Python 3.10+ 语法编写。类型标注保持与邻近代码一致，可使用 `dict | None`、`list[str]`；无需为了统一而机械重写现有 `Optional[...]`。
- 简短函数 docstring 可使用中文或英文，但应准确说明输入、输出或运行角色；不要添加与行为无关的长篇注释。

## 结构与职责

- 配置读取集中在 `load_env`、`get_config` 和 wrapper 的 `get_*` 路径函数中。不要在各渠道或解析函数中重复读取环境变量。
- 通知渠道实现保持统一签名 `(env, title, content) -> bool`，通过 `CHANNEL_HANDLERS` 注册，由 `send_notification` 调度。
- 原始事件在 `parse_input` 或 wrapper 的解析函数中转换为字典，展示文本集中由 `format_message` 生成。
- 网络、SMTP、子进程和文件日志监听属于边界副作用；解析、截断、签名和格式化函数应尽量保持可独立测试。
- wrapper 必须透明传递真实 Codex 的命令行参数和环境，并返回真实 Codex 的退出码。

## 错误处理与输出

- 单个通知渠道失败时返回 `False` 或由调度层捕获异常，不能阻止其他已启用渠道继续发送；参考 `send_notification`。
- 可恢复的网络或日志错误写入 `stderr`，正常发送汇总写入 `stdout`。
- HTTP 边界返回 `(status, body)`；HTTPError 保留响应状态和正文，其他异常使用状态 `0` 表示没有有效 HTTP 状态。
- 解析未知或无效事件时返回 `None`/空数据并由入口决定跳过或失败，不在底层解析函数中退出进程。
- 子进程通知调用使用参数列表，不拼接 shell 命令；通知失败不能中断真实 Codex。

## 测试代码风格

- 测试名称描述可观察行为，例如 `test_channel_exception_does_not_stop_later_channel`。
- 使用局部 fake handler、临时目录和显式环境字典控制输入，不依赖开发机状态。
- 对包含连字符的脚本沿用 `importlib.util` 加载方式，不重命名业务文件来迁就导入。

## 避免的模式

- 不在源码、测试、README、规范或日志中写入真实 webhook、签名密钥、SMTP 密码。
- 不让测试发起真实网络请求或发送真实邮件。
- 不在 wrapper 中复制企业微信、飞书、钉钉或邮件发送实现。
- 不用宽泛异常吞掉所有渠道结果；失败必须保留为对应渠道的 `False`，必要时写入 `stderr`。
- 不引入第三方依赖来替代已有简单标准库实现，除非任务明确要求并同步补充依赖管理方式。
