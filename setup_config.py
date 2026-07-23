#!/usr/bin/env python3
"""AI Task Notify 的 Codex 一键配置器。

该模块只使用标准库。所有写入都先生成计划，再在事务中原子提交；命令行
入口由根目录的 setup.sh 提供，函数保持可注入以便测试使用临时 HOME。
"""

from __future__ import annotations

import argparse
import copy
import getpass
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

MIN_CODEX_VERSION = (0, 144, 5)
STATE_SCHEMA = 1
PATH_START = "# ai-task-notify: begin managed PATH"
PATH_END = "# ai-task-notify: end managed PATH"
KNOWN_CHANNELS = ("wecom", "feishu", "dingtalk", "email")
CHANNEL_FIELDS = {
    "wecom": (("WECOM_WEBHOOK_URL", False),),
    "feishu": (("FEISHU_WEBHOOK_URL", False), ("FEISHU_SECRET", True)),
    "dingtalk": (("DINGTALK_WEBHOOK_URL", False), ("DINGTALK_SECRET", True)),
    "email": (
        ("SMTP_HOST", False), ("SMTP_PORT", False), ("SMTP_USER", False),
        ("SMTP_PASSWORD", True), ("SMTP_USE_SSL", False),
        ("EMAIL_FROM", False), ("EMAIL_TO", False),
    ),
}
SENSITIVE_FIELDS = {field for fields in CHANNEL_FIELDS.values() for field, secret in fields if secret}
OPTIONAL_FIELDS = {"FEISHU_SECRET", "DINGTALK_SECRET", "SMTP_PORT", "SMTP_USE_SSL"}
ALL_KNOWN_FIELDS = {"NOTIFY_CHANNELS"} | {
    field for fields in CHANNEL_FIELDS.values() for field, _ in fields
}


@dataclass(frozen=True)
class Paths:
    repo: Path
    home: Path
    codex_home: Path
    state_dir: Path
    state_file: Path
    config: Path
    hooks: Path
    bashrc: Path
    shim_dir: Path
    shim: Path
    env_file: Path


def resolve_paths(repo: Path | None = None, env: dict | None = None) -> Paths:
    env = os.environ if env is None else env
    repo = (repo or Path(__file__).resolve().parent).resolve()
    home = Path(env.get("HOME", str(Path.home()))).expanduser().resolve()
    codex_home = Path(env.get("CODEX_HOME", str(home / ".codex"))).expanduser().resolve()
    state_root = Path(env.get("XDG_STATE_HOME", str(home / ".local" / "state"))).expanduser().resolve()
    state_dir = state_root / "ai-task-notify"
    return Paths(
        repo, home, codex_home, state_dir, state_dir / "install-state.json",
        codex_home / "config.toml", codex_home / "hooks.json", home / ".bashrc",
        home / ".local" / "codex-wrapper-bin", home / ".local" / "codex-wrapper-bin" / "codex",
        repo / ".env",
    )


