## 1. 测试覆盖

- [x] 1.1 为 `notify.py` 增加单元测试，验证 `NOTIFY_CHANNELS=feishu,email` 会解析出两个启用渠道
- [x] 1.2 为多渠道调度增加单元测试，验证飞书和邮件处理器都会被调用
- [x] 1.3 增加失败隔离测试，验证单个渠道异常或失败时其他渠道仍会被尝试

## 2. 实现检查与修正

- [x] 2.1 检查 `send_notification` 是否满足所有已启用已知渠道都会被尝试的要求
- [x] 2.2 如测试发现缺口，最小范围修正 `notify.py` 的渠道解析或调度逻辑

## 3. 配置文档

- [x] 3.1 更新 `.env.example`，加入 `NOTIFY_CHANNELS=feishu,email` 的组合示例
- [x] 3.2 更新 README，说明同时启用飞书和邮件所需的 Feishu webhook、SMTP、发件人和收件人配置

## 4. 验证

- [x] 4.1 运行 `python3 -m unittest test_codex_wrapper.py` 和新增通知测试
- [x] 4.2 运行 `python3 -m py_compile codex-wrapper.py notify.py test_codex_wrapper.py` 及新增测试文件的语法检查
- [x] 4.3 检查 `openspec status --change "enable-feishu-email-notifications"` 确认变更 artifact 完整
