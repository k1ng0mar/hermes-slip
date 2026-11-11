"""Slip: a mutation list on the final reply for messengers that hide tool calls.

Desktop, Conduit, the TUI and the CLI already show every tool. Telegram,
WhatsApp, Signal and SMS do not, so a write can land and the user only
sees "done". Slip watches post_tool_call, keeps a per-session list of
writes and sends (not reads), and appends it in transform_llm_output.
pre_llm_call clears the list for the next turn.

No credentials, no network, no disk. The list lives in memory. Failed or
blocked calls are ignored. send_message bodies are never copied onto the
slip. transform_llm_output is not registered with hold_stream: a bug here
must not withhold the reply.
"""

import json
import threading

__all__ = ["Slip", "register", "QUIET_PLATFORMS"]

QUIET_PLATFORMS = frozenset({"cli", "tui", "desktop", "acp", "conduit"})
MAX_LINES = 12


def _session_id(kwargs):
    sid = kwargs.get("session_id")
    return sid if isinstance(sid, str) and sid else "_"


def _status_ok(status, result):
    if isinstance(status, str):
        state = status.strip().lower()
        if state in {"blocked", "error"}:
            return False
        if state == "ok":
            return True
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and parsed.get("error"):
            return False
    return status is None and result is not None


def _content_bytes(args):
    content = args.get("content") if isinstance(args, dict) else None
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    if isinstance(content, bytes):
        return len(content)
    return None


def _describe(tool_name, args):
    args = args if isinstance(args, dict) else {}
    if tool_name == "write_file":
        path = args.get("path") or "unknown"
        n = _content_bytes(args)
        if n is None:
            return "wrote %s" % path
        return "wrote %s (%d bytes)" % (path, n)
    if tool_name == "patch":
        return "patched %s" % (args.get("path") or "unknown")
    if tool_name == "send_message":
        action = str(args.get("action") or "send").strip().lower()
        if action in {"list", "react", "unreact"}:
            return None
        target = args.get("target") or "unknown"
        return "sent to %s" % target
    if tool_name == "memory":
        action = str(args.get("action") or "").strip().lower()
        if action in {"add", "replace", "remove"}:
            return "wrote memory"
        return None
    if tool_name == "skill_manage":
        name = args.get("name") or "skill"
        return "changed skill %s" % name
    if tool_name == "cronjob_manage":
        return "changed cron"
    return None


class Slip:
    """Per-session mutation list with a transform_llm_output footer."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lines = {}

    def on_post_tool_call(self, tool_name, args=None, result=None, **kwargs):
        if not _status_ok(kwargs.get("status"), result):
            return None
        line = _describe(tool_name, args)
        if not line:
            return None
        sid = _session_id(kwargs)
        with self._lock:
            bucket = self._lines.setdefault(sid, [])
            bucket.append(line)
        return None

    def on_pre_llm_call(self, **kwargs):
        sid = _session_id(kwargs)
        with self._lock:
            self._lines.pop(sid, None)
        return None

    def on_transform_llm_output(self, response_text=None, platform=None, **kwargs):
        plat = (platform or "").strip().lower()
        if plat in QUIET_PLATFORMS:
            return None
        if not isinstance(response_text, str) or not response_text:
            return None
        sid = _session_id(kwargs)
        with self._lock:
            lines = list(self._lines.pop(sid, []))
        if not lines:
            return None
        extra = 0
        if len(lines) > MAX_LINES:
            extra = len(lines) - MAX_LINES
            lines = lines[:MAX_LINES]
        body = "\n".join(lines)
        if extra:
            body += "\n+%d more" % extra
        return "%s\n\nslip\n%s" % (response_text.rstrip(), body)


def register(ctx):
    slip = Slip()
    ctx.register_hook("post_tool_call", slip.on_post_tool_call)
    ctx.register_hook("pre_llm_call", slip.on_pre_llm_call)
    ctx.register_hook("transform_llm_output", slip.on_transform_llm_output)
    return slip
