"""Explicit, reversible active-view pruning. Never invokes a summarizer."""
from __future__ import annotations

import json
import re
import time
from .util import canonical, digest, bounded_int, redact

# Hosts this package can mutate through an adapter it installs itself.
SUPPORTED_MUTATORS = {"generic", "opencode-v1", "opencode-v2"}

# Hosts this package can mutate ONLY as a jev-bus stage inside another package's carrier.
# It installs no native transform of its own for either, so support here is conditional on
# actually being registered on the bus -- never claimed merely because the name is known.
BUS_ONLY_MUTATORS = {"pi", "hermes"}
PACKAGE = "jev-context-fabric"


def can_mutate(harness: str) -> bool:
    if harness in SUPPORTED_MUTATORS:
        return True
    if harness not in BUS_ONLY_MUTATORS:
        return False
    try:
        from . import bus
        return any(stage.get("package") == PACKAGE for stage in bus.stages_for(harness))
    except Exception:  # noqa: BLE001 - an unreadable registry means no capability, not a crash
        return False


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
    if not can_mutate(harness):
        reason = ("This adapter cannot replace the active message view. Retrieval and capture remain available.")
        if harness in BUS_ONLY_MUTATORS:
            reason = (f"This package installs no native transform for {harness}; it can only prune there as a "
                      f"jev-bus stage, and it is not registered on the bus for that host. Install the package "
                      f"that carries {harness}, then reinstall this one.")
        return {"supported": False, "harness": harness, "applied": False,
                "reason": reason, "native_compaction_called": False}
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


def prepare(core, session: str, harness: str, messages: list[dict], query: str = "",
            original_messages: list[dict] | None = None) -> dict:
    """Filter `messages` using the approved active view.

    When another jev-bus stage ran earlier in the chain, `messages` may already differ from
    what the host holds. `original_messages` is then the pristine pre-chain array, and both
    the snapshot fingerprint and every `msg_` key derive from IT, not from the mutated copy.
    Without that, an upstream edit would re-key every message and silently stale every open
    plan. Keys stay aligned because a stage may not change the array length: an upstream
    stage claiming `message-remove` would collide with this package's own claim and be
    refused at install time. If the lengths disagree anyway, fall back to keying off the
    array actually being filtered, which can only under-remove.
    """
    if not core.config["capture_enabled"]:
        return {"messages":messages,"removed":0,"native_compaction_called":False,
                "note":"Automatic capture is disabled; no snapshot or active-view mutation performed"}
    aligned = (isinstance(original_messages, list) and len(original_messages) == len(messages)
               and all(isinstance(m, dict) for m in original_messages))
    pristine = original_messages if aligned else messages
    snap = snapshot(core,session,harness,pristine)
    row = core.store.db.execute("SELECT excluded FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness)).fetchone()
    excluded = set(json.loads(row[0])) if row and core.config["native_prune_enabled"] else set()
    # Defensive re-check on every request; a changed role or tool block cannot be removed.
    recent = max(2, int(core.config["retained_recent_messages"]))
    pins = {r[0] for r in core.store.db.execute("SELECT s.origin FROM sources s JOIN pins p ON p.source_id=s.id WHERE p.workspace=?", (core.workspace,))}
    guard = re.compile(r"\b(must|never|constraint|requirement|unresolved|blocker|security|permission|decision)\b|do not|don't", re.I)
    kept = []
    for index, message in enumerate(messages):
        source = pristine[index]
        key = message_key(source, index)
        text = plain_assistant_text(source)
        eligible = (index < len(messages)-recent and text is not None and not guard.search(text)
                    and "native-message:" + key not in pins)
        if not (key in excluded and eligible):
            kept.append(message)
    return {"messages":kept,"removed":len(messages)-len(kept),"fingerprint":snap["fingerprint"],
            "keyed_from":"original" if aligned else "current","native_compaction_called":False}


def harness_for_host(host: str, api: str = "") -> str:
    """Map a jev-bus host name onto this package's harness string."""
    if host == "opencode":
        return "opencode-v2" if str(api).lower() in ("v2", "2") else "opencode-v1"
    return host if host in (SUPPORTED_MUTATORS | BUS_ONLY_MUTATORS) else "generic"


def bus_stage(core, request: dict) -> dict:
    """Serve one jev-bus.stage.v1 request.

    This package's stage claims `assistant-prose`, `message-remove` and `system-append`.
    It never approves anything: `transform` applies only an ALREADY-approved active view,
    and `plan` is a preview. Approval stays in this package's own CLI.
    """
    host = str(request.get("host", "generic"))
    harness = harness_for_host(host, str(request.get("api", "")))
    session = str(request.get("session") or "")
    messages = request["messages"]
    if not session:
        return {"ok": True, "messages": messages,
                "notes": [{"action": "passthrough", "detail": "no session id supplied"}]}

    if request["op"] == "plan":
        snapshot(core, session, harness, request.get("original_messages") or messages)
        preview = plan(core, session, harness, str(request.get("goal") or ""),
                       int(core.config["max_evidence_chars"]))
        if not preview.get("supported"):
            return {"ok": True, "messages": messages,
                    "notes": [{"action": "unsupported", "detail": preview.get("reason", "")}]}
        return {"ok": True, "messages": messages, "plan_id": preview["plan_id"],
                "notes": [{"action": "assistant-prose eligible", "count": len(preview["candidates"]),
                           "bytes": preview["estimated_removed_characters"],
                           "detail": f"assistant-prose messages (approve: prune-apply {preview['plan_id']} --enable-native)"}]}

    result = prepare(core, session, harness, messages, str(request.get("goal") or ""),
                     request.get("original_messages"))
    notes = []
    if result["removed"]:
        notes.append({"action": "assistant-prose removed", "count": result["removed"],
                      "detail": "excluded from the active view; canonical sources unchanged"})
    if result.get("note"):
        notes.append({"action": "passthrough", "detail": result["note"]})
    response = {"ok": True, "messages": result["messages"], "notes": notes}
    # Evidence injection is the `system-append` claim. A carrier that has no system array in
    # this hook, or that already injects evidence through a separate hook of its own, sets
    # accepts_system_append false; we then return none rather than smuggling it into the
    # message list, which would double-inject and would also exceed this stage's claims.
    if core.config["inject_enabled"] and request.get("accepts_system_append") is not False:
        pack = core.retrieve(str(request.get("goal") or ""), core.config["max_evidence_chars"], False)
        if pack["context"]:
            response["system_append"] = pack["context"]
            notes.append({"action": "evidence appended", "count": len(pack["evidence"]),
                          "bytes": pack["characters"], "detail": "retrieved sources (untrusted data)"})
    return response


def reset(core, session: str, harness: str) -> dict:
    with core.store.db:
        core.store.db.execute("DELETE FROM views WHERE workspace=? AND session=? AND harness=?", (core.workspace,session,harness))
    return {"restored":True,"note":"Original native messages are used on the next transform; sources were never deleted."}
