"""Minimal, dependency-light client for the local Ollama HTTP API."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

import requests

DEFAULT_URL = "http://localhost:11434"


class OllamaError(RuntimeError):
    """Raised with a human-readable, in-character-ready explanation."""


class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: int = 120) -> None:
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.timeout = timeout

    # ---------------- health / models ----------------
    def is_running(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(
                "Ollama is not responding. Start Ollama (or install it from "
                "https://ollama.com/download) and try again."
            ) from exc
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return sorted(names)

    def pull_model(self, name: str, on_progress: Optional[Callable[[str], None]] = None) -> None:
        """Stream-download a model, reporting status lines."""
        try:
            with requests.post(f"{self.base_url}/api/pull",
                               json={"name": name, "stream": True},
                               stream=True, timeout=600) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    status = chunk.get("status", "")
                    if on_progress and status:
                        if chunk.get("total") and chunk.get("completed"):
                            pct = 100 * chunk["completed"] / max(chunk["total"], 1)
                            on_progress(f"{status} — {pct:5.1f}%")
                        else:
                            on_progress(status)
                    if "error" in chunk:
                        raise OllamaError(chunk["error"])
        except requests.RequestException as exc:
            raise OllamaError(f"Model download failed: {exc}") from exc

    # ---------------- chat ----------------
    def chat(self, model: str, messages: List[Dict[str, str]],
             temperature: float = 0.2) -> str:
        payload = _chat_payload(model, messages, temperature)
        try:
            r = requests.post(f"{self.base_url}/api/chat", json=payload,
                              timeout=self.timeout)
        except requests.RequestException as exc:
            raise OllamaError(
                "I can't reach the local Ollama service. Please start Ollama "
                f"and confirm the model '{model}' is installed."
            ) from exc
        if r.status_code == 404:
            raise OllamaError(
                f"The model '{model}' is not installed. Run 'ollama pull "
                f"{model}' or pick another model in Settings."
            )
        if r.status_code != 200:
            raise OllamaError(f"Ollama returned an error ({r.status_code}).")
        try:
            data = r.json()
        except ValueError as exc:
            raise OllamaError("Ollama returned an unreadable response.") from exc
        content = (data.get("message") or {}).get("content", "")
        return content or ""

    # ---------------- launching Ollama itself ----------------
    @staticmethod
    def find_ollama_exe() -> Optional[str]:
        return shutil.which("ollama")

    @staticmethod
    def is_installed() -> bool:
        if OllamaClient.find_ollama_exe():
            return True
        if sys.platform == "win32":
            local = os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
            return os.path.exists(local)
        return os.path.exists("/usr/local/bin/ollama") or os.path.exists(
            "/Applications/Ollama.app")

    def try_start(self) -> bool:
        """Best-effort: launch 'ollama serve' detached. Returns True if spawned."""
        exe = self.find_ollama_exe()
        if not exe:
            return False
        try:
            kwargs: Dict[str, Any] = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # DETACHED
                )
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             **kwargs)
            return True
        except OSError:
            return False


def _chat_payload(model: str, messages: list, temperature: float) -> dict:
    """Request body for /api/chat — kept in one testable place.

    num_predict caps plan length (snappier replies); keep_alive -1 keeps the
    model loaded between requests so follow-ups skip the 20-30s wake-up
    pause (unload manually with `ollama stop` if RAM is needed elsewhere)."""
    return {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 8192,
                    "num_predict": 800},
        "keep_alive": -1,
    }
