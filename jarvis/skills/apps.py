"""Application, window, media and on-screen input skills.

All OS automation is visible (typed keys, launched windows) and restricted to
sanitised names / a safe key list (see guardrails). There is no shell access.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import Dict, Optional

from . import register
from ..guardrails import POLICY_CONFIRM, POLICY_DOUBLE

# Friendly name -> launcher. Anything else goes through the Start-menu search.
APP_MAP: Dict[str, str] = {
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "firefox": "firefox", "brave": "brave",
    "opera": "opera", "notepad": "notepad", "calculator": "calc",
    "calc": "calc", "paint": "mspaint", "explorer": "explorer",
    "file explorer": "explorer", "files": "explorer",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "teams": "ms-teams", "slack": "slack",
    "discord": "discord", "spotify": "spotify", "steam": "steam",
    "vscode": "code", "visual studio code": "code",
    "terminal": "wt", "powershell": "powershell", "task manager": "taskmgr",
    "settings": "ms-settings:", "control panel": "control",
    "snipping tool": "snippingtool", "clock": "ms-clock:",
    "photos": "ms-photos:", "camera": "microsoft.windows.camera:",
    "vlc": "vlc", "itunes": "itunes", "zoom": "zoom",
    "thunderbird": "thunderbird", "obs": "obs64", "blender": "blender",
}


def _find_window(title_part: str):
    """Return (hwnd, title) of the first visible window matching *title_part*."""
    import win32gui  # type: ignore

    needle = title_part.strip().lower()
    found = []

    def enum(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and needle in title.lower():
                found.append((hwnd, title))

    win32gui.EnumWindows(enum, None)
    return found[0] if found else (None, "")


def _launch(name: str) -> bool:
    key = name.strip().lower()
    target = APP_MAP.get(key, name.strip())
    exe = target if target.lower().endswith(".exe") else (
        target + ".exe" if not target.endswith(":") else target)
    # 1) explicit executable / URI from the map (e.g. ms-settings:)
    for cand in (target, exe):
        try:
            if cand.endswith(":"):  # URI scheme like ms-settings:
                os.startfile(cand)  # type: ignore[attr-defined]
                return True
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                import win32api  # type: ignore
                win32api.ShellExecute(0, "open", cand, None, None, 1)
                return True
            except Exception:
                pass
    # 2) Start-menu / App Paths lookup via `start` with a sanitised name
    if sys.platform == "win32":
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", name.strip()],
                shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000)
            return True
        except OSError:
            return False
    try:
        subprocess.Popen([name.strip()])
        return True
    except OSError:
        return False


@register("open_app", "Open an application by name (e.g. 'spotify', 'chrome', "
          "'notepad', 'settings').", "{name}")
def open_app(name: str) -> str:
    if _launch(name):
        return f"{name} is opening now."
    return (f"ERROR: I couldn't find an application called '{name}'. "
            "Try a different name or ask me to open it from the Start menu.")


@register("close_app", "Close an application's windows (asks the user first — "
          "unsaved work could be lost).", "{name}", policy=POLICY_CONFIRM)
def close_app(name: str) -> str:
    image = name.strip().lower()
    if not image.endswith(".exe"):
        image = APP_MAP.get(image, image) + ".exe"
    if sys.platform == "win32":
        try:
            import psutil
            killed = 0
            for proc in psutil.process_iter(["name", "exe"]):
                if (proc.info.get("name", "") or "").lower() == image:
                    proc.terminate()
                    killed += 1
            if killed:
                return f"Closed {killed} window(s) of {name}."
        except Exception as exc:
            return f"ERROR: could not close {name} ({exc})."
        return f"ERROR: {name} does not appear to be running."
    return f"ERROR: closing apps is only supported on Windows."


@register("focus_window", "Bring an open window to the front by part of its "
          "title.", "{title}")
def focus_window(title: str) -> str:
    if sys.platform != "win32":
        return "ERROR: window control is only supported on Windows."
    import win32con  # type: ignore
    import win32gui  # type: ignore

    hwnd, real = _find_window(title)
    if not hwnd:
        return f"ERROR: no visible window matching '{title}'."
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return f"Focused window '{real}'."
    except Exception as exc:
        return f"ERROR: could not focus that window ({exc})."


@register("minimize_window", "Minimise a window by part of its title.", "{title}")
def minimize_window(title: str) -> str:
    return _window_cmd(title, "SW_MINIMIZE")


@register("maximize_window", "Maximise a window by part of its title.", "{title}")
def maximize_window(title: str) -> str:
    return _window_cmd(title, "SW_MAXIMIZE")


def _window_cmd(title: str, mode: str) -> str:
    if sys.platform != "win32":
        return "ERROR: window control is only supported on Windows."
    import win32con  # type: ignore
    import win32gui  # type: ignore

    hwnd, real = _find_window(title)
    if not hwnd:
        return f"ERROR: no visible window matching '{title}'."
    try:
        win32gui.ShowWindow(hwnd, getattr(win32con, mode))
        return f"Window '{real}' {'minimised' if mode == 'SW_MINIMIZE' else 'maximised'}."
    except Exception as exc:
        return f"ERROR: window operation failed ({exc})."


# ---------------------------------------------------------------- media ----
_MEDIA_KEYS = {
    "playpause": 0xB3, "play": 0xB3, "pause": 0xB3,
    "nexttrack": 0xB0, "next": 0xB0,
    "prevtrack": 0xB1, "previous": 0xB1, "prev": 0xB1,
    "stop": 0xB2,
    "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD,
}


def _send_vk(vk: int) -> None:
    import ctypes

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class _KBD(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_uint), ("time", ctypes.c_uint),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", _KBD)]
        _fields_ = [("type", ctypes.c_uint), ("u", _U)]

    for flags in (0, KEYEVENTF_KEYUP):
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = _KBD(vk, 0, flags, 0, None)
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        time.sleep(0.02)


def _media(action: str) -> str:
    vk = _MEDIA_KEYS.get(action.strip().lower())
    if not vk:
        return f"ERROR: unknown media action '{action}'."
    if sys.platform != "win32":
        return "ERROR: media keys are only supported on Windows."
    _send_vk(vk)
    pretty = {"playpause": "Playback toggled", "play": "Playback toggled",
              "pause": "Playback toggled", "nexttrack": "Skipped to next track",
              "next": "Skipped to next track", "prevtrack": "Previous track",
              "previous": "Previous track", "prev": "Previous track",
              "stop": "Playback stopped", "volumeup": "Volume up",
              "volumedown": "Volume down", "volumemute": "Volume muted/unmuted"}
    return f"{pretty[action.strip().lower()]}."


@register("media_play_pause", "Toggle play/pause in the active media app.")
def media_play_pause() -> str:
    return _media("playpause")


@register("media_next", "Skip to the next track.")
def media_next() -> str:
    return _media("nexttrack")


@register("media_previous", "Go to the previous track.")
def media_previous() -> str:
    return _media("prevtrack")


@register("media_stop", "Stop media playback.")
def media_stop() -> str:
    return _media("stop")


@register("volume_set", "Set master volume to a percentage (0-100).", "{percent}")
def volume_set(percent: int) -> str:
    try:
        level = max(0, min(100, int(percent)))
    except (TypeError, ValueError):
        return "ERROR: volume must be a number between 0 and 100."
    if sys.platform != "win32":
        return "ERROR: volume control is only supported on Windows."
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level} percent."
    except Exception:
        # Coarse fallback: nudge with the hardware volume keys.
        step_key = 0xAF if level >= 50 else 0xAE
        for _ in range(12):
            _send_vk(step_key)
        return (f"Volume adjusted toward {level} percent "
                "(fine control unavailable).")


@register("volume_mute", "Mute, unmute or toggle the master volume.",
          "{mode: toggle|on|off}")
def volume_mute(mode: str = "toggle") -> str:
    if sys.platform != "win32":
        return "ERROR: volume control is only supported on Windows."
    mode = (mode or "toggle").strip().lower()
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        current = bool(volume.GetMute())
        want = (not current) if mode == "toggle" else (mode == "on")
        volume.SetMute(1 if want else 0, None)
        return "Audio muted." if want else "Audio unmuted."
    except Exception:
        _send_vk(_MEDIA_KEYS["volumemute"])
        return "Mute toggled."


# ------------------------------------------------------------- typing -----
@register("type_text", "Type text visibly into whatever field/window has focus "
          "(asks the user first). Never used for passwords.", "{text}",
          policy=POLICY_CONFIRM)
def type_text(text: str) -> str:
    if sys.platform != "win32":
        return "ERROR: typing is only supported on Windows."
    import pyautogui

    pyautogui.PAUSE = 0.02
    if all(ord(ch) < 128 for ch in text):
        pyautogui.write(text, interval=0.01)
    else:
        # Unicode: paste via clipboard, restoring whatever was there after.
        _paste_text(text)
    return f"Typed {len(text)} characters."


def _paste_text(text: str) -> None:
    import pyautogui

    if sys.platform == "win32":
        import win32clipboard  # type: ignore

        win32clipboard.OpenClipboard()
        try:
            old = win32clipboard.GetClipboardData(
                win32clipboard.CF_UNICODETEXT) if win32clipboard.IsClipboardFormatAvailable(
                win32clipboard.CF_UNICODETEXT) else None
        except Exception:
            old = None
        finally:
            win32clipboard.CloseClipboard()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        if old is not None:
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(old, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
    else:
        pyautogui.write(text)


@register("press_keys", "Press a key combo from the safe list (enter, tab, "
          "ctrl+f, alt+tab, media keys...).", "{keys}", policy=POLICY_CONFIRM)
def press_keys(keys: str) -> str:
    if sys.platform != "win32":
        return "ERROR: key input is only supported on Windows."
    import pyautogui

    combo = keys.strip().lower().replace(" ", "")
    parts = combo.split("+")
    pyautogui.hotkey(*parts)
    return f"Pressed {combo}."
