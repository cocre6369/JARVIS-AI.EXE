"""The J.A.R.V.I.S. HUD — main window, dialogs and UI<->core plumbing."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from .. import store
from ..app import JarvisCore
from ..store import Settings
from ..voice import available_engines
from . import theme
from .widgets import ArcReactor, ScrollText

LOG_TAGS = {
    "user": "log_info", "say": "jarvis", "step": "log_act", "acting": "log_act",
    "done": "log_ok", "error": "log_err", "blocked": "log_err",
    "denied": "log_warn", "confirm": "log_warn", "abort": "log_err",
    "reminder": "log_warn", "boot": "boot",
}


class ConfirmDialog(tk.Toplevel):
    """Modal in-theme confirmation. Optional typed phrase for sensitive ops."""

    def __init__(self, master, title: str, message: str, word: str,
                 result: dict, done: threading.Event) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=theme.BG, highlightthickness=2,
                       highlightbackground=theme.GOLD if word else theme.CYAN)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        self.result = result
        self.done = done
        self.word = word

        header = tk.Frame(self, bg=theme.PANEL)
        header.pack(fill="x")
        tk.Label(header, text=f"◈  {title}", font=theme.FONT_UI_B,
                 bg=theme.PANEL, fg=theme.GOLD if word else theme.CYAN,
                 anchor="w", padx=14, pady=8).pack(fill="x")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(body, text=message, font=theme.FONT_UI, bg=theme.BG,
                 fg=theme.TEXT, justify="left", wraplength=430,
                 anchor="w").pack(fill="x")

        self.entry: Optional[tk.Entry] = None
        if word:
            row = tk.Frame(body, bg=theme.BG)
            row.pack(fill="x", pady=(10, 0))
            tk.Label(row, text=f"Type “{word}” to authorise:",
                     font=theme.FONT_SMALL, bg=theme.BG, fg=theme.MUTED
                     ).pack(anchor="w")
            self.entry = tk.Entry(row, font=theme.FONT_UI_B, bg=theme.PANEL,
                                  fg=theme.GOLD, insertbackground=theme.GOLD,
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=theme.BORDER)
            self.entry.pack(fill="x", pady=4, ipady=4)

        btns = tk.Frame(self, bg=theme.BG)
        btns.pack(fill="x", padx=16, pady=(0, 14))
        theme.styled_button(btns, "CANCEL", self._cancel, "ghost").pack(
            side="right", padx=4)
        self.ok_btn = theme.styled_button(
            btns, "AUTHORISE" if word else "CONFIRM",
            self._ok, "gold" if word else "cyan")
        self.ok_btn.pack(side="right", padx=4)
        if self.entry:
            self.entry.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, self._focus_first)

    def _focus_first(self) -> None:
        (self.entry or self.ok_btn).focus_set()

    def _ok(self) -> None:
        if self.entry is not None and self.entry.get().strip().upper() != self.word.upper():
            self.title("Phrase does not match — try again")
            self.bell()
            return
        self.result["ok"] = True
        self.done.set()
        self.destroy()

    def _cancel(self) -> None:
        self.result["ok"] = False
        self.done.set()
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Model / voice / strictness configuration."""

    def __init__(self, master, hud: "JarvisHUD") -> None:
        super().__init__(master)
        self.hud = hud
        self.settings = hud.core.settings
        self.title("J.A.R.V.I.S. — System Configuration")
        self.configure(bg=theme.BG, highlightthickness=2,
                       highlightbackground=theme.CYAN_DIM)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)

        pad = dict(padx=10, pady=4, sticky="w")
        form = tk.Frame(self, bg=theme.BG)
        form.pack(fill="both", expand=True, padx=18, pady=14)
        self.vars: dict = {}

        def add(label, key, kind="entry", values=None, width=32):
            var = tk.StringVar(value=str(self.settings.__dict__.get(key, "")))
            if kind == "combo":
                w = ttk.Combobox(form, textvariable=var, values=values or [],
                                 width=width, font=theme.FONT_UI)
                w.set(str(self.settings.__dict__.get(key, "")))
            elif kind == "check":
                var = tk.BooleanVar(value=bool(self.settings.__dict__.get(key)))
                w = tk.Checkbutton(form, variable=var, bg=theme.BG,
                                   activebackground=theme.BG,
                                   selectcolor=theme.PANEL,
                                   activeforeground=theme.CYAN)
            else:
                w = tk.Entry(form, textvariable=var, font=theme.FONT_UI, width=width,
                             bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.CYAN,
                             relief="flat", highlightthickness=1,
                             highlightbackground=theme.BORDER)
            r = len(self.vars)
            tk.Label(form, text=label, font=theme.FONT_SMALL, bg=theme.BG,
                     fg=theme.MUTED, width=24, anchor="w").grid(row=r, column=0,
                                                                **pad)
            w.grid(row=r, column=1, **pad)
            self.vars[key] = (var, kind)

        models = self._safe_models()
        add("How JARVIS addresses you", "user_name", width=18)
        add("Ollama URL", "ollama_url")
        add("Local model tag", "model", "combo", models or [self.settings.model])
        add("Speak replies (TTS)", "tts_enabled", "check")
        add("TTS voice (blank = auto)", "tts_voice")
        add("TTS rate", "tts_rate", width=8)
        add("STT engine (auto/whisper/windows)", "stt_engine", "combo",
            ["auto"] + available_engines())
        add("Whisper model", "whisper_model", "combo",
            ["tiny.en", "base.en", "small.en", "medium.en"])
        add("Wake word (blank = off)", "wake_word", width=14)
        add("Always on top", "always_on_top", "check")
        add("Confirm EVERY action (strict)", "confirm_every_action", "check")

        btns = tk.Frame(self, bg=theme.BG)
        btns.pack(fill="x", padx=18, pady=(0, 14))
        theme.styled_button(btns, "CANCEL", self.destroy, "ghost").pack(
            side="right", padx=4)
        theme.styled_button(btns, "SAVE", self._save, "gold").pack(
            side="right", padx=4)

    def _safe_models(self):
        try:
            return self.hud.core.client.list_models()
        except Exception:
            return []

    def _save(self) -> None:
        s = self.settings
        for key, (var, kind) in self.vars.items():
            try:
                val = var.get() if kind != "check" else bool(var.get())
                if key in ("tts_rate",):
                    val = int(val)
                setattr(s, key, val)
            except (ValueError, tk.TclError):
                pass
        self.hud.core.reload_settings()
        self.hud.refresh_meta()
        self.hud.narrate("Configuration updated.")
        self.destroy()


