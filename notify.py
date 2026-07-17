#!/usr/bin/env python3
"""
AI Task Notify - Claude Code / Codex 任务完成通知脚本

支持的通知渠道:
- 企业微信 (WeCom)
- 飞书 (Feishu)
- 钉钉 (DingTalk)
- 邮件 (Email)

使用方式:
1. Claude Code (Stop hook): 通过 stdin 接收 JSON
2. Codex CLI (notify): 通过命令行参数接收 JSON
"""

import json
import sys
import os
import re
import hmac
import hashlib
import base64
import time
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from typing import Optional


MAX_COMMAND_PREVIEW = 300
MAX_ERROR_SUMMARY = 300
MAX_MESSAGE_PREVIEW = 500

SENSITIVE_QUOTED_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)([\"']?(?:authorization|api[_-]?key|token|secret|password)[\"']?"
    r"\s*[:=]\s*)([\"']).*?\2"
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)([\"']?(?:authorization|api[_-]?key|token|secret|password)[\"']?"
    r"\s*[:=]\s*)(?:Bearer\s+)?[^\s,;}\"']+"
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;}]+")
URL_WITH_QUERY_PATTERN = re.compile(r"(https?://[^\s?#]+)\?[^\s]+", re.IGNORECASE)
LONG_SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?=[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-]))"
    r"(?=[A-Za-z0-9_-]*[A-Za-z])"
    r"(?=[A-Za-z0-9_-]*\d)"
    r"[A-Za-z0-9_-]+"
)


def load_env(env_path: Optional[str] = None) -> dict:
    """加载 .env 文件"""
    env = {}

    if env_path is None:
        env_path = Path(__file__).parent / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        return env

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()

    return env


def get_config(env: dict, key: str, default: str = "") -> str:
    """获取配置，优先使用环境变量"""
    return os.environ.get(key, env.get(key, default))


def get_enabled_channels(env: dict) -> list:
    """获取启用的通知渠道列表"""
    channels_str = get_config(env, "NOTIFY_CHANNELS", "")
    if not channels_str:
        return []
    return [c.strip().lower() for c in channels_str.split(",") if c.strip()]


def http_post(url: str, data: dict, headers: Optional[dict] = None) -> tuple:
    """发送 HTTP POST 请求"""
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"

    json_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 0, str(e)


# ============ 企业微信 ============

def send_wecom(env: dict, title: str, content: str) -> bool:
    """发送企业微信通知"""
    webhook_url = get_config(env, "WECOM_WEBHOOK_URL")
    if not webhook_url:
        return False

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### {title}\n{content}"
        }
    }

    status, resp = http_post(webhook_url, data)
    if status == 200:
        result = json.loads(resp)
        return result.get("errcode") == 0
    return False


# ============ 飞书 ============

def gen_feishu_sign(secret: str, timestamp: str) -> str:
    """生成飞书签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu(env: dict, title: str, content: str) -> bool:
    """发送飞书通知"""
    webhook_url = get_config(env, "FEISHU_WEBHOOK_URL")
    if not webhook_url:
        return False

    secret = get_config(env, "FEISHU_SECRET")

    data = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content
                }
            ]
        }
    }

    if secret:
        timestamp = str(int(time.time()))
        sign = gen_feishu_sign(secret, timestamp)
        data["timestamp"] = timestamp
        data["sign"] = sign

    status, resp = http_post(webhook_url, data)
    if status == 200:
        result = json.loads(resp)
        return result.get("code") == 0 or result.get("StatusCode") == 0
    return False


# ============ 钉钉 ============

def gen_dingtalk_sign(secret: str, timestamp: str) -> str:
    """生成钉钉签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    return urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))


def send_dingtalk(env: dict, title: str, content: str) -> bool:
    """发送钉钉通知"""
    webhook_url = get_config(env, "DINGTALK_WEBHOOK_URL")
    if not webhook_url:
        return False

    secret = get_config(env, "DINGTALK_SECRET")

    if secret:
        timestamp = str(int(time.time() * 1000))
        sign = gen_dingtalk_sign(secret, timestamp)
        separator = "&" if "?" in webhook_url else "?"
        webhook_url = f"{webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"### {title}\n{content}"
        }
    }

    status, resp = http_post(webhook_url, data)
    if status == 200:
        result = json.loads(resp)
        return result.get("errcode") == 0
    return False


# ============ 邮件 ============

