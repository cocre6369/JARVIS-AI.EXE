"""JarvisCore — wires model, skills, voice, guardrails and UI together."""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from . import skills
from .brain import Brain, Plan
from .executor import Executor
from .guardrails import AbortToken, check_user_request
from .ollama_client import OllamaClient, OllamaError
from .persona import refusal_message
from .store import ActivityLog, ReminderStore, SessionStore, Settings
from .voice import SpeechToText, TTSEngine


class JarvisCore:
    """UI-agnostic controller. All heavy work happens on worker threads;
    callbacks into the UI are made through ``ui_call(fn, *args)`` which the
    HUD implements as a thread-safe dispatch."""

    def __init__(self, ui, settings: Optional[Settings] = None) -> None:
        self.ui = ui
        self.settings = settings or Settings.load()
        self.activity = ActivityLog()
        self.reminders = ReminderStore()
        self.session = SessionStore()
        self.abort = AbortToken()
        self.client = OllamaClient(self.settings.ollama_url)

        skills.load_all()
        skills.misc.configure(self.settings, self._on_reminder_due)

        project_prompt = _load_project_prompt()
        self.brain = Brain(self.client, self.settings,
                           skills.build_catalog(), project_prompt)
        self.brain.restore(self.session.load_messages())
        self.executor = Executor(self.settings, self.abort, _UIAdapter(self))
        self.tts = TTSEngine(self.settings)
        self.stt = SpeechToText(self.settings)

        self.busy = False
        self._worker: Optional[threading.Thread] = None
        self._tick = threading.Thread(target=self._reminder_loop, daemon=True)
        self._tick.start()

    # ------------------------------------------------------------ UI bridge
    def call(self, fn: Callable, *args: Any) -> None:
        self.ui.call(fn, *args)

    def log(self, kind: str, text: str) -> None:
        self.activity.append(kind, text)

    def speak(self, text: str) -> None:
        self.log("say", text)
        self.call(self.ui.add_message, "jarvis", text)
        self.tts.speak(text)

    # ------------------------------------------------------------- commands
    def submit(self, text: str, source: str = "text") -> None:
        """Queue a user command (from text box or voice)."""
        text = (text or "").strip()
        if not text:
            return
        if self.busy:
            self.call(self.ui.narrate,
                      "Still working on the previous request, sir.")
            return
        self.abort.clear()
        self.log("user", text, source=source)
        self.call(self.ui.add_message, "user", text)
        self._worker = threading.Thread(target=self._run, args=(text,),
                                        daemon=True)
        self._worker.start()

    def _run(self, text: str) -> None:
        self.busy = True
        try:
            self.call(self.ui.set_state, "THINKING")

            # Hard guardrail BEFORE the model is even consulted.
            verdict = check_user_request(text)
            if not verdict.ok:
                msg = refusal_message(verdict.reason, self.settings)
                self.log("blocked", f"Refused request ({verdict.reason})")
                self.call(self.ui.set_state, "BLOCKED")
                self.speak(msg)
                return

            plan = self._plan_step(text)
            all_results: List[Dict[str, Any]] = []
            for round_no in range(3):
                if plan.say:
                    self.speak(plan.say)
                if not plan.actions:
                    break
                self.call(self.ui.set_state, "ACTING")
                results = self.executor.execute(plan.actions)
                all_results.extend(results)
                if self.abort.aborted:
                    self.speak("Aborting as ordered. I stand down.")
                    break
                needs_followup = any(r.get("returns_data") or not r.get("ok")
                                     for r in results)
                if not needs_followup or round_no == 2:
                    break
                self.call(self.ui.set_state, "THINKING")
                plan = self._follow_up(results)

            if not plan.say and not all_results:
                self.speak("Nothing to report.")
        except OllamaError as exc:
            self.log("error", str(exc))
            self.call(self.ui.set_state, "ERROR")
            self.speak(str(exc))
        except Exception as exc:  # never take the app down
            self.log("error", traceback.format_exc(limit=3))
            self.call(self.ui.set_state, "ERROR")
            self.speak(f"A glitch in the matrix, I'm afraid: {exc}")
        finally:
            self.session.save_messages(self.brain.export())
            self.busy = False
            self.call(self.ui.set_state, "IDLE")

    def _plan_step(self, text: str) -> Plan:
        try:
            return self.brain.ask(text)
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaError(f"Model error: {exc}") from exc

    def _follow_up(self, results: List[Dict[str, Any]]) -> Plan:
        try:
            return self.brain.follow_up(results)
        except Exception:
            return Plan(say="", actions=[])

    # ------------------------------------------------------------- voice
    def listen_once(self) -> None:
        """Record one utterance and run it as a command."""
        if self.busy:
            return
        self.abort.clear()

        def work() -> None:
            self.call(self.ui.set_state, "LISTENING")
            self.call(self.ui.narrate, "Listening…")
            text = self.stt.listen(
                seconds=7.0,
                on_level=lambda lvl: self.call(self.ui.set_level, lvl),
                on_status=lambda s: self.call(self.ui.narrate, "Transcribing…"),
            )
            if not text:
                self.call(self.ui.set_state, "IDLE")
                self.call(self.ui.narrate, "I didn't quite catch that.")
                return
            self.submit(text, source="voice")

        threading.Thread(target=work, daemon=True).start()

    def listen_push(self) -> None:
        """Begin push-to-talk recording (button pressed)."""
        if self.busy:
            return
        self._ptt_stop = threading.Event()
        self._ptt_text: List[str] = []

        def work() -> None:
            self.call(self.ui.set_state, "LISTENING")
            text = self.stt.listen(
                seconds=30.0,
                stop_event=self._ptt_stop,
                on_level=lambda lvl: self.call(self.ui.set_level, lvl),
                on_status=lambda s: self.call(self.ui.narrate, "Transcribing…"),
            )
            if text:
                self.submit(text, source="voice")
            else:
                self.call(self.ui.set_state, "IDLE")

        self._ptt_thread = threading.Thread(target=work, daemon=True)
        self._ptt_thread.start()

    def listen_release(self) -> None:
        """Button released — stop recording."""
        ev = getattr(self, "_ptt_stop", None)
        if ev is not None:
            ev.set()

    def abort_now(self) -> None:
        self.abort.abort()
        self.log("abort", "User hit STOP")
        self.tts.stop()

    # ---------------------------------------------------------- reminders
    def _on_reminder_due(self, text: str) -> None:
        self.log("reminder", text)
        self.call(self.ui.notify, text)
        self.speak(text)
        self.call(self.ui.flash_alert, text)

    def _reminder_loop(self) -> None:
        while True:
            time.sleep(5)
            try:
                skills.misc.pump_due_reminders()
            except Exception:
                pass

    # ------------------------------------------------------------- model
    def reload_settings(self) -> None:
        self.settings.save()
        self.client.base_url = self.settings.ollama_url.rstrip("/")
        self.brain.settings = self.settings
        self.brain.reload()
        self.tts.reload()
        self.executor.settings = self.settings

    def shutdown(self) -> None:
        self.abort.abort()
        self.tts.stop()
        self.session.save_messages(self.brain.export())


class _UIAdapter:
    """Executor-facing UI protocol → JarvisCore (which forwards thread-safe)."""

    def __init__(self, core: JarvisCore) -> None:
        self.core = core

    def narrate(self, text: str) -> None:
        self.core.log("step", text)
        self.core.call(self.core.ui.narrate, text)

    def say(self, text: str) -> None:
        self.core.speak(text)

    def log(self, kind: str, text: str) -> None:
        self.core.log(kind, text)

    def confirm(self, title: str, message: str) -> bool:
        return self.core.ui.confirm(title, message)

    def confirm_typed(self, title: str, message: str, word: str) -> bool:
        return self.core.ui.confirm_typed(title, message, word)

    def open_settings(self) -> None:
        self.core.call(self.core.ui.open_settings)


def _load_project_prompt() -> Optional[str]:
    from pathlib import Path

    from .store import resource_dir

    for candidate in (resource_dir() / "jarvis_ai_prompt.txt",
                      Path.cwd() / "jarvis_ai_prompt.txt"):
        try:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return None
