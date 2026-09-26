@echo off
setlocal enabledelayedexpansion
title J.A.R.V.I.S. Diagnostic Console
cd /d "%~dp0"
color 0B

echo.
echo  ============================================================
echo   J.A.R.V.I.S.  —  DIAGNOSTIC CONSOLE
echo   "Sometimes you gotta run before you can walk."
echo  ============================================================
echo.
echo  [1] FILES IN THIS FOLDER
echo  ------------------------------------------------------------
dir /b JARVIS-AI*.exe JARVIS-CRASH.txt 2>nul
if not exist JARVIS-AI.exe if not exist JARVIS-AI-Lite.exe (
    echo     !! No JARVIS-AI.exe found in %cd%
    echo     Download it from: https://github.com/cocre6369/JARVIS-AI.EXE/releases/tag/nightly
)
echo.

echo  [2] WINDOWS
echo  ------------------------------------------------------------
ver
echo.

echo  [3] OLLAMA INSTALLED?
echo  ------------------------------------------------------------
where ollama >nul 2>nul && (echo     ollama.exe found: & where ollama) || (
    echo     ollama NOT found on PATH.
    echo     Install from: https://ollama.com/download
)
echo.

echo  [4] OLLAMA RUNNING?  (local model service)
echo  ------------------------------------------------------------
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -TimeoutSec 3 http://localhost:11434/api/tags; Write-Host '     Ollama is RUNNING. Models:'; $r.models | ForEach-Object { Write-Host ('       - ' + $_.name) } } catch { Write-Host '     Ollama is NOT responding on localhost:11434.'; Write-Host '     Start it from the Start menu, or run: ollama serve' }"
echo.

echo  [5] LAST STARTUP LOG  (%%LOCALAPPDATA%%\JARVIS\logs\boot.log)
echo  ------------------------------------------------------------
if exist "%LOCALAPPDATA%\JARVIS\logs\boot.log" (
    powershell -NoProfile -Command "Get-Content -Tail 25 '%LOCALAPPDATA%\JARVIS\logs\boot.log'"
) else (
    echo     No boot.log yet — the exe has never reached startup logging.
    echo     If double-clicking the exe does NOTHING, the cause is almost
    echo     certainly Windows blocking it. See section [7].
)
echo.

echo  [6] CRASH REPORTS
echo  ------------------------------------------------------------
if exist "JARVIS-CRASH.txt" (
    echo     JARVIS-CRASH.txt found next to the exe: ---------
    type "JARVIS-CRASH.txt"
) else if exist "%LOCALAPPDATA%\JARVIS\CRASH.txt" (
    type "%LOCALAPPDATA%\JARVIS\CRASH.txt"
) else (
    echo     No crash reports. Good.
)
echo.

echo  [7] IF THE EXE "DOES NOTHING" WHEN DOUBLE-CLICKED
echo  ------------------------------------------------------------
echo     A. SmartScreen "Windows protected your PC"?
echo        -^> Click "More info" then "Run anyway".
echo     B. No dialog at all?  Unblock the file:
echo        -^> Right-click JARVIS-AI.exe -^> Properties
echo        -^> General tab: tick "Unblock" at the bottom -^> Apply -^> retry
echo     C. Windows Security / antivirus removed it?
echo        -^> Open Windows Security -^> Protection history
echo        -^> Allow the file, or add this folder as an exclusion.
echo        (Automation tools inside JARVIS trip false-positive heuristics.)
echo     D. Still nothing? Install the VC++ runtime:
echo        https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
echo.

echo  ============================================================
echo   If you're still stuck, send me a screenshot of THIS window.
echo  ============================================================
echo.
pause
