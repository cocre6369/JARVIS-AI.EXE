"""Iron Man / Stark HUD visual language."""
from __future__ import annotations

# ---------------------------------------------------------------- palette --
BG = "#04070c"            # deep space
PANEL = "#081120"         # panel navy
PANEL_2 = "#0b1826"
BORDER = "#0e3a4d"
CYAN = "#00d4ff"          # arc-reactor blue
CYAN_SOFT = "#3ee6ff"
CYAN_DIM = "#0a4a5e"
CYAN_TEXT = "#9be8f7"
GOLD = "#ffc857"          # mark-iii gold
GOLD_DIM = "#7a5b1e"
RED = "#ff3b30"
RED_DIM = "#5c1512"
GREEN = "#2ee66b"
TEXT = "#d3eef7"
MUTED = "#4f7787"
WHITE = "#ffffff"

# ------------------------------------------------------------------ fonts --
FONT_UI = ("Consolas", 10)
FONT_UI_B = ("Consolas", 10, "bold")
FONT_TITLE = ("Consolas", 14, "bold")
FONT_SMALL = ("Consolas", 8)
FONT_SMALL_B = ("Consolas", 8, "bold")
FONT_HERO = ("Consolas", 20, "bold")

# ------------------------------------------------------------------ state --
STATE_COLORS = {
    "IDLE": CYAN,
    "LISTENING": GREEN,
    "THINKING": GOLD,
    "ACTING": CYAN_SOFT,
    "SPEAKING": CYAN,
    "BLOCKED": RED,
    "ERROR": RED,
    "STANDBY": "#34525e",
}

STATE_LABELS = {
    "IDLE": "IDLE",
    "LISTENING": "LISTENING…",
    "THINKING": "PROCESSING…",
    "ACTING": "EXECUTING…",
    "SPEAKING": "RESPONDING…",
    "BLOCKED": "BLOCKED",
    "ERROR": "ERROR",
    "STANDBY": "STANDBY",
}

HOTKEY_HINTS = (
    "CTRL+ALT+P .... STANDBY / WAKE\n"
    "CTRL+ALT+SPACE  HOLD TO TALK\n"
    "CTRL+ALT+J .... SHOW / HIDE\n"
    "ESC ........... ABORT"
)


def style_ttk(root) -> None:
    """Force the dark palette onto ttk comboboxes etc."""
    try:
        from tkinter import ttk

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL_2,
                        background=PANEL_2, foreground=TEXT,
                        arrowcolor=CYAN, bordercolor=BORDER,
                        lightcolor=PANEL_2, darkcolor=PANEL_2)
        style.map("TCombobox",
                  fieldbackground=[("readonly", PANEL_2)],
                  foreground=[("readonly", TEXT)],
                  selectbackground=[("readonly", PANEL_2)],
                  selectforeground=[("readonly", CYAN)])
        style.configure("TEntry", fieldbackground=PANEL_2, foreground=TEXT,
                        bordercolor=BORDER)
    except Exception:
        pass


def styled_button(parent, text, command, kind="cyan", width=None):
    """Flat HUD button with hover glow."""
    import tkinter as tk

    base, hover, fg = {
        "cyan": (PANEL_2, CYAN_DIM, CYAN_TEXT),
        "gold": (PANEL_2, GOLD_DIM, GOLD),
        "red": (RED_DIM, RED, WHITE),
        "ghost": (BG, PANEL_2, MUTED),
    }[kind]

    btn = tk.Button(
        parent, text=text, command=command, font=FONT_UI_B,
        bg=base, fg=fg, activebackground=hover, activeforeground=WHITE,
        relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
        highlightthickness=1, highlightbackground=BORDER,
        highlightcolor=hover,
        width=width or 0,
    )

    def enter(_):
        btn.configure(bg=hover, highlightbackground=hover)

    def leave(_):
        btn.configure(bg=base, highlightbackground=BORDER)

    btn.bind("<Enter>", enter)
    btn.bind("<Leave>", leave)
    return btn


def hud_frame(parent, **kw):
    import tkinter as tk

    return tk.Frame(parent, bg=PANEL, highlightthickness=1,
                    highlightbackground=BORDER, **kw)


def bracket(canvas, x1, y1, x2, y2, color=CYAN_DIM, size=14, width=2):
    """Draw HUD corner brackets on a canvas."""
    canvas.create_line(x1, y1, x1 + size, y1, fill=color, width=width)
    canvas.create_line(x1, y1, x1, y1 + size, fill=color, width=width)
    canvas.create_line(x2, y1, x2 - size, y1, fill=color, width=width)
    canvas.create_line(x2, y1, x2, y1 + size, fill=color, width=width)
    canvas.create_line(x1, y2, x1 + size, y2, fill=color, width=width)
    canvas.create_line(x1, y2, x1, y2 - size, fill=color, width=width)
    canvas.create_line(x2, y2, x2 - size, y2, fill=color, width=width)
    canvas.create_line(x2, y2, x2, y2 - size, fill=color, width=width)
