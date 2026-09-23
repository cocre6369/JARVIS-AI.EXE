#!/usr/bin/env python3
"""J.A.R.V.I.S. — entry point.

Run directly (``python main.py``) or build the standalone Windows binary
(``build_exe.bat`` / the GitHub Actions workflow) into JARVIS-AI.exe.

Startup is staged and logged to %LOCALAPPDATA%\\JARVIS\\logs\\boot.log. ANY
failure — even one that takes out tkinter itself — surfaces a real error
dialog (native MessageBox as the last resort) instead of vanishing silently.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# Everything in this first block must be bulletproof stdlib-only.
try:
    from jarvis.store import APP_TITLE, VERSION, data_dir
except Exception:  # last-ditch location
    def data_dir() -> Path:                       # type: ignore
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        p = Path(base) / "JARVIS"
        p.mkdir(parents=True, exist_ok=True)
        return p
    APP_TITLE, VERSION = "J.A.R.V.I.S.", "0.0.0"

_BOOT: Path = data_dir() / "logs" / "boot.log"


def boot(stage: str) -> None:
    """Write one startup stage line so 'nothing happens' becomes diagnosable."""
    try:
        _BOOT.parent.mkdir(parents=True, exist_ok=True)
        if stage == "--reset--":
            _BOOT.write_text("", encoding="utf-8")
            return
        with _BOOT.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')}  {stage}\n")
    except Exception:
        pass


def show_error(title: str, text: str) -> None:
    """Always-visible error: tkinter box if possible, else native Win32 box."""
    text = (text or "Unknown error")[-1800:]
    try:
        import tkinter as tk
        import tkinter.messagebox as mb

        root = tk.Tk()
        root.withdraw()
        mb.showerror(title, text)
        root.destroy()
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        try:
            (data_dir() / "CRASH.txt").write_text(f"{title}\n\n{text}",
                                                  encoding="utf-8")
        except Exception:
            pass


def main() -> int:
    boot("--reset--")
    boot(f"boot — {APP_TITLE} v{VERSION}  (python {sys.version.split()[0]}, "
         f"frozen={bool(getattr(sys, 'frozen', False))})")
    boot(f"executable: {getattr(sys, 'executable', '?')}")
    boot(f"local data: {data_dir()}")

    log = None
    try:
        import logging

        log_dir = data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "jarvis.log"), level=logging.INFO,
            format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
        log = logging.getLogger("jarvis")
        boot("logging ready")
    except Exception as exc:
        boot(f"logging failed (continuing): {exc}")

    hud = None
    try:
        boot("importing tkinter…")
        import tkinter as tk
        boot("tkinter OK")

        boot("importing UI + core…")
        from jarvis.ui.hud import JarvisHUD
        from jarvis.ui.tray import start_tray
        boot("imports OK")

        boot("building HUD…")
        hud = JarvisHUD()
        boot("HUD online — entering main loop")

        try:
            if start_tray(hud):
                boot("tray icon online")
            else:
                boot("tray icon unavailable (non-fatal)")
        except Exception as exc:
            boot(f"tray error (non-fatal): {exc}")

        hud.mainloop()
        boot("main loop ended cleanly")
        return 0
    except KeyboardInterrupt:
        boot("interrupted by user")
        return 0
    except Exception:
        tb = traceback.format_exc()
        boot("FATAL STARTUP ERROR:\n" + tb)
        if log:
            log.error("Fatal:\n%s", tb)
        try:   # also drop a copy next to the exe when possible
            exe_dir = Path(getattr(sys, "executable", ".")).resolve().parent
            (exe_dir / "JARVIS-CRASH.txt").write_text(
                f"{APP_TITLE} startup failure\n\n{tb}\n\n"
                f"Run JARVIS-Doctor.bat for full diagnostics.",
                encoding="utf-8")
        except Exception:
            pass
        show_error(
            f"{APP_TITLE} — startup failure",
            "J.A.R.V.I.S. could not start. Details:\n\n"
            f"{tb[-1200:]}\n\n"
            f"A copy was saved to:\n{data_dir() / 'logs' / 'boot.log'}\n\n"
            "Also run JARVIS-Doctor.bat (next to the exe) and send me its "
            "output.")
        return 1
    finally:
        if hud is not None:
            try:
                hud.core.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
