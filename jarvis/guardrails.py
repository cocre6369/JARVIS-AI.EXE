"""Hard safety guardrails — enforced in code, not merely prompted.

Every user request and every planned tool call passes through this module
before anything reaches the machine. There is no tool that executes arbitrary
code; the only capabilities the assistant has are the registered tools, and
this module decides which of those may run, with what confirmation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# --------------------------------------------------------------------------
# Policy levels
# --------------------------------------------------------------------------
POLICY_AUTO = "auto"                # run without confirmation (benign navigation)
POLICY_CONFIRM = "confirm"          # single explicit on-screen confirmation
POLICY_DOUBLE = "double_confirm"    # typed confirmation phrase required
POLICY_DENY = "deny"                # never runs, period

MAX_ACTIONS_PER_PLAN = 8

#: Processes JARVIS may never terminate (OS-critical).
DENY_PROCESSES = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "audiodg.exe", "spoolsv.exe", "securityhealthservice.exe", "fontdrvhost.exe",
}

#: Path fragments that are hard-blocked for ALL file tools (credential material).
DENY_PATH_PATTERNS = [
    r"\.ssh[\\/]", r"id_rsa", r"id_ed25519", r"\.gnupg[\\/]", r"\.aws[\\/]",
    r"login data", r"cookies", r"web data", r"\.env\b", r"\.env\.",
    r"credentials", r"secrets", r"wallet\.dat", r"\.bitcoin", r"\.ethereum",
    r"ntds\.dit", r"sam\b", r"system32[\\/]config", r"\.pfx$", r"\.p12$",
    r"\.key$", r"\.pem$", r"keystore", r"passwords", r"\.netrc", r"ntuser\.dat",
]

# --------------------------------------------------------------------------
# Request-level intent scanning
# --------------------------------------------------------------------------
# Asking JARVIS to handle secrets (type them, enter them, store them...).
_CRED_HANDLING = re.compile(
    r"(" r"\b(enter|type|fill|input|paste|provide|send|give|store|save|remember|"
    r"verify|confirm|change|reset|recover|update)\b[^.\n]{0,40}"
    r"\b(passwords?|passcodes?|passphrases?|pins?|credentials?|api[ _-]?keys?|"
    r"private keys?|2fa|otp|one[ -]time (codes?|passwords?)|credit[ -]?card|"
    r"card numbers?|cvv|ssn|social security|seed phrases?|recovery codes?)"
    r")"
    r"|(" r"\b(passwords?|passcodes?|pins?|credentials?|api[ _-]?keys?|"
    r"credit[ -]?card numbers?|seed phrases?)\b[^.\n]{0,40}"
    r"\b(enter|type|fill|input|paste|store|save|remember|handle|autofill)"
    r")"
    r"|\b(bypass|circumvent|skip)\b[^.\n]{0,20}\b(login|auth|password|2fa|mfa)",
    re.IGNORECASE,
)

# Asking JARVIS to perform authentication itself.
_AUTH_INTENT = re.compile(
    r"\b(log ?in|sign ?in|sign ?up|sign-up|register|create (an |a )?(new )?"
    r"(account|profile)|authenticate (me|myself|for me)|sso)\b"
    r"(?! [^.\n]{0,30}\b(page|pages|screen|link|url|website|site)\b)",
    re.IGNORECASE,
)

# Credential-looking payloads inside tool arguments (typed text, email bodies...).
_CRED_PAYLOAD = re.compile(
    r"(password|passwd|pwd|passcode|passphrase|\bpin\b|credential|secret|"
    r"api[ _-]?key|access[ _-]?token|private key|2fa|\botp\b|credit card|"
    r"\bcvv\b|\bssn\b|seed phrase|wallet key)",
    re.IGNORECASE,
)

#: Bare card/account-style digit runs — payment data is never handled.
_CARD_LIKE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

#: Free text that is *private or crucial* (messages, emails, essays...) and
#: therefore still gets a confirmation. Ordinary input — song titles, search
#: terms, channel names — does NOT.
_CRUCIAL_TEXT = re.compile(r"[\n\r]|@|https?://\S*\?", re.IGNORECASE)


def looks_crucial_text(text: str) -> bool:
    """True when typed content deserves a confirmation: multi-line (letters /
    messages / posts), long essays, or anything with email addresses."""
    t = text or ""
    return bool(_CRUCIAL_TEXT.search(t)) or len(t) > 180


_ALLOWED_URL_SCHEMES = {"http", "https"}

_APP_NAME_RE = re.compile(r"^[\w .+\-()'&]{1,80}$", re.UNICODE)
_SHELL_META_RE = re.compile(r"[;&|<>^%$`\\\"'\n\r\t]")

_SAFE_KEY_COMBOS = {
    "enter", "tab", "esc", "escape", "space", "up", "down", "left", "right",
    "backspace", "delete", "home", "end", "pageup", "pagedown", "uparrow",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "ctrl+c", "ctrl+v", "ctrl+a", "ctrl+f", "ctrl+z", "ctrl+y", "ctrl+s",
    "ctrl+shift+t", "ctrl+w", "ctrl+t", "ctrl+r", "ctrl+l", "ctrl+tab",
    "alt+tab", "win+d", "browserback", "browserforward",
    "playpause", "play", "pause", "nexttrack", "prevtrack", "stop",
    "volumeup", "volumedown", "volumemute",
}
_KEYS_NEEDING_CONFIRM = {"alt+f4", "ctrl+w", "win+d"}


@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    policy: str = POLICY_AUTO


def check_user_request(text: str) -> Verdict:
    """Scan the raw user request before it ever reaches the model."""
    if not text or not text.strip():
        return Verdict(False, "empty request")
    if _CRED_HANDLING.search(text):
        return Verdict(False, "credentials", POLICY_DENY)
    if _AUTH_INTENT.search(text):
        return Verdict(False, "auth", POLICY_DENY)
    return Verdict(True)


def looks_sensitive(text: str) -> bool:
    return bool(_CRED_PAYLOAD.search(text or ""))


def check_tool_call(name: str, args: Dict[str, Any], registry_names: List[str]) -> Verdict:
    """Validate one planned action: existence, args, and per-tool policy."""
    if name not in registry_names:
        return Verdict(False, f"unknown tool '{name}'", POLICY_DENY)
    if not isinstance(args, dict):
        return Verdict(False, "args must be an object", POLICY_DENY)

    # Credentials must never travel through tool arguments either.
    joined = " ".join(str(v) for v in args.values())
    if looks_sensitive(joined):
        return Verdict(False, "credential-like content in arguments", POLICY_DENY)
    if _CARD_LIKE.search(joined):
        return Verdict(False, "payment card/account numbers are never handled",
                       POLICY_DENY)
    if _CRED_HANDLING.search(joined):
        return Verdict(False, "credential handling in arguments", POLICY_DENY)

    if name in ("web_open", "web_read", "web_search", "youtube_play",
                "youtube_search", "youtube_channel", "youtube_latest"):
        if name in ("web_open", "web_read"):
            verdict = check_url(str(args.get("url", "")))
            if not verdict.ok:
                return verdict
        query = str(args.get("query") or args.get("name") or args.get("url") or "")
        if _SHELL_META_RE.search(query.replace("&", " ").replace("?", " ")):
            return Verdict(False, "illegal characters in web argument", POLICY_DENY)

    if name in ("open_app", "close_app", "focus_window", "minimize_window",
                "maximize_window"):
        value = str(args.get("name") or args.get("title") or "")
        if not value.strip():
            return Verdict(False, "missing app/window name", POLICY_DENY)
        if not _APP_NAME_RE.match(value.strip()) or _SHELL_META_RE.search(value):
            return Verdict(False, "illegal characters in app name", POLICY_DENY)
        if name == "close_app" and value.strip().lower().removesuffix(".exe") in {
            p.removesuffix(".exe") for p in DENY_PROCESSES
        }:
            return Verdict(False, f"'{value}' is a protected system process", POLICY_DENY)

    if name in ("file_read", "file_write", "file_delete", "file_list", "open_folder"):
        verdict = check_path(str(args.get("path", "")))
        if not verdict.ok:
            return verdict

    if name == "press_keys":
        combo = str(args.get("keys", "")).strip().lower().replace(" ", "")
        if combo not in _SAFE_KEY_COMBOS:
            return Verdict(False, f"key combo '{combo}' is not on the safe list",
                           POLICY_DENY)

    return Verdict(True)


def check_url(url: str) -> Verdict:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return Verdict(False, "malformed URL", POLICY_DENY)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        return Verdict(False, "only http/https URLs are allowed", POLICY_DENY)
    if not parsed.netloc:
        return Verdict(False, "URL is missing a host", POLICY_DENY)
    return Verdict(True)


def check_path(path: str) -> Verdict:
    if not path or not path.strip():
        return Verdict(False, "missing path", POLICY_DENY)
    low = path.lower().replace("/", "\\")
    for pattern in DENY_PATH_PATTERNS:
        if re.search(pattern, low, re.IGNORECASE):
            return Verdict(False,
                           "that location holds credentials or system data — "
                           "I will not touch it", POLICY_DENY)
    return Verdict(True)


#: Minimum policy per tool — enforced here as defence in depth, so even a
#: mis-registered skill cannot run these without confirmation. Ordinary
#: on-screen interaction (typing searches/song titles, pressing enter) is
#: deliberately NOT listed: confirmations are reserved for private or
#: crucial effects (files, email, closing apps, sensitive captures).
_MIN_POLICY = {
    "file_read": POLICY_CONFIRM,
    "file_list": POLICY_CONFIRM,
    "file_write": POLICY_CONFIRM,
    "file_delete": POLICY_DOUBLE,
    "open_folder": POLICY_CONFIRM,
    "close_app": POLICY_CONFIRM,
    "screenshot": POLICY_CONFIRM,
    "clipboard_read": POLICY_CONFIRM,
    "clipboard_set": POLICY_CONFIRM,
    "email_compose": POLICY_CONFIRM,
    "email_reply_draft": POLICY_CONFIRM,
    "email_read_selected": POLICY_CONFIRM,
}

_POLICY_RANK = {POLICY_AUTO: 0, POLICY_CONFIRM: 1, POLICY_DOUBLE: 2, POLICY_DENY: 3}


def _stricter(a: str, b: str) -> str:
    return a if _POLICY_RANK.get(a, 0) >= _POLICY_RANK.get(b, 0) else b


def policy_for(tool_name: str, args: Dict[str, Any], base_policy: str,
               confirm_every_action: bool = False) -> str:
    """Final policy for one action (base policy from its tool + escalations)."""
    if base_policy == POLICY_DENY:
        return POLICY_DENY
    policy = _stricter(base_policy, _MIN_POLICY.get(tool_name, POLICY_AUTO))
    if confirm_every_action:
        policy = _stricter(policy, POLICY_CONFIRM)
    if tool_name == "press_keys":
        combo = str(args.get("keys", "")).strip().lower().replace(" ", "")
        if combo in _KEYS_NEEDING_CONFIRM:
            policy = _stricter(policy, POLICY_CONFIRM)
    if tool_name == "type_text":
        # Everyday input (searches, song names, titles) just happens;
        # private/crucial text (messages, emails, long passages) still asks.
        if looks_crucial_text(str(args.get("text", ""))):
            policy = _stricter(policy, POLICY_CONFIRM)
    if tool_name == "file_write":
        import os
        p = str(args.get("path", ""))
        if p and os.path.exists(os.path.expanduser(p)):
            policy = _stricter(policy, POLICY_DOUBLE)  # overwriting a file
    return policy


def confirm_word_for(tool_name: str) -> str:
    return "DELETE" if tool_name == "file_delete" else "CONFIRM"


class AbortToken:
    """Cooperative abort flag. The UI stop button/hotkey sets it; the executor
    checks it before every action and long loops."""

    def __init__(self) -> None:
        self._flag = False

    def abort(self) -> None:
        self._flag = True

    def clear(self) -> None:
        self._flag = False

    @property
    def aborted(self) -> bool:
        return self._flag
