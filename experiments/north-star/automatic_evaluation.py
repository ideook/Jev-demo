"""Replay sealed deidentified project cases through automatic hooks, with a call cap."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ns", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def run(cases_file, output, live=False, max_calls=32, replay=None):
    output = output.resolve()
    if output.exists():
        raise ValueError("Preserve the existing evaluation output")
    cases = json.loads(cases_file.read_text(encoding="utf-8"))
    saved = json.loads(replay.read_text(encoding="utf-8")) if replay else None
    if saved and (live or saved["cases_sha256"] != ns.digest(cases_file.read_bytes())):
        raise ValueError("Replay requires the identical sealed cases and no live calls")
    expected_calls = sum(1 + bool(c.get("recovery_work")) for c in cases)
    if expected_calls > max_calls:
        raise ValueError("Evaluation exceeds the explicit request budget")
    report = {"cases_sha256": ns.digest(cases_file.read_bytes()), "policy_source_sha256": ns.digest((REPO / "hooks/north-star/automatic.py").read_bytes()),
              "skill_sha256": ns.digest((REPO / "skills/north-star/SKILL.md").read_bytes()),
              "expected_calls": expected_calls, "http_requests": 0, "results": [], "live": live,
              "replay_sha256": ns.digest(replay.read_bytes()) if replay else None}
    ns.atomic(output, report)
    key = ns.credentials() if live else "dry-run-placeholder"
    if live and not key:
        raise ValueError("No configured TypeSafe credential")
    workspace = output.with_suffix("")
    for index, case in enumerate(cases):
        root = workspace / case["id"]
        sessions = root / "sessions"
        sessions.mkdir(parents=True)
        transcript = sessions / "synthetic-deidentified.jsonl"
        sid = f"evaluation-{index:04d}"
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid, "source": "vscode"}}) + "\n", encoding="utf-8")
        cfg = {**ns.DEFAULTS, "automatic_goals": True, "allow_export": True,
               "model": "jev-1.14.0", "transcript_roots": [str(sessions)]}
        def event(name, text):
            role = "user" if name == "UserPromptSubmit" else "assistant"
            with transcript.open("ab") as f:
                f.write((json.dumps({"type": "response_item", "payload": {"type": "message", "role": role,
                         "phase": None if role == "user" else "commentary", "content": text}}, ensure_ascii=False) + "\n").encode())
            return {"hook_event_name": name, "session_id": sid, "turn_id": "turn-1", "transcript_path": str(transcript),
                    "prompt": text if role == "user" else None, "last_assistant_message": text if role == "assistant" else None,
                    "tool_use_id": ns.digest(text)[:16], "tool_name": "exec_command", "tool_response": {"exit_code": 0}}
        observed = []
        saved_observations = iter(saved["results"][index]["observations"]) if saved else None
        def provider(body, credential, timeout):
            if saved_observations is not None:
                observation = next(saved_observations)
                if ns.digest(body) != observation["request_sha256"]:
                    raise RuntimeError("Replay request differs from the original live request")
                observed.append({**observation, "replayed": True})
                return observation["judgment"], observation["metrics"]
            if not live:
                ns.atomic(root / f"request-{len(observed)}.json", body)
                observed.append({"dry_run": True})
                raise TimeoutError("Dry run never calls a provider")
            if report["http_requests"] >= max_calls:
                raise RuntimeError("Request cap reached")
            if credential in json.dumps(body):
                raise ValueError("Credential in outgoing payload")
            report["http_requests"] += 1
            ns.atomic(output, report)  # Reserve before the one non-retried network request.
            result, metrics = ns.ask(body, credential, timeout)
            observed.append({"request_sha256": ns.digest(body), "judgment": result, "metrics": metrics})
            return result, metrics
        started = time.monotonic()
        with patch.object(ns, "credentials", return_value=key):
            ns.handle(event("UserPromptSubmit", case["goal"]), root / "north-star", cfg, provider, now=10000)
            store = ns.Store(root / "north-star", sid)
            captured = bool(store.read()["active"])
            before = ns.handle(event("PostToolUse", case["work"]), root / "north-star", cfg, provider, now=10001)
            state = store.read()
            status = state["health"]["status"]
            issued = bool(state.get("recovery"))
            if case.get("recovery_work"):
                # Historical continuation is replay, not an agent responding to our new hook.
                ns.handle(event("PostToolUse", case["recovery_work"]), root / "north-star", cfg, provider, now=10100)
            after = store.read()
        row = {"id": case["id"], "project": case["project"], "category": case["category"],
               "goal_captured": captured, "health": status, "recovery_requested": issued,
               "local_review_requested": bool(before.get("hookSpecificOutput")) and not issued,
               "expected_recovery": case["expected_recovery"], "observations": observed,
               "recovery_replayed": bool(case.get("recovery_work")),
               "recovery_confirmed": after["health"]["status"] == "recovery_aligned",
               "elapsed_ms": round((time.monotonic() - started) * 1000)}
        row["judged"] = status in ("aligned", "recovery_requested", "notice_suppressed", "recovery_pending")
        row["matches_expected"] = captured and row["judged"] and issued == case["expected_recovery"]
        report["results"].append(row)
        ns.atomic(output, report)
        print(json.dumps({k: row[k] for k in ("id", "category", "health", "recovery_requested", "matches_expected")}), flush=True)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--max-calls", type=int, default=32)
    p.add_argument("--replay", type=Path, help="Reuse a sealed live report without API requests")
    args = p.parse_args()
    run(args.cases, args.output, args.live, args.max_calls, args.replay)
