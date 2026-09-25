"""Plan repair — broken model JSON must EXECUTE, never dump raw text.

User screenshot (v1.1.5): the model's plan came back with every [ ] { }
missing and the raw markup was printed into the chat while NO action ran.
parse_plan must salvage the intended say+actions and run them.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BROKEN = ('"say": "Focusing on Spotify and typing \'Kanye West violent '
          'crimes\' to search. Pressing Enter to submit.", "actions": '
          '"tool": "open_app", "args": "name": "spotify", "tool": '
          '"type_text", "args": "text": "Kanye West violent crimes", '
          '"tool": "press_keys", "args": "keys": "enter"')


class TestPlanRepair(unittest.TestCase):
    def test_screenshot_broken_json_repairs_into_runnable_plan(self):
        from jarvis.brain import parse_plan
        plan = parse_plan(BROKEN)
        self.assertEqual([a["tool"] for a in plan.actions],
                         ["open_app", "type_text", "press_keys"])
        self.assertEqual(plan.actions[0]["args"], {"name": "spotify"})
        self.assertEqual(plan.actions[1]["args"],
                         {"text": "Kanye West violent crimes"})
        self.assertEqual(plan.actions[2]["args"], {"keys": "enter"})
        self.assertIn("Focusing on Spotify", plan.say)
        self.assertNotIn('"tool"', plan.say)      # no raw markup to the user

    def test_valid_json_still_parses_identically(self):
        from jarvis.brain import parse_plan
        plan = parse_plan('{"say": "Hi.", "actions": '
                          '[{"tool": "open_app", "args": {"name": "spotify"}}]}')
        self.assertEqual(plan.say, "Hi.")
        self.assertEqual(plan.actions[0]["args"], {"name": "spotify"})

    def test_think_wrapped_json_parses(self):
        from jarvis.brain import parse_plan
        plan = parse_plan('<think>planning...</think>```json\n'
                          '{"say": "On it.", "actions": []}\n```')
        self.assertEqual(plan.say, "On it.")

    def test_unsalvageable_never_echoes_markup(self):
        from jarvis.brain import parse_plan
        plan = parse_plan('{"say": "ummm" "actions": [oops')
        self.assertNotIn('"say"', plan.say)
        self.assertNotIn('"actions"', plan.say)

    def test_plain_conversation_unchanged(self):
        from jarvis.brain import parse_plan
        plan = parse_plan('Right away, sir.')
        self.assertEqual(plan.say, "Right away, sir.")
        self.assertEqual(plan.actions, [])


class TestVisibleSwitching(unittest.TestCase):
    def test_focus_window_is_a_real_tool(self):
        from jarvis import skills
        skills.load_all()
        self.assertIn("focus_window", skills.build_catalog())

    def test_persona_advertises_media_play_and_switching(self):
        from jarvis.persona import build_system_prompt
        from jarvis.store import Settings
        p = build_system_prompt(Settings(), "- click {name}")
        self.assertIn("ALWAYS use `media_play`", p)
        self.assertIn("`focus_window`", p)


class TestVersionBumped(unittest.TestCase):
    def test_version_is_1_1_6(self):
        from jarvis import store
        self.assertEqual(store.VERSION, "1.1.6")


if __name__ == "__main__":
    unittest.main(verbosity=2)
