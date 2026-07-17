import importlib.util
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("codex-wrapper.py")
SPEC = importlib.util.spec_from_file_location("codex_wrapper", MODULE_PATH)
codex_wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_wrapper)


class CodexWrapperConfigTest(unittest.TestCase):
    def test_default_paths_are_relative_to_user_and_project(self):
        env = {"HOME": "/home/example"}

        self.assertEqual(
            codex_wrapper.get_log_path(env),
            Path("/home/example/.codex/log/codex-tui.log"),
        )
        self.assertEqual(
            codex_wrapper.get_notify_script(env),
            MODULE_PATH.with_name("notify.py").resolve(),
        )

    def test_find_real_codex_skips_wrapper_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            wrapper = root / "bin1" / "codex"
            real = root / "bin2" / "codex"
            wrapper.parent.mkdir()
            real.parent.mkdir()
            wrapper.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
            real.chmod(real.stat().st_mode | stat.S_IXUSR)

            found = codex_wrapper.find_real_codex(
                {},
                path_env=os.pathsep.join([str(wrapper.parent), str(real.parent)]),
                wrapper_path=wrapper,
            )

        self.assertEqual(found, real.resolve())

    def test_real_codex_env_override_wins(self):
        env = {"CODEX_WRAPPER_REAL_CODEX": "/opt/codex/bin/codex"}

        self.assertEqual(
            codex_wrapper.find_real_codex(env, path_env="", wrapper_path=MODULE_PATH),
            Path("/opt/codex/bin/codex"),
        )


class CodexQuestionParserTest(unittest.TestCase):
    def make_payload(self):
        return {
            "questions": [
                {
                    "header": "范围",
                    "id": "scope",
                    "question": "选择范围",
                    "options": [
                        {"label": "最小", "description": "仅修复问题"},
                        {"label": "完整", "description": "同时重构"},
                    ],
                }
            ]
        }

    def test_question_parser_accepts_fields_after_json(self):
        line = (
            "INFO codex_core: ToolCall: request_user_input "
            f"{json.dumps(self.make_payload(), ensure_ascii=False)} "
            "thread_id=thread-1 turn_id=turn-1 cwd=/workspace\n"
        )

        event = codex_wrapper.parse_question_toolcall(line)

        self.assertEqual(event["thread_id"], "thread-1")
        self.assertEqual(event["turn_id"], "turn-1")
        self.assertEqual(event["question_text"], "选择范围")
        self.assertEqual(event["option_labels"], ["最小", "完整"])

    def test_question_parser_accepts_fields_before_json(self):
        line = (
            "thread_id=thread-2 sub_id=turn-2 cwd=/repo "
            "ToolCall: AskUserQuestion "
            f"{json.dumps(self.make_payload(), ensure_ascii=False)}\n"
        )

        event = codex_wrapper.parse_question_toolcall(line)

        self.assertEqual(event["thread_id"], "thread-2")
        self.assertEqual(event["turn_id"], "turn-2")
        self.assertEqual(event["tool_name"], "AskUserQuestion")

    def test_question_parser_rejects_invalid_json_and_empty_questions(self):
        self.assertIsNone(
            codex_wrapper.parse_question_toolcall(
                "ToolCall: request_user_input {broken thread_id=thread-1"
            )
        )
        self.assertIsNone(
            codex_wrapper.parse_question_toolcall(
                'ToolCall: request_user_input {"questions": []} thread_id=thread-1'
            )
        )


class CodexFailureParserTest(unittest.TestCase):
    def test_intermediate_retry_is_not_a_final_failure(self):
        self.assertIsNone(
            codex_wrapper.parse_upstream_failure(
                "WARN stream disconnected - retrying sampling request (1/5 in 200ms)..."
            )
        )

    def test_final_failure_extracts_status_fields_and_redacts_secret(self):
        line = (
            "thread_id=thread-1 turn_id=turn-1 cwd=/workspace "
            "Turn error: HTTP status 429 quota exceeded "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"
        )

        event = codex_wrapper.parse_upstream_failure(line)

        self.assertEqual(event["error_category"], "rate-limit")
        self.assertEqual(event["http_status"], 429)
        self.assertEqual(event["thread_id"], "thread-1")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", event["summary"])

    def test_failure_categories_cover_supported_classes(self):
        cases = {
            "authentication failed: status 401": "authentication",
            "response stream connection failed": "stream-connect",
            "stream disconnected before completion": "stream-disconnected",
            "maximum retries exhausted": "retry-exhausted",
            "connection refused by upstream": "http-connection",
            "unexpected provider response": "upstream-error",
        }

        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(codex_wrapper.classify_upstream_error(message), expected)


class CodexWrapperRuntimeTest(unittest.TestCase):
    def test_bounded_seen_evicts_oldest_key(self):
        seen = codex_wrapper.BoundedSeen(max_items=2)

        self.assertTrue(seen.add(("one",)))
        self.assertTrue(seen.add(("two",)))
        self.assertFalse(seen.add(("two",)))
        self.assertTrue(seen.add(("three",)))
        self.assertTrue(seen.add(("one",)))

    def test_emit_once_and_throttled_avoid_log_spam(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            self.assertTrue(codex_wrapper.emit_once(set(), "key", "message"))
            warned = set()
            self.assertTrue(codex_wrapper.emit_once(warned, "key", "once"))
            self.assertFalse(codex_wrapper.emit_once(warned, "key", "twice"))
            emitted = {}
            self.assertTrue(codex_wrapper.emit_throttled(emitted, "read", "first", now=10))
            self.assertFalse(codex_wrapper.emit_throttled(emitted, "read", "second", now=20))
            self.assertTrue(codex_wrapper.emit_throttled(emitted, "read", "third", now=50))

        self.assertNotIn("twice", stderr.getvalue())
        self.assertNotIn("second", stderr.getvalue())

    def test_send_notification_uses_background_launcher(self):
        with patch.object(
            codex_wrapper,
            "start_background_notification",
            return_value=(True, ""),
        ) as starter:
            result = codex_wrapper.send_notification(
                "question-required",
                {"thread_id": "thread-1"},
                Path("/tmp/notify.py"),
            )

        self.assertTrue(result)
        payload = starter.call_args.args[0]
        self.assertEqual(payload["source"], "codex-wrapper")
        self.assertEqual(payload["type"], "question-required")
        self.assertEqual(payload["thread_id"], "thread-1")


if __name__ == "__main__":
    unittest.main()
