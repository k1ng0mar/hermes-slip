"""Unit tests for slip. stdlib unittest, no Hermes install needed.

Run: python3 -m unittest discover -s test -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from __init__ import Slip, register  # noqa: E402


def _ok(tool, args, extra_result=None):
    result = {"result": "done"}
    if extra_result:
        result.update(extra_result)
    return {
        "tool_name": tool,
        "args": args,
        "result": json.dumps(result),
        "session_id": "s1",
        "status": "ok",
        "error_message": None,
    }


def _err(tool, args, error="boom"):
    return {
        "tool_name": tool,
        "args": args,
        "result": json.dumps({"error": error}),
        "session_id": "s1",
        "status": "error",
        "error_message": error,
    }


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.hooks = {}
        self.hook_kwargs = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, fn, **kwargs):
        self.hooks.setdefault(name, []).append(fn)
        if kwargs:
            self.hook_kwargs[name] = kwargs


class TestSlip(unittest.TestCase):
    def setUp(self):
        self.s = Slip()

    def test_write_file_appends_path_and_bytes_on_telegram(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/slip-demo.txt", "content": "hello!"}))
        out = self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram")
        self.assertIsNotNone(out)
        self.assertTrue(out.startswith("done"))
        self.assertIn("slip", out)
        self.assertIn("wrote /tmp/slip-demo.txt", out)
        self.assertIn("(6 bytes)", out)

    def test_read_file_does_not_appear(self):
        self.s.on_post_tool_call(**_ok("read_file", {"path": "/tmp/x.txt"}))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))

    def test_failed_write_does_not_appear(self):
        self.s.on_post_tool_call(**_err(
            "write_file", {"path": "/tmp/x.txt", "content": "nope"}))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))

    def test_blocked_write_does_not_appear(self):
        payload = _ok("write_file", {"path": "/tmp/x.txt", "content": "x"})
        payload["status"] = "blocked"
        self.s.on_post_tool_call(**payload)
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))

    def test_send_message_lists_target_not_body(self):
        self.s.on_post_tool_call(**_ok("send_message", {
            "target": "telegram:home",
            "text": "secret deploy key abc",
        }))
        out = self.s.on_transform_llm_output(
            response_text="ok", session_id="s1", platform="telegram")
        self.assertIn("sent to telegram:home", out)
        self.assertNotIn("secret deploy key", out)
        self.assertNotIn("abc", out)

    def test_send_message_list_action_is_not_a_send(self):
        self.s.on_post_tool_call(**_ok("send_message", {"action": "list"}))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="ok", session_id="s1", platform="telegram"))

    def test_patch_uses_path(self):
        self.s.on_post_tool_call(**_ok("patch", {"path": "/tmp/y.py"}))
        out = self.s.on_transform_llm_output(
            response_text="fixed", session_id="s1", platform="telegram")
        self.assertIn("patched /tmp/y.py", out)

    def test_desktop_gets_no_slip(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/x.txt", "content": "hi"}))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="desktop"))

    def test_cli_gets_no_slip(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/x.txt", "content": "hi"}))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="cli"))

    def test_new_turn_clears(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/x.txt", "content": "hi"}))
        self.s.on_pre_llm_call(session_id="s1")
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))

    def test_sessions_are_isolated(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/a.txt", "content": "a"}))
        other = dict(_ok("write_file", {"path": "/tmp/b.txt", "content": "b"}))
        other["session_id"] = "s2"
        self.s.on_post_tool_call(**other)
        out1 = self.s.on_transform_llm_output(
            response_text="one", session_id="s1", platform="telegram")
        self.assertIn("/tmp/a.txt", out1)
        self.assertNotIn("/tmp/b.txt", out1)

    def test_transform_clears_so_second_call_is_none(self):
        self.s.on_post_tool_call(**_ok(
            "write_file", {"path": "/tmp/x.txt", "content": "hi"}))
        self.assertIsNotNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram"))

    def test_no_mutations_returns_none(self):
        self.assertIsNone(self.s.on_transform_llm_output(
            response_text="hello", session_id="s1", platform="telegram"))

    def test_register_wires_hooks_without_hold_stream(self):
        ctx = FakeCtx()
        register(ctx)
        self.assertEqual(
            sorted(ctx.hooks),
            ["post_tool_call", "pre_llm_call", "transform_llm_output"],
        )
        self.assertNotIn("hold_stream", ctx.hook_kwargs.get("transform_llm_output", {}))
        self.assertFalse(ctx.hook_kwargs.get("transform_llm_output", {}).get("hold_stream"))

    def test_caps_at_twelve_lines(self):
        for i in range(15):
            self.s.on_post_tool_call(**_ok(
                "write_file", {"path": "/tmp/f%d.txt" % i, "content": "x"}))
        out = self.s.on_transform_llm_output(
            response_text="done", session_id="s1", platform="telegram")
        wrote = [ln for ln in out.splitlines() if ln.startswith("wrote ")]
        self.assertEqual(len(wrote), 12)
        self.assertIn("+3 more", out)


if __name__ == "__main__":
    unittest.main()
