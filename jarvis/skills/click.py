"""On-screen click skill — completes tasks instead of half-doing them.

Uses Windows UI Automation (accessibility API) to find a clickable element in
the foreground window BY ITS VISIBLE LABEL — "Violent Crimes", "Play", a
search-result row — and click it. This is how Jarvis finishes "play X" by
actually starting playback instead of merely typing a query.

Safety (see guardrails for the policy escalation):
- clicks are visible on screen (the cursor moves to the target);
- labels that look destructive/financial (delete, buy, send, publish…)
  require user confirmation first;
- no element matching the label -> a clear error so the model can fall back
  to keyboard selection (down + enter) or ask the user.
"""
from __future__ import annotations

import difflib
import re
import time
from typing import List, Optional, Tuple

from . import register

_SEARCH_BUDGET_S = 5.0
_MAX_NODES = 2500


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

# Window buttons that exist on every title bar — never search results.
_CHROME = {"minimise", "minimize", "maximise", "maximize", "restore",
           "close", "back", "forward"}


def _is_chrome(label: str) -> bool:
    return _norm(label) in _CHROME


def _find_element(name: str, timeout: float = _SEARCH_BUDGET_S):
    """Search the foreground window's UIA tree for a label matching *name*.

    Returns (control, score) for the best match (score >= 0.55) or None.
    """
    import uiautomation as auto  # type: ignore

    window = auto.GetForegroundControl()
    if window is None:
        return None, 0.0
    needle = _norm(name)
    if not needle:
        return None, 0.0

    best, best_score = None, 0.0
    seen = 0
    deadline = time.time() + timeout
    try:
        for control, _depth in auto.WalkControl(window, includeTop=False,
                                                maxDepth=12):
            seen += 1
            if seen > _MAX_NODES or time.time() > deadline:
                break
            try:
                elname = _norm(control.Name)
            except Exception:
                continue
            if not elname:
                continue
            if needle == elname:
                return control, 1.0
            if needle in elname or elname in needle:
                score = 0.85
            else:
                score = difflib.SequenceMatcher(None, needle, elname).ratio()
                if score < 0.55:
                    continue
            if score > best_score:
                best, best_score = control, score
            if best_score >= 0.92:
                break
    except Exception:
        pass
    return (best, best_score) if best_score >= 0.55 else (None, 0.0)


def _do_click(control) -> bool:
    import uiautomation as auto  # type: ignore

    try:
        control.SetFocus()
    except Exception:
        pass
    # Prefer the accessibility Invoke pattern (reliable), then a real
    # physical-style click at the element's centre (always visible).
    try:
        pattern = control.GetInvokePattern()
        if pattern:
            pattern.Invoke()
            return True
    except Exception:
        pass
    try:
        control.Click()
        return True
    except Exception:
        pass
    try:
        rect = control.BoundingRectangle
        if rect and rect.width() > 0:
            import pyautogui

            pyautogui.click(rect.xcenter(), rect.ycenter())
            return True
    except Exception:
        pass
    return False


@register("click", "Click the on-screen button, link, row or search result "
          "whose visible label matches {name} in the FRONT window (bring the "
          "app forward first with focus_window). Use this to actually FINISH "
          "a task: play the song, open the video, press Play, select the "
          "result you just searched for. Labels that delete, buy, pay, send "
          "or publish ask the user first.", "{name}")
def click(name: str) -> str:
    label = (name or "").strip()
    if not label:
        return "ERROR: click needs the label of what to click."
    if os_name_is_not_windows():
        return "ERROR: clicking is only supported on Windows."
    try:
        control, score = _find_element(label)
    except Exception as exc:
        return (f"ERROR: could not inspect the screen ({exc}). "
                "Use press_keys instead (down + enter selects the "
                "highlighted result).")
    if control is None:
        near = _visible_labels(12)
        seen = (" Closest visible labels: " + "; ".join(near) + ".") if near \
            else " No labelled controls found — the window may still be loading."
        return (f"ERROR: nothing clickable labelled '{label}' in the front "
                f"window.{seen} Don't give up: call screen_state and click an "
                "exact label you saw, or press_keys down then enter.")
    try:
        shown = control.Name
    except Exception:
        shown = label
    if _do_click(control):
        return f"Clicked “{shown}” (match {score:.0%})."
    return f"ERROR: found “{shown}” but could not click it."


@register("double_click", "Double-click an on-screen item by its visible "
          "label (e.g. a file or list row).", "{name}")
def double_click(name: str) -> str:
    label = (name or "").strip()
    if not label:
        return "ERROR: double_click needs a label."
    if os_name_is_not_windows():
        return "ERROR: clicking is only supported on Windows."
    try:
        control, score = _find_element(label)
    except Exception as exc:
        return f"ERROR: could not inspect the screen ({exc})."
    if control is None:
        return f"ERROR: nothing labelled '{label}' in the front window."
    try:
        control.SetFocus()
        control.DoubleClick()
        return f"Double-clicked “{control.Name}”."
    except Exception as exc:
        return f"ERROR: double-click failed ({exc})."


