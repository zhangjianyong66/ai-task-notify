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


WRAPPER_PATH = Path(__file__).resolve()
REAL_CODEX_ENV = "CODEX_WRAPPER_REAL_CODEX"
LOG_PATH_ENV = "CODEX_WRAPPER_LOG_PATH"
NOTIFY_SCRIPT_ENV = "CODEX_WRAPPER_NOTIFY_SCRIPT"
POLL_INTERVAL_SECONDS = 0.2
STARTUP_READ_BYTES = 64 * 1024
TOOLCALL_PATTERN = re.compile(
    r'thread_id=(?P<thread_id>\S+).+?ToolCall: exec_command (?P<args>\{.*\})'
)
QUESTION_PATTERN = re.compile(
    r"ToolCall: (?P<tool_name>request_user_input|AskUserQuestion) "
    r"(?P<args>\{.*\}) thread_id=(?P<thread_id>\S+)"
)


def get_log_path(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    configured = env.get(LOG_PATH_ENV)
    if configured:
        return Path(configured).expanduser()

    home = Path(env.get("HOME", str(Path.home()))).expanduser()
    return home / ".codex" / "log" / "codex-tui.log"


def get_notify_script(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    configured = env.get(NOTIFY_SCRIPT_ENV)
    if configured:
        return Path(configured).expanduser()

    return WRAPPER_PATH.with_name("notify.py").resolve()


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find_real_codex(
    env: dict | None = None,
    path_env: str | None = None,
    wrapper_path: Path | None = None,
) -> Path | None:
    env = os.environ if env is None else env
    configured = env.get(REAL_CODEX_ENV)
    if configured:
        return Path(configured).expanduser()

    wrapper_path = WRAPPER_PATH if wrapper_path is None else Path(wrapper_path)
    wrapper_resolved = wrapper_path.resolve()
    path_env = env.get("PATH", "") if path_env is None else path_env

    for directory in path_env.split(os.pathsep):
        if not directory:
            continue

        candidate = Path(directory).expanduser() / "codex"
        if not _is_executable(candidate):
            continue

        try:
            if candidate.resolve() == wrapper_resolved:
                continue
        except OSError:
            continue

        return candidate.resolve()

    return None


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


def send_notification(event_type: str, event: dict, notify_script: Path):
    body = {
        "source": "codex-wrapper",
        "type": event_type,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    body.update(event)

    try:
        subprocess.run(
            [sys.executable, str(notify_script), json.dumps(body, ensure_ascii=False)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"codex-wrapper: notify failed: {exc}", file=sys.stderr)


def monitor_log(stop_event: threading.Event, log_path: Path, notify_script: Path):
    seen = set()
    current_inode = None
    position = 0

    while not stop_event.is_set():
        try:
            stat = log_path.stat()
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
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
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
                    send_notification("approval-required", approval_event, notify_script)

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
                    send_notification("question-required", question_event, notify_script)


def main() -> int:
    env = os.environ.copy()
    real_codex_bin = find_real_codex(env)
    if real_codex_bin is None:
        print(
            f"codex-wrapper: real codex not found in PATH; set {REAL_CODEX_ENV}",
            file=sys.stderr,
        )
        return 127

    log_path = get_log_path(env)
    notify_script = get_notify_script(env)

    stop_event = threading.Event()
    monitor = threading.Thread(
        target=monitor_log,
        args=(stop_event, log_path, notify_script),
        daemon=True,
    )
    monitor.start()

    process = subprocess.Popen([str(real_codex_bin), *sys.argv[1:]], env=env)
    return_code = process.wait()

    stop_event.set()
    monitor.join(timeout=1)
    return return_code


if __name__ == "__main__":
    sys.exit(main())
