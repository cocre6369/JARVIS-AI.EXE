"""Smarts package v1.1.9 — self-correcting plans + qwen3 focus switch.

'user says the ai is still dumb': the brain now (1) retries once with a
corrective nudge when it fumbles plan JSON instead of dead-ending, (2)
switches qwen3's runaway <think> mode off (/no_think) for faster, cleaner
plans, and (3) media_play simplifies its own search and retries before
ever reporting failure.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MEDIA = (ROOT / "jarvis" / "skills" / "media.py").read_text(encoding="utf-8")


class FakeClient:
    """Scripted OllamaClient stand-in counting chat() calls."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, model, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0)


class TestQwen3Focus(unittest.TestCase):
    def test_no_think_added_for_qwen3(self):
        from jarvis.brain import effective_system_prompt
        p = effective_system_prompt("qwen3:14b", "Be a butler.")
        self.assertTrue(p.endswith("/no_think"))

    def test_other_models_untouched(self):
        from jarvis.brain import effective_system_prompt
        self.assertEqual(effective_system_prompt("qwen3:8b-butler", "x")
                         if False else
                         effective_system_prompt("llama3:8b", "Be a butler."),
                         "Be a butler.")

    def test_idempotent(self):
        from jarvis.brain import effective_system_prompt
        once = effective_system_prompt("qwen3:14b", "Be a butler.")
        self.assertEqual(effective_system_prompt("qwen3:14b", once), once)

    def test_brain_applies_it(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        brain = Brain(FakeClient([]), Settings(), "- click {name}")
        self.assertTrue(brain.system_prompt.endswith("/no_think"))


class TestPlanRetry(unittest.TestCase):
    def test_fumbled_plan_gets_one_corrective_retry(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        bad = '"say": "Hmm" "actions": oops'          # markup, unsalvageable
        good = ('{"say": "On it.", "actions": '
                '[{"tool": "open_app", "args": {"name": "spotify"}}]}')
        client = FakeClient([bad, good])
        brain = Brain(client, Settings(), "- click {name}")
        plan = brain.ask("open spotify and play violent crimes")
        self.assertEqual(len(client.calls), 2)        # retried exactly once
        self.assertEqual(plan.actions[0]["tool"], "open_app")
        self.assertEqual(plan.actions[0]["args"], {"name": "spotify"})

    def test_good_plan_needs_no_retry(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        good = '{"say": "Hi.", "actions": []}'
        client = FakeClient([good])
        Brain(client, Settings(), "- click {name}").ask("hello")
        self.assertEqual(len(client.calls), 1)

    def test_plain_chat_never_triggers_retry(self):
        from jarvis.brain import Brain
        from jarvis.store import Settings
        client = FakeClient(["Right away, sir."])
        plan = Brain(client, Settings(), "- click {name}").ask("hello")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(plan.say, "Right away, sir.")


class TestMediaSelfSimplify(unittest.TestCase):
    def test_ritual_simplifies_and_retries(self):
        self.assertIn("search_and_pick(query)", MEDIA)
        self.assertIn('search_and_pick(" ".join(tokens[:2]))', MEDIA)
        self.assertIn("simplifying the search", MEDIA)


class TestVersionBumped(unittest.TestCase):
    def test_version_is_1_1_9(self):
        from jarvis import store
        self.assertEqual(store.VERSION, "1.1.9")


if __name__ == "__main__":
    unittest.main(verbosity=2)
