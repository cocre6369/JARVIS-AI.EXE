"""Static lint: every Tk widget option used in the UI must actually exist.

This catches typos like ``minheight=34`` on a ``tk.Label`` (a real bug that
prevented the window from opening at all) without needing a display — it is
pure AST analysis and runs anywhere.

Run:  python -m unittest tests.test_tk_options -v
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Union of every option valid on any tk widget / geometry manager / canvas
# item / text tag / ttk style that this project may legitimately use.
KNOWN_OPTIONS = {
    # universal
    "text", "textvariable", "bitmap", "image", "compound", "underline",
    "font", "fg", "bg", "bd", "width", "height", "anchor", "padx", "pady",
    "relief", "borderwidth", "background", "foreground", "cursor", "state",
    "takefocus", "class", "colormap", "container", "visual", "screen",
    "title", "menu", "menuactive",
    # highlight / focus
    "highlightthickness", "highlightbackground", "highlightcolor",
    # label-ish
    "justify", "wraplength", "wrap", "activebackground", "activeforeground",
    "disabledforeground", "disabledbackground", "readonlybackground",
    # button-ish
    "command", "default", "overrelief", "repeatdelay", "repeatinterval",
    # entry-ish
    "insertbackground", "insertborderwidth", "insertofftime", "insertontime",
    "insertwidth", "invalidcommand", "show", "validate", "validatecommand",
    "exportselection", "xscrollcommand", "yscrollcommand",
    # checkbutton / radio
    "variable", "indicatoron", "onvalue", "offvalue", "selectcolor",
    "selectimage", "selectbackground", "selectforeground",
    "selectborderwidth", "troughcolor", "sliderlength", "sliderrelief",
    # canvas
    "closeenough", "confine", "scrollregion", "xscrollincrement",
    "yscrollincrement", "offset",
    # text widget + tags
    "autoseparators", "blockcursor", "endchar", "startchar", "endline",
    "startline", "inactiveselectbackground", "insertunfocussed", "maxundo",
    "setgrid", "spacing1", "spacing2", "spacing3", "tabs", "tabstyle",
    "undo", "lmargin1", "lmargin2", "rmargin", "elide", "overstrike",
    "relief", "justify",
    # scrollbar
    "activerelief", "elementborderwidth", "jump", "orient",
    # ttk widgets
    "values", "postcommand", "tearoff", "tearoffcommand", "type",
    # geometry managers
    "side", "fill", "expand", "ipadx", "ipady", "sticky", "row", "column",
    "rowspan", "columnspan", "before", "after", "in_",
    # canvas items
    "outline", "fill", "start", "extent", "style", "dash", "smooth", "tags",
    "arrow", "arrowshape", "capstyle", "joinstyle", "splinesteps", "angle",
    # ttk style.configure layout names (clam)
    "fieldbackground", "arrowcolor", "bordercolor", "lightcolor",
    "darkcolor", "indicatorcolor", "thumbthickness", "gripcount",
    "sliderthickness", "slidersize", "embordercolor", "tabmargins",
    # misc helpers used in this codebase
    "alpha", "topmost", "zoomed", "toolwindow", "disabled", "normal",
}

UI_FILES = [ROOT / "jarvis" / "ui" / f for f in
            ("hud.py", "widgets.py", "wizard.py", "theme.py", "tray.py")]
UI_FILES.append(ROOT / "main.py")

CHECK_FUNCS = {"configure", "itemconfigure", "config", "tag_configure",
               "tag_config", "style", "wm_attributes", "pack", "grid",
               "place"}


class TestTkOptionLints(unittest.TestCase):
    def test_no_unknown_tk_options(self):
        problems = []
        for path in UI_FILES:
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                interesting = name in {
                    "Label", "Button", "Entry", "Frame", "Canvas", "Text",
                    "Scrollbar", "Menu", "Checkbutton", "Radiobutton",
                    "Toplevel", "Tk", "Listbox", "Scale", "Spinbox",
                    "Combobox", "Notebook", "Progressbar", "Separator",
                    "Sizegrip", "Treeview", "PanedWindow",
                } or name in CHECK_FUNCS
                if not interesting:
                    continue
                for kw in node.keywords:
                    key = kw.arg or ""
                    if key and key not in KNOWN_OPTIONS:
                        problems.append(
                            f"{path.name}:{node.lineno}  {name}(... "
                            f"{key}=...) is not a valid Tk option")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
