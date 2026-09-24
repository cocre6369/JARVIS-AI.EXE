"""Configuration, activity log, reminder and memory persistence.

Everything lives under %LOCALAPPDATA%\\JARVIS (Windows) or ~/.jarvis (elsewhere),
so settings and history survive restarts without polluting the install folder.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_NAME = "JARVIS"
APP_TITLE = "J.A.R.V.I.S."
APP_SUBTITLE = "Just A Rather Very Intelligent System"
VERSION = "1.1.1"

_LOCK = threading.RLock()


def is_windows() -> bool:
    return os.name == "nt"


def data_dir() -> Path:
    """Per-user writable directory for settings, logs, models and memory."""
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        p = Path(base) / APP_NAME
    else:
        p = Path.home() / ".jarvis"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_dir() -> Path:
    """Directory with bundled resources (works both from source and frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """User preferences. Persisted as JSON and forward-compatible (unknown
    keys are preserved, missing keys fall back to defaults)."""

    # Identity / model
    user_name: str = "sir"                 # how JARVIS addresses you ("sir", "boss", "Alex"...)
    model: str = "qwen3:8b"                # default Ollama model tag
    ollama_url: str = "http://localhost:11434"

    # Voice
    tts_enabled: bool = True
    tts_voice: str = ""                    # SAPI voice id/name; "" = auto-pick
    tts_rate: int = 175
    stt_engine: str = "auto"               # auto | whisper | windows
    whisper_model: str = "base.en"         # tiny.en | base.en | small.en ...
    mic_device: str = ""                   # sounddevice input name; "" = default
    wake_word: str = ""                    # "" = disabled, e.g. "jarvis"

    # UI
    always_on_top: bool = True
    hotkey_show: str = "ctrl+alt+j"
    hotkey_standby: str = "ctrl+alt+p"   # master on/off — standby at any time
    hotkey_talk: str = "ctrl+alt+space"  # hold to talk from anywhere
    confirm_every_action: bool = False     # extra-strict: confirm even "safe" actions

    # Book-keeping
    first_run_done: bool = False
    memory: Dict[str, str] = field(default_factory=dict)

    def save(self) -> None:
        with _LOCK:
            path = data_dir() / "settings.json"
            data = asdict(self)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(path)

    @classmethod
    def load(cls) -> "Settings":
        with _LOCK:
            path = data_dir() / "settings.json"
            obj = cls()
            if not path.exists():
                return obj
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return obj
            known = {f.name for f in fields(cls)}
            for key, value in (raw or {}).items():
                if key in known:
                    setattr(obj, key, value)
            return obj


class ActivityLog:
    """Append-only JSONL log of everything JARVIS hears and does, with a
    bounded size so it never fills the disk."""

    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self) -> None:
        self.path = data_dir() / "activity.jsonl"
        self._listeners: List[Any] = []

    def append(self, kind: str, text: str, **extra: Any) -> Dict[str, Any]:
        entry = {"t": time.time(), "kind": kind, "text": text, **extra}
        with _LOCK:
            try:
                if self.path.exists() and self.path.stat().st_size > self.MAX_BYTES:
                    self.path.replace(self.path.with_suffix(".jsonl.1"))
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass
        for cb in list(self._listeners):
            try:
                cb(entry)
            except Exception:
                pass
        return entry

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        with _LOCK:
            if not self.path.exists():
                return []
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
            except OSError:
                return []
        out: List[Dict[str, Any]] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)


class ReminderStore:
    """Timers and reminders persisted across restarts."""

    def __init__(self) -> None:
        self.path = data_dir() / "reminders.json"

    def _load(self) -> List[Dict[str, Any]]:
        with _LOCK:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (OSError, ValueError):
                return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        with _LOCK:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def add(self, fire_at: float, text: str) -> Dict[str, Any]:
        items = self._load()
        item = {"id": uuid.uuid4().hex[:8], "fire_at": fire_at, "text": text}
        items.append(item)
        self._save(items)
        return item

    def list(self) -> List[Dict[str, Any]]:
        return sorted(self._load(), key=lambda i: i.get("fire_at", 0))

    def due(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        now = time.time() if now is None else now
        return [i for i in self._load() if float(i.get("fire_at", 1e18)) <= now]

    def remove(self, ref: str) -> bool:
        items = self._load()
        keep = [i for i in items if ref not in (i.get("id"), i.get("text"))]
        if len(keep) == len(items):
            return False
        self._save(keep)
        return True


class SessionStore:
    """Short-term conversational context kept across restarts."""

    def __init__(self) -> None:
        self.path = data_dir() / "session.json"

    def load_messages(self) -> List[Dict[str, str]]:
        with _LOCK:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except (OSError, ValueError):
                return []

    def save_messages(self, messages: List[Dict[str, str]], keep: int = 20) -> None:
        with _LOCK:
            trimmed = messages[-keep:]
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
