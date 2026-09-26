#!/usr/bin/env python3
"""Regenerate assets/jarvis_icon.ico (multi-resolution) from the PNG icon."""
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Pillow is required: pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "assets" / "jarvis_icon.png"
dst = ROOT / "assets" / "jarvis_icon.ico"

img = Image.open(src).convert("RGBA")
img.save(dst, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                     (128, 128), (256, 256)])
print(f"wrote {dst}")
