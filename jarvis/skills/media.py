"""Play media INSIDE a desktop app — the whole ritual, verified in code.

This encodes the common sense the brain kept fumbling ("played the first
song on Spotify", "opened it then gave up", "takes years"): focus the app,
WAIT until its window and RESULTS are really ready, open ITS search, type
the query, READ the on-screen rows and DOUBLE-click the one that genuinely
matches the request — never a bare "Play" button, never the user's own
mixes, never a guess-click, and no extra AI round-trip on success.
"""
from __future__ import annotations

import os
import re
import time
from typing import List

from ..guardrails import looks_crucial_text
from . import apps, register
from .click import _do_click, _find_element, _is_chrome, _norm, \
    _visible_labels

# Labels that are NEVER a search result — clicking one of these is exactly
# how Jarvis ended up "playing the first song".
_GENERIC = {
    "play", "pause", "songs", "search", "home", "your library", "library",
    "playlist", "playlists", "more", "like", "next", "previous", "shuffle",
    "radio", "browse", "premium", "profile", "settings", "queue", "all",
    "your top mixes", "made for you", "recently played", "jump back in",
    "top results", "tracks", "artists", "albums", "podcasts", "videos",
    "your episodes", "downloaded", "create playlist", "whats new",
}
# Filler words that carry no identifying meaning for matching.
_STOP = {"play", "the", "a", "an", "by", "on", "in", "my", "some", "song",
         "video", "videos", "channel", "music", "please", "and", "of",
         "to", "from", "latest", "me", "put", "up", "search"}


def _tokens(query: str) -> List[str]:
    """Meaningful words of the request: 'kanye west violent crimes' ->
    ['kanye', 'west', 'violent', 'crimes']."""
    return [t for t in re.findall(r"[a-z0-9]+", _norm(query))
            if t not in _STOP and len(t) > 1]


def _row_score(label: str, tokens: List[str]) -> float:
    """How much of the request this visible label actually fulfils:
    1.0 = every meaningful word present; 0.0 = irrelevant or generic."""
    lab = _norm(label)
    if not tokens or not lab or lab in _GENERIC or _is_chrome(lab):
        return 0.0
    hits = sum(1 for t in tokens if t in lab)
    if hits == 0:
        return 0.0
    score = hits / len(tokens)
    if score < 1.0:
        score = min(score, 0.8)      # a partial match never beats a full one
    return score


def _play_row(control) -> bool:
    """Start playback on a result row: DOUBLE-click (a single click usually
    only selects the row). Falls back to two rapid clicks."""
    try:
        control.SetFocus()
        control.DoubleClick()
        return True
    except Exception:
        pass
    try:
        if _do_click(control):
            time.sleep(0.12)
            return bool(_do_click(control))
    except Exception:
        pass
    return False


@register("media_play", "Play a song/album/podcast/video/channel inside a "
          "desktop app (spotify, youtube music…). Runs the WHOLE verified "
          "ritual: focuses the app, opens ITS search, types the query, "
          "WAITS for the results to appear, then DOUBLE-clicks the row that "
          "truly matches. Prefer this over manual type+click for 'play X'.",
          "{app} {query}")
