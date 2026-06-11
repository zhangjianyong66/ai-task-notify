import unittest
from contextlib import redirect_stderr
from io import StringIO

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


if __name__ == "__main__":
    unittest.main()