def file_hash(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return "link:" + os.readlink(path)
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def read_state(paths: Paths) -> dict | None:
    try:
        with paths.state_file.open(encoding="utf-8") as handle:
            state = json.load(handle)
        if state.get("schema") != STATE_SCHEMA or not isinstance(state.get("managed"), list):
            return None
        return state
    except (OSError, ValueError, TypeError):
        return None


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def effective_env(paths: Paths, env: dict | None = None) -> dict[str, str]:
    process = os.environ if env is None else env
    values = load_dotenv(paths.env_file)
    values.update({key: value for key, value in process.items() if key in ALL_KNOWN_FIELDS})
    return values


def enabled_channels(values: dict[str, str]) -> list[str]:
    raw = values.get("NOTIFY_CHANNELS", "")
    result = []
    for item in raw.split(","):
        channel = item.strip().lower()
        if channel and channel not in result:
            result.append(channel)
    return result


def missing_notification_fields(values: dict[str, str]) -> list[str]:
    missing: list[str] = []
    channels = enabled_channels(values)
    unknown = [channel for channel in channels if channel not in KNOWN_CHANNELS]
    if unknown:
        return [f"NOTIFY_CHANNELS({channel})" for channel in unknown]
    for channel in channels:
        for field, _ in CHANNEL_FIELDS[channel]:
            value = values.get(field, "")
            if not value and field not in OPTIONAL_FIELDS:
                missing.append(field)
    return missing


def format_plan(items: Iterable[dict]) -> str:
    lines = []
    for item in items:
        action = item.get("action", "unchanged")
        lines.append(f"{action}: {item.get('kind', '配置')} -> {item.get('path', '')}")
        if item.get("reason"):
            lines.append(f"  {item['reason']}")
    return "\n".join(lines) if lines else "unchanged: 无需变更"


def version_tuple(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?:^|\s|v)(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def discover_real_codex(env: dict | None = None, wrapper: Path | None = None) -> tuple[Path | None, tuple[int, int, int] | None, str]:
    env = os.environ if env is None else env
    configured = env.get("CODEX_WRAPPER_REAL_CODEX")
    wrapper = (wrapper or Path(__file__).with_name("codex-wrapper.py")).resolve()
    candidates = [Path(configured).expanduser()] if configured else [Path(directory) / "codex" for directory in env.get("PATH", "").split(os.pathsep) if directory]
    seen: set[Path] = set()
    errors: list[str] = []
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen or candidate == wrapper or not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        seen.add(candidate)
        try:
            result = subprocess.run([str(candidate), "--version"], capture_output=True, text=True, timeout=10, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        text = (result.stdout + " " + result.stderr).strip()
        version = version_tuple(text)
        if result.returncode == 0 and version is not None and version >= MIN_CODEX_VERSION:
            return candidate, version, ""
        errors.append(f"{candidate}: 版本无法验证或低于 0.144.5")
    return None, None, "; ".join(errors) or "PATH 中未找到可用 codex"


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def edit_config_toml(original: str, notify_script: Path, log_dir: Path) -> str:
    """仅编辑顶层 notify/log_dir 的单行简单写法。"""
    lines = original.splitlines(keepends=True)
    updates = {
        "notify": f"notify = [\"python3\", {_toml_string(str(notify_script))}]\n",
        "log_dir": f"log_dir = {_toml_string(str(log_dir))}\n",
    }
    seen: set[str] = set()
    result: list[str] = []
    in_table = False
    first_table_index: int | None = None
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("["):
            if first_table_index is None:
                first_table_index = len(result)
            in_table = True
        match = re.match(r"^(\s*)(notify|log_dir)\s*=\s*(.*?)(\r?\n)?$", line)
        if not match or match.group(2) not in updates or in_table:
            result.append(line)
            continue
        key, value = match.group(2), match.group(3).strip()
        if key in seen:
            raise ValueError(f"重复的顶层 {key} 配置")
        if not value or value.startswith("[") and "]" not in value or value.startswith(('"""', "'''")):
            raise ValueError(f"不支持的 {key} 多行配置")
        comment = re.search(r"\s+(#.*)$", value)
        replacement = updates[key].rstrip("\n")
        if comment:
            replacement += "  " + comment.group(1)
        result.append(match.group(1) + replacement + "\n")
        seen.add(key)
    if result and not result[-1].endswith(("\n", "\r")):
        result[-1] += "\n"
    additions = [updates[key] for key in ("notify", "log_dir") if key not in seen]
    if first_table_index is None:
        result.extend(additions)
    else:
        result[first_table_index:first_table_index] = additions
    return "".join(result)


def merge_hooks(original: str, hook_script: Path, previous_hook_script: Path | None = None) -> str:
    try:
        data = json.loads(original) if original.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"hooks.json 无效 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("hooks.json 根节点必须是对象")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks.json 的 hooks 必须是对象")
    groups = hooks.setdefault("PermissionRequest", [])
    if not isinstance(groups, list):
        raise ValueError("PermissionRequest 必须是数组")
    command = f"python3 {hook_script}"
    for group in groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list):
            continue
        for item in handlers:
            if not isinstance(item, dict):
                continue
            if item.get("command") == command:
                return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            if previous_hook_script and item.get("command") == f"python3 {previous_hook_script}":
                item["command"] = command
                return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    groups.append({"hooks": [{"type": "command", "command": command, "timeout": 5, "statusMessage": "Sending approval notification"}]})
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def managed_path_block(original: str, shim_dir: Path) -> tuple[str, bool]:
    block = f'{PATH_START}\nexport PATH="{shim_dir}:$PATH"\n{PATH_END}\n'
    pattern = re.compile(re.escape(PATH_START) + r"\n.*?" + re.escape(PATH_END) + r"\n?", re.S)
    if pattern.search(original):
        return pattern.sub(block, original, count=1), True
    # 明确等价的外部配置保持所有权。
    equivalent = re.compile(rf"(^|\n)\s*export\s+PATH=\"?{re.escape(str(shim_dir))}:\$PATH\"?\s*(?:\n|$)")
    if equivalent.search(original):
        return original, True
    prefix = "" if not original or original.endswith("\n") else "\n"
    return original + prefix + block, False


def validate_bash_candidate(content: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["bash", "-n"],
            input=content,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return result.returncode == 0, result.stderr.strip()[:300]


def write_atomic(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Transaction:
    def __init__(self, paths: Paths, dry_run: bool = False):
        self.paths = paths
        self.dry_run = dry_run
        self.backup_dir = paths.state_dir / f"backup-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}"
        self.snapshots: dict[Path, tuple[bool, bytes | str | None, int]] = {}
        self.backup_refs: dict[Path, str] = {}
        self.changed: list[Path] = []

    def snapshot(self, path: Path) -> None:
        if path in self.snapshots:
            return
        exists = path.exists() or path.is_symlink()
        mode = stat.S_IMODE(path.lstat().st_mode) if exists else 0o600
        data: bytes | str | None = os.readlink(path) if path.is_symlink() else (path.read_bytes() if exists else None)
        self.snapshots[path] = (exists, data, mode)
        if exists and not self.dry_run:
            self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = self.backup_dir / hashlib.sha256(str(path).encode()).hexdigest()[:16]
            if isinstance(data, str):
                backup.write_text(data, encoding="utf-8")
            else:
                backup.write_bytes(data or b"")
            os.chmod(backup, 0o600)
            self.backup_refs[path] = str(backup.relative_to(self.paths.state_dir))

    def replace_file(self, path: Path, content: str, mode: int = 0o600) -> None:
        if self.dry_run:
            return
        self.snapshot(path)
        write_atomic(path, content, mode)
        self.changed.append(path)

    def replace_link(self, path: Path, target: Path) -> None:
        if self.dry_run:
            return
        self.snapshot(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp.unlink(missing_ok=True)
        temp.symlink_to(target)
        os.replace(temp, path)
        self.changed.append(path)

    def remove(self, path: Path) -> None:
        if self.dry_run:
            return
        self.snapshot(path)
        if path.exists() or path.is_symlink():
            path.unlink()
            self.changed.append(path)

    def rollback(self) -> None:
        if self.dry_run:
            return
        for path in reversed(self.changed):
            exists, data, mode = self.snapshots[path]
            try:
                if path.exists() or path.is_symlink():
                    path.unlink()
                if exists:
                    if isinstance(data, str):
                        path.symlink_to(data)
                    else:
                        write_atomic(path, (data or b"").decode("utf-8"), mode)
            except OSError:
                pass


def _safe_path(path: Path) -> str:
    return str(path)


def build_plan(paths: Paths, values: dict[str, str], codex: Path | None, state: dict | None, persisted_values: dict[str, str] | None = None) -> tuple[list[dict], dict[str, str]]:
    persisted_values = values if persisted_values is None else persisted_values
    plan: list[dict] = []
    if missing_notification_fields(values):
        plan.append({"action": "conflict", "kind": "通知配置", "path": _safe_path(paths.env_file), "reason": "缺少字段: " + ", ".join(missing_notification_fields(values))})
    if codex is None:
        plan.append({"action": "conflict", "kind": "Codex", "path": "PATH", "reason": "未找到满足版本要求的真实 codex"})
    desired: dict[str, str] = {}
    desired["env"] = _env_content(paths.env_file, persisted_values)
    desired["config"] = edit_config_toml(paths.config.read_text(encoding="utf-8") if paths.config.exists() else "", paths.repo / "notify.py", paths.codex_home / "log")
    previous_repo = Path(state["repo_path"]) if state and state.get("repo_path") and Path(state["repo_path"]).resolve() != paths.repo else None
    desired["hooks"] = merge_hooks(
        paths.hooks.read_text(encoding="utf-8") if paths.hooks.exists() else "{}",
        paths.repo / "codex-hook.py",
        previous_repo / "codex-hook.py" if previous_repo else None,
    )
    bash_original = paths.bashrc.read_text(encoding="utf-8") if paths.bashrc.exists() else ""
    desired["bashrc"], external_path = managed_path_block(bash_original, paths.shim_dir)
    bash_valid, bash_error = validate_bash_candidate(desired["bashrc"])
    if not bash_valid:
        raise ValueError(f".bashrc 候选语法无效: {bash_error}")
    for key, path in (("env", paths.env_file), ("config", paths.config), ("hooks", paths.hooks), ("bashrc", paths.bashrc)):
        action = "unchanged" if path.exists() and path.read_text(encoding="utf-8") == desired[key] and (key != "env" or stat.S_IMODE(path.stat().st_mode) == 0o600) else ("update" if path.exists() else "create")
        plan.append({"action": action, "kind": key, "path": _safe_path(path)})
    if paths.shim.is_symlink() and paths.shim.resolve() == (paths.repo / "codex-wrapper.py").resolve():
        shim_action = "unchanged"
    elif previous_repo and paths.shim.is_symlink() and paths.shim.resolve() == (previous_repo / "codex-wrapper.py").resolve():
        shim_action = "update"
    else:
        shim_action = "conflict" if paths.shim.exists() or paths.shim.is_symlink() else "create"
    plan.append({"action": shim_action, "kind": "wrapper shim", "path": _safe_path(paths.shim), "reason": "已有非本项目 shim" if shim_action == "conflict" else ""})
    if not external_path:
        plan[-2]["reason"] = "维护 Bash PATH 区块"
    return plan, desired


def _state_entry(path: Path, kind: str, original: tuple[bool, bytes | str | None, int], backup_rel: str | None, created: bool) -> dict:
    exists, data, mode = original
    return {"kind": kind, "path": str(path), "managed_hash": file_hash(path), "original_exists": exists, "original_is_symlink": isinstance(data, str), "original_mode": mode, "original_backup": backup_rel, "created": created}


def _managed_entry(path: Path, kind: str, snapshot: tuple[bool, bytes | str | None, int], backup_rel: str | None, old: dict | None) -> dict:
    entry = _state_entry(path, kind, snapshot, backup_rel, not snapshot[0])
    if old:
        for key in ("original_exists", "original_is_symlink", "original_mode", "original_backup", "created"):
            entry[key] = old.get(key)
    return entry


def validate_config_candidate(codex: Path, paths: Paths, content: str, env: dict | None = None) -> tuple[bool, str]:
    """在隔离 CODEX_HOME 中让真实 Codex 校验候选配置。"""
    with tempfile.TemporaryDirectory(prefix="ai-task-notify-config-") as temp_dir:
        candidate_home = Path(temp_dir)
        (candidate_home / "config.toml").write_text(content, encoding="utf-8")
        child_env = (os.environ if env is None else env).copy()
        child_env["CODEX_HOME"] = str(candidate_home)
        try:
            result = subprocess.run(
                [str(codex), "--strict-config", "--version"],
                env=child_env,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)
        if result.returncode != 0:
            return False, "Codex 拒绝候选配置（详细错误未输出以避免泄露配置内容）"
    return True, ""


def _save_state(paths: Paths, state: dict) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(paths.state_dir, 0o700)
    write_atomic(paths.state_file, json.dumps(state, ensure_ascii=False, indent=2) + "\n", 0o600)


def _interactive_env(paths: Paths, values: dict[str, str]) -> dict[str, str]:
    current = copy.deepcopy(values)
    if enabled_channels(current) and not missing_notification_fields(current):
        reuse = input("已有通知配置完整，直接复用？[Y/n] ").strip().lower()
        if reuse not in {"n", "no"}:
            return current
    default = ",".join(enabled_channels(current))
    selected = input(f"通知渠道（逗号分隔，支持 wecom/feishu/dingtalk/email） [{default}]: ").strip() or default
    current["NOTIFY_CHANNELS"] = selected
    for channel in enabled_channels(current):
        if channel not in CHANNEL_FIELDS:
            continue
        for field, secret in CHANNEL_FIELDS[channel]:
            old = current.get(field, "")
            status = "已配置" if old else "缺失"
            prompt = f"{field}（{status}）"
            value = getpass.getpass(prompt + ": ") if secret else input(prompt + ": ")
            if value:
                current[field] = value
    return current


def send_test_notifications(values: dict[str, str], sender: Callable | None = None) -> bool:
    if sender is None:
        from notify import send_notification as sender
    results = sender(values, "AI Task Notify 配置测试", "Codex 通知配置已完成。")
    channels = enabled_channels(values)
    for channel in channels:
        print(f"{'OK' if results.get(channel) else 'FAIL'} 测试通知: {channel}")
    return bool(channels) and all(results.get(channel, False) for channel in channels)


def _env_content(path: Path, values: dict[str, str]) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    ordered = ["NOTIFY_CHANNELS"] + [field for channel in KNOWN_CHANNELS for field, _ in CHANNEL_FIELDS[channel]]
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=.*$", line)
        key = match.group(2) if match else None
        if key in values and key in ordered:
            result.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            result.append(line)
    for key in ordered:
        if key in values and key not in seen:
            result.append(f"{key}={values[key]}")
    return "\n".join(result).rstrip() + "\n"


def install(paths: Paths, args: argparse.Namespace, env: dict | None = None) -> int:
    process_env = os.environ if env is None else env
    persisted_values = load_dotenv(paths.env_file)
    if not args.dry_run and not args.non_interactive:
        persisted_values = _interactive_env(paths, persisted_values)
    values = persisted_values.copy()
    values.update({key: value for key, value in process_env.items() if key in ALL_KNOWN_FIELDS})
    missing = missing_notification_fields(values)
    if missing:
        print("缺少通知配置字段: " + ", ".join(missing), file=sys.stderr)
        return 1
    codex, version, error = discover_real_codex(process_env)
    if codex is None:
        print(f"Codex 检查失败: {error}", file=sys.stderr)
        return 1
    state = read_state(paths)
    if state and Path(state.get("repo_path", "")).resolve() != paths.repo:
        if args.non_interactive and not args.migrate:
            print("检测到其他仓库副本已激活；非交互迁移必须使用 --migrate", file=sys.stderr)
            return 1
        if not args.non_interactive and not args.migrate:
            answer = input(f"检测到已激活副本 {state.get('repo_path')}，迁移到当前仓库？[y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("已取消迁移。", file=sys.stderr)
                return 1
    try:
        plan, desired = build_plan(paths, values, codex, state, persisted_values)
    except (OSError, ValueError) as exc:
        print(f"配置解析失败，未执行写入: {exc}", file=sys.stderr)
        return 1
    try:
        valid, validation_error = validate_config_candidate(codex, paths, desired["config"], process_env)
    except (OSError, ValueError) as exc:
        valid, validation_error = False, str(exc)
    if not valid:
        print(f"config.toml 候选校验失败: {validation_error}", file=sys.stderr)
        return 1
    print(format_plan(plan))
    conflicts = [item for item in plan if item["action"] == "conflict"]
    if conflicts:
        if args.non_interactive:
            print("存在冲突，未执行写入。", file=sys.stderr)
            return 1
        for item in conflicts:
            answer = input(f"冲突项 {item['path']} 是否覆盖？[y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("存在未确认的冲突，未执行写入。", file=sys.stderr)
                return 1
        plan = [item for item in plan if item["action"] != "conflict"]
    if args.dry_run:
        return 0
    tx = Transaction(paths)
    old_managed = {item["path"]: item for item in (state or {}).get("managed", [])}
    managed: list[dict] = []
    try:
        targets = [(paths.env_file, "env", desired["env"], 0o600), (paths.config, "config", desired["config"], 0o600), (paths.hooks, "hooks", desired["hooks"], 0o600), (paths.bashrc, "bashrc", desired["bashrc"], 0o644)]
        for path, kind, content, mode in targets:
            old = old_managed.get(str(path))
            before = file_hash(path)
            current_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
            needs_change = before != hashlib.sha256(content.encode()).hexdigest() or current_mode != mode
            if kind == "env":
                if needs_change:
                    tx.replace_file(path, content, mode)
                continue
            if not old:
                tx.snapshot(path)
            if needs_change:
                tx.replace_file(path, content, mode)
            snapshot = tx.snapshots.get(path, (path.exists(), path.read_bytes() if path.exists() else None, stat.S_IMODE(path.stat().st_mode) if path.exists() else mode))
            backup_rel = old.get("original_backup") if old else tx.backup_refs.get(path)
            managed.append(_managed_entry(path, kind, snapshot, backup_rel, old))
        old = old_managed.get(str(paths.shim))
        if not old:
            tx.snapshot(paths.shim)
        target = paths.repo / "codex-wrapper.py"
        if not paths.shim.is_symlink() or paths.shim.resolve() != target.resolve():
            tx.replace_link(paths.shim, target)
        snapshot = tx.snapshots.get(paths.shim, (False, None, 0o755))
        managed.append(_managed_entry(paths.shim, "shim", snapshot, old.get("original_backup") if old else tx.backup_refs.get(paths.shim), old))
        for path in [paths.repo / "setup.sh", paths.repo / "notify.py", paths.repo / "codex-hook.py", paths.repo / "codex-wrapper.py"]:
            if path.exists():
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
        state_payload = {"schema": STATE_SCHEMA, "repo_path": str(paths.repo), "codex_path": str(codex), "codex_version": ".".join(map(str, version or ())), "managed": managed, "updated_at": time.time()}
        _save_state(paths, state_payload)
    except Exception as exc:
        tx.rollback()
        print(f"安装失败，已回滚: {exc}", file=sys.stderr)
        return 1
    print("安装完成。请进入 Codex 的 /hooks 页面审核并信任新增 hook；该人工审核不由脚本代办。")
    if not args.non_interactive:
        answer = input("是否向已启用渠道发送测试通知？[y/N] ").strip().lower()
        if answer in {"y", "yes"} and not send_test_notifications(values):
            print("测试通知存在失败；本地配置已保留。", file=sys.stderr)
            return 1
    return 0


def check(paths: Paths, env: dict | None = None) -> int:
    process_env = os.environ if env is None else env
    values = effective_env(paths, process_env)
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info >= (3, 10), ".".join(map(str, sys.version_info[:3]))))
    codex, version, error = discover_real_codex(process_env)
    checks.append(("Codex", codex is not None, str(codex or error)))
    missing = missing_notification_fields(values)
    checks.append(("通知配置", not missing, "完整" if not missing else "缺少: " + ", ".join(missing)))
    checks.append((".env 权限", not paths.env_file.exists() or stat.S_IMODE(paths.env_file.stat().st_mode) == 0o600, str(paths.env_file)))
    try:
        config_original = paths.config.read_text(encoding="utf-8")
        config_expected = edit_config_toml(config_original, paths.repo / "notify.py", paths.codex_home / "log")
        config_ok = config_original == config_expected
    except (OSError, ValueError):
        config_ok = False
    checks.append(("config.toml", config_ok, str(paths.config)))
    try:
        hooks_original = paths.hooks.read_text(encoding="utf-8")
        hooks_expected = merge_hooks(hooks_original, paths.repo / "codex-hook.py")
        hooks_ok = json.loads(hooks_original) == json.loads(hooks_expected)
    except (OSError, ValueError):
        hooks_ok = False
    checks.append(("hooks.json", hooks_ok, str(paths.hooks)))
    checks.append(("wrapper shim", paths.shim.is_symlink() and paths.shim.resolve() == (paths.repo / "codex-wrapper.py").resolve(), str(paths.shim)))
    state = read_state(paths)
    state_ok = state is not None and Path(state.get("repo_path", "")).resolve() == paths.repo
    if state_ok:
        state_ok = all(file_hash(Path(item["path"])) == item.get("managed_hash") for item in state.get("managed", []))
    if state_ok and paths.state_file.exists():
        state_ok = stat.S_IMODE(paths.state_file.stat().st_mode) == 0o600 and stat.S_IMODE(paths.state_dir.stat().st_mode) == 0o700
    checks.append(("安装状态", state_ok, str(paths.state_file)))
    bash_text = paths.bashrc.read_text(encoding="utf-8") if paths.bashrc.exists() else ""
    _, bash_ok = managed_path_block(bash_text, paths.shim_dir)
    checks.append(("Bash PATH", bash_ok, str(paths.bashrc)))
    scripts_ok = all(path.is_file() and os.access(path, os.X_OK) for path in (paths.repo / "notify.py", paths.repo / "codex-hook.py", paths.repo / "codex-wrapper.py"))
    checks.append(("脚本权限", scripts_ok, str(paths.repo)))
    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
    print("提示：如新增 hook 尚未生效，请在 Codex 中进入 /hooks 完成人工审核。")
    return 0 if all(ok for _, ok, _ in checks) else 1


def uninstall(paths: Paths, args: argparse.Namespace) -> int:
    state = read_state(paths)
    if not state:
        print("未找到安装状态，无需卸载。")
        return 0
    plan: list[dict] = []
    conflicts: list[dict] = []
    for item in state.get("managed", []):
        path = Path(item["path"])
        if path == paths.env_file:
            continue
        current = file_hash(path)
        if current != item.get("managed_hash"):
            action = "conflict"
            conflicts.append(item)
        else:
            action = "restore" if item.get("original_exists") else "remove"
        plan.append({"action": action, "kind": item.get("kind"), "path": str(path)})
    print(format_plan(plan))
    if not args.non_interactive and not args.dry_run:
        answer = input("确认执行卸载？[y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("已取消。")
            return 0
    if args.dry_run:
        return 0
    tx = Transaction(paths)
    remaining = []
    try:
        for item in state.get("managed", []):
            path = Path(item["path"])
            if path == paths.env_file or item in conflicts:
                remaining.append(item)
                continue
            tx.snapshot(path)
            if item.get("original_exists"):
                backup = paths.state_dir / item["original_backup"] if item.get("original_backup") else None
                if not backup or not backup.exists():
                    raise OSError(f"缺少恢复备份: {path}")
                if item.get("original_is_symlink"):
                    tx.replace_link(path, Path(backup.read_text(encoding="utf-8")))
                else:
                    data = backup.read_text(encoding="utf-8")
                    tx.replace_file(path, data, int(item.get("original_mode") or 0o600))
            else:
                tx.remove(path)
        if remaining:
            state["managed"] = remaining
            _save_state(paths, state)
        else:
            paths.state_file.unlink(missing_ok=True)
            try:
                paths.state_dir.rmdir()
            except OSError:
                pass
    except Exception as exc:
        tx.rollback()
        print(f"卸载失败，已回滚: {exc}", file=sys.stderr)
        return 1
    if conflicts:
        print("存在用户后改冲突，冲突项已保留。", file=sys.stderr)
        return 1
    print("卸载完成；.env、备份和未标记的外部 PATH 配置已保留。")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Task Notify Codex 一键配置")
    sub = parser.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--non-interactive", action="store_true")
    install_parser.add_argument("--migrate", action="store_true")
    install_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("check")
    uninstall_parser = sub.add_parser("uninstall")
    uninstall_parser.add_argument("--non-interactive", action="store_true")
    uninstall_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "check" and any(flag in argv for flag in ("--dry-run", "--migrate", "--non-interactive")):
        parser.error("check 不接受安装/卸载选项")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return int(exc.code)
    paths = resolve_paths()
    if args.command == "install":
        return install(paths, args)
    if args.command == "check":
        return check(paths)
    return uninstall(paths, args)


if __name__ == "__main__":
    sys.exit(main())
