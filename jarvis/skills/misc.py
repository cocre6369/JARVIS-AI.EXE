"""Productivity (timers/reminders), file, memory and system skills."""
from __future__ import annotations

import datetime as _dt
import os
import re
import time
from pathlib import Path
from typing import Optional

from . import register
from ..guardrails import POLICY_CONFIRM, POLICY_DOUBLE
from ..store import ReminderStore, Settings

_store = ReminderStore()
_settings: Optional[Settings] = None
_notify = None            # callable(text) wired by the app controller


def configure(settings: Settings, notifier) -> None:
    """Wire shared state (settings store + 'a timer is due' callback)."""
    global _settings, _notify
    _settings = settings
    _notify = notifier


# ------------------------------------------------------------- timers -----
@register("timer_set", "Set a countdown timer (spoken + on-screen alert when "
          "it fires).", "{minutes, label}", policy=POLICY_CONFIRM)
def timer_set(minutes: float, label: str = "timer") -> str:
    try:
        mins = float(minutes)
    except (TypeError, ValueError):
        return "ERROR: minutes must be a number."
    if mins <= 0 or mins > 60 * 24:
        return "ERROR: timers run between 0 and 1440 minutes."
    fire_at = time.time() + mins * 60.0
    item = _store.add(fire_at, f"Timer: {label}")
    return f"Timer '{label}' set for {_fmt_duration(mins * 60)} from now (id {item['id']})."


@register("reminder_set", "Set a reminder for later ('in_minutes' or "
          "'at_time' as HH:MM).", "{text, in_minutes?, at_time?}",
          policy=POLICY_CONFIRM)
def reminder_set(text: str, in_minutes: Optional[float] = None,
                 at_time: str = "") -> str:
    if in_minutes:
        try:
            fire_at = time.time() + float(in_minutes) * 60.0
        except (TypeError, ValueError):
            return "ERROR: in_minutes must be a number."
    elif at_time:
        try:
            parsed = _dt.datetime.strptime(str(at_time).strip()[:5], "%H:%M")
        except ValueError:
            return "ERROR: at_time must look like HH:MM."
        now = _dt.datetime.now()
        fire = now.replace(hour=parsed.hour, minute=parsed.minute, second=0,
                           microsecond=0)
        if fire <= now:
            fire += _dt.timedelta(days=1)
        fire_at = fire.timestamp()
    else:
        return "ERROR: give me 'in_minutes' or 'at_time'."
    item = _store.add(fire_at, f"Reminder: {text}")
    when = _dt.datetime.fromtimestamp(fire_at).strftime("%H:%M")
    return f"Reminder set for {when} (id {item['id']}): {text}"


@register("list_reminders", "List pending timers and reminders.", "{}",
          returns_data=True)
def list_reminders() -> str:
    items = _store.list()
    if not items:
        return "No timers or reminders pending."
    now = time.time()
    out = [f"{i['id']}: in {_fmt_duration(i['fire_at'] - now)} — {i['text']}"
           for i in items]
    return "PENDING:\n" + "\n".join(out)


@register("cancel_reminder", "Cancel a timer/reminder by id or keyword.", "{ref}",
          policy=POLICY_CONFIRM)
def cancel_reminder(ref: str) -> str:
    if _store.remove(str(ref)):
        return f"Cancelled '{ref}'."
    return f"ERROR: nothing pending matches '{ref}'."


def pump_due_reminders() -> None:
    """Called from the app's background tick; fires anything that is due."""
    if _notify is None:
        return
    for item in _store.due():
        if _store.remove(item["id"]):
            _notify(item.get("text", "Reminder"))


# -------------------------------------------------------------- memory ----
@register("remember", "Save a user preference/for future sessions.",
          "{key, value}", policy=POLICY_CONFIRM)
def remember(key: str, value: str) -> str:
    if _settings is None:
        return "ERROR: memory store not ready."
    _settings.memory[str(key).strip()[:60]] = str(value).strip()[:300]
    _settings.save()
    return f"Noted — I'll remember {key}: {value}."


@register("recall_memory", "Recall saved user preferences.", "{}",
          returns_data=True)
def recall_memory() -> str:
    if _settings is None or not _settings.memory:
        return "Nothing committed to memory yet."
    return "\n".join(f"{k}: {v}" for k, v in _settings.memory.items())


# ---------------------------------------------------------------- files ---
@register("file_list", "List files in a folder (personal folders always need "
          "the user's explicit confirmation).", "{path}", policy=POLICY_CONFIRM,
          returns_data=True)
