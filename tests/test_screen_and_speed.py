"""Screen-reading + speed + app-ready-wait guarantees.

User report: 'it opens Spotify and immediately selects stuff before it
loads' and 'make the AI able to read your screen'. These tools make the
executor wait for and SEE the UI before acting on it.
"""
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestScreenReading(unittest.TestCase):
    def test_screen_state_registered(self):
        from jarvis import skills
        skills.load_all()
        catalog = skills.build_catalog()
        self.assertIn("screen_state", catalog)

    def test_screen_state_and_wait_are_safe_here(self):
        from jarvis.skills.click import screen_state, wait_for_window
        out = screen_state()
        self.assertIsInstance(out, str)
        self.assertTrue(out)
        t0 = time.time()
        ready = wait_for_window("spotify", timeout=0.5)
        self.assertLess(time.time() - t0, 5.0)  # never hangs
        self.assertIsInstance(ready, str)

    def test_persona_teaches_screen_reading_and_waits(self):
        from jarvis.persona import build_system_prompt
        from jarvis.store import Settings
        p = build_system_prompt(Settings(), "- click {name}")
        self.assertIn("screen_state", p)
        self.assertIn("READ THE SCREEN", p)
        self.assertIn("before its open_app action finishes", p)


class TestSpeedSettings(unittest.TestCase):
    def test_chat_payload_keeps_model_loaded_and_caps_tokens(self):
        from jarvis.ollama_client import _chat_payload
        body = _chat_payload("qwen3:8b", [{"role": "user", "content": "hi"}], 0.2)
        self.assertEqual(body.get("keep_alive"), -1)   # no wake-up pause
        self.assertLessEqual(body["options"].get("num_predict", 0), 800)


if __name__ == "__main__":
    unittest.main()
