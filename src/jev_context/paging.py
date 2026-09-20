"""Explicit, reversible active-view pruning. Never invokes a summarizer."""
from __future__ import annotations

import json
import re
import time
from .util import canonical, digest, bounded_int, redact

SUPPORTED_MUTATORS = {"generic", "opencode-v1", "opencode-v2"}


def message_key(message: dict, index: int = 0) -> str:
    # Hash the entire native object: modifications invalidate an old exclusion.
    return "msg_" + digest(canonical([index, message]))


def plain_assistant_text(message: dict) -> str | None:
    """Only remove standalone assistant prose. Tool/thinking/media blocks stay intact."""
    role = message.get("role", message.get("info", {}).get("role"))
    if role != "assistant":
        return None
    if any(k in message for k in ("tool_calls", "function_call", "reasoning_content", "reasoning", "thinking")):
        return None
    if "parts" in message:
        parts = message["parts"]
        if not isinstance(parts, list) or not parts or any(not isinstance(p, dict) or p.get("type") != "text" for p in parts):
            return None
        return "\n".join(p.get("text", "") for p in parts)
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and all(isinstance(p, dict) and p.get("type") == "text" for p in content):
        return "\n".join(p.get("text", "") for p in content)
    return None


def snapshot(core, session: str, harness: str, messages: list[dict]) -> dict:
    if not isinstance(messages, list) or len(messages) > 10000 or any(not isinstance(m, dict) for m in messages):
        raise ValueError("messages must be an array of at most 10000 native message objects")
    payload = canonical(messages)
    if len(payload.encode()) > 8 * 1024 * 1024:
        raise ValueError("Snapshot too large; capture smaller source pages")
    fingerprint = digest(payload)
    old = core.store.db.execute("SELECT fingerprint FROM snapshots WHERE workspace=? AND session=? AND harness=?", (core.workspace, session,harness)).fetchone()
    if not old or old[0] != fingerprint:
        # Every native message is canonical evidence, not merely an index summary.
        for index, msg in enumerate(messages):
            core.store.capture(core.workspace, canonical(msg), session=session, harness=harness,
                               origin="native-message:" + message_key(msg, index), metadata={"native_message": True})
        with core.store.db:
            core.store.db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?)", (
                core.workspace, session, harness, fingerprint, payload, time.time()))
    return {"fingerprint": fingerprint, "messages": len(messages)}


