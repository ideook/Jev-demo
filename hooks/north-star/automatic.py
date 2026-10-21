"""Source-backed automatic lifecycle. Tool bodies stay local; Jev reviews conversation."""
import json
from pathlib import Path
import time

EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "PreCompact", "PostCompact")


def contextual_reply(text):
    return text.lstrip().startswith("<send_user_message_question_reply>")


def original_goal(rows):
    return next((r for r in reversed(rows) if r["role"] == "user"
                 and not contextual_reply(r["text"]) and not r["text"].lstrip().startswith("/")), None)


def canonical_transcript(core, event, store, roots):
    # Some native clients supply a temporary transcript projection. Anchor only
    # to an identity-checked original rollout under explicitly allowed roots.
    cached = store.read().get("canonical_transcript")
    for path in (event.get("transcript_path"), cached):
        if path:
            try:
                return core.transcript(path, store.sid, roots)
            except (OSError, ValueError, TypeError):
                pass
    matches = []
    for root in roots:
        for path in Path(root).glob(f"**/*{store.sid}*.jsonl"):
            try:
                matches.append(core.transcript(path, store.sid, roots))
            except (OSError, ValueError, TypeError):
                continue
    matches = list(dict.fromkeys(matches))
    return matches[0] if len(matches) == 1 else None


def execution_succeeded(event):
    response = event.get("tool_response")
    if event.get("tool_name") == "Bash" and isinstance(response, str):
        return False  # Native Bash sends stdout only, including any forged JSON/header.
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return False
    return (isinstance(response, dict) and response.get("isError") is not True
            and type(response.get("exit_code")) is int and response["exit_code"] == 0)


def observed_execution(state, event, now):
    if execution_succeeded(event):
        return True
    recovery = state.get("recovery") or {}
    receipt = recovery.get("verified_execution") or {}
    command = event.get("tool_input", {}).get("command", "") if isinstance(event.get("tool_input"), dict) else ""
    return (event.get("tool_name") == "Bash" and bool(receipt.get("id"))
            and receipt["id"] in command and "verify-execution" in command
            and receipt.get("anchor_version") == state["anchor_version"]
            and recovery.get("goal") == state["active"]
            and receipt.get("exit_code") == 0 and 0 <= now - receipt.get("at", 0) <= 120)


def execution_shape(value):
    """Record envelope types locally, never command output or arbitrary field names."""
    if isinstance(value, dict):
        names = ("exit_code", "exitCode", "metadata", "content", "output", "isError", "text", "result")
        return {"type": "object", "fields": {k: type(value[k]).__name__ for k in names if k in value}}
    if isinstance(value, list):
        return {"type": "array", "items": [execution_shape(x) for x in value[:3]]}
    if isinstance(value, str):
        try:
            return {"type": "json_string", "value": execution_shape(json.loads(value))}
        except ValueError:
            return {"type": "text", "native_exec_header": value.startswith("Chunk ID:")}
    return {"type": type(value).__name__}


def close_recovery(core, store, state, event, now):
    state["recovery"].update(status="aligned_execution", confirmed_at=now,
                             tool_event_hash=core.digest([event.get("tool_use_id"), event.get("tool_response")]))
    state["last_recovery"] = state["recovery"]
    state["recovery"] = None
    save_health(core, store, state, "recovery_aligned", now)


def capture(core, store, event):
    text = event.get("prompt", "")
    record = {"type": "response_item", "payload": {
        "type": "message", "role": "user", "content": text}}
    if not core.message(record):
        return None
    source = store.directory / "sources" / (core.digest([event.get("turn_id"), text]) + ".jsonl")
    source.parent.mkdir(exist_ok=True, mode=core.DIRECTORY_MODE)
    meta = json.dumps({"type": "session_meta", "payload": {
        "id": store.sid, "source": "north-star-original-user-prompt"}}).encode() + b"\n"
    raw = json.dumps(record, ensure_ascii=False).encode() + b"\n"
    expected = meta + raw
    try:
        with source.open("xb") as f:
            f.write(expected)
        source.chmod(0o600)
    except FileExistsError:
        if source.is_symlink() or source.read_bytes() != expected:
            raise core.Invalid("changed_prompt_source")
    start = 0
    if text.lstrip().startswith("# Files mentioned by the user:") and "## My request:" in text:
        start = text.index("## My request:") + len("## My request:")
    return core.reference(source, store.sid, len(meta), raw, start=start)


