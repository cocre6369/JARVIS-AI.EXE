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
        # success must FINISH without an extra AI round-trip (user: "it
        # takes years to do stuff")
        self.assertFalse(skills.get_tool("media_play").returns_data)

    def test_chrome_never_pollutes_results(self):
        from jarvis.skills.click import _is_chrome
        self.assertTrue(_is_chrome("Minimise"))
        self.assertTrue(_is_chrome("restore"))
        self.assertFalse(_is_chrome("Violent Crimes"))
        self.assertFalse(_is_chrome("Kanye West"))

    def test_plays_with_double_click(self):
        # a single click usually only SELECTS a result row — playback needs
        # a double-click
        import inspect
        from jarvis.skills import media
        self.assertIn("DoubleClick", inspect.getsource(media._play_row))

    def test_needs_a_query(self):
        from jarvis.skills.media import media_play
        self.assertIn("ERROR", media_play("spotify", ""))

    @unittest.skipIf(sys.platform.startswith("win"),
                     "on Windows this test would run the real ritual "
                     "(launch apps on the CI machine)")
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

    def test_visible_labels_never_crash(self):
        # On Windows this runs the REAL UIA walk (never raises); off Windows
        # it must be a clean no-op. Either way: a bounded list, no crash.
        from jarvis.skills.click import _visible_labels
        out = _visible_labels(5)
        self.assertIsInstance(out, list)
        self.assertLessEqual(len(out), 5)

    @unittest.skipUnless(not sys.platform.startswith("win"),
                         "strict no-op behaviour is off-Windows only")
    def test_visible_labels_noop_off_windows(self):
        from jarvis.skills.click import _visible_labels
        self.assertEqual(_visible_labels(5), [])


class TestVersionBumped(unittest.TestCase):
    def test_version_is_1_1_6(self):
        from jarvis import store
        self.assertEqual(store.VERSION, "1.1.6")


if __name__ == "__main__":
    unittest.main(verbosity=2)
