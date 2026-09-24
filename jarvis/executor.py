"""Executes a planned chain of tool calls — with guardrails and narration."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from . import skills
from .guardrails import (
    AbortToken, MAX_ACTIONS_PER_PLAN, POLICY_CONFIRM, POLICY_DENY,
    POLICY_DOUBLE, check_tool_call, check_user_request, confirm_word_for,
    policy_for,
)
from .store import Settings


class Executor:
    """Runs Plan.actions one at a time.

    ``ui`` is a small protocol implemented by the HUD (thread-safe):
        narrate(text)                  -> tell the user what is happening
        say(text)                      -> speak/print a reply
        log(kind, text)                -> activity log line
        confirm(title, message)        -> bool (blocking dialog)
        confirm_typed(title, msg, word)-> bool (typed phrase dialog)
    """

    def __init__(self, settings: Settings, abort: AbortToken, ui) -> None:
        self.settings = settings
        self.abort = abort
        self.ui = ui

    # ------------------------------------------------------------------
    def execute(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        actions = actions[:MAX_ACTIONS_PER_PLAN]
        names = skills.tool_names()

        for idx, action in enumerate(actions):
            if self.abort.aborted:
                results.append({"tool": action.get("tool"), "ok": False,
                                "result": "aborted by user"})
                break

            name = str(action.get("tool", ""))
            args = action.get("args") or {}
            tool = skills.get_tool(name)
            verdict = check_tool_call(name, args, names)

            if not verdict.ok or tool is None:
                reason = verdict.reason or "unknown tool"
                self.ui.log("blocked", f"BLOCKED {name}: {reason}")
                results.append({"tool": name, "ok": False, "result": f"BLOCKED: {reason}"})
                continue

            # Re-scan the full request too (defence in depth).
            blob = f"{name} " + " ".join(str(v) for v in args.values())
            req = check_user_request(blob)
            if not req.ok:
                self.ui.log("blocked", f"BLOCKED {name}: guardrail {req.reason}")
                results.append({"tool": name, "ok": False,
                                "result": f"BLOCKED by guardrail: {req.reason}"})
                continue

            policy = policy_for(name, args, tool.policy,
                                self.settings.confirm_every_action)

            if policy == POLICY_DENY:
                self.ui.log("blocked", f"BLOCKED {name}: denied by policy")
                results.append({"tool": name, "ok": False, "result": "BLOCKED by policy"})
                continue

            human = _humanise(name, args)
            if policy in (POLICY_CONFIRM, POLICY_DOUBLE):
                word = confirm_word_for(name)
                title = "CONFIRM ACTION" if policy == POLICY_CONFIRM else \
                    "CONFIRM SENSITIVE ACTION"
                message = (f"JARVIS wants to perform:\n\n{human}\n\n"
                           "Allow this action?")
                if policy == POLICY_DOUBLE:
                    message = (f"This is a sensitive/irreversible action:\n\n"
                               f"{human}\n\nType {word} to authorise it.")
                self.ui.log("confirm", f"Confirming: {human}")
                allowed = (self.ui.confirm_typed(title, message, word)
                           if policy == POLICY_DOUBLE
                           else self.ui.confirm(title, message))
                if not allowed:
                    self.ui.log("denied", f"User declined: {human}")
                    results.append({"tool": name, "ok": False,
                                    "result": "user declined this action"})
                    continue

            self.ui.narrate(_narrate_line(name, args))
            self.ui.log("acting", human)
            started = time.time()
            try:
                output = skills.dispatch(tool, args)
            except Exception as exc:  # never crash mid-chain
                output = f"ERROR: {exc}"
            if str(tool) in ("open_app", "launch_app") or \
                    str(name) in ("open_app", "launch_app"):
                # Apps need seconds to load. Wait for the window, focus it,
                # so the NEXT keystrokes/clicks land in the right place
                # instead of a half-loaded app.
                from .skills.click import wait_for_window
                ready = wait_for_window(str(args.get("name", "")))
                if ready:
                    output = f"{output} [window ready: {ready[:60]}]"
            took = time.time() - started

            ok = not str(output).startswith("ERROR")
            self.ui.log("done" if ok else "error",
                        f"{'OK' if ok else 'FAIL'} ({took:.1f}s) {name}: "
                        f"{str(output)[:220]}")
            results.append({"tool": name, "ok": ok, "result": str(output)[:4000],
                            "returns_data": tool.returns_data})

            # Special in-app commands intercepted by the UI.
            if output == "SETTINGS":
                self.ui.open_settings()
                results[-1]["result"] = "Opened the settings panel."

            if self.abort.aborted:
                results.append({"tool": None, "ok": False,
                                "result": "aborted by user"})
                break

        return results


# --------------------------------------------------------------------------
def _humanise(name: str, args: Dict[str, Any]) -> str:
    pretty = {
        "web_open": lambda a: f"Open website {a.get('url')}",
        "web_search": lambda a: f"Search the web for {a.get('query')!r}",
        "web_read": lambda a: f"Read {a.get('url')} for summarising",
        "youtube_play": lambda a: f"Play the top YouTube match for {a.get('query')!r}",
        "youtube_search": lambda a: f"Show YouTube results for {a.get('query')!r}",
        "youtube_channel": lambda a: f"Open the YouTube channel {a.get('name')!r}",
        "youtube_latest": lambda a: f"Play the newest video from {a.get('channel')!r}",
        "open_app": lambda a: f"Open the application {a.get('name')!r}",
        "close_app": lambda a: f"Close the application {a.get('name')!r}",
        "focus_window": lambda a: f"Focus the window {a.get('title')!r}",
        "minimize_window": lambda a: f"Minimise the window {a.get('title')!r}",
        "maximize_window": lambda a: f"Maximise the window {a.get('title')!r}",
        "media_play_pause": lambda a: "Toggle media play/pause",
        "media_next": lambda a: "Skip to the next track",
        "media_previous": lambda a: "Go to the previous track",
        "media_stop": lambda a: "Stop media playback",
        "volume_set": lambda a: f"Set the volume to {a.get('percent')}%",
        "volume_mute": lambda a: f"Set mute mode to {a.get('mode', 'toggle')}",
        "type_text": lambda a: f"Type {len(str(a.get('text', '')))} characters "
                               f"into the focused window: {str(a.get('text'))[:80]!r}",
        "press_keys": lambda a: f"Press the keys {a.get('keys')}",
        "click": lambda a: f"Click the on-screen item labelled {a.get('name')!r}",
        "double_click": lambda a: f"Double-click the item {a.get('name')!r}",
        "click_xy": lambda a: f"Click at screen ({a.get('x')}, {a.get('y')})",
        "email_read_selected": lambda a: "Read the email you have selected in Outlook",
        "email_reply_draft": lambda a: "Prepare a reply draft in Outlook "
                                       "(won't be sent)",
        "email_compose": lambda a: "Prepare a new email draft (won't be sent)",
        "timer_set": lambda a: f"Set a {a.get('minutes')} minute timer "
                               f"({a.get('label', 'timer')})",
        "reminder_set": lambda a: f"Set a reminder: {a.get('text')}",
        "list_reminders": lambda a: "List your pending reminders",
        "cancel_reminder": lambda a: f"Cancel reminder {a.get('ref')}",
        "remember": lambda a: f"Remember {a.get('key')}: {a.get('value')}",
        "recall_memory": lambda a: "Recall saved notes",
        "file_list": lambda a: f"List files in {a.get('path')}",
        "file_read": lambda a: f"Read the file {a.get('path')}",
        "file_write": lambda a: f"Write to the file {a.get('path')}",
        "file_delete": lambda a: f"Move {a.get('path')} to the Recycle Bin",
        "open_folder": lambda a: f"Open the folder {a.get('path')}",
        "system_status": lambda a: "Report system status",
        "screenshot": lambda a: "Capture the screen",
        "clipboard_read": lambda a: "Read the clipboard",
        "clipboard_set": lambda a: "Set the clipboard",
        "open_settings": lambda a: "Open JARVIS settings",
    }
    fn = pretty.get(name)
    try:
        return fn(args) if fn else f"{name}({args})"
    except Exception:
        return f"{name}({args})"


def _narrate_line(name: str, args: Dict[str, Any]) -> str:
    short = {
        "web_open": "Opening the site",
        "web_search": "Searching the web",
        "web_read": "Reading the page",
        "youtube_play": "Pulling up the video",
        "youtube_search": "Bringing up the results",
        "youtube_channel": "Opening the channel",
        "youtube_latest": "Fetching the latest video",
        "open_app": f"Launching {args.get('name', 'the app')}",
        "close_app": f"Closing {args.get('name', 'the app')}",
        "focus_window": "Bringing the window forward",
        "email_read_selected": "Reading the selected message",
        "email_reply_draft": "Preparing your reply draft",
        "email_compose": "Preparing your draft",
        "type_text": "Typing on screen now",
        "click": f"Clicking “{args.get('name', '')}”",
        "double_click": f"Opening “{args.get('name', '')}”",
        "screenshot": "Capturing the screen",
    }
    return short.get(name, "Working on it")