def literal_node(core, store, ref, roots):
    original = core.read_ref(ref, store.sid, roots)["text"]
    # This label is not a semantic summary; the complete source remains authoritative.
    label = core.judgment_text(original, "user").strip()[:300]
    return {"id": "auto_" + ref["id"][:16], "parent": None, "goal": label,
            "refs": [ref], "result_refs": [], "done_when": [], "constraints": [],
            "status": "active", "completed": [], "remaining": [], "automatic_source": True}


def context(core, store, state, reason):
    recovery = state.get("recovery") or {}
    execution = (f"\nPending recovery token: {recovery['observation_hash']}. "
                 f"For a native Bash result without exit metadata, use the skill's verify-execution "
                 f"CLI with --root {store.root} before the subcommand to run the next authorized check."
                 if recovery else "")
    return (core.skill_context(store.root, state) + "\n" + reason + execution +
            "\nMaintain this privately. Verify original human scope and actual local tool evidence. "
            "Do not ask the user to name the goal, announce routine checks, or treat a score as authority. "
            "Acknowledge recovery only after the next actual action advances the authorized goal.")


def save_health(core, store, state, status, now):
    state["health"] = {"status": status, "at": now}
    store.save(state)
    core.atomic(store.root / "last-status.json", {"thread": store.sid, "at": now,
                "status": status, "active": bool(state["active"]),
                "pending_recovery": bool(state.get("recovery"))})


def private_review(core, store, state, event, status, now):
    """An unavailable judgment asks Codex to check locally, not to declare alignment."""
    save_health(core, store, state, status, now)
    if event not in ("PostToolUse", "UserPromptSubmit"):
        return {}
    key = core.digest([state["active"], state["anchor_version"], status])
    reviews = state.setdefault("local_reviews", {})
    if now - reviews.get(key, -1e20) < core.DEFAULTS["cooldown_seconds"]:
        return {}
    reviews[key] = now
    state["local_reviews"] = dict(list(reviews.items())[-64:])
    store.save(state)
    return core.internal_context(event, context(core, store, state,
        f"The automatic check is unverified ({status}). Read this thread's original human sources "
        "and compare the actual local operation with their scope once. Refine the source-backed "
        "anchor if needed, resume authorized work if drift is found, and otherwise continue silently. "
        "Do not send more history, retry Jev, or count this request as a detected error."))


def archive(core, store, state):
    core.atomic(store.directory / "history" / f"{state['anchor_version']:06d}.json",
                {"active": state["active"], "nodes": state["nodes"],
                 "version": state["anchor_version"]})


def request_body(core, view, model):
    body = core.request_body(view, model)
    questions = body["questions"]
    questions["evidence"]["instructions"] = "Do the original HUMAN source excerpts support the active goal? Judge authorization of scope, not execution success. Summaries alone are insufficient."
    questions["evidence"]["criteria"] = {"true": "Original human requests support the goal.", "false": "Sources are absent or contradict the goal."}
    questions["remind"]["instructions"] = "Is the ASSISTANT pursuing an unrelated unrequested objective or confused about the current task? Normal implementation, debugging and verification are subtasks; explicit human pivots and returns are legitimate."
    questions["remind"]["criteria"] = {"true": "Assistant work has departed from human intent.", "false": "Work is aligned, or the human legitimately changes topic."}
    questions["omission"]["instructions"] = "For Stop only: does the final result omit relevant earlier completed work in the SAME goal's ancestry, making the last check sound like the whole task? A retry alone does not narrow reporting scope. Respect explicit narrow questions and different targets or stages. Assistant completion reports are claims, not proof."
    questions["omission"]["criteria"] = {"true": "A relevant earlier result should be connected to this final report but is omitted.", "false": "Relevant results are explained, scope is explicitly narrow, evidence is absent, or this is not Stop."}
    questions["contradiction"]["instructions"] = "For Stop only: does the final report deny an earlier supported result for the SAME target and stage? Saying this verification made no additional changes does not deny prior implementation. Different targets, corrected unverified claims and quoted denials are not contradictions."
    questions["contradiction"]["criteria"] = {"true": "The report denies the same supported result.", "false": "No contradiction is evidenced, or this is not Stop."}
    questions["report_scope"]["instructions"] = "From the latest human request and current assistant text, identify the report scope. A retry request alone does not restrict the final report to that check."
    questions["report_scope"]["criteria"] = {"result": "Final result without an explicit narrow restriction.", "narrow": "The human explicitly requests only a particular fact/check.", "progress": "Intermediate work, not a final report."}
    return body


