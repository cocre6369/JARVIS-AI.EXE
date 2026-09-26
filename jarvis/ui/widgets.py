"""Custom HUD widgets: the animated arc reactor and friends."""
from __future__ import annotations

import math
import tkinter as tk
from typing import Optional

from . import theme


class ArcReactor(tk.Canvas):
    """Animated arc-reactor core. Visual heartbeat of the assistant:

    IDLE      — slow cyan rotation
    LISTENING — green pulsing rings
    THINKING  — fast gold counter-rotation
    ACTING    — cyan sweep with an expanding ping
    BLOCKED / ERROR — red alarm pulse
    """

    SIZE = 190

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, width=self.SIZE, height=self.SIZE,
                         bg=theme.BG, highlightthickness=0, **kw)
        self.state = "IDLE"
        self.level = 0.0          # mic level 0..1 while listening
        self._t = 0.0
        self._items: dict = {}
        self._build()
        self._animate()

    # ------------------------------------------------------------------ --
    def _c(self) -> tuple:
        return self.SIZE / 2, self.SIZE / 2, self.SIZE * 0.42

    def _build(self) -> None:
        c = self.SIZE / 2
        r = self.SIZE * 0.42
        bg = theme.BG
        self.create_oval(c - r - 6, c - r - 6, c + r + 6, c + r + 6,
                         outline=theme.BORDER, width=1)
        # concentric housing
        self.create_oval(c - r, c - r, c + r, c + r,
                         outline=theme.CYAN_DIM, width=2)
        self.create_oval(c - r * 0.86, c - r * 0.86, c + r * 0.86, c + r * 0.86,
                         outline=theme.BORDER, width=1)
        self.create_oval(c - r * 0.55, c - r * 0.55, c + r * 0.55, c + r * 0.55,
                         outline=theme.CYAN_DIM, width=2)

        # 12 coil wedges
        self._items["coils"] = []
        for i in range(12):
            a0 = i * 30 + 7
            a1 = i * 30 + 23
            pts = []
            for a, rad in ((a0, r * 0.60), (a1, r * 0.60),
                           (a1, r * 0.82), (a0, r * 0.82)):
                ang = math.radians(a - 90)
                pts += [c + rad * math.cos(ang), c + rad * math.sin(ang)]
            item = self.create_polygon(pts, outline=theme.CYAN_DIM,
                                       fill="#06222e", width=1)
            self._items["coils"].append(item)

        # rotating arcs
        self._items["arc1"] = self.create_arc(
            c - r * 0.93, c - r * 0.93, c + r * 0.93, c + r * 0.93,
            start=20, extent=70, style="arc", outline=theme.CYAN, width=3)
        self._items["arc2"] = self.create_arc(
            c - r * 0.93, c - r * 0.93, c + r * 0.93, c + r * 0.93,
            start=200, extent=40, style="arc", outline=theme.CYAN_SOFT, width=2)
        self._items["ping"] = self.create_oval(
            c - r * 0.3, c - r * 0.3, c + r * 0.3, c + r * 0.3,
            outline="", width=2)

        # triangular core (inverted, like the mark-i reactor)
        s = r * 0.34
        self._items["core"] = self.create_polygon(
            c - s, c - s * 0.7, c + s, c - s * 0.7, c, c + s * 0.95,
            fill=theme.CYAN_SOFT, outline=theme.WHITE, width=1)
        self._items["halo"] = self.create_oval(
            c - s * 1.5, c - s * 1.5, c + s * 1.5, c + s * 1.5,
            outline="", width=2)

        # tick marks (HUD garnish)
        for i in range(60):
            ang = math.radians(i * 6 - 90)
            r1 = r * 1.02
            r2 = r * (1.08 if i % 5 == 0 else 1.05)
            self.create_line(c + r1 * math.cos(ang), c + r1 * math.sin(ang),
                             c + r2 * math.cos(ang), c + r2 * math.sin(ang),
                             fill=theme.CYAN_DIM if i % 5 == 0 else "#12303d")

    # ------------------------------------------------------------------ --
    def set_state(self, state: str) -> None:
        self.state = state

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, level / 32.0))

    def _animate(self) -> None:
        self._t += 1
        t = self._t
        state = self.state
        color = theme.STATE_COLORS.get(state, theme.CYAN)
        c = self.SIZE / 2
        r = self.SIZE * 0.42

        speed = {"IDLE": 0.6, "LISTENING": 2.2, "THINKING": 3.5,
                 "ACTING": 2.8, "SPEAKING": 1.6, "BLOCKED": 1.0,
                 "ERROR": 1.0, "STANDBY": 0.12}.get(state, 1.0)
        pulse = (math.sin(t * 0.08 * speed) + 1) / 2        # 0..1
        glow = 0.35 + 0.65 * (pulse if state != "IDLE" else 0.5 + pulse * 0.2)

        # coil glow
        coil_fill = _mix("#06222e", color, 0.15 + glow * 0.55)
        for item in self._items["coils"]:
            self.itemconfigure(item, fill=coil_fill, outline=color if glow > 0.6
                               else theme.CYAN_DIM)

        # rotation
        a1 = (t * speed * 1.4) % 360
        a2 = (-t * speed * 0.9) % 360
        self.itemconfigure(self._items["arc1"], outline=color,
                           width=3 if glow > 0.5 else 2)
        self.coords(self._items["arc1"],
                    c - r * 0.93, c - r * 0.93, c + r * 0.93, c + r * 0.93)
        self.itemconfigure(self._items["arc1"], start=a1, extent=60 + pulse * 30)
        self.itemconfigure(self._items["arc2"], outline=_mix(color, theme.WHITE, 0.3),
                           start=a2, extent=30 + pulse * 20)

        # core pulse / mic level
        energy = max(pulse * 0.35, self.level)
        s = r * (0.34 + energy * 0.06)
        self.coords(self._items["core"],
                    c - s, c - s * 0.7, c + s, c - s * 0.7, c, c + s * 0.95)
        self.itemconfigure(self._items["core"],
                           fill=_mix(color, theme.WHITE, 0.25 + energy * 0.4))

        # halo
        if state in ("ACTING", "LISTENING", "SPEAKING"):
            k = (t * speed * 0.02) % 1.0
            hr = r * (0.4 + k * 0.75)
            self.coords(self._items["halo"], c - hr, c - hr, c + hr, c + hr)
            self.itemconfigure(self._items["halo"], outline=_fade(color, 1 - k))
        elif state in ("BLOCKED", "ERROR"):
            if (t // 12) % 2 == 0:
                hr = r * 0.55
                self.coords(self._items["halo"], c - hr, c - hr, c + hr, c + hr)
                self.itemconfigure(self._items["halo"], outline=theme.RED, width=3)
            else:
                self.itemconfigure(self._items["halo"], outline="")
        else:
            self.itemconfigure(self._items["halo"], outline="")

        # ping ring while acting
        if state == "ACTING":
            k = (t * 0.03) % 1.0
            pr = r * (0.3 + k * 1.0)
            self.coords(self._items["ping"], c - pr, c - pr, c + pr, c + pr)
            self.itemconfigure(self._items["ping"], outline=_fade(theme.CYAN, 1 - k))
        else:
            self.itemconfigure(self._items["ping"], outline="")

        self.after(40, self._animate)


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v))) for v in rgb))


