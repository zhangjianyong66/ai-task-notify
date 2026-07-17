import importlib.util
import json
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("codex-hook.py")
SPEC = importlib.util.spec_from_file_location("codex_hook", MODULE_PATH)
codex_hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_hook)


class CodexHookParserTest(unittest.TestCase):
    def test_permission_request_maps_safe_fields(self):
        event = codex_hook.parse_permission_request({
            "hook_event_name": "PermissionRequest",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "cwd": "/workspace",
            "tool_name": "Bash",
            "tool_input": {
                "command": "git status --short",
                "description": "查看工作区状态",
            },
        })

        self.assertEqual(event["source"], "codex-hook")
        self.assertEqual(event["type"], "approval-required")
        self.assertEqual(event["command"], "git status --short")
        self.assertEqual(event["description"], "查看工作区状态")
        self.assertNotIn("decision", event)

    def test_mcp_input_only_exposes_argument_names(self):
        event = codex_hook.parse_permission_request({
            "hook_event_name": "PermissionRequest",
            "tool_name": "mcp__server__write",
            "tool_input": {
                "path": "/tmp/output",
                "api_key": "must-not-leak",
            },
        })

        self.assertIn("api_key", event["tool_input_summary"])
        self.assertIn("path", event["tool_input_summary"])
        self.assertNotIn("must-not-leak", event["tool_input_summary"])
        self.assertEqual(event["description"], "(无)")

    def test_non_permission_event_is_ignored(self):
        self.assertIsNone(codex_hook.parse_permission_request({
            "hook_event_name": "Stop",
        }))


class CodexHookMainTest(unittest.TestCase):
    def test_main_starts_one_notification_without_stdout(self):
        calls = []

        def starter(event, script):
            calls.append((event, script))
            return True, ""

        stdin = StringIO(json.dumps({
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "echo ok"},
        }))
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = codex_hook.main(stdin, starter)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0]["command"], "echo ok")

    def test_invalid_json_exits_zero_without_stdout(self):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = codex_hook.main(StringIO("not-json"), lambda *_: (True, ""))

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("invalid JSON", stderr.getvalue())
