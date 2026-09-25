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
    text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.DOTALL).strip()
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

    # Structurally broken JSON (8B models drop brackets sometimes):
    # repair it by regex-extracting the say + tool/args pairs, so the plan
    # actually RUNS instead of being dumped into the chat as text.
    fixed = _repair_plan(text)
    if fixed:
        return fixed

    # No JSON at all — treat the whole thing as conversational speech.
    # NEVER echo raw plan markup to the user.
    if '"say"' in text or '"tool"' in text:
        return Plan(say="I couldn't form a valid plan just then — could you "
                        "rephrase that?", actions=[], raw=text)
    cleaned = re.sub(r"[{}\[\]]", "", text).strip()
    return Plan(say=cleaned[:600], actions=[], raw=text)


_SAY_RE = re.compile(r'"say"\s*:\s*"((?:[^"\\]|\\.)*)"')
_TOOL_RE = re.compile(r'"tool"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"')
_KV_RE = re.compile(r'"([A-Za-z0-9_]+)"\s*:\s*"((?:[^"\\]|\\.)*)"(?!\s*:)')
_PLAN_MARKERS = ("say", "reply", "response", "actions", "tool", "args")


def _unesc(s: str) -> str:
    try:
        return json.loads('"%s"' % s)
    except ValueError:
        return s


def _repair_plan(text: str) -> Optional[Plan]:
    """Salvage {"say": ...} + tool/args pairs from broken JSON — even when
    every [ ] { } around them is missing."""
    if '"tool"' not in text and '"say"' not in text:
        return None
    say = ""
    m = _SAY_RE.search(text)
    if m:
        say = _unesc(m.group(1)).strip()
    actions: List[Dict[str, Any]] = []
    tools = list(_TOOL_RE.finditer(text))
    for i, tm in enumerate(tools):
        seg_end = tools[i + 1].start() if i + 1 < len(tools) else len(text)
        seg = text[tm.end():seg_end]
        args: Dict[str, Any] = {}
        for km in _KV_RE.finditer(seg):
            key = km.group(1)
            if key in _PLAN_MARKERS:
                continue
            val = _unesc(km.group(2))
            args[key] = int(val) if val.isdigit() else val
        actions.append({"tool": tm.group(1), "args": args})
    if say or actions:
        return Plan(say=say, actions=actions, raw=text)
    return None


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


def effective_system_prompt(model: str, prompt: str) -> str:
    """qwen3 models think out loud by default, which wastes seconds and
    leaks reasoning into plans; the /no_think soft switch stops that."""
    m = (model or "").strip().lower()
    if m.startswith("qwen3") and "/no_think" not in prompt:
        return prompt.rstrip() + "\n\n/no_think"
    return prompt


_PLAN_NUDGE = ('That was not a valid plan. Reply with ONLY the JSON plan: '
               '{{"say": "...", "actions": [{{"tool": "...", '
               '"args": {{...}}}}]}} — no other text.')


def _looks_like_plan(text: str) -> bool:
    return '"tool"' in text or '"actions"' in text or '"say"' in text


def _is_well_formed_json(text: str) -> bool:
    cand = _first_balanced_object(text) or text.strip()
    try:
        return isinstance(json.loads(cand), dict)
    except ValueError:
        return False


class Brain:
    """Owns the conversation history and produces action plans via Ollama."""

    MAX_HISTORY = 16

    def __init__(self, client: OllamaClient, settings: Settings,
                 tool_catalog: str, project_prompt: Optional[str] = None) -> None:
        self.client = client
        self.settings = settings
        self.tool_catalog = tool_catalog
        self.system_prompt = effective_system_prompt(
            settings.model,
            build_system_prompt(settings, tool_catalog, project_prompt))
        self.history: List[Dict[str, str]] = []

    def reload(self) -> None:
        self.system_prompt = effective_system_prompt(
            self.settings.model,
            build_system_prompt(self.settings, self.tool_catalog))

    def restore(self, messages: List[Dict[str, str]]) -> None:
        self.history = [m for m in messages if m.get("role") in ("user", "assistant")
                        and m.get("content")][-self.MAX_HISTORY:]

    def export(self) -> List[Dict[str, str]]:
        return [{"role": m["role"], "content": m["content"]} for m in self.history]

    def _complete_plan(self) -> Plan:
        """Complete + parse; if the model fumbled the plan FORMAT, give it
        ONE corrective retry instead of dead-ending the user."""
        reply = self._complete()
        plan = parse_plan(reply)
        if (not plan.actions and _looks_like_plan(reply)
                and not _is_well_formed_json(reply)):
            self.history.append({"role": "user", "content": _PLAN_NUDGE})
            plan2 = parse_plan(self._complete())
            if plan2.actions or not plan.say:
                plan = plan2
        return plan

    def ask(self, user_text: str) -> Plan:
        self.history.append({"role": "user", "content": user_text})
        plan = self._complete_plan()
        self._remember(plan)
        return plan

    def follow_up(self, results: List[Dict[str, Any]]) -> Plan:
        self.history.append({"role": "user", "content": tool_results_message(results)})
        plan = self._complete_plan()
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
