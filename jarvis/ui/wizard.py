"""First-run setup wizard: Ollama → model → voice → safety → done."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, List

from ..store import VERSION
from ..voice import TTSEngine, available_engines
from . import theme

if TYPE_CHECKING:
    from .hud import JarvisHUD

PAGES = ["WELCOME", "OLLAMA", "MODEL", "VOICE", "SAFETY", "COMPLETE"]


class FirstRunWizard(tk.Toplevel):
    def __init__(self, master, hud: "JarvisHUD") -> None:
        super().__init__(master)
        self.hud = hud
        self.title(f"J.A.R.V.I.S. — First Run Setup  (v{VERSION})")
        self.configure(bg=theme.BG, highlightthickness=2,
                       highlightbackground=theme.CYAN_DIM)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        self.geometry("620x470")

        self.page = 0
        self.models: List[str] = []

        self.header = tk.Label(self, text="", font=theme.FONT_TITLE,
                               bg=theme.BG, fg=theme.CYAN, anchor="w")
        self.header.pack(fill="x", padx=24, pady=(18, 0))
        self.sub = tk.Label(self, text="", font=theme.FONT_SMALL, bg=theme.BG,
                            fg=theme.MUTED, anchor="w")
        self.sub.pack(fill="x", padx=24)
        self.body = tk.Frame(self, bg=theme.BG)
        self.body.pack(fill="both", expand=True, padx=24, pady=12)

        nav = tk.Frame(self, bg=theme.BG)
        nav.pack(fill="x", padx=24, pady=(0, 18))
        self.next_btn = theme.styled_button(nav, "NEXT ▸", self._next, "gold")
        self.next_btn.pack(side="right", padx=4)
        self.back_btn = theme.styled_button(nav, "◂ BACK", self._back, "ghost")
        self.back_btn.pack(side="right", padx=4)
        self.skip_btn = theme.styled_button(nav, "SKIP SETUP", self._skip,
                                            "ghost")
        self.skip_btn.pack(side="left", padx=4)
        self.step = tk.Label(nav, text="", font=theme.FONT_SMALL, bg=theme.BG,
                             fg=theme.MUTED)
        self.step.pack(side="left", padx=12)

        self._render()
        self.protocol("WM_DELETE_WINDOW", self._skip)

    # ------------------------------------------------------------- pages ---
    def _clear(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    def _alive(self, fn, *args):
        """Run fn on the UI thread — but only if this wizard still exists.
        Prevents 'invalid command name' when a background check lands after
        the wizard was closed."""
        import tkinter as tk

        def run():
            try:
                if self.winfo_exists():
                    fn(*args)
            except tk.TclError:
                pass

        try:
            self.after(0, run)
        except tk.TclError:
            pass

    def _text(self, content: str, **kw) -> None:
        tk.Label(self.body, text=content, font=theme.FONT_UI, bg=theme.BG,
                 fg=theme.TEXT, justify="left", anchor="w", wraplength=540,
                 **kw).pack(fill="x", pady=2)

    def _render(self) -> None:
        self._clear()
        page = PAGES[self.page]
        self.step.configure(text=f"STEP {self.page + 1} / {len(PAGES)}  ·  {page}")
        self.back_btn.configure(state="normal" if self.page else "disabled")
        self.next_btn.configure(text="FINISH ▸" if page == "COMPLETE" else "NEXT ▸")
        getattr(self, f"_page_{page.lower()}")()

    def _page_welcome(self) -> None:
        self.header.configure(text="◈  J.A.R.V.I.S.  ONLINE")
        self.sub.configure(text="Just A Rather Very Intelligent System — "
                                f"local instance {VERSION}")
        self._text("Welcome. I am Jarvis — your local, privacy-respecting "
                   "assistant.")
        self._text("Everything runs on YOUR machine: a local Ollama model "
                   "does the thinking, and I handle the keyboard, browser and "
                   "apps on your behalf. Nothing is sent to the cloud.")
        self._text("\nIn the next steps we will:")
        self._text("   1.  verify Ollama is installed and running\n"
                   "   2.  choose which local model drives me\n"
                   "   3.  test voice input/output\n"
                   "   4.  confirm the safety limits")

    def _page_ollama(self) -> None:
        self.header.configure(text="◈  OLLAMA CORE")
        self.sub.configure(text="the local model runtime")
        self.ollama_status = tk.Label(
            self.body, text="Checking for Ollama…", font=theme.FONT_UI,
            bg=theme.BG, fg=theme.GOLD, justify="left", anchor="w",
            wraplength=540)
        self.ollama_status.pack(fill="x", pady=8)
        row = tk.Frame(self.body, bg=theme.BG)
        row.pack(fill="x", pady=8)
        theme.styled_button(row, "CHECK AGAIN", self._check_ollama,
                            "cyan").pack(side="left", padx=4)
        theme.styled_button(row, "START OLLAMA", self._start_ollama,
                            "gold").pack(side="left", padx=4)
        theme.styled_button(row, "DOWNLOAD PAGE", self._open_download,
                            "ghost").pack(side="left", padx=4)
        self._check_ollama()

    def _page_model(self) -> None:
        self.header.configure(text="◈  SELECT MODEL")
        self.sub.configure(text="the brain behind the operation")
        self._text("Pick one of your installed Ollama models — or pull a new "
                   "one below.")
        self.model_box = ttk.Combobox(self.body, font=theme.FONT_UI, width=44)
        self.model_box.pack(fill="x", pady=6)
        if self.models:
            self.model_box.configure(values=self.models)
            current = self.hud.core.settings.model
            self.model_box.set(current if current in self.models
                               else self.models[0])
        else:
            self.model_box.set(self.hud.core.settings.model)
        pull = tk.Frame(self.body, bg=theme.BG)
        pull.pack(fill="x", pady=8)
        self.pull_entry = tk.Entry(pull, font=theme.FONT_UI, bg=theme.PANEL,
                                   fg=theme.TEXT, insertbackground=theme.CYAN,
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=theme.BORDER)
        self.pull_entry.insert(0, "qwen3:8b")
        self.pull_entry.pack(side="left", fill="x", expand=True, ipady=4)
        theme.styled_button(pull, "PULL", self._pull_model, "gold").pack(
            side="left", padx=6)
        self.pull_status = tk.Label(self.body, text=(
            "Smartest for commands: qwen3:8b (or qwen3:14b on 12GB+ GPU) · "
            "Pure tool specialist: llama3-groq-tool-use:8b · "
            "Lightest: llama3.2"), font=theme.FONT_SMALL, bg=theme.BG,
            fg=theme.MUTED, wraplength=540, justify="left")
        self.pull_status.pack(fill="x", pady=6)
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _page_voice(self) -> None:
        self.header.configure(text="◈  VOICE SYSTEMS")
        self.sub.configure(text="microphone in, British butler out")
        s = self.hud.core.settings
        self._text("Text mode always works. Voice uses fully local speech "
                   "recognition (Whisper if present, otherwise Windows speech).")
        self.tts_var = tk.BooleanVar(value=s.tts_enabled)
        tk.Checkbutton(self.body, text="Speak replies aloud (TTS)",
                       variable=self.tts_var, bg=theme.BG, fg=theme.TEXT,
                       activebackground=theme.BG, selectcolor=theme.PANEL,
                       font=theme.FONT_UI).pack(anchor="w", pady=4)
        voices = TTSEngine.list_voices()
        short = [v.split("|")[0].strip() for v in voices] or ["(default)"]
        self.voice_box = ttk.Combobox(self.body, values=short, width=44,
                                      font=theme.FONT_UI)
        self.voice_box.set(s.tts_voice or (short[0] if short else ""))
        self.voice_box.pack(fill="x", pady=4)
        engines = available_engines()
        self._text(f"Speech recognition engines detected: "
                   f"{', '.join(engines) if engines else 'none (text only)'}")
        row = tk.Frame(self.body, bg=theme.BG)
        row.pack(fill="x", pady=8)
        theme.styled_button(row, "▶ TEST VOICE", self._test_voice,
                            "cyan").pack(side="left", padx=4)
        theme.styled_button(row, "🎤 TEST MIC", self._test_mic,
                            "gold").pack(side="left", padx=4)
        self.voice_status = tk.Label(self.body, text="", font=theme.FONT_SMALL,
                                     bg=theme.BG, fg=theme.MUTED,
                                     wraplength=540, justify="left")
        self.voice_status.pack(fill="x", pady=4)

    def _page_safety(self) -> None:
        self.header.configure(text="◈  SAFETY LIMITS")
        self.sub.configure(text="hard-coded, not merely asked nicely")
        self._text("I will NEVER, under any circumstances:")
        self._text(
            "   ✕  log in, sign up or authenticate anywhere\n"
            "   ✕  enter, store or handle passwords, PINs, card numbers\n"
            "   ✕  touch SSH keys, password stores or .env files\n"
            "   ✕  delete or move your files without your explicit approval\n"
            "   ✕  send email — I only prepare drafts for YOUR review")
        self._text("\nEvery sensitive action asks for your explicit on-screen "
                   "confirmation first, and STOP (or Esc) halts me instantly.")
        self._text("\nYou are always in control: the mic only listens while you "
                   "hold the button (or Ctrl+Alt+Space), and Ctrl+Alt+P puts "
                   "me fully in standby at any moment — mic off, speech off, "
                   "automation halted.")
        self._text("\nHow should I address you?")
        self.name_entry = tk.Entry(self.body, font=theme.FONT_UI, width=20,
                                   bg=theme.PANEL, fg=theme.TEXT,
                                   insertbackground=theme.CYAN, relief="flat",
                                   highlightthickness=1,
                                   highlightbackground=theme.BORDER)
        self.name_entry.insert(0, self.hud.core.settings.user_name)
        self.name_entry.pack(anchor="w", pady=4, ipady=3)
        self.strict_var = tk.BooleanVar(
            value=self.hud.core.settings.confirm_every_action)
        tk.Checkbutton(self.body, text="Strict mode — confirm every single "
                                       "action (recommended)",
                       variable=self.strict_var, bg=theme.BG, fg=theme.GOLD,
                       activebackground=theme.BG, selectcolor=theme.PANEL,
                       font=theme.FONT_UI, justify="left").pack(anchor="w",
                                                                pady=6)

    def _page_complete(self) -> None:
        self.header.configure(text="◈  ALL SYSTEMS ONLINE")
        self.sub.configure(text="setup complete")
        self._text("Configuration saved. The HUD behind me is ready.")
        self._text("\nTry things like:\n"
                   "   “open YouTube and play Marques Brownlee”\n"
                   "   “open Spotify, play my daily mix, then open Notepad”\n"
                   "   “reply to this email saying I'll be there at 6”\n"
                   "   “set a 10 minute timer for the pizza”\n"
                   "   “volume to 30%”")
        self._text("\nHold 🎤 to speak, or simply type. Say the word, "
                   f"{self.hud.core.settings.user_name}.")

    # ------------------------------------------------------------ actions --
    def _next(self) -> None:
        if PAGES[self.page] == "MODEL":
            picked = self.model_box.get().strip()
            if picked:
                self.hud.core.settings.model = picked
        if PAGES[self.page] == "VOICE":
            s = self.hud.core.settings
            s.tts_enabled = bool(self.tts_var.get())
            s.tts_voice = self.voice_box.get().strip()
            s.tts_voice = "" if s.tts_voice.startswith("(") else s.tts_voice
        if PAGES[self.page] == "SAFETY":
            self.hud.core.settings.user_name = (
                self.name_entry.get().strip() or "sir")
            self.hud.core.settings.confirm_every_action = bool(
                self.strict_var.get())
        if PAGES[self.page] == "COMPLETE":
            self._finish()
            return
        self.page += 1
        self._render()

    def _back(self) -> None:
        if self.page:
            self.page -= 1
            self._render()

    def _skip(self) -> None:
        self._finish()

    def _finish(self) -> None:
        s = self.hud.core.settings
        s.first_run_done = True
        self.hud.core.reload_settings()
        self.hud.refresh_meta()
        self.hud.narrate("Setup complete. Ready.")
        self.destroy()

    # ---------------------------------------------------------- ollama -----
    def _check_ollama(self) -> None:
        self.ollama_status.configure(text="Checking for Ollama…", fg=theme.GOLD)
        client = self.hud.core.client

        def set_status(msg, color):
            self._alive(lambda: self.ollama_status.configure(text=msg, fg=color))

        def work():
            installed = client.is_installed()
            running = client.is_running()
            if running:
                try:
                    models = client.list_models()
                    msg = (f"✓ Ollama is running — {len(models)} model(s) "
                           f"installed.")
                    color = theme.GREEN
                except Exception:
                    msg = "✓ Ollama is running."
                    color = theme.GREEN
            elif installed:
                msg = ("○ Ollama is installed but not running — press "
                       "START OLLAMA.")
                color = theme.GOLD
            else:
                msg = ("✕ Ollama not found. Install it from "
                       "https://ollama.com/download then press CHECK AGAIN.")
                color = theme.RED
            set_status(msg, color)

        threading.Thread(target=work, daemon=True).start()

    def _start_ollama(self) -> None:
        ok = self.hud.core.client.try_start()
        self.ollama_status.configure(
            text=("Starting Ollama in the background…" if ok
                  else "Couldn't launch 'ollama serve' — is Ollama installed?"),
            fg=theme.GOLD if ok else theme.RED)
        self._alive(self._check_ollama)
        # and once more after the service has had a moment to come up
        threading.Thread(
            target=lambda: (time.sleep(3), self._alive(self._check_ollama)),
            daemon=True).start()

    def _open_download(self) -> None:
        import webbrowser

        webbrowser.open("https://ollama.com/download")

    def _fetch_models(self) -> None:
        try:
            self.models = self.hud.core.client.list_models()
        except Exception:
            self.models = []

        def apply():
            if self.models:
                self.model_box.configure(values=self.models)

        self._alive(apply)

    def _pull_model(self) -> None:
        name = self.pull_entry.get().strip()
        if not name:
            return
        self.pull_status.configure(text=f"Pulling {name}…", fg=theme.GOLD)
        client = self.hud.core.client

        def set_status(msg, color):
            self._alive(lambda: self.pull_status.configure(text=msg, fg=color))

        def work():
            try:
                client.pull_model(
                    name,
                    on_progress=lambda s: set_status(f"{name}: {s}",
                                                     theme.CYAN_TEXT))
                set_status(f"✓ {name} ready.", theme.GREEN)
                self._alive(self._fetch_models)
            except Exception as exc:
                set_status(f"Pull failed: {exc}", theme.RED)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ voice ----
    def _test_voice(self) -> None:
        s = self.hud.core.settings
        s.tts_enabled = True
        s.tts_voice = self.voice_box.get().strip()
        if s.tts_voice.startswith("("):
            s.tts_voice = ""
        self.hud.core.tts.stop()
        engine = TTSEngine(s)
        engine.speak(f"All systems online. Good to see you, "
                     f"{s.user_name}. This is how I sound.")
        self.voice_status.configure(text="Speaking…")

    def _test_mic(self) -> None:
        self.voice_status.configure(text="Say something for 4 seconds…",
                                    fg=theme.GOLD)
        hud = self.hud

        def work():
            text = hud.core.stt.listen(seconds=4.0)
            msg = f'I heard: “{text}”' if text else (
                "I didn't catch that — check your microphone permissions.")
            self._alive(lambda: self.voice_status.configure(
                text=msg, fg=theme.GREEN if text else theme.RED))

        threading.Thread(target=work, daemon=True).start()
