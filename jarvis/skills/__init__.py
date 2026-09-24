"""Skill registry — the ONLY capabilities JARVIS has on the machine.

Every skill is a whitelisted function with a JSON-ish parameter description
(shown to the model) and a safety policy (enforced by the executor). There is
deliberately no shell/exec skill: new capabilities are added by registering new
functions here, never by executing model-written code.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..guardrails import POLICY_AUTO, POLICY_CONFIRM, POLICY_DENY, POLICY_DOUBLE


@dataclass
class Tool:
    name: str
    description: str
    params: str                      # short arg spec for the prompt, e.g. "{url}"
    func: Callable[..., str]
    policy: str = POLICY_AUTO
    returns_data: bool = False       # result fed back to the model


_REGISTRY: Dict[str, Tool] = {}


def register(name: str, description: str, params: str = "{}",
             policy: str = POLICY_AUTO, returns_data: bool = False):
    """Decorator: register a skill function under a safe, fixed name."""

    def wrap(func: Callable[..., str]) -> Callable[..., str]:
        _REGISTRY[name] = Tool(name=name, description=description, params=params,
                               func=func, policy=policy, returns_data=returns_data)
        return func

    return wrap


def get_tool(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def tool_names() -> List[str]:
    return sorted(_REGISTRY)


def build_catalog() -> str:
    lines = []
    for tool in sorted(_REGISTRY.values(), key=lambda t: t.name):
        policy = {
            POLICY_AUTO: "auto",
            POLICY_CONFIRM: "needs user confirmation",
            POLICY_DOUBLE: "needs typed confirmation",
            POLICY_DENY: "forbidden",
        }[tool.policy]
        data = " (returns data to you)" if tool.returns_data else ""
        lines.append(f"- {tool.name} {tool.params} :: {tool.description} "
                     f"[{policy}]{data}")
    return "\n".join(lines)


def dispatch(tool: Tool, args: Dict[str, Any]) -> str:
    """Call a skill with only the parameters its signature accepts."""
    sig = inspect.signature(tool.func)
    kwargs = {}
    for pname in sig.parameters:
        if pname in args and args[pname] is not None:
            kwargs[pname] = args[pname]
    return tool.func(**kwargs)


def load_all() -> None:
    """Import every skill module so its @register calls run."""
    from . import apps, click, email, misc, web  # noqa: F401
