"""Voice input/output — fully local, nothing leaves the machine.

TTS: Windows SAPI via pyttsx3 (British voice preferred — the classic Jarvis).
STT pipeline: record push-to-talk WAV via sounddevice, then transcribe with
  1. faster-whisper (best accuracy, when the optional bundle is present)
  2. Windows' built-in speech engine via PowerShell System.Speech (offline)
"""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import wave
from pathlib import Path
from typing import List, Optional

from .store import Settings, data_dir


# ============================================================== TTS =========
class TTSEngine:
    """Thread-safe wrapper around pyttsx3 (SAPI5 on Windows)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._ok = False
        self._start()

    def _start(self) -> None:
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._apply_voice()
            self._ok = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        except Exception:
            self._ok = False

    def _apply_voice(self) -> None:
        if not self._engine:
            return
        try:
            self._engine.setProperty("rate", int(self.settings.tts_rate))
            self._engine.setProperty("volume", 1.0)
            wanted = (self.settings.tts_voice or "").strip().lower()
            voices = self._engine.getProperty("voices") or []
            chosen = None
            if wanted:
                for v in voices:
                    if wanted in (v.id or "").lower() or wanted in (v.name or "").lower():
                        chosen = v
                        break
            if chosen is None:
                for v in voices:   # British voice = classic Jarvis timbre
                    blob = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()
                    if any(tag in blob for tag in ("en_gb", "en-gb", "daniel",
                                                   "great britain", "gb_")):
                        chosen = v
                        break
            if chosen is None and voices:
                for v in voices:
                    blob = f"{v.id} {v.name}".lower()
                    if "david" in blob or "mark" in blob or "male" in blob:
                        chosen = v
                        break
            if chosen is not None:
                self._engine.setProperty("voice", chosen.id)
        except Exception:
            pass

    @staticmethod
    def list_voices() -> List[str]:
        try:
            import pyttsx3

            eng = pyttsx3.init()
            return [f"{v.name} | {v.id}" for v in (eng.getProperty("voices") or [])]
        except Exception:
            return []

    def reload(self) -> None:
        self._apply_voice()

    def speak(self, text: str) -> None:
        if not self.settings.tts_enabled or not text:
            return
        self._queue.put(text)

    def stop(self) -> None:
        """Flush pending speech (used by the ABORT control)."""
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            try:
                if self._engine is not None:
                    self._engine.say(item[:1200])
                    self._engine.runAndWait()
            except Exception:
                pass


# ============================================================== STT =========
_POWERSHELL = (os.path.expandvars(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
               if os.name == "nt" else "powershell")

_PS_DICTATE = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$eng = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$eng.SetInputToWaveFile('%WAV%')
$gram = New-Object System.Speech.Recognition.DictationGrammar
$eng.LoadGrammar($gram)
try {
  $res = $eng.Recognize([TimeSpan]::FromSeconds(20))
  if ($res) { Write-Output $res.Text }
} catch { }
"""


def has_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def available_engines() -> List[str]:
    names = []
    if has_whisper():
        names.append("whisper")
    if os.name == "nt":
        names.append("windows")
    try:
        import sounddevice  # noqa: F401
        names.append("mic")
    except Exception:
        pass
    return names


class SpeechToText:
    """Push-to-talk transcription. ``listen`` blocks and returns text (or '')."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._whisper = None
        self._whisper_name = ""
        self._model_lock = threading.Lock()

    # ---------------- recording ----------------
    def record_seconds(self, seconds: float = 6.0,
                       stop_event: Optional[threading.Event] = None,
                       on_level=None) -> Optional[Path]:
        """Record mono 16 kHz WAV until time expires or stop_event is set."""
        try:
            import numpy as np
            import sounddevice as sd
        except Exception:
            return None
        rate = 16000
        frames: List = []
        try:
            dev = self.settings.mic_device or None
            with sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                device=dev, blocksize=1600) as stream:
                chunks = int(seconds * rate / 1600)
                for _ in range(max(chunks, 1)):
                    if stop_event is not None and stop_event.is_set():
                        break
                    data, _overflow = stream.read(1600)
                    frames.append(data.copy())
                    if on_level is not None:
                        try:
                            on_level(float(np.abs(data).mean()))
                        except Exception:
                            pass
        except Exception:
            return None
        if not frames:
            return None
        pcm = b"".join(f.tobytes() for f in frames)
        path = data_dir() / "last_utterance.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        return path

    # ---------------- transcription ----------------
    def _get_whisper(self):
        want = self.settings.whisper_model or "base.en"
        with self._model_lock:
            if self._whisper is not None and self._whisper_name == want:
                return self._whisper
            from faster_whisper import WhisperModel  # type: ignore

            models = data_dir() / "models"
            models.mkdir(exist_ok=True)
            self._whisper = WhisperModel(want, device="cpu", compute_type="int8",
                                         download_root=str(models))
            self._whisper_name = want
            return self._whisper

    def _transcribe_whisper(self, wav_path: Path) -> str:
        import numpy as np

        model = self._get_whisper()
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = model.transcribe(audio, language="en", beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()

    def _transcribe_windows_speech(self, wav_path: Path) -> str:
        """Offline fallback: Windows' own speech engine via System.Speech."""
        if os.name != "nt":
            return ""
        script = _PS_DICTATE.replace("%WAV%", str(wav_path))
        try:
            out = subprocess.run(
                [_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=45, creationflags=0x08000000)
            return (out.stdout or b"").decode("utf-8", "replace").strip()
        except Exception:
            return ""

    # ---------------- public ----------------
    def listen(self, seconds: float = 6.0,
               stop_event: Optional[threading.Event] = None,
               on_level=None, on_status=None) -> str:
        """Record one utterance and transcribe it. '' when nothing heard."""
        engine = (self.settings.stt_engine or "auto").lower()

        wav = self.record_seconds(seconds, stop_event, on_level)
        if wav is None:
            return ""
        if on_status:
            on_status("transcribing")

        if engine in ("auto", "whisper") and has_whisper():
            try:
                text = self._transcribe_whisper(wav)
                if text:
                    return text
            except Exception:
                if engine == "whisper":
                    return ""
        if engine in ("auto", "windows"):
            return self._transcribe_windows_speech(wav)
        return ""


def check_wake_word(text: str, wake: str) -> bool:
    return bool(wake) and wake.lower() in (text or "").lower()
