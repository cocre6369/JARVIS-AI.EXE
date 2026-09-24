"""Play media INSIDE a desktop app — the whole ritual, verified in code.

This encodes the common sense the brain kept fumbling ("played the first
song on Spotify", "opened it then gave up"): focus the app, WAIT until its
window is really ready, open ITS search, type the query, READ the on-screen
results and click the row that genuinely matches the request — never a bare
"Play" button, never the user's own mixes, and never a guess-click.
"""
from __future__ import annotations

import os
import re
import time
from typing import List

from ..guardrails import looks_crucial_text
from . import apps, register
from .click import _do_click, _find_element, _norm, _visible_labels, \
    wait_for_window

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
         "to", "from", "latest", "me", "put"}


def _tokens(query: str) -> List[str]:
    """Meaningful words of the request: 'violent crimes kanye west' ->
    ['violent', 'crimes', 'kanye', 'west']."""
    return [t for t in re.findall(r"[a-z0-9]+", _norm(query))
            if t not in _STOP and len(t) > 1]


def _row_score(label: str, tokens: List[str]) -> float:
    """How much of the request this visible label actually fulfils:
    1.0 = every meaningful word present; 0.0 = irrelevant or generic."""
    lab = _norm(label)
    if not tokens or not lab or lab in _GENERIC:
        return 0.0
    hits = sum(1 for t in tokens if t in lab)
    if hits == 0:
        return 0.0
    score = hits / len(tokens)
    if score < 1.0:
        score = min(score, 0.8)      # a partial match never beats a full one
    return score


@register("media_play", "Play a song/album/podcast/video/channel inside a "
          "desktop app (spotify, spotify, youtube music…). Runs the WHOLE "
          "verified ritual: focuses the app, opens ITS search, types the "
          "query, READS the on-screen results and clicks the row that truly "
          "matches. Prefer this over manual type+click for 'play X'.",
          "{app} {query}", returns_data=True)
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

    # 1) Bring the app up and READY (the 'give Spotify time to open' fix).
    try:
        canon = apps.canonical_for(app_name) or app_name
    except Exception:
        canon = app_name
    title = wait_for_window(canon, timeout=6.0)
    if not title:
        ok, msg = apps.launch_app(canon)
        if not ok:
            return f"ERROR: could not open {app_name}: {msg}"
        title = wait_for_window(canon, timeout=20.0) or canon

    # 2) Drive the app's OWN search — never the browser, never another app.
    try:
        apps.press_keys("ctrl+k")        # focus the app's search field
        time.sleep(0.7)
        apps.type_text(query)
        time.sleep(0.4)
        apps.press_keys("enter")
        time.sleep(2.5)                  # results need a moment to load
    except Exception as exc:
        return f"ERROR: could not drive {app_name}'s search: {exc}"

    # 3) READ the screen; click only a row that genuinely matches.
    tokens = _tokens(query)
    try:
        labels = _visible_labels(80)
    except Exception:
        labels = []
    best_label, best = "", 0.0
    for label in labels:
        s = _row_score(label, tokens)
        if s > best:
            best_label, best = label, s
    if best_label and best >= 0.5:
        for _attempt in range(2):        # one re-find after the UI settles
            ctrl, score = _find_element(best_label)
            if ctrl is not None and _do_click(ctrl):
                time.sleep(1.5)          # let playback actually start
                return (f"Playing “{best_label}” in {canon.title()} — "
                        f"matched {max(best, score):.0%} of “{query}”.")
            time.sleep(0.8)

    # 4) No confident match: report what WAS on screen so the brain can pick
    #    an exact label or simplify the query — never guess-click.
    near = "; ".join(labels[:12]) or "(no labelled controls read)"
    return ("ERROR: searched, but nothing on screen clearly matches "
            f"“{query}”. Visible: {near}. Click an exact listed label, or "
            "retry with a simpler query (artist + title).")
