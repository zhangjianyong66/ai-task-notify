import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import notify


class NotifyChannelConfigTest(unittest.TestCase):
    def test_feishu_and_email_channels_are_enabled_together(self):
        env = {"NOTIFY_CHANNELS": "feishu,email"}

        self.assertEqual(notify.get_enabled_channels(env), ["feishu", "email"])

    def test_channel_list_accepts_surrounding_whitespace(self):
        env = {"NOTIFY_CHANNELS": "feishu, email"}

        self.assertEqual(notify.get_enabled_channels(env), ["feishu", "email"])


class NotifyDispatchTest(unittest.TestCase):
    def setUp(self):
        self.original_handlers = notify.CHANNEL_HANDLERS.copy()

    def tearDown(self):
        notify.CHANNEL_HANDLERS.clear()
        notify.CHANNEL_HANDLERS.update(self.original_handlers)

    def test_send_notification_attempts_feishu_and_email(self):
        calls = []

        def handler(channel):
            def send(env, title, content):
                calls.append((channel, title, content))
                return True

            return send

        notify.CHANNEL_HANDLERS.clear()
        notify.CHANNEL_HANDLERS.update({
            "feishu": handler("feishu"),
            "email": handler("email"),
        })

        results = notify.send_notification(
            {"NOTIFY_CHANNELS": "feishu,email"},
            "测试标题",
            "测试内容",
        )

        self.assertEqual([call[0] for call in calls], ["feishu", "email"])
        self.assertEqual(results, {"feishu": True, "email": True})

    def test_channel_exception_does_not_stop_later_channel(self):
        calls = []

        def failing_handler(env, title, content):
            calls.append("feishu")
            raise RuntimeError("boom")

        def succeeding_handler(env, title, content):
            calls.append("email")
            return True

        notify.CHANNEL_HANDLERS.clear()
        notify.CHANNEL_HANDLERS.update({
            "feishu": failing_handler,
            "email": succeeding_handler,
        })

        with redirect_stderr(StringIO()):
            results = notify.send_notification(
                {"NOTIFY_CHANNELS": "feishu,email"},
                "测试标题",
                "测试内容",
            )

        self.assertEqual(calls, ["feishu", "email"])
        self.assertEqual(results, {"feishu": False, "email": True})

    def test_failed_channel_result_preserves_successful_channel(self):
        notify.CHANNEL_HANDLERS.clear()
        notify.CHANNEL_HANDLERS.update({
            "feishu": lambda env, title, content: True,
            "email": lambda env, title, content: False,
        })

        results = notify.send_notification(
            {"NOTIFY_CHANNELS": "feishu,email"},
            "测试标题",
            "测试内容",
        )

        self.assertEqual(results, {"feishu": True, "email": False})


class NotifyFormattingTest(unittest.TestCase):
    def test_codex_completion_uses_structured_fields(self):
        title, content = notify.format_message(
            "codex",
            "agent-turn-complete",
            {
                "thread-id": "thread-1",
                "turn-id": "turn-1",
                "cwd": "/workspace",
                "input-messages": ["请修复测试"],
                "last-assistant-message": "测试已修复",
            },
        )

        self.assertIn("Codex 任务完成", title)
        self.assertIn("thread-1", content)
        self.assertIn("turn-1", content)
        self.assertIn("请修复测试", content)
        self.assertIn("测试已修复", content)
        self.assertNotIn("原始数据", content)

    def test_codex_hook_approval_handles_missing_description(self):
        title, content = notify.format_message(
            "codex-hook",
            "approval-required",
            {
                "session_id": "session-1",
                "turn_id": "turn-1",
                "cwd": "/workspace",
                "tool_name": "mcp__server__write",
                "command": "",
                "tool_input_summary": "参数字段: path",
            },
        )

        self.assertIn("需要提权审批", title)
        self.assertIn("mcp__server__write", content)
        self.assertIn("参数字段: path", content)
        self.assertNotIn("原始数据", content)

    def test_upstream_failure_formats_safe_summary(self):
        _, content = notify.format_message(
            "codex-wrapper",
            "upstream-response-failed",
            {
                "error_category": "rate-limit",
                "http_status": 429,
                "retry_exhausted": True,
                "summary": "rate limit exceeded",
            },
        )

        self.assertIn("限流或额度不足", content)
        self.assertIn("429", content)
        self.assertIn("重试耗尽**: 是", content)


class NotifySecurityTest(unittest.TestCase):
    def test_sanitize_error_summary_redacts_credentials_and_url_query(self):
        summary = notify.sanitize_error_summary(
            "Authorization: Bearer top-secret-token api_key=sk-123456789012345678901234 "
            'password="two words secret" '
            "url=https://api.example.com/v1/responses?token=secret&trace=1"
        )

        self.assertNotIn("top-secret-token", summary)
        self.assertNotIn("sk-123456789012345678901234", summary)
        self.assertNotIn("two words secret", summary)
        self.assertNotIn("token=secret", summary)
        self.assertIn("[REDACTED]", summary)
        self.assertIn("https://api.example.com/v1/responses?[REDACTED]", summary)

    def test_sanitize_error_summary_redacts_suspicious_long_token(self):
        summary = notify.sanitize_error_summary(
            "provider returned abcdefghijklmnopqrstuvwxyz0123456789"
        )

        self.assertEqual(summary, "provider returned [REDACTED]")


class BackgroundNotificationTest(unittest.TestCase):
    def test_start_background_notification_detaches_process(self):
        with patch.object(notify.subprocess, "Popen") as popen:
            ok, error = notify.start_background_notification(
                {"source": "codex-wrapper", "type": "question-required"},
                Path("/tmp/notify.py"),
            )

        self.assertTrue(ok)
        self.assertEqual(error, "")
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], [notify.sys.executable, "/tmp/notify.py"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertIs(popen.call_args.kwargs["stdin"], notify.subprocess.DEVNULL)

    def test_start_background_notification_reports_launch_failure(self):
        with patch.object(notify.subprocess, "Popen", side_effect=OSError("boom")):
            ok, error = notify.start_background_notification({"type": "test"})

        self.assertFalse(ok)
        self.assertIn("boom", error)


if __name__ == "__main__":
    unittest.main()
