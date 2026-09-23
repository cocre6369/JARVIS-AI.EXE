# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for JARVIS-AI.exe (one-file, no console).

Environment:
  JARVIS_SLIM=1  -> build the Lite binary without the Whisper bundle
  JARVIS_NAME    -> override the output file stem
"""
import os

SLIM = os.environ.get("JARVIS_SLIM", "0") == "1"
OUTPUT_NAME = os.environ.get("JARVIS_NAME") or ("JARVIS-AI-Lite" if SLIM else "JARVIS-AI")

datas = [("assets", "assets"), ("jarvis_ai_prompt.txt", ".")]
binaries = []
hiddenimports = [
    "pyttsx3", "pyttsx3.drivers", "pyttsx3.drivers.sapi5",
    "pythoncom", "win32com", "win32com.client", "win32com.shell",
    "win32com.gen_py", "win32timezone", "pywintypes",
    "win32gui", "win32api", "win32con", "win32clipboard", "win32process",
    "comtypes", "comtypes.stream",
    "pystray", "pystray._win32",
    "pynput", "pynput.keyboard", "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "send2trash", "send2trash.util",
    "psutil",
    "requests", "certifi",
]

collect_targets = ["pycaw", "sounddevice", "pyautogui", "PIL", "tkinter"]
if not SLIM:
    collect_targets += [
        "faster_whisper", "ctranslate2", "tokenizers", "huggingface_hub",
        "av", "onnxruntime", "numpy",
    ]

for pkg in collect_targets:
    try:
        from PyInstaller.utils.hooks import collect_all

        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # pragma: no cover - build-time diagnostics
        print(f"WARN: collect_all({pkg!r}) skipped: {exc}")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "scipy", "matplotlib", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=OUTPUT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # windowed app — no black console box
    disable_windowed_traceback=False,
    icon="assets/jarvis_icon.ico",
    version="file_version_info.txt",
)
