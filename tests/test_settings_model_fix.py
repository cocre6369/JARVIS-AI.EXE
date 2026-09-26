"""Settings dialog model_box crash + model tag normalisation.

User report (v1.1.6, choosing qwen3:14b): "UI error: 'SettingsDialog'
object has no attribute 'model_box'" — the background model-list refresh
referenced a widget name that only exists in the first-run wizard.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HUD = (ROOT / "jarvis" / "ui" / "hud.py").read_text(encoding="utf-8")


class TestSettingsModelFix(unittest.TestCase):
    def test_dialog_owns_a_model_box(self):
        # the exact AttributeError from the user's report
        self.assertIn("self.model_box = w", HUD)
        self.assertIn('hasattr(self, "model_box")', HUD)

    def test_model_tag_normalised_on_save(self):
        self.assertIn("normalize_model_tag", HUD)

    def test_uninstalled_model_warns_with_pull_command(self):
        self.assertIn("ollama pull", HUD)


class TestNormalizeModelTag(unittest.TestCase):
    def test_space_after_colon(self):
        from jarvis.store import normalize_model_tag
        self.assertEqual(normalize_model_tag("qwen3: 14b"), "qwen3:14b")

    def test_whitespace_and_case(self):
        from jarvis.store import normalize_model_tag
        self.assertEqual(normalize_model_tag("  Qwen3:14B "), "qwen3:14b")

    def test_clean_tag_untouched(self):
        from jarvis.store import normalize_model_tag
        self.assertEqual(normalize_model_tag("qwen3:8b"), "qwen3:8b")
        self.assertEqual(normalize_model_tag("llama3-groq-tool-use:8b"),
                         "llama3-groq-tool-use:8b")

    def test_blank_stays_blank(self):
        from jarvis.store import normalize_model_tag
        self.assertEqual(normalize_model_tag(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