@register("click_xy", "Click absolute screen coordinates (user confirms "
          "first — blind click). Prefer the 'click' tool with a label.",
          "{x, y}")
def click_xy(x: int, y: int) -> str:
    if os_name_is_not_windows():
        return "ERROR: clicking is only supported on Windows."
    try:
        import pyautogui

        pyautogui.click(int(x), int(y))
        return f"Clicked at ({int(x)}, {int(y)})."
    except Exception as exc:
        return f"ERROR: click failed ({exc})."


def os_name_is_not_windows() -> bool:
    import os

    return os.name != "nt"


# ─── screen reading + app-ready wait ───────────────────────────────────
def _title_matches(title: str, name: str) -> bool:
    t, n = _norm(title), _norm(name)
    return bool(n) and (n in t or t in n)


def wait_for_window(name: str, timeout: float = 15.0) -> str:
    """Wait until a window for the app exists, then focus it and let it
    settle. Stops Jarvis typing/clicking into a half-loaded app ('it opens
    Spotify and immediately selects stuff too early'). Returns the matched
    window title, or '' on best-effort failure. Never raises."""
    import os as _os
    if _os.name != "nt":
        return ""
    try:
        import win32gui  # type: ignore
    except Exception:
        time.sleep(min(2.0, timeout))
        return ""
    deadline = time.time() + max(0.5, timeout)
    found = 0
    while time.time() < deadline:
        hits: list = []

        def enum(hwnd, acc):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and _title_matches(title, name):
                        acc.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(enum, hits)
        except Exception:
            break
        if hits:
            found = hits[0]
            break
        time.sleep(0.25)
    if not found:
        return ""
    try:
        win32gui.ShowWindow(found, 9)        # SW_RESTORE
        win32gui.SetForegroundWindow(found)  # so input lands HERE
    except Exception:
        pass
    time.sleep(0.8)                          # let it paint & accept input
    try:
        return win32gui.GetWindowText(found)
    except Exception:
        return ""


@register("screen_state", "READ THE SCREEN: list the active window's visible "
          "controls with their exact labels (use before clicking when unsure "
          "what is on screen)", "{}", returns_data=True)
def screen_state(max_items: int = 60) -> str:
    """READ THE SCREEN: the active window's visible controls with their
    exact labels, as text the model can reason over. Call before clicking
    when unsure what is actually on screen. Never raises."""
    import os as _os
    if _os.name != "nt":
        return "screen_state: not on Windows — no UI tree available"
    try:
        import win32gui  # type: ignore
        title = win32gui.GetWindowText(win32gui.GetForegroundWindow()) \
            or "(untitled window)"
    except Exception:
        title = "(unknown window)"
    lines = [f"Window: {title}"]
    count = 0
    try:
        import uiautomation as auto  # type: ignore
        win = auto.GetForegroundControl()
        if win is None:
            return lines[0] + "\n(no controls read)"
        queue = [(win, 0)]
        while queue and count < max_items:
            elem, depth = queue.pop(0)
            try:
                name = (elem.Name or "").strip()
                ctype = str(elem.ControlTypeName or "") \
                    .replace("Control", "").strip()
            except Exception:
                continue
            if (name and 0 < len(name) <= 60 and depth > 0
                    and not _is_chrome(name)):
                lines.append(f"{'  ' * min(depth, 3)}[{ctype}] {name}")
                count += 1
            try:
                kids = elem.GetChildren() or []
            except Exception:
                kids = []
            if depth < 6:
                for k in kids[:16]:
                    queue.append((k, depth + 1))
        if count == 0:
            lines.append("(no labelled controls found — the window may "
                         "still be loading; retry screen_state shortly)")
    except Exception as exc:
        lines.append(f"(UI read failed: {exc})")
    return "\n".join(lines)


def _visible_labels(max_items: int = 25) -> List[str]:
    """Plain visible control labels of the foreground window (best-effort,
    never raises). Used by click failures and the media ritual so the brain
    can pick an EXACT label instead of guessing."""
    import os as _os
    if _os.name != "nt":
        return []
    out: List[str] = []
    try:
        import uiautomation as auto  # type: ignore
        window = auto.GetForegroundControl()
        if window is None:
            return []
        seen = 0
        deadline = time.time() + _SEARCH_BUDGET_S
        for control, _depth in auto.WalkControl(window, includeTop=False,
                                                maxDepth=12):
            seen += 1
            if seen > 400 or time.time() > deadline or len(out) >= max_items:
                break
            try:
                name = (control.Name or "").strip()
            except Exception:
                continue
            if (name and 0 < len(name) <= 60 and name not in out
                    and not _is_chrome(name)):
                out.append(name)
    except Exception:
        pass
    return out