def _mix(a: str, b: str, k: float) -> str:
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    k = max(0.0, min(1.0, k))
    return _rgb_to_hex([ra[i] + (rb[i] - ra[i]) * k for i in range(3)])


def _fade(color: str, k: float) -> str:
    r, g, b = _hex_to_rgb(color)
    k = max(0.0, min(1.0, k))
    bg = _hex_to_rgb(theme.BG)
    return _rgb_to_hex([bg[i] + (v - bg[i]) * k for i, v in enumerate((r, g, b))])


class ScrollText(tk.Frame):
    """Dark themed scrolling text panel with tag helpers."""

    def __init__(self, parent, height=10, width=40, wrap="word",
                 font=None) -> None:
        super().__init__(parent, bg=theme.PANEL)
        self.text = tk.Text(
            self, height=height, width=width, wrap=wrap, font=font or theme.FONT_UI,
            bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.CYAN,
            relief="flat", bd=0, padx=10, pady=8, spacing1=2, spacing3=4,
            state="disabled", highlightthickness=1,
            highlightbackground=theme.BORDER,
        )
        scroll = tk.Scrollbar(self, command=self.text.yview, width=10,
                              troughcolor=theme.BG, bg=theme.CYAN_DIM,
                              activebackground=theme.CYAN, relief="flat",
                              bd=0, highlightthickness=0)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.text.tag_configure("user", foreground=theme.TEXT,
                                lmargin1=40, lmargin2=40, justify="right",
                                rmargin=8, font=theme.FONT_UI)
        self.text.tag_configure("user_who", foreground=theme.MUTED,
                                font=theme.FONT_SMALL_B, justify="right",
                                rmargin=8)
        self.text.tag_configure("jarvis", foreground=theme.CYAN_TEXT,
                                lmargin1=8, lmargin2=8, font=theme.FONT_UI)
        self.text.tag_configure("jarvis_who", foreground=theme.CYAN,
                                font=theme.FONT_SMALL_B)
        self.text.tag_configure("log_ok", foreground=theme.GREEN,
                                font=theme.FONT_SMALL)
        self.text.tag_configure("log_info", foreground=theme.MUTED,
                                font=theme.FONT_SMALL)
        self.text.tag_configure("log_act", foreground=theme.CYAN_TEXT,
                                font=theme.FONT_SMALL)
        self.text.tag_configure("log_warn", foreground=theme.GOLD,
                                font=theme.FONT_SMALL)
        self.text.tag_configure("log_err", foreground=theme.RED,
                                font=theme.FONT_SMALL)
        self.text.tag_configure("boot", foreground=theme.CYAN,
                                font=theme.FONT_SMALL_B)

    def add(self, line: str, tag: str = "log_info") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
