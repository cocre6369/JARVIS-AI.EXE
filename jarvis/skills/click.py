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
from typing import Optional, Tuple

from . import register

_SEARCH_BUDGET_S = 5.0
_MAX_NODES = 500


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


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
                                                maxDepth=8):
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
        return (f"ERROR: nothing clickable labelled '{label}' in the front "
                "window. Try press_keys [down] then [enter] to activate the "
                "highlighted result, or ask the user to click it.")
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
