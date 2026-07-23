#!/usr/bin/env python3
"""
Wrap the real codex binary and emit notifications for key Codex interaction
events not covered by native hooks, such as structured user questions and
final upstream response failures.
"""

from collections import OrderedDict
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
if str(WRAPPER_PATH.parent) not in sys.path:
    sys.path.insert(0, str(WRAPPER_PATH.parent))

from notify import sanitize_error_summary
from notify import start_background_notification


REAL_CODEX_ENV = "CODEX_WRAPPER_REAL_CODEX"
LOG_PATH_ENV = "CODEX_WRAPPER_LOG_PATH"
NOTIFY_SCRIPT_ENV = "CODEX_WRAPPER_NOTIFY_SCRIPT"
POLL_INTERVAL_SECONDS = 0.2
STARTUP_READ_BYTES = 64 * 1024
LOG_MISSING_WARNING_SECONDS = 5.0
LOG_ERROR_THROTTLE_SECONDS = 30.0
MAX_DEDUPE_ITEMS = 256
QUESTION_MARKER_PATTERN = re.compile(
    r"ToolCall:\s+(?P<tool_name>request_user_input|AskUserQuestion)\s+"
)
LOG_FIELD_PATTERNS = {}
HTTP_STATUS_PATTERN = re.compile(
    r"(?i)(?:http(?:\s+status)?|status(?:\s+code)?)\D{0,12}([1-5]\d{2})"
)
COMMON_HTTP_STATUS_PATTERN = re.compile(r"\b(401|403|408|409|429|5\d{2})\b")


def get_log_path(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    configured = env.get(LOG_PATH_ENV)
    if configured:
        return Path(configured).expanduser()

    home = Path(env.get("HOME", str(Path.home()))).expanduser()
    codex_home = env.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "log" / "codex-tui.log"
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


def extract_log_field(line: str, field: str, default: str = "N/A") -> str:
    pattern = LOG_FIELD_PATTERNS.get(field)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(field)}=(?:\"([^\"]*)\"|(\S+))")
        LOG_FIELD_PATTERNS[field] = pattern
    match = pattern.search(line)
    if not match:
        return default
    return (match.group(1) or match.group(2) or default).rstrip(",")


def extract_json_object(text: str, start: int) -> dict | None:
    object_start = text.find("{", start)
    if object_start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[object_start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_question_toolcall(line: str):
    if "ToolCall: request_user_input " not in line and "ToolCall: AskUserQuestion " not in line:
        return None

    match = QUESTION_MARKER_PATTERN.search(line)
    if not match:
        return None

    payload = extract_json_object(line, match.end())
    if payload is None:
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
        "thread_id": extract_log_field(line, "thread_id"),
        "turn_id": extract_log_field(
            line,
            "turn_id",
            extract_log_field(line, "sub_id"),
        ),
        "cwd": extract_log_field(line, "cwd"),
        "tool_name": match.group("tool_name"),
        "question_count": len(questions),
        "question_header": first_question.get("header", ""),
        "question_id": first_question.get("id", ""),
        "question_text": first_question.get("question", ""),
        "option_labels": option_labels,
        "questions": questions,
    }


def extract_http_status(text: str) -> int | None:
    match = HTTP_STATUS_PATTERN.search(text) or COMMON_HTTP_STATUS_PATTERN.search(text)
    return int(match.group(1)) if match else None


def classify_upstream_error(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in (
        "unauthorized",
        "authentication",
        "invalid api key",
        "invalid_api_key",
        "status 401",
        "http 401",
    )):
        return "authentication"
    if any(keyword in lowered for keyword in (
        "rate limit",
        "rate_limit",
        "insufficient_quota",
        "quota exceeded",
        "status 429",
        "http 429",
    )):
        return "rate-limit"
    if any(keyword in lowered for keyword in (
        "response stream connection",
        "failed to connect response stream",
        "error connecting to stream",
    )):
        return "stream-connect"
    if any(keyword in lowered for keyword in (
        "stream disconnected before completion",
        "stream closed before response.completed",
        "response stream disconnected",
    )):
        return "stream-disconnected"
    if any(keyword in lowered for keyword in (
        "retries exhausted",
        "retry limit",
        "max retries",
        "maximum retries",
    )):
        return "retry-exhausted"
    if extract_http_status(text) is not None or any(keyword in lowered for keyword in (
        "connection refused",
        "connection reset",
        "dns error",
        "timed out",
        "timeout",
        "error sending request",
        "http error",
    )):
        return "http-connection"
    return "upstream-error"


