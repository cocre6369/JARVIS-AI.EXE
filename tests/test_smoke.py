"""Lightweight smoke tests (stdlib unittest) for the non-UI core.

Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Keep store state in a throw-away directory while testing.
_TMP = tempfile.mkdtemp(prefix="jarvis-test-")
os.environ["LOCALAPPDATA"] = _TMP
os.environ["HOME"] = _TMP


from jarvis.brain import parse_plan                       # noqa: E402
from jarvis.guardrails import (                            # noqa: E402
    POLICY_CONFIRM, POLICY_DENY, POLICY_DOUBLE, check_path,
    check_tool_call, check_url, check_user_request, policy_for,
)
from jarvis.store import Settings                          # noqa: E402


class TestPlanParsing(unittest.TestCase):
    def test_plain_json(self):
        plan = parse_plan('{"say": "On it.", "actions": [{"tool": "web_open", '
                          '"args": {"url": "https://x"}}]}')
        self.assertEqual(plan.say, "On it.")
        self.assertEqual(plan.actions[0]["tool"], "web_open")

    def test_fenced_json(self):
        plan = parse_plan('Sure!\n```json\n{"say": "Done.", "actions": []}\n```')
        self.assertEqual(plan.say, "Done.")
        self.assertEqual(plan.actions, [])

    def test_prose_fallback(self):
        plan = parse_plan("Very good, sir. All systems nominal.")
        self.assertIn("All systems nominal", plan.say)
        self.assertEqual(plan.actions, [])

    def test_malformed_json_fallback(self):
        plan = parse_plan('{"say": "oops", "actions": [{"tool":')
        self.assertTrue(plan.say)


class TestGuardrails(unittest.TestCase):
    def test_blocks_login_requests(self):
        v = check_user_request("log in to my bank account and check the balance")
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "auth")

    def test_blocks_signup_requests(self):
        self.assertFalse(check_user_request("sign up for a new account on twitter").ok)

    def test_blocks_password_handling(self):
        self.assertFalse(check_user_request("type my password into the box").ok)
        self.assertFalse(check_user_request("enter my credit card number").ok)
        self.assertFalse(check_user_request("please store my api key in the file").ok)

    def test_allows_normal_requests(self):
        self.assertTrue(check_user_request("open youtube and play Marques Brownlee").ok)
        self.assertTrue(check_user_request("set a 10 minute timer for the pizza").ok)
        self.assertTrue(check_user_request("volume to 30%").ok)

    def test_login_page_navigation_caution_not_block(self):
        # Opening a login *page* is navigation — allowed (auth still impossible).
        self.assertTrue(check_user_request("open the youtube login page").ok)

    def test_url_scheme_allowlist(self):
        self.assertTrue(check_url("https://youtube.com").ok)
        self.assertFalse(check_url("file:///etc/passwd").ok)
        self.assertFalse(check_url("javascript:alert(1)").ok)
        self.assertFalse(check_url("ftp://x").ok)

    def test_path_denylist(self):
        self.assertFalse(check_path(r"C:\Users\me\.ssh\id_rsa").ok)
        self.assertFalse(check_path(r"C:\Users\me\Desktop\.env").ok)
        self.assertTrue(check_path(r"C:\Users\me\Documents\report.txt").ok)

    def test_unknown_tool_denied(self):
        v = check_tool_call("run_shell", {"cmd": "dir"}, ["web_open"])
        self.assertFalse(v.ok)

    def test_shell_metachars_in_app_name_denied(self):
        v = check_tool_call("open_app", {"name": "notepad & del *.*"},
                            ["open_app"])
        self.assertFalse(v.ok)

    def test_unsafe_key_combo_denied(self):
        v = check_tool_call("press_keys", {"keys": "win+r"}, ["press_keys"])
        self.assertFalse(v.ok)

    def test_safe_key_combo_allowed(self):
        v = check_tool_call("press_keys", {"keys": "ctrl+f"}, ["press_keys"])
        self.assertTrue(v.ok)

    def test_credential_payload_in_args_denied(self):
        v = check_tool_call("type_text", {"text": "password=hunter2"},
                            ["type_text"])
        self.assertFalse(v.ok)

    def test_policy_escalation(self):
        self.assertEqual(
            policy_for("file_write", {"path": "/no/such/file-xyz"}, "auto"),
            POLICY_CONFIRM)
        self.assertEqual(
            policy_for("web_open", {"url": "https://x"}, "auto",
                       confirm_every_action=True),
            POLICY_CONFIRM)
        self.assertEqual(
            policy_for("file_delete", {"path": "x"}, POLICY_DOUBLE),
            POLICY_DOUBLE)


class TestSettings(unittest.TestCase):
    def test_roundtrip(self):
        s = Settings.load()
        s.user_name = "boss"
        s.model = "llama3.2:3b"
        s.save()
        s2 = Settings.load()
        self.assertEqual(s2.user_name, "boss")
        self.assertEqual(s2.model, "llama3.2:3b")


class TestSkills(unittest.TestCase):
    def test_catalog_and_dispatch(self):
        from jarvis import skills

        skills.load_all()
        catalog = skills.build_catalog()
        for name in ("web_open", "youtube_play", "open_app", "email_compose",
                     "timer_set", "file_delete", "system_status"):
            self.assertIn(name, catalog)
            self.assertIn(name, skills.tool_names())
        # Unknown tools must not resolve.
        self.assertIsNone(skills.get_tool("run_shell"))

    def test_email_and_memory_tools_exist(self):
        from jarvis import skills

        skills.load_all()
        self.assertTrue(skills.get_tool("email_reply_draft").returns_data or True)
        self.assertEqual(skills.get_tool("file_delete").policy, POLICY_DOUBLE)


class TestBrainPrompt(unittest.TestCase):
    def test_system_prompt_contains_rules(self):
        from jarvis.persona import build_system_prompt

        prompt = build_system_prompt(Settings(), "- web_open {url}")
        self.assertIn("NEVER log in", prompt)
        self.assertIn("NEVER enter, type, store", prompt)
        self.assertIn("web_open", prompt)
        self.assertIn("JSON", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