def send_email(env: dict, title: str, content: str) -> bool:
    """发送邮件通知"""
    smtp_host = get_config(env, "SMTP_HOST")
    smtp_user = get_config(env, "SMTP_USER")
    smtp_password = get_config(env, "SMTP_PASSWORD")
    email_from = get_config(env, "EMAIL_FROM")
    email_to = get_config(env, "EMAIL_TO")

    if not all([smtp_host, smtp_user, smtp_password, email_from, email_to]):
        return False

    smtp_port = int(get_config(env, "SMTP_PORT", "465"))
    use_ssl = get_config(env, "SMTP_USE_SSL", "true").lower() == "true"

    recipients = [e.strip() for e in email_to.split(",") if e.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = title
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)

    html_content = f"""
    <html>
    <body>
        <h2>{title}</h2>
        <pre style="background-color: #f5f5f5; padding: 15px; border-radius: 5px;">
{content}
        </pre>
    </body>
    </html>
    """

    msg.attach(MIMEText(content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.sendmail(email_from, recipients, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}", file=sys.stderr)
        return False


# ============ 通知调度 ============

CHANNEL_HANDLERS = {
    "wecom": send_wecom,
    "feishu": send_feishu,
    "dingtalk": send_dingtalk,
    "email": send_email,
}


def send_notification(env: dict, title: str, content: str) -> dict:
    """发送通知到所有启用的渠道"""
    channels = get_enabled_channels(env)
    results = {}

    for channel in channels:
        handler = CHANNEL_HANDLERS.get(channel)
        if handler:
            try:
                results[channel] = handler(env, title, content)
            except Exception as e:
                print(f"Channel {channel} error: {e}", file=sys.stderr)
                results[channel] = False

    return results


def format_json_block(data: dict, limit: int = 1000) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)[:limit]


def truncate_text(text: str, limit: int = MAX_COMMAND_PREVIEW) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def sanitize_error_summary(text: str, limit: int = MAX_ERROR_SUMMARY) -> str:
    """生成适合通知的脱敏错误摘要。"""
    summary = " ".join(str(text or "").split())
    summary = URL_WITH_QUERY_PATTERN.sub(r"\1?[REDACTED]", summary)
    summary = SENSITIVE_QUOTED_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", summary)
    summary = SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", summary)
    summary = BEARER_PATTERN.sub("Bearer [REDACTED]", summary)
    summary = LONG_SECRET_PATTERN.sub("[REDACTED]", summary)
    return truncate_text(summary, limit)


def start_background_notification(
    data: dict,
    notify_script: Path | str | None = None,
) -> tuple[bool, str]:
    """后台启动通知脚本，返回 (是否启动成功, 错误信息)。"""
    script = Path(notify_script or __file__).resolve()
    try:
        subprocess.Popen(
            [sys.executable, str(script), json.dumps(data, ensure_ascii=False)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except (OSError, ValueError) as exc:
        return False, str(exc)
    return True, ""


def format_input_messages(messages) -> str:
    if not isinstance(messages, list):
        return truncate_text(str(messages or "(无)"), MAX_MESSAGE_PREVIEW)

    parts = []
    for item in messages:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content") or item.get("message") or ""
        else:
            text = str(item)
        if text:
            parts.append(str(text))
    return truncate_text("\n".join(parts) or "(无)", MAX_MESSAGE_PREVIEW)


def format_option_labels(option_labels: list[str], limit: int = 6) -> str:
    if not option_labels:
        return "(无)"

    labels = [f"{index}. {truncate_text(label, 80)}" for index, label in enumerate(option_labels[:limit], start=1)]
    if len(option_labels) > limit:
        labels.append(f"... 还有 {len(option_labels) - limit} 个选项")
    return "\n".join(labels)


def format_message(source: str, event_type: str, data: dict) -> tuple:
    """格式化通知消息，返回 (title, content)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if source == "claude-code":
        # Claude Code 直接传入 last_assistant_message 字段
        last_message = data.get("last_assistant_message", "")[:500]

        title = "🤖 Claude Code 任务完成"
        content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**会话ID**: {data.get('session_id', 'N/A')[:8]}...

**最后消息**:
{last_message or '(无内容)'}"""

    elif source == "kimi":
        hook_event = data.get("hook_event_name", event_type)

        if hook_event == "Stop":
            title = "🤖 Kimi 任务完成"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**会话ID**: {data.get('session_id', 'N/A')[:8]}...
**事件**: Agent 轮次结束"""
        elif hook_event == "Notification":
            notif_type = data.get("notification_type", "")
            notif_title = data.get("title", "")
            notif_body = data.get("body", "")[:800]
            severity = data.get("severity", "info")

            if notif_type == "permission_prompt":
                title = "🔔 Kimi 需要执行审批"
            else:
                title = f"🔔 Kimi 通知: {notif_title or notif_type}"

            content = f"""**时间**: {now}
**通知类型**: {notif_type}
**严重程度**: {severity}
**工作目录**: {data.get('cwd', 'N/A')}

**内容**:
{notif_body or '(无内容)'}"""
        else:
            title = f"🤖 Kimi 事件: {hook_event}"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**会话ID**: {data.get('session_id', 'N/A')[:8]}...

**原始数据**:
```json
{json.dumps(data, ensure_ascii=False, indent=2)[:1000]}
```"""

    elif source in {"codex", "codex-hook", "codex-wrapper"}:
        if event_type == "agent-turn-complete":
            title = "🤖 Codex 任务完成"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**线程**: {data.get('thread-id', data.get('thread_id', 'N/A'))}
**轮次**: {data.get('turn-id', data.get('turn_id', 'N/A'))}

**用户输入**:
{format_input_messages(data.get('input-messages', data.get('input_messages')))}

**最后回复**:
{truncate_text(data.get('last-assistant-message', data.get('last_assistant_message', '(无)')), 800)}"""
        elif event_type == "approval-required":
            title = "🔐 Codex 需要提权审批"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', data.get('workdir', 'N/A'))}
**会话**: {data.get('session_id', data.get('thread_id', 'N/A'))}
**轮次**: {data.get('turn_id', 'N/A')}
**工具**: {data.get('tool_name', 'N/A')}
**审批原因**: {truncate_text(data.get('description', data.get('justification', '(无)')), 300)}
**调用摘要**: `{truncate_text(data.get('command') or data.get('tool_input_summary') or data.get('cmd') or '(无)')}`"""
        elif event_type == "question-required":
            title = "❓ Codex 正在等你回答"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**线程**: {data.get('thread_id', 'N/A')}
**轮次**: {data.get('turn_id', 'N/A')}
**问题ID**: {data.get('question_id', 'N/A')}
**问题标题**: {data.get('question_header', '(无)')}
**提问工具**: {data.get('tool_name', 'N/A')}
**问题数量**: {data.get('question_count', 1)}

**问题**:
{truncate_text(data.get('question_text', '(无)'), 500)}

**选项**:
{format_option_labels(data.get('option_labels') or [])}"""
        elif event_type == "upstream-response-failed":
            category_labels = {
                "authentication": "认证失败",
                "rate-limit": "限流或额度不足",
                "stream-connect": "响应流连接失败",
                "stream-disconnected": "响应流中断",
                "retry-exhausted": "重试耗尽",
                "http-connection": "HTTP 或连接失败",
                "upstream-error": "其他上游错误",
            }
            category = data.get("error_category", "upstream-error")
            status = data.get("http_status") or "N/A"
            title = "🚨 Codex 上游响应失败"
            content = f"""**时间**: {now}
**工作目录**: {data.get('cwd', 'N/A')}
**线程**: {data.get('thread_id', 'N/A')}
**轮次**: {data.get('turn_id', 'N/A')}
**错误类别**: {category_labels.get(category, category)}
**HTTP 状态**: {status}
**重试耗尽**: {'是' if data.get('retry_exhausted') else '否'}

**错误摘要**:
{sanitize_error_summary(data.get('summary', '(无)'))}"""
        else:
            title = f"🤖 Codex 事件: {event_type}"
            content = f"""**时间**: {now}
**事件类型**: {event_type}

**原始数据**:
```json
{format_json_block(data)}
```"""

    else:
        title = "🤖 AI 任务完成"
        content = f"""**时间**: {now}
**来源**: {source}

**数据**:
```json
{format_json_block(data)}
```"""

    return title, content


def parse_input() -> tuple:
    """
    解析输入，返回 (source, event_type, data)

    Claude Code: 通过 stdin 传入 JSON
    Codex: 通过命令行参数传入 JSON
    """
    data = {}
    source = "unknown"
    event_type = ""

    # 尝试从命令行参数读取 (Codex 方式)
    if len(sys.argv) > 1:
        try:
            data = json.loads(sys.argv[1])
            source = data.get("source", "codex")
            event_type = data.get("type", "")

            # Codex 只处理已知事件
            if source == "codex" and event_type != "agent-turn-complete":
                return source, event_type, None
            if source == "codex-hook" and event_type != "approval-required":
                return source, event_type, None
            if source == "codex-wrapper" and event_type not in {
                "question-required",
                "upstream-response-failed",
            }:
                return source, event_type, None

        except json.JSONDecodeError:
            pass

    # 尝试从 stdin 读取 (Claude Code / Kimi CLI 方式)
    if not data and not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read()
            if stdin_data.strip():
                data = json.loads(stdin_data)
                if "hook_event_name" in data:
                    source = "kimi"
                    event_type = data.get("hook_event_name", "")
                else:
                    source = "claude-code"
                    event_type = "stop"
        except json.JSONDecodeError:
            pass

    return source, event_type, data


def main() -> int:
    # 加载配置
    env = load_env()

    # 检查是否有启用的渠道
    channels = get_enabled_channels(env)
    if not channels:
        print("No notification channels enabled", file=sys.stderr)
        return 0

    # 解析输入
    source, event_type, data = parse_input()

    # Kimi Stop hook 防循环：如果 stop_hook_active 为 true，跳过通知
    if source == "kimi" and event_type == "Stop" and data.get("stop_hook_active"):
        return 0

    if data is None:
        # 事件类型不需要处理
        return 0

    if not data:
        print("No valid input data", file=sys.stderr)
        return 1

    # 格式化消息
    title, content = format_message(source, event_type, data)

    # 发送通知
    results = send_notification(env, title, content)

    # 输出结果
    success_count = sum(1 for v in results.values() if v)
    print(f"Notifications sent: {success_count}/{len(results)}")
    for channel, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {channel}")

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