def parse_upstream_failure(line: str):
    marker = "Turn error:"
    marker_index = line.find(marker)
    if marker_index < 0:
        return None

    raw_summary = line[marker_index + len(marker):].strip()
    summary = sanitize_error_summary(raw_summary)
    if not summary:
        return None

    lowered = raw_summary.lower()
    return {
        "thread_id": extract_log_field(line, "thread_id"),
        "turn_id": extract_log_field(
            line,
            "turn_id",
            extract_log_field(line, "sub_id"),
        ),
        "cwd": extract_log_field(line, "cwd"),
        "error_category": classify_upstream_error(raw_summary),
        "http_status": extract_http_status(raw_summary),
        "retry_exhausted": any(keyword in lowered for keyword in (
            "retries exhausted",
            "retry limit",
            "max retries",
            "maximum retries",
        )),
        "summary": summary,
    }


class BoundedSeen:
    def __init__(self, max_items: int = MAX_DEDUPE_ITEMS):
        self.max_items = max_items
        self.items = OrderedDict()

    def add(self, key: tuple) -> bool:
        if key in self.items:
            self.items.move_to_end(key)
            return False
        self.items[key] = None
        if len(self.items) > self.max_items:
            self.items.popitem(last=False)
        return True


def emit_once(seen: set, key: str, message: str) -> bool:
    if key in seen:
        return False
    seen.add(key)
    print(message, file=sys.stderr)
    return True


def emit_throttled(
    last_emitted: dict,
    key: str,
    message: str,
    interval: float = LOG_ERROR_THROTTLE_SECONDS,
    now: float | None = None,
) -> bool:
    current = time.monotonic() if now is None else now
    previous = last_emitted.get(key)
    if previous is not None and current - previous < interval:
        return False
    last_emitted[key] = current
    print(message, file=sys.stderr)
    return True


def send_notification(event_type: str, event: dict, notify_script: Path) -> bool:
    body = {
        "source": "codex-wrapper",
        "type": event_type,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    body.update(event)

    ok, error = start_background_notification(body, notify_script)
    if not ok:
        print(f"codex-wrapper: notify launch failed: {error}", file=sys.stderr)
    return ok


def monitor_log(stop_event: threading.Event, log_path: Path, notify_script: Path):
    seen = BoundedSeen()
    one_time_diagnostics = set()
    throttled_diagnostics = {}
    current_inode = None
    position = 0
    pending = ""
    started_at = time.monotonic()

    while not stop_event.is_set():
        try:
            stat = log_path.stat()
        except FileNotFoundError:
            if time.monotonic() - started_at >= LOG_MISSING_WARNING_SECONDS:
                emit_once(
                    one_time_diagnostics,
                    "missing-log",
                    f"codex-wrapper: log file not found: {log_path}; configure Codex log_dir explicitly",
                )
            stop_event.wait(POLL_INTERVAL_SECONDS)
            continue
        except OSError as exc:
            emit_throttled(
                throttled_diagnostics,
                "log-stat",
                f"codex-wrapper: log stat failed: {exc}",
            )
            stop_event.wait(POLL_INTERVAL_SECONDS)
            continue

        inode = (stat.st_dev, stat.st_ino)
        if current_inode != inode:
            first_open = current_inode is None
            current_inode = inode
            pending = ""
            position = max(0, stat.st_size - STARTUP_READ_BYTES) if first_open else 0

        if stat.st_size < position:
            position = 0
            pending = ""

        if stat.st_size == position:
            stop_event.wait(POLL_INTERVAL_SECONDS)
            continue

        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                chunk = handle.read()
                position = handle.tell()
        except OSError as exc:
            emit_throttled(
                throttled_diagnostics,
                "log-read",
                f"codex-wrapper: log read failed: {exc}",
            )
            stop_event.wait(POLL_INTERVAL_SECONDS)
            continue

        pending += chunk
        lines = pending.splitlines(keepends=True)
        pending = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            pending = lines.pop()

        for line in lines:
            question_event = parse_question_toolcall(line)
            if question_event:
                dedupe_key = (
                    "question-required",
                    question_event["thread_id"],
                    question_event["question_id"],
                    question_event["question_text"],
                    tuple(question_event["option_labels"]),
                )
                if seen.add(dedupe_key):
                    send_notification("question-required", question_event, notify_script)
            elif "ToolCall: request_user_input " in line or "ToolCall: AskUserQuestion " in line:
                emit_once(
                    one_time_diagnostics,
                    "question-parse",
                    "codex-wrapper: recognized question tool log but could not parse its JSON; Codex log format may have changed",
                )

            failure_event = parse_upstream_failure(line)
            if failure_event:
                dedupe_key = (
                    "upstream-response-failed",
                    failure_event["thread_id"],
                    failure_event["turn_id"],
                    failure_event["error_category"],
                    failure_event["summary"],
                )
                if seen.add(dedupe_key):
                    send_notification("upstream-response-failed", failure_event, notify_script)
            elif "Turn error:" in line:
                emit_once(
                    one_time_diagnostics,
                    "failure-parse",
                    "codex-wrapper: recognized final turn error log but could not build a safe summary; Codex log format may have changed",
                )


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
