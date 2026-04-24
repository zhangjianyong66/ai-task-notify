#!/usr/bin/env python3
"""
Wrap the real codex binary and emit notifications for key Codex interaction
events such as escalated approvals and structured user questions.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


REAL_CODEX_BIN = "/Users/zhangjianyong/.nvm/versions/node/v22.22.1/bin/codex"
LOG_PATH = Path("/Users/zhangjianyong/.codex/log/codex-tui.log")
NOTIFY_SCRIPT = Path("/Users/zhangjianyong/project/ai-task-notify/notify.py")
POLL_INTERVAL_SECONDS = 0.2
STARTUP_READ_BYTES = 64 * 1024
TOOLCALL_PATTERN = re.compile(
    r'thread_id=(?P<thread_id>\S+).+?ToolCall: exec_command (?P<args>\{.*\})'
)
QUESTION_PATTERN = re.compile(
    r"ToolCall: (?P<tool_name>request_user_input|AskUserQuestion) "
    r"(?P<args>\{.*\}) thread_id=(?P<thread_id>\S+)"
)


def parse_toolcall(line: str):
    if 'ToolCall: exec_command ' not in line:
        return None

    match = TOOLCALL_PATTERN.search(line)
    if not match:
        return None

    try:
        payload = json.loads(match.group("args"))
    except json.JSONDecodeError:
        return None

    if payload.get("sandbox_permissions") != "require_escalated":
        return None

    return {
        "thread_id": match.group("thread_id"),
        "cmd": payload.get("cmd", ""),
        "workdir": payload.get("workdir", ""),
        "justification": payload.get("justification", ""),
        "prefix_rule": payload.get("prefix_rule") or [],
    }


def parse_question_toolcall(line: str):
    if "ToolCall: request_user_input " not in line and "ToolCall: AskUserQuestion " not in line:
        return None

    match = QUESTION_PATTERN.search(line)
    if not match:
        return None

    try:
        payload = json.loads(match.group("args"))
    except json.JSONDecodeError:
        return None

    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return None

    first_question = questions[0] if isinstance(questions[0], dict) else {}
    if not first_question:
        return None

    options = first_question.get("options") or []
    option_labels = [
        option.get("label", "").strip()
        for option in options
        if isinstance(option, dict) and option.get("label")
    ]

    return {
        "thread_id": match.group("thread_id"),
        "tool_name": match.group("tool_name"),
        "question_count": len(questions),
        "question_header": first_question.get("header", ""),
        "question_id": first_question.get("id", ""),
        "question_text": first_question.get("question", ""),
        "option_labels": option_labels,
        "questions": questions,
    }


def send_notification(event_type: str, event: dict):
    body = {
        "source": "codex-wrapper",
        "type": event_type,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    body.update(event)

    try:
        subprocess.run(
            [sys.executable, str(NOTIFY_SCRIPT), json.dumps(body, ensure_ascii=False)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"codex-wrapper: notify failed: {exc}", file=sys.stderr)


def monitor_log(stop_event: threading.Event):
    seen = set()
    current_inode = None
    position = 0

    while not stop_event.is_set():
        try:
            stat = LOG_PATH.stat()
        except FileNotFoundError:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        except OSError as exc:
            print(f"codex-wrapper: log stat failed: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        inode = (stat.st_dev, stat.st_ino)
        if current_inode != inode:
            current_inode = inode
            # On (re)start, replay only the log tail to avoid missing events that
            # happen immediately after Codex launches while still avoiding full scan.
            position = max(0, stat.st_size - STARTUP_READ_BYTES)

        if stat.st_size < position:
            position = stat.st_size

        if stat.st_size == position:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        try:
            with LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                chunk = handle.read()
                position = handle.tell()
        except OSError as exc:
            print(f"codex-wrapper: log read failed: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        for line in chunk.splitlines():
            approval_event = parse_toolcall(line)
            if approval_event:
                dedupe_key = (
                    "approval-required",
                    approval_event["thread_id"],
                    approval_event["cmd"],
                    approval_event["justification"],
                )
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    send_notification("approval-required", approval_event)

            question_event = parse_question_toolcall(line)
            if question_event:
                dedupe_key = (
                    "question-required",
                    question_event["thread_id"],
                    question_event["question_id"],
                    question_event["question_text"],
                    tuple(question_event["option_labels"]),
                )
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    send_notification("question-required", question_event)


def main() -> int:
    stop_event = threading.Event()
    monitor = threading.Thread(target=monitor_log, args=(stop_event,), daemon=True)
    monitor.start()

    env = os.environ.copy()
    process = subprocess.Popen([REAL_CODEX_BIN, *sys.argv[1:]], env=env)
    return_code = process.wait()

    stop_event.set()
    monitor.join(timeout=1)
    return return_code


if __name__ == "__main__":
    sys.exit(main())
