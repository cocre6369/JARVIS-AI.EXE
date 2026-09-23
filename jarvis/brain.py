"""Conversation manager: builds model prompts and parses structured plans."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .ollama_client import OllamaClient
from .persona import build_system_prompt, tool_results_message
from .store import Settings


@dataclass
class Plan:
    say: str = ""
    actions: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""


_BRAIN_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_plan(text: str) -> Plan:
    """Extract {"say": ..., "actions": [...]} from model output, tolerating
    stray prose or markdown fences. Falls back to speaking the raw text."""
    text = (text or "").strip()
    if not text:
        return Plan(say="I'm afraid I lost my train of thought. Could you repeat that?")

    candidates: List[str] = []
    for m in _BRAIN_BLOCK.finditer(text):
        candidates.append(m.group(1))
    brace = _first_balanced_object(text)
    if brace:
        candidates.append(brace)
    candidates.append(text)

    for cand in candidates:
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        say = str(obj.get("say") or obj.get("reply") or obj.get("response") or "").strip()
        raw_actions = obj.get("actions") or obj.get("tool_calls") or []
        actions: List[Dict[str, Any]] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if isinstance(item, dict) and item.get("tool"):
                    actions.append({
                        "tool": str(item["tool"]),
                        "args": item.get("args") or {},
                    })
        if say or actions:
            return Plan(say=say, actions=actions, raw=text)

    # No JSON at all — treat the whole thing as conversational speech.
    cleaned = re.sub(r"[{}\[\]]", "", text).strip()
    return Plan(say=cleaned[:600], actions=[], raw=text)


def _first_balanced_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


class Brain:
    """Owns the conversation history and produces action plans via Ollama."""

    MAX_HISTORY = 16

    def __init__(self, client: OllamaClient, settings: Settings,
                 tool_catalog: str, project_prompt: Optional[str] = None) -> None:
        self.client = client
        self.settings = settings
        self.tool_catalog = tool_catalog
        self.system_prompt = build_system_prompt(settings, tool_catalog,
                                                 project_prompt)
        self.history: List[Dict[str, str]] = []

    def reload(self) -> None:
        self.system_prompt = build_system_prompt(self.settings, self.tool_catalog)

    def restore(self, messages: List[Dict[str, str]]) -> None:
        self.history = [m for m in messages if m.get("role") in ("user", "assistant")
                        and m.get("content")][-self.MAX_HISTORY:]

    def export(self) -> List[Dict[str, str]]:
        return [{"role": m["role"], "content": m["content"]} for m in self.history]

    def ask(self, user_text: str) -> Plan:
        self.history.append({"role": "user", "content": user_text})
        reply = self._complete()
        plan = parse_plan(reply)
        self._remember(plan)
        return plan

    def follow_up(self, results: List[Dict[str, Any]]) -> Plan:
        self.history.append({"role": "user", "content": tool_results_message(results)})
        reply = self._complete()
        plan = parse_plan(reply)
        self._remember(plan)
        return plan

    def _remember(self, plan: Plan) -> None:
        try:
            blob = json.dumps({"say": plan.say,
                               "actions": [{"tool": a["tool"],
                                            "args": a["args"]} for a in plan.actions]},
                              ensure_ascii=False)
        except ValueError:
            blob = plan.say
        self.history.append({"role": "assistant", "content": blob})
        self.history = self.history[-self.MAX_HISTORY:]

    def _complete(self) -> str:
        messages = [{"role": "system", "content": self.system_prompt}] + self.history
        return self.client.chat(self.settings.model, messages)