def media_play(app: str = "spotify", query: str = "") -> str:
    app_name = (app or "spotify").strip() or "spotify"
    query = (query or "").strip()
    if not query:
        return ("ERROR: media_play needs to know what to play, e.g. "
                "query='violent crimes kanye west'.")
    if looks_crucial_text(query):
        return ("REFUSED: that query looks private/sensitive. If the user "
                "really wants it typed, do it with type_text so it can be "
                "approved first.")
    if os.name != "nt":
        return ("media_play: playback automation is Windows-only — nothing "
                "was done here.")

    # 1) Bring the app up and READY — verified by PROCESS, not title: a
    #    browser tab titled 'Spotify - Web Player' must never stand in for
    #    the desktop app (that is how searches ended up in the address bar).
    try:
        canon = apps.canonical_for(app_name) or app_name
    except Exception:
        canon = app_name
    title = _app_window(canon, timeout=4.0)      # already running?
    if not title:
        ok, msg = apps.launch_app(canon)
        if not ok:
            return f"ERROR: could not open the {app_name} desktop app: {msg}"
        title = _app_window(canon, timeout=25.0)
    if not title:
        return (f"ERROR: the {app_name} DESKTOP app window never appeared. "
                "If you only have it open in your web browser, open or "
                "install the desktop app — Jarvis automates the real app, "
                "not a browser tab.")

    def search_and_pick(q: str) -> str:
        """Search q in the app's OWN field, READ the screen until real
        results appear, and double-click the row that truly matches.
        Returns the success message, or '' when nothing clearly matched."""
        try:
            apps.press_keys("ctrl+k")    # focus the app's search field
            time.sleep(0.35)
            apps.type_text(q)
            time.sleep(0.15)
            apps.press_keys("enter")
        except Exception as exc:
            return f"ERROR: could not drive {app_name}'s search: {exc}"
        toks = _tokens(q)
        labels: List[str] = []
        deadline = time.time() + 4.0
        while True:
            try:
                labels = _visible_labels(80)
            except Exception:
                labels = []
            if labels or time.time() > deadline:
                break                    # chrome is filtered at the source
            time.sleep(0.4)
        best_label, best = "", 0.0
        for label in labels:
            sc = _row_score(label, toks)
            if sc > best:
                best_label, best = label, sc
        if best_label and best >= 0.5:
            for _attempt in range(2):    # one re-find after the UI settles
                ctrl, score = _find_element(best_label)
                if ctrl is not None and _play_row(ctrl):
                    time.sleep(1.2)      # let playback actually start
                    return (f"Playing “{best_label}” in {canon.title()} — "
                            f"matched {max(best, score):.0%} of “{q}”.")
                time.sleep(0.6)
        return ""

    # 2) Search + read + play — and if the full request matched nothing,
    #    SIMPLIFY the query (its first meaningful words) and try once more
    #    before ever reporting failure.
    result = search_and_pick(query)
    if result:
        return result
    tokens = _tokens(query)
    if len(tokens) > 2:
        result = search_and_pick(" ".join(tokens[:2]))
        if result:
            return result + " (found it after simplifying the search)"

    # 4) Still nothing after both attempts: report what WAS on screen so
    #    the brain can pick an exact label — never a guess-click.
    labels = _visible_labels(80)
    if not labels:
        hint = ("Only window controls were visible — the results may still "
                "be loading. Wait a moment, then call screen_state and "
                "click an exact label you see.")
    else:
        hint = ("Visible: " + "; ".join(labels[:12]) + ". Click an exact "
                "listed label, or retry with a simpler query "
                "(artist + title).")
    return (f"ERROR: searched, but nothing on screen clearly matches "
            f"“{query}”. {hint}")


def _process_of(hwnd) -> str:
    """Name of the process that OWNS a window ('spotify' for Spotify.exe).
    Empty off-Windows or whenever it cannot be determined. Never raises."""
    if os.name != "nt":
        return ""
    try:
        import win32process  # type: ignore
        import psutil
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        name = psutil.Process(pid).name().lower()
        return name[:-4] if name.endswith(".exe") else name
    except Exception:
        return ""


def _app_window(app_key: str, timeout: float = 10.0) -> str:
    """Wait for a visible window OWNED BY the app's process, focus it and
    let it settle. Unlike title matching, a browser tab mentioning the app
    in its title can never match. Returns the window title or ''. """
    if os.name != "nt":
        return ""
    try:
        import win32gui  # type: ignore
    except Exception:
        time.sleep(min(2.0, timeout))
        return ""
    key = _norm(app_key)

    def owns(hwnd) -> bool:
        proc = _process_of(hwnd)
        return bool(proc) and (proc == key or key in proc or proc in key)

    deadline = time.time() + max(0.5, timeout)
    found = 0
    while time.time() < deadline:
        hits: list = []

        def enum(hwnd, acc):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    if win32gui.GetWindowText(hwnd) and owns(hwnd):
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
        win32gui.SetForegroundWindow(found)
    except Exception:
        pass
    time.sleep(0.6)                          # let it paint & accept input
    try:
        return win32gui.GetWindowText(found)
    except Exception:
        return ""
