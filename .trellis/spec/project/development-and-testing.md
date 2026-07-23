# 开发与测试命令

## 运行环境

- 使用 Python 3，当前代码仅依赖标准库。
- `codex-wrapper.py` 使用 `dict | None`，`notify.py` 使用 `list[str]`，因此实际语法基线至少是 Python 3.10；不要沿用 README 中过时的 Python 3.6 说法。
- 仓库没有 `requirements.txt`、`pyproject.toml` 或虚拟环境约定，运行测试前无需安装第三方包。

## 常用命令

从项目根目录执行：

```bash
# 完整标准库单元测试
python3 -m unittest test_setup_config.py test_codex_wrapper.py test_notify.py test_codex_hook.py

# 只验证通知渠道配置和调度
python3 -m unittest test_notify.py

# 语法检查
python3 -m py_compile setup_config.py codex-wrapper.py codex-hook.py notify.py test_setup_config.py test_codex_wrapper.py test_codex_hook.py test_notify.py
bash -n setup.sh

# 验证 wrapper 能找到并透传真实 Codex
python3 codex-wrapper.py --version
```

这些命令由 `AGENTS.md` 和现有测试文件共同定义。项目当前没有正式的 lint、格式化、覆盖率或构建命令，不要把未配置的 Ruff、Black、pytest、mypy 等工具写成强制门禁。

## 测试约定

- 使用标准库 `unittest`，测试类继承 `unittest.TestCase`，测试方法以 `test_` 开头。
- 测试必须隔离外部副作用：不访问真实 webhook、SMTP、用户日志或真实 Codex 会话。
- 可变全局注册表需要在测试后恢复。`NotifyDispatchTest.setUp`/`tearDown` 会备份并恢复 `notify.CHANNEL_HANDLERS`。
- 临时可执行文件和目录使用 `tempfile.TemporaryDirectory`，见 `test_codex_wrapper.py`。
- 需要断言错误输出时使用 `redirect_stderr(StringIO())`，不要让预期异常污染测试输出。
- 多渠道行为应同时验证调用顺序、结果字典以及单渠道异常不会阻断后续渠道。

## 手工验证边界

- `python3 codex-wrapper.py --version` 会启动真实 Codex 的版本命令，但不应发送通知。
- 直接运行 `notify.py` 且使用真实 `.env` 可能发送 webhook 或邮件；除非明确进行集成验证，否则不要把它作为常规检查命令。
- 改动日志解析时，优先为 `parse_question_toolcall`、`parse_upstream_failure` 增加纯字符串测试，不读取真实用户日志。
- 改动审批 hook 时，使用 `test_codex_hook.py` 的注入式启动器验证退出码、stderr 和无 stdout 行为，不制造真实审批或通知。
