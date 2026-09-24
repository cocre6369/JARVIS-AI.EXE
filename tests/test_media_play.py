"""media_play — the verified search → read → click playback ritual.

User report: 'played the first song on spotify', 'opens the app then gives
up'. media_play must pick rows by token match (never generic 'Play'/'Your
Mix'), and click failures must show what WAS on screen so the brain can
correct itself instead of giving up.
"""
import inspect
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestMediaPlay(unittest.TestCase):
    def test_registered_in_catalog(self):
        from jarvis import skills
        skills.load_all()
        self.assertIn("media_play", skills.build_catalog())

    def test_needs_a_query(self):
        from jarvis.skills.media import media_play
        self.assertIn("ERROR", media_play("spotify", ""))

    def test_quick_and_graceful_off_windows(self):
        from jarvis.skills.media import media_play
        t0 = time.time()
        out = media_play("spotify", "violent crimes kanye west")
        self.assertIsInstance(out, str)
        self.assertTrue(out)
        self.assertLess(time.time() - t0, 5.0)   # must never hang

    def test_row_scoring_has_common_sense(self):
        from jarvis.skills.media import _row_score, _tokens
        q = _tokens("violent crimes kanye west")
        self.assertEqual(_row_score("Play", q), 0.0)          # generic button
        self.assertEqual(_row_score("Your Top Mix", q), 0.0)  # user's own mix
        self.assertEqual(_row_score("Made For You", q), 0.0)
        self.assertEqual(_row_score("Violent Crimes - Kanye West", q), 1.0)
        self.assertEqual(_row_score("Violent Crimes", q), 0.5)
        self.assertEqual(_row_score("Kanye West Essentials", q), 0.5)

    def test_persona_common_sense_rules(self):
        from jarvis.persona import build_system_prompt
        from jarvis.store import Settings
        p = build_system_prompt(Settings(), "- click {name}")
        self.assertIn("media_play", p)
        self.assertIn('NEVER click a bare "Play" button', p)
        self.assertIn("simplify the query", p)
        self.assertIn("not my playlist", p)     # correction example present


class TestClickFailureShowsScreen(unittest.TestCase):
    def test_click_failure_lists_visible_labels(self):
        from jarvis.skills import click
        src = inspect.getsource(click.click)
        self.assertIn("_visible_labels", src)   # failure path reads the screen

    def test_visible_labels_safe_off_windows(self):
        from jarvis.skills.click import _visible_labels
        self.assertEqual(_visible_labels(5), [])


class TestVersionBumped(unittest.TestCase):
    def test_version_is_1_1_4(self):
        from jarvis import store
        self.assertEqual(store.VERSION, "1.1.4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