def handle(core, event, root, cfg, ask_fn, now=None):
    now = time.time() if now is None else now
    name = event.get("hook_event_name")
    if cfg["mode"] == "off" or name not in EVENTS or event.get("agent_id") or event.get("agent_transcript_path"):
        return {}
    store = core.Store(root, event["session_id"])
    roots = [*(cfg.get("transcript_roots") or [str(Path.home() / ".codex/sessions")]),
             str(store.directory / "sources")]
    transcript = canonical_transcript(core, event, store, roots)
    ref = None
    restored = False
    with store.lock():
        state = store.read()
        if transcript:
            state["canonical_transcript"] = str(transcript)
        if name == "UserPromptSubmit":
            ref = capture(core, store, event)
            if ref is None:
                return {}
        active = next((n for n in state["nodes"] if n["id"] == state["active"]), None)
        repair_reply = bool(len(state["nodes"]) == 1 and active and active.get("automatic_source") and contextual_reply(
            core.read_ref(active["refs"][0], store.sid, roots)["text"]))
        reply = contextual_reply(event.get("prompt") or "")
        if ((not state["active"] and (ref is None or reply)) or repair_reply) and transcript:
            rows, _ = core.recent(transcript, store.sid, 32)
            human = original_goal(rows)
            if human:
                node = literal_node(core, store, human["ref"], roots)
                archive(core, store, state)
                state.update(nodes=[node], active=node["id"], anchor_version=state["anchor_version"] + 1,
                             latest_request_ref=human["ref"], bootstrap_sent=True)
                save_health(core, store, state, "goal_restored_from_source", now)
                restored = True
        if name in ("PreCompact", "PostCompact"):
            state["checkpoint"] = {"event": name, "version": state["anchor_version"], "time": now}
            save_health(core, store, state, "checkpoint_preserved", now)
            return {}
        if name == "SessionStart":
            save_health(core, store, state, "ready" if state["active"] else "awaiting_user_request", now)
            return core.internal_context(name, context(core, store, state, "Automatic goal capture is enabled."))
        if event.get("stop_hook_active"):
            return {}
        if ref:
            state["latest_request_ref"] = ref
            state["bootstrap_sent"] = True
            if not state["active"]:
                if reply:
                    return private_review(core, store, state, name, "awaiting_original_task_source", now)
                node = literal_node(core, store, ref, roots)
                archive(core, store, state)
                state.update(nodes=[node], active=node["id"], anchor_version=state["anchor_version"] + 1)
                save_health(core, store, state, "goal_registered", now)
                return core.internal_context(name, context(core, store, state,
                    "The first user goal is already saved from the complete original prompt. "
                    "Refine its summary, constraints and milestones from the original sources as work progresses."))
            store.save(state)
            if restored:
                return core.internal_context(name, context(core, store, state,
                    "The original task is restored. The latest structured answer is contextual "
                    "authorization or clarification, not an independent replacement goal."))
        if not state["active"]:
            save_health(core, store, state, "awaiting_user_source", now)
            return {}
        if not transcript:
            return private_review(core, store, state, name,
                                  "invalid_transcript" if event.get("transcript_path") else "missing_transcript", now)
        recent, _ = core.recent(transcript, store.sid, 8)
        assistant = next((row for row in reversed(recent) if row["role"] == "assistant"), None)
        current = event.get("prompt") if name == "UserPromptSubmit" else event.get("last_assistant_message")
        if name == "PostToolUse":
            current = assistant["text"] if assistant else ""
            state["last_execution_envelope"] = {"tool": event.get("tool_name"),
                "shape": execution_shape(event.get("tool_response")), "success": execution_succeeded(event)}
            if state.get("recovery") and assistant and execution_succeeded(event):
                state["recovery"]["execution_observation"] = {
                    "intent_ref": assistant["ref"], "at": now,
                    "tool_hash": core.digest([event.get("tool_use_id"), event.get("tool_response")])}
        if not current:
            save_health(core, store, state, "missing_work_description", now)
            return {}
        recovery = state.get("recovery")
        if (name == "Stop" and recovery and cfg["mode"] == "conditional"
                and cfg["stop_continuation"] and not recovery.get("verification_continuation_sent")):
            recovery["verification_continuation_sent"] = True
            save_health(core, store, state, "recovery_execution_unverified", now)
            return {"decision": "block", "reason": context(core, store, state,
                "Recovery remains open: printed Bash output did not provide a process exit code. "
                "Before finishing, run the next already-authorized check through verify-execution "
                "as documented in the installed skill, with this current version and recovery token. "
                "Its native PostToolUse can confirm observed execution. Review actual effects locally. "
                "This is one bounded continuation, not new authority. If the check cannot run, "
                "leave recovery unverified and finish without claiming it closed.")}
        # Hash full local input for event identity, but never export its command/body/output.
        eid = core.digest([name, event.get("turn_id"), current, event.get("tool_use_id"),
                           event.get("tool_name"), event.get("tool_input")])
        if eid in state["events"]:
            return {}
        state["events"] = (state["events"] + [eid])[-128:]
        fingerprint = core.digest([state["active"], state["anchor_version"], state.get("latest_request_ref", {}).get("id"), current])
        if name == "PostToolUse" and state.get("last_work_fingerprint") == fingerprint:
            if state.get("recovery") and state.get("last_outcome") == "silent" and observed_execution(state, event, now):
                close_recovery(core, store, state, event, now)
                return {}
            if state.get("recovery") and state.get("last_outcome") == "silent":
                return private_review(core, store, state, name, "recovery_execution_unverified", now)
            save_health(core, store, state, "unchanged_work_cached", now)
            return {}
        state["revision"] += 1
        revision = state["revision"]
        state["calls"] = [t for t in state["calls"] if t > now - 3600]
        status = ("export_disabled" if not cfg["allow_export"] else
                  "provider_backoff" if now < state.get("backoff_until", 0) else
                  "call_budget_exhausted" if len(state["calls"]) >= cfg["max_calls_per_thread_hour"] else None)
        if status:
            return private_review(core, store, state, name, status, now)
        store.save(state)
    key = core.credentials(env_file=cfg.get("env_file"))
    if not key:
        with store.lock():
            latest = store.read()
            return private_review(core, store, latest, name, "missing_key", now)
    snapshot_event = {**event, "transcript_path": str(transcript), "last_assistant_message": current}
    if name == "PostToolUse":
        snapshot_event["hook_event_name"] = "Stop"
    attempted = False
    try:
        view = core.snapshot(state, snapshot_event, roots, key)
        view["event"] = name
        if not view["evidence_complete"]:
            with store.lock():
                latest = store.read()
                return private_review(core, store, latest, name, "clipped_evidence", now)
        body = request_body(core, view, cfg["model"])
        if name == "PostToolUse":
            body["state"]["work_observation"] = "Latest assistant intent before a completed tool; tool bodies remain local. Not proof of the tool's effect."
        if name == "UserPromptSubmit":
            choices = {n["id"]: n["goal"] for n in state["nodes"] if n.get("parent") is None}
            body["questions"]["target_goal"] = {"type": "choice", "criteria": {**choices, "new": "A new independent human goal"},
                "instructions": "Which recorded root goal does the latest HUMAN request continue or return to? Choose new only for a new independent topic. Use original human sources; shared tools alone do not link unrelated goals."}
        with store.lock():
            latest = store.read()
            if latest["revision"] != revision or latest["anchor_version"] != state["anchor_version"]:
                save_health(core, store, latest, "stale_snapshot", now)
                return {}
            latest["calls"].append(now)
            store.save(latest)
        attempted = True
        judgment, metrics = ask_fn(body, key, cfg["timeout_seconds"])
        required = {"relation", "confidence", "aligned_probability", "navigation_probability", "evidence",
                    "remind", "omission", "contradiction", "report_scope", "scope_confidence"}
        if not required <= judgment.keys() or any(not core.probability(judgment[k]) for k in required - {"relation", "report_scope"}):
            raise core.Invalid("invalid_automatic_judgment")
        if judgment["relation"] not in core.RELATIONS or judgment["report_scope"] not in ("result", "narrow", "progress"):
            raise core.Invalid("invalid_automatic_choice")
        outcome = core.action(judgment, view, cfg)
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        with store.lock():
            latest = store.read()
            if attempted:
                latest["backoff_until"] = now + cfg["failure_backoff_seconds"]
            return private_review(core, store, latest, name,
                                  "provider_unavailable" if attempted else "invalid_evidence", now)
    with store.lock():
        latest = store.read()
        if latest["revision"] != revision or latest["anchor_version"] != state["anchor_version"]:
            save_health(core, store, latest, "stale_response", now)
            return {}
        store.audit(name, status=outcome, judgment=judgment, **metrics)
        latest["last_work_fingerprint"] = fingerprint
        latest["last_outcome"] = outcome
        if outcome == "maintain" and name == "UserPromptSubmit" and cfg["mode"] != "shadow":
            target = judgment.get("target_goal")
            confidence = judgment.get("target_confidence", 0)
            if not core.probability(confidence) or confidence < cfg["confidence"]:
                save_health(core, store, latest, "goal_selection_uncertain", now)
                return core.internal_context(name, context(core, store, latest,
                    "Privately reconcile the latest human request with recorded goals using original sources."))
            node = None
            if target == "new" and judgment["relation"] == "user_switch" and ref:
                node = literal_node(core, store, ref, roots)
                if len(latest["nodes"]) >= 32:
                    save_health(core, store, latest, "goal_capacity_reached", now)
                    return {}
                latest["nodes"].append(node)
            elif judgment["relation"] == "return":
                node = next((n for n in latest["nodes"] if n["id"] == target and n.get("parent") is None), None)
            if node:
                # The archived graph must precede changes to any existing node.
                archive(core, store, state)
                old = next(n for n in latest["nodes"] if n["id"] == latest["active"])
                if old["status"] == "active":
                    old["status"] = "paused"
                node["status"] = "active"
                latest.update(active=node["id"], anchor_version=latest["anchor_version"] + 1, recovery=None)
                save_health(core, store, latest, "human_goal_changed", now)
                return core.internal_context(name, context(core, store, latest, "The human's selected goal is saved. Follow their current intent."))
        recovery = latest.get("recovery")
        if outcome == "silent" and name in ("PostToolUse", "Stop") and recovery:
            if name == "PostToolUse" and observed_execution(latest, event, now):
                close_recovery(core, store, latest, event, now)
            else:
                return private_review(core, store, latest, name, "recovery_execution_unverified", now)
            return {}
        if cfg["mode"] == "shadow" or outcome not in ("remind", "report", "review"):
            if outcome == "abstain" and cfg["mode"] != "shadow":
                return private_review(core, store, latest, name, "abstain", now)
            save_health(core, store, latest, "aligned" if outcome == "silent" else outcome, now)
            return {}
        notice_key = core.digest([latest["active"], latest["anchor_version"], outcome])
        if now - latest["notices"].get(notice_key, -1e20) < cfg["cooldown_seconds"]:
            save_health(core, store, latest, "recovery_pending" if recovery else "notice_suppressed", now)
            return {}
        latest["notices"][notice_key] = now
        latest["recovery"] = {"goal": latest["active"], "reason": outcome, "issued_at": now,
                              "status": "requested", "observation_hash": fingerprint}
        text = context(core, store, latest,
            "Possible work drift or report omission. Check original goal and actual tool effects locally now; "
            "resume the authorized task if drift is confirmed. Respect genuine human topic changes. "
            "Do not claim success from Jev's score or undo an action automatically.")
        save_health(core, store, latest, "recovery_requested", now)
        if name == "Stop" and cfg["stop_continuation"]:
            return {"decision": "block", "reason": text + "\nOne bounded recovery continuation, not new authorization. Stop silently if the finding is false."}
        return core.internal_context(name, text)