def plan(core, session: str, harness: str, goal: str, target_chars: int = 12000) -> dict:
    bounded_int(target_chars, "target_chars", 1, 2_000_000)
    if harness not in SUPPORTED_MUTATORS:
        return {"supported": False, "harness": harness, "applied": False,
                "reason": "This adapter cannot replace the active message view. Retrieval and capture remain available.",
                "native_compaction_called": False}
    row = core.store.db.execute("SELECT * FROM snapshots WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness)).fetchone()
    if not row:
        raise ValueError("No snapshot for this session. Start the harness or submit a generic prepare request first.")
    messages = json.loads(row["messages"])
    recent = max(2, int(core.config["retained_recent_messages"]))
    goal_words = set(re.findall(r"\w+", goal.lower()))
    old_view = core.store.db.execute("SELECT excluded FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness)).fetchone()
    already_excluded = set(json.loads(old_view[0])) if old_view and core.config["native_prune_enabled"] else set()
    candidates = []
    guard = re.compile(r"\b(must|never|constraint|requirement|unresolved|blocker|security|permission|decision)\b|do not|don't", re.I)
    pins = {r[0] for r in core.store.db.execute("SELECT s.origin FROM sources s JOIN pins p ON p.source_id=s.id WHERE p.workspace=?", (core.workspace,))}
    for index, message in enumerate(messages[:-recent] if len(messages) > recent else []):
        text = plain_assistant_text(message)
        key = message_key(message, index)
        if key in already_excluded or text is None or not text.strip() or guard.search(text) or "native-message:" + key in pins:
            continue
        words = set(re.findall(r"\w+", text.lower()))
        relevance = len(words & goal_words) / max(1, len(goal_words))
        candidates.append({"key":key, "index":index, "characters":len(canonical(message)),
                           "overlap":relevance, "preview": redact(text[:160])})
    candidates.sort(key=lambda c:(c["overlap"], c["index"]))
    picked, reclaimed = [], 0
    for item in candidates:
        if reclaimed >= target_chars:
            break
        picked.append(item)
        reclaimed += item["characters"]
    result = {"supported":True, "session":session, "harness":harness, "fingerprint":row["fingerprint"],
              "goal":goal, "candidates":picked, "estimated_removed_characters":reclaimed,
              "requested_characters":target_chars, "sufficient":reclaimed >= target_chars,
              "applied":False, "native_compaction_called":False,
              "warning":"Preview only. Preserves all user/system/developer messages, recent messages, pins and tool/thinking/media blocks. Review before CLI approval."}
    ident = "plan_" + digest(canonical(result))
    result["plan_id"] = ident
    with core.store.db:
        core.store.db.execute("INSERT OR REPLACE INTO prune_plans VALUES(?,?,?,?,?,?,?)", (
            ident,core.workspace,session,harness,row["fingerprint"],canonical(result),time.time()))
    return result


def apply(core, plan_id: str) -> dict:
    row = core.store.db.execute("SELECT * FROM prune_plans WHERE id=? AND workspace=?", (plan_id,core.workspace)).fetchone()
    if not row:
        raise ValueError("Plan not found in this workspace")
    current = core.store.db.execute("SELECT fingerprint FROM snapshots WHERE workspace=? AND session=? AND harness=?", (core.workspace,row["session"],row["harness"])).fetchone()
    if not current or current[0] != row["fingerprint"]:
        raise ValueError("Stale plan: the native transcript changed. Generate a fresh plan.")
    data = json.loads(row["data"])
    keys = [c["key"] for c in data["candidates"]]
    if not keys:
        return {"applied":False,"reason":"No eligible messages", "native_compaction_called":False}
    if core.config["native_prune_enabled"] is not True:
        raise PermissionError("Native pruning is disabled; CLI approval requires --enable-native")
    with core.store.db:
        old = core.store.db.execute("SELECT excluded,generation FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,row["session"],row["harness"])).fetchone()
        keys = sorted(set(keys) | set(json.loads(old[0]) if old else []))
        core.store.db.execute("INSERT OR REPLACE INTO views VALUES(?,?,?,?,?)", (
            core.workspace,row["session"],row["harness"],canonical(keys),(old[1]+1) if old else 1))
    return {"applied":True,"view_saved":True,"session":row["session"], "harness":row["harness"],
            "excluded_message_count":len(keys),"native_compaction_called":False,
            "note":"The next supported context-transform hook applies this view. Canonical sources are unchanged."}


def prepare(core, session: str, harness: str, messages: list[dict], query: str = "") -> dict:
    if not core.config["capture_enabled"]:
        return {"messages":messages,"removed":0,"native_compaction_called":False,
                "note":"Automatic capture is disabled; no snapshot or active-view mutation performed"}
    snap = snapshot(core,session,harness,messages)
    row = core.store.db.execute("SELECT excluded FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness)).fetchone()
    excluded = set(json.loads(row[0])) if row and core.config["native_prune_enabled"] else set()
    # Defensive re-check on every request; a changed role or tool block cannot be removed.
    recent = max(2, int(core.config["retained_recent_messages"]))
    pins = {r[0] for r in core.store.db.execute("SELECT s.origin FROM sources s JOIN pins p ON p.source_id=s.id WHERE p.workspace=?", (core.workspace,))}
    guard = re.compile(r"\b(must|never|constraint|requirement|unresolved|blocker|security|permission|decision)\b|do not|don't", re.I)
    kept = []
    for index, message in enumerate(messages):
        key = message_key(message, index)
        text = plain_assistant_text(message)
        eligible = (index < len(messages)-recent and text is not None and not guard.search(text)
                    and "native-message:" + key not in pins)
        if not (key in excluded and eligible):
            kept.append(message)
    return {"messages":kept,"removed":len(messages)-len(kept),"fingerprint":snap["fingerprint"],
            "native_compaction_called":False}


def reset(core, session: str, harness: str) -> dict:
    with core.store.db:
        core.store.db.execute("DELETE FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness))
    return {"restored":True,"note":"Original native messages are used on the next transform; sources were never deleted."}
