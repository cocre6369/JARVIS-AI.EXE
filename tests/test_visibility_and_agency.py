"""v1.2.0 — visibility + forced agency.

User: 'too difficult to see whether the app is working' and 'not even
trying to actually use your device stuff'. JARVIS now shows every step in
a big always-visible strip + tray balloons, and the brain gets an agency
nudge when it merely TALKS about an actionable request.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HUD = (ROOT / "jarvis" / "ui" / "hud.py").read_text(encoding="utf-8")
TRAY = (ROOT / "jarvis" / "ui" / "tray.py").read_text(encoding="utf-8")
APP = (ROOT / "jarvis" / "app.py").read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, model, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0)


class TestAgencyNudge(unittest.TestCase):
    def test_talk_only_gets_one_agency_retry(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        talk = "Sure! I would open Spotify for you right away."
        good = ('{"say": "On it.", "actions": '
                '[{"tool": "open_app", "args": {"name": "spotify"}}]}')
        client = FakeClient([talk, good])
        plan = Brain(client, Settings(), "- click {name}").ask(
            "open spotify and play violent crimes")
        self.assertEqual(len(client.calls), 2)       # nudged exactly once
        self.assertEqual(plan.actions[0]["tool"], "open_app")

    def test_plain_chat_never_nudged(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        client = FakeClient(["Right away, sir."])
        Brain(client, Settings(), "- click {name}").ask("hello there friend")
        self.assertEqual(len(client.calls), 1)

    def test_persistent_talk_keeps_first_say(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        client = FakeClient(["Sure, I would open Spotify.", "I really would."])
        plan = Brain(client, Settings(), "- click {name}").ask(
            "open spotify")
        self.assertEqual(plan.say, "Sure, I would open Spotify.")
        self.assertEqual(len(client.calls), 2)

    def test_action_regex_scope(self):
        from jarvis.brain import _ACTION_RE as A
        self.assertTrue(A.search("open spotify and play x"))
        self.assertTrue(A.search("set the volume"))
        self.assertFalse(A.search("hello there friend"))
        self.assertFalse(A.search("what is spotify exactly?"))


class TestVisibility(unittest.TestCase):
    def test_hud_has_persistent_step_strip(self):
        self.assertIn("self.step_strip = tk.Label(", HUD)
        self.assertIn('self.step_strip.configure(text=f"\u25b6  {text}")', HUD)
        self.assertIn("\u2713  {self._last_narration}", HUD)

    def test_tray_notify_is_best_effort(self):
        self.assertIn("def notify(title: str, text: str) -> bool:", TRAY)
        self.assertIn('hasattr(_tray, "notify")', TRAY)

    def test_app_announces_finish_and_errors(self):
        self.assertEqual(APP.count("tray_mod.notify("), 2)


class TestVersionBumped(unittest.TestCase):
    def test_version_is_1_2_0(self):
        from jarvis import store
        self.assertEqual(store.VERSION, "1.2.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
