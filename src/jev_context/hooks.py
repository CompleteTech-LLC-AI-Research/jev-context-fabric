"""Translate documented host envelopes without assuming hooks can delete history."""
from __future__ import annotations

from pathlib import Path
from .core import Core
from .util import canonical

EVENT_MAP = {
    "SessionStart":"SESSION_START", "UserPromptSubmit":"USER_INPUT", "PreToolUse":"PRE_TOOL",
    "PostToolUse":"POST_TOOL", "Stop":"TURN_END", "SubagentStop":"SUBAGENT_END", "SessionEnd":"SESSION_END",
    "on_session_start":"SESSION_START", "pre_llm_call":"PRE_MODEL", "pre_tool_call":"PRE_TOOL",
    "post_tool_call":"POST_TOOL", "post_llm_call":"TURN_END", "on_session_end":"SESSION_END", "subagent_stop":"SUBAGENT_END",
}


def run_hook(home: Path, default_workspace: str, harness: str, event: str, payload: dict) -> dict:
    if not isinstance(payload,dict):
        raise ValueError("Hook payload must be a JSON object")
    extra = payload.get("extra",{})
    data = {**(extra if isinstance(extra,dict) else {}), **{k:v for k,v in payload.items() if v is not None}}
    prompt = data.get("prompt") or data.get("user_message") or ""
    # Native /compact remains untouched and incurs zero JEV calls.
    if event in {"PreCompact","PostCompact"} or data.get("source") == "compact" or (isinstance(prompt,str) and prompt.lstrip().split(maxsplit=1)[:1] == ["/compact"]):
        return {}
    if "jev_" in str(data.get("tool_name", "")) or "jev-context" in str(data.get("tool_name", "")):
        return {}
    kind = EVENT_MAP.get(event)
    if kind is None:
        return {}
    workspace = str(data.get("cwd") or default_workspace)
    session = str(data.get("session_id") or data.get("task_id") or "")
    if not session:
        # Missing session identity must not accidentally merge unrelated active views.
        return {}
    if kind in {"USER_INPUT","PRE_MODEL"}:
        content = prompt if isinstance(prompt,str) else canonical(prompt)
    elif kind == "POST_TOOL":
        result = data.get("tool_response",data.get("result",data.get("output")))
        content = canonical({"tool":data.get("tool_name"),"input":data.get("tool_input",data.get("args")),"result":result})
    elif kind in {"TURN_END","SUBAGENT_END"}:
        result = data.get("last_assistant_message") or data.get("assistant_message") or data.get("response") or data.get("result")
        content = result if isinstance(result,str) else canonical(result) if result is not None else ""
    else:
        content = ""
    core = Core(home,workspace)
    try:
        result = core.event({"kind":kind,"session":session,"harness":harness,"content":content,
            "query":prompt if isinstance(prompt,str) else "", "native_id":data.get("tool_use_id") or data.get("tool_call_id") or data.get("turn_id"),
            "origin":event})
        context = result.get("context","")
        if not context:
            return {}
        if harness == "hermes":
            return {"context":context} if event == "pre_llm_call" else {}
        if event in {"SessionStart","UserPromptSubmit"}:
            return {"hookSpecificOutput":{"hookEventName":event,"additionalContext":context}}
        return {}
    finally:
        core.close()