def file_list(path: str) -> str:
    p = Path(os.path.expanduser(path))
    try:
        entries = sorted(p.iterdir(), key=lambda e: e.is_file())[:100]
    except OSError as exc:
        return f"ERROR: cannot list that folder ({exc})."
    lines = [f"{'DIR ' if e.is_dir() else 'FILE'} {e.name}" for e in entries]
    return "\n".join(lines) or "(empty folder)"


@register("file_read", "Read a text file (up to 8000 characters).", "{path}",
          policy=POLICY_CONFIRM, returns_data=True)
def file_read(path: str) -> str:
    p = Path(os.path.expanduser(path))
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"ERROR: cannot read that file ({exc})."
    return text[:8000]


@register("file_write", "Write a NEW text file (overwrites need typed "
          "confirmation).", "{path, content}", policy=POLICY_CONFIRM)
def file_write(path: str, content: str) -> str:
    p = Path(os.path.expanduser(path))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content or "", encoding="utf-8")
    except OSError as exc:
        return f"ERROR: cannot write that file ({exc})."
    return f"Written to {p} ({len(content or '')} characters)."


@register("file_delete", "Move a file to the Recycle Bin (typed confirmation "
          "required — never permanent).", "{path}", policy=POLICY_DOUBLE)
def file_delete(path: str) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"ERROR: no such file: {p}"
    try:
        from send2trash import send2trash  # type: ignore

        send2trash(str(p))
        return f"Moved {p.name} to the Recycle Bin."
    except Exception as exc:
        return f"ERROR: delete failed ({exc})."


@register("open_folder", "Open a folder in File Explorer.", "{path}",
          policy=POLICY_CONFIRM)
def open_folder(path: str) -> str:
    p = Path(os.path.expanduser(path))
    try:
        os.startfile(str(p))  # type: ignore[attr-defined]
        return f"Opened {p} in the file explorer."
    except Exception as exc:
        return f"ERROR: cannot open that folder ({exc})."


# --------------------------------------------------------------- system ---
@register("system_status", "Report CPU, memory, disk and battery state.", "{}",
          returns_data=True)
def system_status() -> str:
    try:
        import psutil

        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.expanduser("~"))
        cpu = psutil.cpu_percent(interval=0.4)
        lines = [
            f"CPU: {cpu:.0f}%",
            f"Memory: {vm.percent:.0f}% of {_fmt_bytes(vm.total)}",
            f"Disk free: {_fmt_bytes(disk.free)}",
        ]
        try:
            bat = psutil.sensors_battery()
            if bat:
                state = "charging" if bat.power_plugged else "on battery"
                lines.append(f"Battery: {bat.percent:.0f}% ({state})")
        except Exception:
            pass
        return "; ".join(lines)
    except Exception as exc:
        return f"ERROR: system stats unavailable ({exc})."


@register("screenshot", "Capture the screen to Pictures/JARVIS (user "
          "confirms first — the screen may show private data).", "{}",
          policy=POLICY_CONFIRM)
def screenshot() -> str:
    try:
        from PIL import ImageGrab

        shots = Path.home() / "Pictures" / "JARVIS"
        shots.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = shots / f"jarvis-{stamp}.png"
        ImageGrab.grab().save(path)
        return f"Screenshot saved to {path}."
    except Exception as exc:
        return f"ERROR: screenshot failed ({exc})."


@register("clipboard_read", "Read the clipboard (user confirms first — it may "
          "hold private data).", "{}", policy=POLICY_CONFIRM, returns_data=True)
def clipboard_read() -> str:
    if os.name != "nt":
        return "ERROR: clipboard access is Windows-only."
    try:
        import win32clipboard  # type: ignore

        win32clipboard.OpenClipboard()
        try:
            data = win32clipboard.GetClipboardData(
                win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return str(data)[:4000] or "(clipboard is empty)"
    except Exception as exc:
        return f"ERROR: clipboard read failed ({exc})."


@register("clipboard_set", "Put text on the clipboard.", "{text}",
          policy=POLICY_CONFIRM)
def clipboard_set(text: str) -> str:
    if os.name != "nt":
        return "ERROR: clipboard access is Windows-only."
    try:
        import win32clipboard  # type: ignore

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text or "", win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return f"Clipboard set to {len(text or '')} characters."
    except Exception as exc:
        return f"ERROR: clipboard write failed ({exc})."


@register("open_settings", "Open JARVIS settings (model, voice, strictness).",
          "{}")
def open_settings() -> str:
    return "SETTINGS"   # handled by the UI layer


# ------------------------------------------------------------- helpers ----
def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