class JarvisHUD(tk.Tk):
    """Main application window. Implements the core's UI protocol; every
    method is safe to call from worker threads through ``call``."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__()
        self.withdraw()
        self.settings = settings or Settings.load()
        self.title(store.APP_TITLE + " — " + store.APP_SUBTITLE)
        self.configure(bg=theme.BG)
        self.geometry("1120x720")
        self.minsize(900, 560)

        try:
            self.iconphoto(True, tk.PhotoImage(
                file=str(store.resource_dir() / "assets" / "jarvis_icon.png")))
        except Exception:
            pass

        self._queue: "queue.SimpleQueue" = queue.SimpleQueue()
        self._state = "IDLE"
        theme.style_ttk(self)

        # Surface Tk callback errors instead of losing them in the void.
        def _cb_error(exc, val, tb):
            import traceback as _tb

            detail = "".join(_tb.format_exception(exc, val, tb))[-1200:]
            core = getattr(self, "core", None)
            if core is not None:
                try:
                    core.log("error", f"UI error: {val}")
                except Exception:
                    pass
            try:
                self.narrate("A UI glitch occurred — see the activity log.")
            except Exception:
                pass

        self.report_callback_exception = _cb_error

        self._build()
        self._pump()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Escape>", self._escape)
        self.bind_all("<Control-q>", lambda _e: self.quit_app())

        self.core = JarvisCore(self, self.settings)
        # Mirror every activity-log entry into the HUD panel (thread-safe).
        self.core.activity.add_listener(
            lambda e: self.call(self.log_line, e.get("kind", ""),
                                e.get("text", "")))
        self.refresh_meta()
        self._boot_sequence()
        self._start_hotkeys()
        self.deiconify()
        self._tick_clock()
        self.entry.focus_set()
        # Pre-warm the speech engine so the first voice command is instant.
        self.after(2500, self.core.preload_speech)

        if not self.settings.first_run_done:
            self.after(700, self.run_wizard)

    # ------------------------------------------------------------ layout --
    def _build(self) -> None:
        # ---- header ------------------------------------------------------
        head = tk.Frame(self, bg=theme.PANEL, highlightthickness=1,
                        highlightbackground=theme.BORDER)
        head.pack(fill="x")
        tk.Label(head, text="  ◈  J.A.R.V.I.S.", font=theme.FONT_TITLE,
                 bg=theme.PANEL, fg=theme.CYAN).pack(side="left")
        tk.Label(head, text=store.APP_SUBTITLE + "  ·  STARK LOCAL INSTANCE",
                 font=theme.FONT_SMALL, bg=theme.PANEL, fg=theme.MUTED
                 ).pack(side="left", padx=12)
        self.clock = tk.Label(head, text="", font=theme.FONT_UI_B,
                              bg=theme.PANEL, fg=theme.CYAN_TEXT)
        self.clock.pack(side="right", padx=14)
        self.meta = tk.Label(head, text="", font=theme.FONT_SMALL,
                             bg=theme.PANEL, fg=theme.MUTED)
        self.meta.pack(side="right", padx=10)
        self.state_chip = tk.Label(head, text="  IDLE  ", font=theme.FONT_UI_B,
                                   bg=theme.PANEL_2, fg=theme.CYAN,
                                   highlightthickness=1,
                                   highlightbackground=theme.CYAN_DIM, padx=8)
        self.state_chip.pack(side="right", padx=8, pady=6)

        menu = tk.Menu(self, tearoff=0, bg=theme.PANEL, fg=theme.TEXT,
                       activebackground=theme.CYAN_DIM,
                       activeforeground=theme.WHITE, relief="flat")
        main = tk.Menu(menu, tearoff=0, bg=theme.PANEL, fg=theme.TEXT,
                       activebackground=theme.CYAN_DIM,
                       activeforeground=theme.WHITE, relief="flat",
                       font=theme.FONT_UI)
        main.add_command(label="Configuration…", command=self.open_settings)
        main.add_command(label="Run setup wizard…", command=self.run_wizard)
        main.add_separator()
        self.enabled_var = tk.BooleanVar(value=True)
        main.add_checkbutton(label="JARVIS enabled (off = standby)",
                             variable=self.enabled_var,
                             command=self._toggle_enabled,
                             accelerator="Ctrl+Alt+P")
        main.add_command(label="Hold to talk (keep pressed)",
                         state="disabled", accelerator="Ctrl+Alt+Space")
        main.add_separator()
        self.tts_var = tk.BooleanVar(value=self.settings.tts_enabled)
        main.add_checkbutton(label="Speak replies", variable=self.tts_var,
                             command=self._toggle_tts)
        self.top_var = tk.BooleanVar(value=self.settings.always_on_top)
        main.add_checkbutton(label="Always on top", variable=self.top_var,
                             command=self._toggle_top)
        main.add_separator()
        main.add_command(label="Show / Hide window", command=self._toggle_visibility,
                         accelerator="Ctrl+Alt+J")
        main.add_command(label="Abort automation", command=self.abort_now,
                         accelerator="Esc")
        main.add_separator()
        main.add_command(label="Exit", command=self.quit_app,
                         accelerator="Ctrl+Q")
        menu.add_cascade(label="☰  J.A.R.V.I.S.", menu=main)
        self.config(menu=menu)

        # ---- main row ----------------------------------------------------
        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body.columnconfigure(0, minsize=230)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2)
        body.rowconfigure(0, weight=1)

        # left: reactor
        left = theme.hud_frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.reactor = ArcReactor(left)
        self.reactor.pack(pady=(26, 6))
        self.state_label = tk.Label(left, text="STANDING BY",
                                    font=theme.FONT_UI_B, bg=theme.PANEL,
                                    fg=theme.CYAN)
        self.state_label.pack(pady=2)
        self.narration = tk.Label(left, text="All systems nominal.",
                                  font=theme.FONT_SMALL, bg=theme.PANEL,
                                  fg=theme.MUTED, wraplength=200, height=3,
                                  justify="left")
        self.narration.pack(pady=6, padx=10)
        sep = tk.Frame(left, bg=theme.BORDER, height=1)
        sep.pack(fill="x", padx=14, pady=10)
        tk.Label(left, text="GUARDRAILS: ACTIVE\nNO LOGINS · NO SECRETS\n"
                            "CONFIRM BEFORE TOUCH",
                 font=theme.FONT_SMALL, bg=theme.PANEL, fg=theme.GOLD_DIM,
                 justify="center").pack(pady=(0, 8))
        self.abort_btn = theme.styled_button(left, "■  ABORT", self.abort_now,
                                             "red", width=14)
        self.abort_btn.pack(pady=(4, 10))
        tk.Label(left, text=theme.HOTKEY_HINTS, font=theme.FONT_SMALL,
                 bg=theme.PANEL, fg=theme.MUTED, justify="left"
                 ).pack(anchor="w", padx=16, pady=(0, 14))

        # centre: chat
        centre = theme.hud_frame(body)
        centre.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self._panel_title(centre, "◈  DIALOGUE")
        self.chat = ScrollText(centre, height=18, width=52)
        self.chat.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # right: activity log
        right = theme.hud_frame(body)
        right.grid(row=0, column=2, sticky="nsew")
        self._panel_title(right, "◈  ACTIVITY LOG")
        self.activity_view = ScrollText(right, height=18, width=30,
                                        font=theme.FONT_SMALL)
        self.activity_view.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # ---- input row ---------------------------------------------------
        bottom = theme.hud_frame(body)
        bottom.grid(row=1, column=0, columnspan=3, sticky="ew",
                    pady=(8, 0), padx=0)
        self.entry = tk.Entry(bottom, font=theme.FONT_UI, bg=theme.PANEL_2,
                              fg=theme.TEXT, insertbackground=theme.CYAN,
                              relief="flat", highlightthickness=1,
                              highlightbackground=theme.BORDER)
        self.entry.pack(side="left", fill="x", expand=True, padx=(12, 6),
                        pady=10, ipady=6)
        self.entry.bind("<Return>", self._send_event)
        theme.styled_button(bottom, "SEND ▸", self._send, "cyan").pack(
            side="left", padx=4, pady=10)
        self.mic_btn = theme.styled_button(bottom, "🎤  HOLD TO TALK",
                                           lambda: None, "gold")
        self.mic_btn.pack(side="left", padx=4, pady=10)
        self.mic_btn.bind("<ButtonPress-1>", self._mic_down)
        self.mic_btn.bind("<ButtonRelease-1>", self._mic_up)
        theme.styled_button(bottom, "■  STOP", self.abort_now, "red").pack(
            side="left", padx=(4, 12), pady=10)

    @staticmethod
    def _panel_title(parent, text: str) -> None:
        bar = tk.Frame(parent, bg=theme.PANEL_2)
        bar.pack(fill="x", padx=6, pady=6)
        tk.Label(bar, text=text, font=theme.FONT_SMALL_B, bg=theme.PANEL_2,
                 fg=theme.CYAN, anchor="w").pack(fill="x", padx=8, pady=3)

    # --------------------------------------------------------- UI protocol --
    def call(self, fn: Callable, *args: Any) -> None:
        self._queue.put((fn, args))

    def _pump(self) -> None:
        try:
            while True:
                fn, args = self._queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(40, self._pump)

    def set_state(self, state: str) -> None:
        self._state = state
        color = theme.STATE_COLORS.get(state, theme.CYAN)
        label = theme.STATE_LABELS.get(state, state)
        self.state_chip.configure(text=f"  {label}  ", fg=color,
                                  highlightbackground=color)
        self.state_label.configure(text=label, fg=color)
        self.reactor.set_state(state)

    def set_level(self, level: float) -> None:
        self.reactor.set_level(level)

    def narrate(self, text: str) -> None:
        self.narration.configure(text=text)

    def add_message(self, who: str, text: str) -> None:
        stamp = time.strftime("%H:%M")
        if who == "user":
            self.chat.add(f"YOU · {stamp}", "user_who")
            self.chat.add(text, "user")
        else:
            self.chat.add(f"JARVIS · {stamp}", "jarvis_who")
            self.chat.add(text, "jarvis")
        self.chat.add("", "log_info")

    def notify(self, text: str) -> None:
        self.narrate(text)
        self.bell()

    def set_enabled(self, enabled: bool) -> None:
        """Mirror the core standby switch in the menu, mic button and chip."""
        self.enabled_var.set(bool(enabled))
        if enabled:
            self.mic_btn.configure(state="normal", bg=theme.PANEL_2,
                                   text="🎤  HOLD TO TALK")
        else:
            self.mic_btn.configure(state="disabled",
                                   text="🎤  STANDBY — Ctrl+Alt+P")

    def flash_alert(self, text: str) -> None:
        self.activity_view.add(f"⏰ {time.strftime('%H:%M:%S')}  {text}",
                               "log_warn")

    def log_line(self, kind: str, text: str) -> None:
        tag = LOG_TAGS.get(kind, "log_info")
        icon = {"done": "✔", "error": "✖", "blocked": "⛔", "denied": "⛔",
                "confirm": "…", "acting": "▸", "step": "·", "abort": "■",
                "reminder": "⏰", "user": "«", "say": "»"}.get(kind, "·")
        self.activity_view.add(
            f"{icon} {time.strftime('%H:%M:%S')}  {text[:160]}", tag)

    def confirm(self, title: str, message: str) -> bool:
        result = {"ok": False}
        done = threading.Event()
        self.call(self._show_confirm, title, message, "", result, done)
        done.wait(600)
        return result["ok"]

    def confirm_typed(self, title: str, message: str, word: str) -> bool:
        result = {"ok": False}
        done = threading.Event()
        self.call(self._show_confirm, title, message, word, result, done)
        done.wait(600)
        return result["ok"]

    def _show_confirm(self, title, message, word, result, done) -> None:
        ConfirmDialog(self, title, message, word, result, done)

    def open_settings(self) -> None:
        SettingsDialog(self, self)

    def run_wizard(self) -> None:
        from .wizard import FirstRunWizard

        FirstRunWizard(self, self)

    # ------------------------------------------------------------- actions --
    def _send_event(self, _event=None):
        self._send()

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.core.submit(text, source="text")

    def _mic_down(self, _event=None) -> None:
        self.mic_btn.configure(bg=theme.RED, text="●  LISTENING — release")
        self.core.listen_push()

    def _mic_up(self, _event=None) -> None:
        self.mic_btn.configure(bg=theme.PANEL_2, text="🎤  HOLD TO TALK")
        self.core.listen_release()

    def abort_now(self) -> None:
        self.core.abort_now()
        self.set_state("IDLE")
        self.narrate("Stopped.")

    def _escape(self, _event=None) -> None:
        if getattr(self.core, "busy", False):
            self.abort_now()

    def refresh_meta(self) -> None:
        s = self.core.settings
        eng = ",".join(available_engines()[:2]) or "text-only"
        self.meta.configure(
            text=f"MODEL: {s.model}   STT: {eng}   OLLAMA: "
                 f"{s.ollama_url.split('//')[-1]}")
        self.tts_var.set(s.tts_enabled)
        self.attributes("-topmost", bool(s.always_on_top))

    def _toggle_tts(self) -> None:
        self.core.settings.tts_enabled = bool(self.tts_var.get())
        self.core.reload_settings()

    def _toggle_enabled(self) -> None:
        self.core.toggle_standby(force=not bool(self.enabled_var.get()))

    def toggle_standby_hotkey(self) -> None:
        self.core.toggle_standby()

    def _toggle_top(self) -> None:
        self.core.settings.always_on_top = bool(self.top_var.get())
        self.core.reload_settings()
        self.attributes("-topmost", self.core.settings.always_on_top)

    def _tick_clock(self) -> None:
        self.clock.configure(text=time.strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _boot_sequence(self) -> None:
        lines = [
            ("boot", "INITIALIZING J.A.R.V.I.S. INTERFACE …"),
            ("log_info", "arc reactor ............ STABLE"),
            ("log_info", f"voice synthesis ........ "
                         f"{'ONLINE' if self.core.tts._ok else 'MUTED'}"),
            ("log_info", "safety guardrails ...... ARMED"),
            ("log_info", "credential handling .... PERMANENTLY DISABLED"),
            ("boot", "ALL SYSTEMS ONLINE. GOOD TO SEE YOU, "
                     f"{self.core.settings.user_name.upper()}."),
        ]
        for i, (tag, text) in enumerate(lines):
            self.after(180 * i, lambda t=text, g=tag: self.activity_view.add(t, g))
        for entry in self.core.activity.tail(8):
            self.after(200, lambda e=entry: self.log_line(
                e.get("kind", "info"), e.get("text", "")))

    def _start_hotkeys(self) -> None:
        """Global hotkeys, registered in one background listener:

        Ctrl+Alt+P      — master standby / wake  (the off switch)
        Ctrl+Alt+Space  — hold to talk
        Ctrl+Alt+J      — show / hide the HUD
        """
        def listen():
            try:
                from pynput import keyboard

                combo_show = (self.core.settings.hotkey_show or "ctrl+alt+j").lower()
                combo_stdby = (self.core.settings.hotkey_standby or "ctrl+alt+p").lower()

                def norm(key) -> str:
                    name = getattr(key, "name", None) or str(key)
                    name = name.replace("Key.", "").replace("_l", "").replace("_r", "")
                    return name.lower()

                held = set()
                talking = {"on": False}

                def on_press(key):
                    held.add(norm(key))
                    if ("space" in held and "ctrl" in held and "alt" in held
                            and not talking["on"]):
                        talking["on"] = True
                        self.call(self._mic_down)

                def on_release(key):
                    if talking["on"] and norm(key) in ("space", "ctrl", "alt"):
                        talking["on"] = False
                        self.call(self._mic_up)
                    held.discard(norm(key))

                listener = keyboard.Listener(on_press=on_press,
                                             on_release=on_release)
                listener.start()
                hk = keyboard.GlobalHotKeys({
                    combo_show: lambda: self.call(self._toggle_visibility),
                    combo_stdby: lambda: self.call(self.toggle_standby_hotkey),
                })
                hk.start()
            except Exception:
                pass

        threading.Thread(target=listen, daemon=True).start()

    def _toggle_visibility(self) -> None:
        if self.state() == "withdrawn" or not self.winfo_viewable():
            self.deiconify()
            self.lift()
            self.entry.focus_set()
        else:
            self.withdraw()

    def _on_close(self) -> None:
        self.withdraw()   # minimise to tray; Exit menu really quits

    def quit_app(self) -> None:
        try:
            self.core.shutdown()
        except Exception:
            pass
        try:
            from .tray import stop_tray

            stop_tray()
        except Exception:
            pass
        self.destroy()


