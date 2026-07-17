#!/usr/bin/env python3
"""把 Codex PermissionRequest hook 转换为异步通知事件。"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from notify import start_background_notification
from notify import truncate_text


HOOK_PATH = Path(__file__).resolve()


def summarize_tool_input(tool_name: str, tool_input) -> tuple[str, str]:
    if not isinstance(tool_input, dict):
        return "", f"{tool_name or '工具'} 参数不可用"

    command = tool_input.get("command")
    if isinstance(command, str) and command.strip():
        return truncate_text(command.strip()), truncate_text(command.strip())

    keys = sorted(str(key) for key in tool_input.keys() if key != "description")
    if keys:
        return "", f"参数字段: {', '.join(keys[:8])}"
    return "", "(无参数摘要)"


def parse_permission_request(data: dict) -> dict | None:
    if not isinstance(data, dict) or data.get("hook_event_name") != "PermissionRequest":
        return None

    tool_name = str(data.get("tool_name") or "未知工具")
    tool_input = data.get("tool_input")
    command, input_summary = summarize_tool_input(tool_name, tool_input)
    description = ""
    if isinstance(tool_input, dict) and isinstance(tool_input.get("description"), str):
        description = truncate_text(tool_input["description"].strip(), 300)

    return {
        "source": "codex-hook",
        "type": "approval-required",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "session_id": str(data.get("session_id") or "N/A"),
        "turn_id": str(data.get("turn_id") or "N/A"),
        "cwd": str(data.get("cwd") or "N/A"),
        "tool_name": tool_name,
        "command": command,
        "description": description or "(无)",
        "tool_input_summary": input_summary,
    }


def main(stdin=None, notification_starter=start_background_notification) -> int:
    input_stream = sys.stdin if stdin is None else stdin
    try:
        raw = input_stream.read()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError):
        print("codex-hook: invalid JSON input", file=sys.stderr)
        return 0

    event = parse_permission_request(data)
    if event is None:
        return 0

    ok, error = notification_starter(event, HOOK_PATH.with_name("notify.py"))
    if not ok:
        print(f"codex-hook: notify launch failed: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
