@echo off
REM ============================================================
REM  J.A.R.V.I.S. — local .exe builder for Windows
REM  Usage:   build_exe.bat          (full build, with Whisper STT)
REM           build_exe.bat lite     (lite build, Windows speech STT)
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo  [J.A.R.V.I.S.] Installing build dependencies...
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller >nul

if /I "%~1"=="lite" (
    set JARVIS_SLIM=1
    set JARVIS_NAME=JARVIS-AI-Lite
    pip install -r requirements.txt
) else (
    set JARVIS_SLIM=0
    set JARVIS_NAME=JARVIS-AI
    pip install -r requirements-full.txt
)

python scripts\make_icon.py

echo.
echo  [J.A.R.V.I.S.] Building the executable...
pyinstaller JARVIS.spec --noconfirm --clean
if errorlevel 1 (
    echo  BUILD FAILED — see messages above.
    exit /b 1
)

echo.
echo  ============================================================
echo   Build complete:  dist\%JARVIS_NAME%.exe
echo   Copy it anywhere and double-click. First run opens the
echo   setup wizard (Ollama check, model pick, voice test).
echo  ============================================================
endlocal
