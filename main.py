#!/usr/bin/env python3
"""J.A.R.V.I.S. — entry point.

Run directly (``python main.py``) or build the standalone Windows binary
(``build_exe.bat`` / the GitHub Actions workflow) into JARVIS-AI.exe.
"""
from __future__ import annotations

import logging
import sys
import traceback

from jarvis.store import APP_TITLE, VERSION, data_dir


def _setup_logging() -> logging.Logger:
    log_file = data_dir() / "logs"
    log_file.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file / "jarvis.log"),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    )
    return logging.getLogger("jarvis")


def main() -> int:
    log = _setup_logging()
    log.info("Starting %s v%s", APP_TITLE, VERSION)

    try:
        from jarvis.ui.hud import JarvisHUD
        from jarvis.ui.tray import start_tray
    except Exception:
        log.error("Import failure:\n%s", traceback.format_exc())
        try:
            import tkinter.messagebox as mb
            mb.showerror(APP_TITLE,
                         "J.A.R.V.I.S. failed to initialise.\n\n"
                         "See the log in %s" % (data_dir() / "logs"))
        except Exception:
            pass
        return 1

    hud = None
    try:
        hud = JarvisHUD()
        start_tray(hud)
        hud.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception:
        log.error("Fatal:\n%s", traceback.format_exc())
        if hud is not None:
            try:
                import tkinter.messagebox as mb
                mb.showerror(APP_TITLE,
                             "J.A.R.V.I.S. encountered a fault and will shut "
                             "down. Details were written to the log.")
            except Exception:
                pass
    finally:
        if hud is not None:
            try:
                hud.core.shutdown()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
