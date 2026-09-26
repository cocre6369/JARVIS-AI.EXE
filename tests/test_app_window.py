"""App-process verification — a browser tab must never stand in for the app.

User report (v1.1.7): 'Visible: Spotify Free; View site information; Addr'
— media_play matched a BROWSER TAB titled 'Spotify - Web Player' by title
substring, focused Chrome, and typed the search into the address bar
('I HAVE NO IDEA WHERE ITS SEARCHING').
"""
import inspect
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MEDIA = (ROOT / "jarvis" / "skills" / "media.py").read_text(encoding="utf-8")


class TestAppProcessVerification(unittest.TestCase):
    def test_window_found_by_process_never_title(self):
        # the ritual must verify the app's OWN PROCESS (Spotify.exe), not
        # match window titles — a 'Spotify - Web Player' browser tab has a
        # matching title but chrome.exe as its process
        self.assertIn("_app_window(canon", MEDIA)
        self.assertNotIn("wait_for_window(", MEDIA)
        src = inspect.getsource(
            __import__("jarvis.skills.media", fromlist=["_app_window"])
            ._app_window)
        self.assertIn("_process_of", src)      # process check in the matcher
        self.assertIn("IsWindowVisible", src)

    def test_helpers_safe_off_windows(self):
        from jarvis.skills.media import _app_window, _process_of
        t0 = time.time()
        self.assertEqual(_process_of(0), "")
        self.assertEqual(_app_window("spotify", timeout=0.3), "")
        self.assertLess(time.time() - t0, 5.0)

    def test_failure_names_the_desktop_app(self):
        self.assertIn("DESKTOP app", MEDIA)

    def test_launch_happens_only_after_process_check(self):
        i_check = MEDIA.find("_app_window(canon")
        i_launch = MEDIA.find("apps.launch_app(canon)")
        self.assertGreater(i_launch, 0)
        self.assertLess(i_check, i_launch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
