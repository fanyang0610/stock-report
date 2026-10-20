"""WeChat delivery through bridge/wechat.mjs (Node helper around the cli-wechat-bridge npm package)."""

import json
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "bridge" / "wechat.mjs"
MAX_TEXT_BYTES = 4000
PASS_THROUGH = ("CLI_WECHAT_BRIDGE_CONTEXT_MAX_AGE_SECONDS",)


class DeliveryError(RuntimeError):
    pass


def _config() -> tuple[dict, str]:
    values = dotenv_values(ROOT / ".env")
    recipient = (values.get("EQUITYSIGNALS_WECHAT_RECIPIENT_ID") or "").strip()
    if not recipient:
        raise DeliveryError("EQUITYSIGNALS_WECHAT_RECIPIENT_ID is missing from .env")
    env = dict(os.environ)
    env.update({k: values[k] for k in PASS_THROUGH if values.get(k)})
    return env, recipient


def _scrub(text: str, recipient: str) -> str:
    """Never let the recipient id from .env reach logs or the terminal."""
    return text.replace(recipient, "<recipient>") if recipient else text


def _bridge(args: list[str], stdin: str | None = None, timeout: int = 90) -> dict:
    env, recipient = _config()
    args = [recipient if a == "{recipient}" else a for a in args]
    try:
        proc = subprocess.run(
            ["node", str(BRIDGE), *args], input=stdin, capture_output=True,
            text=True, env=env, cwd=ROOT, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise DeliveryError(f"bridge {args[0]} timed out after {timeout}s") from None
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        detail = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        raise DeliveryError(_scrub(f"bridge {args[0]} failed (exit {proc.returncode}): {detail}", recipient)) from None
    result.pop("recipient", None)
    if result.get("sent") is False:
        reason = (result.get("failed") or {}).get("reason", "unknown error")
        raise DeliveryError(_scrub(f"bridge {args[0]} not sent: {reason}", recipient))
    return result


def status() -> dict:
    """{ready, lastInboundAgeSeconds, ...}; ready means the bot can reply now."""
    return _bridge(["status"], timeout=30)


def poll(timeout_ms: int = 30000) -> list[dict]:
    """New messages from the recipient: [{id, text, receivedAt}] (the id has the recipient id taken out).
    Polling also refreshes the reply window."""
    _, recipient = _config()
    result = _bridge(["poll-messages", str(timeout_ms)], timeout=timeout_ms // 1000 + 30)
    return [
        {"id": _scrub(m["id"], recipient), "text": m["text"], "receivedAt": m["receivedAt"]}
        for m in result.get("messages", [])
        if m.get("recipientId") == recipient
    ]


def send_text(text: str) -> None:
    size = len(text.encode("utf-8"))
    if size > MAX_TEXT_BYTES:
        raise DeliveryError(f"text is {size} bytes, limit is {MAX_TEXT_BYTES}")
    _bridge(["notify", "--stdin", "{recipient}"], stdin=text)


def _send_media(command: str, path: Path, title: str | None) -> None:
    _, recipient = _config()
    payload = {"recipientId": recipient, "filePath": str(Path(path).resolve()), "title": title or Path(path).name}
    _bridge([command], stdin=json.dumps(payload), timeout=180)


def send_file(path: Path, title: str | None = None) -> None:
    _send_media("send-file", path, title)

