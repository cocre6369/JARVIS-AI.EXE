"""System tray icon (arc reactor) with show/hide and exit."""
from __future__ import annotations

import threading
from typing import Optional

from .. import store

_tray = None
_thread: Optional[threading.Thread] = None


def start_tray(hud) -> bool:
    """Start the tray icon if pystray is available. Returns success."""
    global _tray, _thread
    try:
        import pystray
        from PIL import Image
    except Exception:
        return False

    icon_path = store.resource_dir() / "assets" / "jarvis_icon.png"
    try:
        image = Image.open(icon_path)
    except Exception:
        return False

    def on_show(icon, _item):
        hud.call(hud.deiconify)
        hud.call(hud.lift)

    def on_exit(icon, _item):
        icon.stop()
        hud.call(hud.quit_app)

    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", on_show, default=True),
        pystray.MenuItem("Abort automation", lambda *_: hud.call(hud.abort_now)),
        pystray.MenuItem("Exit", on_exit),
    )
    _tray = pystray.Icon("JARVIS", image, "J.A.R.V.I.S.", menu)
    _thread = threading.Thread(target=_tray.run, daemon=True)
    _thread.start()
    return True


def notify(title: str, text: str) -> bool:
    """Best-effort balloon notification, visible from ANY app."""
    try:
        if _tray is not None and hasattr(_tray, "notify"):
            _tray.notify(text or "", title or "J.A.R.V.I.S.")
            return True
    except Exception:
        pass
    return False


def stop_tray() -> None:
    global _tray
    if _tray is not None:
        try:
            _tray.stop()
        except Exception:
            pass
        _tray = None
