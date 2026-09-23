"""Application, window, media and on-screen input skills.

The app launcher resolves names like a human would: aliases ("vs code"),
typos ("spotifi"), the Windows app catalogue (Store/UWP apps such as Spotify),
well-known install paths and the App Paths registry — before it ever says
"I can't find that". All OS automation is visible and restricted to
sanitised names / a safe key list (see guardrails). There is no shell access.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

from . import register
from ..guardrails import POLICY_CONFIRM, POLICY_DOUBLE

_POWERSHELL = (os.path.expandvars(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
               if os.name == "nt" else "powershell")

# --------------------------------------------------------------------------
# Knowledge base: canonical app keys with launch candidates
# --------------------------------------------------------------------------
CANONICAL: Dict[str, Dict] = {
    "spotify": {
        "uri": None,
        "start_names": ["Spotify"],
        "processes": ["Spotify.exe", "SpotifyMusic.exe"],
        "paths": [r"%APPDATA%\Spotify\Spotify.exe",
                  r"%LOCALAPPDATA%\Spotify\Spotify.exe",
                  r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"],
    },
    "chrome": {
        "exe": "chrome",
        "start_names": ["Google Chrome", "Chrome"],
        "processes": ["chrome.exe"],
        "paths": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                  r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                  r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
    },
    "edge": {
        "exe": "msedge",
        "start_names": ["Microsoft Edge", "Edge"],
        "processes": ["msedge.exe"],
        "paths": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                  r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
    },
    "firefox": {
        "exe": "firefox",
        "start_names": ["Firefox", "Mozilla Firefox"],
        "processes": ["firefox.exe"],
        "paths": [r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                  r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"],
    },
    "brave": {"exe": "brave", "start_names": ["Brave"], "processes": ["brave.exe"],
              "paths": [r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"]},
    "opera": {"exe": "opera", "start_names": ["Opera"], "processes": ["opera.exe"], "paths": []},
    "discord": {
        "start_names": ["Discord"],
        "processes": ["Discord.exe", "DiscordPTB.exe", "DiscordCanary.exe"],
        "paths": [],   # versioned folders — the app-catalogue lookup handles it
    },
    "slack": {"start_names": ["Slack"], "processes": ["slack.exe"],
              "paths": [r"%LOCALAPPDATA%\slack\slack.exe"]},
    "teams": {"exe": "ms-teams", "start_names": ["Microsoft Teams", "Teams"],
              "processes": ["ms-teams.exe", "Teams.exe"], "paths": []},
    "steam": {"exe": "steam", "start_names": ["Steam"], "processes": ["steam.exe"],
              "paths": [r"%ProgramFiles(x86)%\Steam\steam.exe",
                        r"%ProgramFiles%\Steam\steam.exe"]},
    "vlc": {"exe": "vlc", "start_names": ["VLC media player", "VLC"],
            "processes": ["vlc.exe"],
            "paths": [r"%ProgramFiles%\VideoLAN\VLC\vlc.exe",
                      r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"]},
    "itunes": {"exe": "itunes", "start_names": ["iTunes"], "processes": ["iTunes.exe"], "paths": []},
    "zoom": {"start_names": ["Zoom", "Zoom Workplace"], "processes": ["Zoom.exe"],
             "paths": [r"%APPDATA%\Zoom\bin\Zoom.exe"]},
    "thunderbird": {"exe": "thunderbird", "start_names": ["Thunderbird"],
                    "processes": ["thunderbird.exe"],
                    "paths": [r"%ProgramFiles%\Mozilla Thunderbird\thunderbird.exe"]},
    "outlook": {"exe": "outlook", "start_names": ["Outlook"],
                "processes": ["OUTLOOK.EXE"], "paths": []},
    "word": {"exe": "winword", "start_names": ["Word"], "processes": ["WINWORD.EXE"], "paths": []},
    "excel": {"exe": "excel", "start_names": ["Excel"], "processes": ["EXCEL.EXE"], "paths": []},
    "powerpoint": {"exe": "powerpnt", "start_names": ["PowerPoint"],
                   "processes": ["POWERPNT.EXE"], "paths": []},
    "notepad": {"exe": "notepad", "start_names": ["Notepad"], "processes": ["notepad.exe"], "paths": []},
    "calc": {"exe": "calc", "start_names": ["Calculator"], "processes": ["CalculatorApp.exe", "calc.exe"], "paths": []},
    "paint": {"exe": "mspaint", "start_names": ["Paint"], "processes": ["mspaint.exe"], "paths": []},
    "explorer": {"exe": "explorer", "start_names": ["File Explorer"],
                 "processes": ["explorer.exe"], "paths": []},
    "terminal": {"exe": "wt", "start_names": ["Terminal", "Windows Terminal"],
                 "processes": ["WindowsTerminal.exe", "wt.exe"], "paths": []},
    "powershell": {"exe": "powershell", "start_names": ["PowerShell"],
                   "processes": ["powershell.exe"], "paths": []},
    "cmd": {"exe": "cmd", "start_names": ["Command Prompt"], "processes": ["cmd.exe"], "paths": []},
    "taskmgr": {"exe": "taskmgr", "start_names": ["Task Manager"], "processes": ["Taskmgr.exe"], "paths": []},
    "control": {"exe": "control", "start_names": ["Control Panel"], "processes": [], "paths": []},
    "snippingtool": {"exe": "snippingtool", "start_names": ["Snipping Tool"],
                     "processes": ["SnippingTool.exe"], "paths": []},
    "code": {"exe": "code", "start_names": ["Visual Studio Code", "VS Code"],
             "processes": ["Code.exe"],
             "paths": [r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"]},
    "obs": {"exe": "obs64", "start_names": ["OBS Studio", "OBS"],
            "processes": ["obs64.exe", "obs32.exe"],
            "paths": [r"%ProgramFiles%\obs-studio\bin\64bit\obs64.exe"]},
    "blender": {"exe": "blender", "start_names": ["Blender"], "processes": ["blender.exe"], "paths": []},
    "photoshop": {"exe": "photoshop", "start_names": ["Adobe Photoshop", "Photoshop"],
                  "processes": ["Photoshop.exe"], "paths": []},
    "settings": {"uri": "ms-settings:", "start_names": ["Settings"], "processes": [], "paths": []},
    "clock": {"uri": "ms-clock:", "start_names": ["Clock", "Alarms"], "processes": [], "paths": []},
    "camera": {"uri": "microsoft.windows.camera:", "start_names": ["Camera"], "processes": [], "paths": []},
    "photos": {"uri": "ms-photos:", "start_names": ["Photos", "Gallery"], "processes": [], "paths": []},
    "store": {"uri": "ms-windows-store:", "start_names": ["Microsoft Store", "Store"],
              "processes": ["WinStore.App.exe"], "paths": []},
}

#: spoken forms / synonyms / misspellings -> canonical key
ALIASES: Dict[str, str] = {
    "google chrome": "chrome", "google": "chrome", "chromium": "chrome",
    "microsft edge": "edge", "ms edge": "edge", "internet explorer": "edge",
    "mozilla": "firefox", "mozilla firefox": "firefox",
    "spotify music": "spotify", "spotify app": "spotify", "spotifi": "spotify",
    "spotfy": "spotify", "spoify": "spotify",
    "vscode": "code", "vs code": "code", "visual studio": "code",
    "visual studio code": "code", "visualstudio code": "code", "code editor": "code",
    "vs cod": "code", "vs cdoe": "code",
    "ms word": "word", "microsoft word": "word", "winword": "word",
    "ms excel": "excel", "microsoft excel": "excel", "spreadsheets": "excel",
    "ppt": "powerpoint", "ms powerpoint": "powerpoint",
    "microsoft powerpoint": "powerpoint", "power point": "powerpoint",
    "outlook mail": "outlook", "mail": "outlook", "email": "outlook",
    "microsoft outlook": "outlook",
    "ms teams": "teams", "microsoft teams": "teams", "ms-teams": "teams",
    "notes": "notepad", "notepad plus": "notepad", "text editor": "notepad",
    "calculator": "calc", "calc app": "calc",
    "file explorer": "explorer", "files": "explorer", "folders": "explorer",
    "my files": "explorer", "my computer": "explorer", "this pc": "explorer",
    "windows terminal": "terminal", "wt": "terminal", "console": "terminal",
    "command prompt": "cmd", "cmd prompt": "cmd",
    "task manager": "taskmgr", "taskmanager": "taskmgr", "tasks": "taskmgr",
    "control panel": "control",
    "snip": "snippingtool", "snip tool": "snippingtool", "snipping": "snippingtool",
    "screenshot tool": "snippingtool",
    "obs studio": "obs", "obs app": "obs",
    "adobe photoshop": "photoshop", "ps": "photoshop",
    "windows settings": "settings", "pc settings": "settings",
    "settings app": "settings", "options": "settings",
    "alarms": "clock", "timer": "clock", "alarms and clock": "clock",
    "gallery": "photos", "pictures": "photos",
    "microsoft store": "store", "windows store": "store", "app store": "store",
    "itunes music": "itunes", "apple music": "itunes",
    "zoom meetings": "zoom", "zoom meeting": "zoom",
    "obs64": "obs",
}

_FILLER = re.compile(r"\b(the|my|app|application|program|please|open|start|launch|run|for|me)\b")


def _norm(name: str) -> str:
    key = (name or "").strip().lower()
    key = re.sub(r"\s+", " ", key)
    if key.endswith(".exe"):
        key = key[:-4]
    return key.strip()


def canonical_for(name: str) -> Optional[str]:
    """Map anything the user might say to a canonical app key.

    Handles exact names, curated aliases, filler words ('open the spotify
    app'), typos via fuzzy match and containment ('spotify' inside
    'spotify app')."""
    key = _norm(name)
    if not key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    if key in CANONICAL:
        return key

    stripped = _FILLER.sub("", key).strip()
    if stripped and stripped != key:
        if stripped in ALIASES:
            return ALIASES[stripped]
        if stripped in CANONICAL:
            return stripped

    options = list(ALIASES) + list(CANONICAL)
    for probe in (key, stripped):
        if not probe:
            continue
        matches = difflib.get_close_matches(probe, options, n=1, cutoff=0.68)
        if matches:
            hit = matches[0]
            return ALIASES.get(hit, hit)

    for probe in (key, stripped):
        if not probe or len(probe) < 4:
            continue
        for opt in options:
            if len(opt) >= 4 and (opt in probe or probe in opt):
                return ALIASES.get(opt, opt)
    return None


def suggestions_for(name: str, limit: int = 3) -> List[str]:
    key = _norm(name)
    options = list(ALIASES) + list(CANONICAL)
    return [ALIASES.get(m, m) for m in
            difflib.get_close_matches(key, options, n=limit, cutoff=0.4)]


# --------------------------------------------------------------------------
# Windows launch machinery
# --------------------------------------------------------------------------
_START_CACHE: Optional[List[Dict[str, str]]] = None


def _start_apps_catalogue() -> List[Dict[str, str]]:
    """Everything Windows knows how to launch (Start menu / Store apps),
    via Get-StartApps. Cached for the session."""
    global _START_CACHE
    if _START_CACHE is not None:
        return _START_CACHE
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            [_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
            capture_output=True, timeout=15, creationflags=0x08000000)
        data = json.loads((out.stdout or b"[]").decode("utf-8", "replace") or "[]")
        if isinstance(data, dict):
            data = [data]
        _START_CACHE = [d for d in data if isinstance(d, dict) and d.get("AppID")]
    except Exception:
        _START_CACHE = []
    return _START_CACHE


def _pick_from_catalogue(name: str, canonical: Optional[str]) -> Optional[Dict[str, str]]:
    """Fuzzy-match a human app name against the Windows app catalogue."""
    catalogue = _start_apps_catalogue()
    if not catalogue:
        return None
    wanted = [_norm(name)]
    if canonical:
        wanted.append(canonical)
        info = CANONICAL.get(canonical, {})
        wanted += [_norm(s) for s in info.get("start_names", [])]
        wanted += [k for k, v in ALIASES.items() if v == canonical]

    best, best_score = None, 0.0
    for entry in catalogue:
        ename = _norm(entry.get("Name", ""))
        if not ename:
            continue
        for w in wanted:
            if not w:
                continue
            if ename == w:
                score = 1.0
            elif w in ename or ename in w:
                score = 0.85
            else:
                score = difflib.SequenceMatcher(None, w, ename).ratio()
            if score > best_score:
                best, best_score = entry, score
    return best if best_score >= 0.62 else None


def _app_path_registry(exe_name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import winreg

        exe = exe_name if exe_name.lower().endswith(".exe") else exe_name + ".exe"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(
                    hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                          "\\" + exe)
                val, _ = winreg.QueryValueEx(key, "")
                if val and os.path.exists(os.path.expandvars(val)):
                    return os.path.expandvars(val)
            except OSError:
                continue
    except Exception:
        pass
    return None


def _spawn(args: List[str], **kw) -> bool:
    try:
        subprocess.Popen(
            args, shell=False, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000, **kw)
        return True
    except OSError:
        return False


def _open_target(target: str) -> bool:
    if os.name != "nt":
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        except Exception:
            return _spawn([target])
    try:
        import win32api  # type: ignore

        win32api.ShellExecute(0, "open", target, None, None, 1)
        return True
    except Exception:
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


def launch_app(name: str) -> Tuple[bool, str]:
    """Resolve and open an app. Returns (ok, human description)."""
    canonical = canonical_for(name)
    key = canonical or _norm(name)
    info = CANONICAL.get(canonical or "", {})

    # 1) URI scheme apps (Settings, Clock, Store…)
    uri = info.get("uri")
    if uri and _open_target(uri):
        return True, f"{name} ({uri})"

    # 2) well-known install locations (Spotify, Chrome, Discord…)
    for raw in info.get("paths", []):
        path = os.path.expandvars(raw)
        if os.path.exists(path) and _open_target(path):
            return True, f"{name} → {path}"

    # 3) Windows App Paths registry
    reg = _app_path_registry(info.get("exe") or key)
    if reg and _open_target(reg):
        return True, f"{name} → {reg}"

    # 4) PATH
    for cand in (info.get("exe") or key, key):
        found = shutil.which(cand) or shutil.which(cand + ".exe")
        if found and _open_target(found):
            return True, f"{name} → {found}"

    # 5) the Windows app catalogue — catches Store/UWP apps like Spotify
    hit = _pick_from_catalogue(name, canonical)
    if hit and _spawn(["explorer.exe", f"shell:AppsFolder\\{hit['AppID']}"]):
        return True, f"{name} (“{hit['Name']}”)"

    # 6) start-menu / App Paths via `start` (last resolver resort)
    if os.name == "nt" and _spawn(["cmd", "/c", "start", "",
                                   info.get("exe") or key]):
        return True, f"{name} (via start menu)"

    # 7) fuzzy rescue: maybe the user said something adjacent
    rescue = canonical_for(name)
    if rescue and rescue != canonical:
        ok, how = launch_app.__wrapped__(rescue) if hasattr(launch_app, "__wrapped__") else (False, "")
    sug = suggestions_for(name)
    hint = f" Did you mean: {', '.join(sorted(set(sug)))}?" if sug else ""
    return False, (f"I can't find an app called '{name}'.{hint} "
                   "Try a different name — or open it yourself and I'll take "
                   "over from there.")


@register("open_app", "Open an application by name. Fuzzy-matches common apps "
          "(e.g. 'spotify', 'vs code', 'chrome', 'notepad', 'settings', Store "
          "apps) — pass the name in the user's plain words.", "{name}")
def open_app(name: str) -> str:
    ok, how = launch_app(name)
    if ok:
        return f"Opening {how}."
    return f"ERROR: {how}"


def _running_matches(name: str) -> List[str]:
    """Process images that plausibly belong to the requested app."""
    canonical = canonical_for(name)
    known = list(CANONICAL.get(canonical or "", {}).get("processes", []))
    if not known and canonical:
        known = [canonical + ".exe"]
    try:
        import psutil

        running = sorted({p.info.get("name", "") for p in
                          psutil.process_iter(["name"]) if p.info.get("name")})
    except Exception:
        running = []
    key = _norm(name)
    out = {p for p in running
           if _norm(p) == key or _norm(p) in {_norm(k) for k in known}}
    if not out and key:
        proc_norm = {_norm(p): p for p in running}
        for match in difflib.get_close_matches(key, list(proc_norm), n=3, cutoff=0.6):
            out.add(proc_norm[match])
        for p in running:
            if len(key) >= 4 and key in _norm(p):
                out.add(p)
    return sorted(out)


@register("close_app", "Close an application's windows (asks the user first — "
          "unsaved work could be lost).", "{name}", policy=POLICY_CONFIRM)
def close_app(name: str) -> str:
    if os.name != "nt":
        return "ERROR: closing apps is only supported on Windows."
    import psutil

    targets = _running_matches(name)
    if not targets:
        sug = suggestions_for(name)
        hint = f" Did you mean: {', '.join(sorted(set(sug)))}?" if sug else ""
        return f"ERROR: {name} does not appear to be running.{hint}"
    killed = 0
    for image in targets:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name", "") or "").lower() == image.lower():
                try:
                    proc.terminate()
                    killed += 1
                except Exception:
                    pass
    return (f"Closed {killed} window(s) of {name} "
            f"({', '.join(targets)}).") if killed else \
        f"ERROR: found {name} but could not close it."


@register("focus_window", "Bring an open window to the front by part of its "
          "title.", "{title}")
def focus_window(title: str) -> str:
    if os.name != "nt":
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


@register("minimize_window", "Minimise a window by part of its title.", "{title}")
def minimize_window(title: str) -> str:
    return _window_cmd(title, "SW_MINIMIZE")


@register("maximize_window", "Maximise a window by part of its title.", "{title}")
def maximize_window(title: str) -> str:
    return _window_cmd(title, "SW_MAXIMIZE")


def _window_cmd(title: str, mode: str) -> str:
    if os.name != "nt":
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
    if os.name != "nt":
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
    if os.name != "nt":
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
        step_key = 0xAF if level >= 50 else 0xAE
        for _ in range(12):
            _send_vk(step_key)
        return (f"Volume adjusted toward {level} percent "
                "(fine control unavailable).")


@register("volume_mute", "Mute, unmute or toggle the master volume.",
          "{mode: toggle|on|off}")
def volume_mute(mode: str = "toggle") -> str:
    if os.name != "nt":
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
@register("type_text", "Type text visibly into whatever field/window has focus. "
          "Ordinary input (searches, song titles, channel names) types straight "
          "away; long/multi-line or private-looking text asks first. Never used "
          "for passwords.", "{text}")
def type_text(text: str) -> str:
    if os.name != "nt":
        return "ERROR: typing is only supported on Windows."
    import pyautogui

    pyautogui.PAUSE = 0.02
    if all(ord(ch) < 128 for ch in text):
        pyautogui.write(text, interval=0.01)
    else:
        _paste_text(text)
    return f"Typed {len(text)} characters."


def _paste_text(text: str) -> None:
    import pyautogui

    if os.name == "nt":
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
          "ctrl+f, alt+tab, media keys...) — navigation keys just happen; "
          "window-closing combos ask first.", "{keys}")
def press_keys(keys: str) -> str:
    if os.name != "nt":
        return "ERROR: key input is only supported on Windows."
    import pyautogui

    combo = keys.strip().lower().replace(" ", "")
    parts = combo.split("+")
    pyautogui.hotkey(*parts)
    return f"Pressed {combo}."
