"""Evaluate frozen, deidentified historical cases without changing the policy."""
import argparse
import importlib.util
import json
from pathlib import Path
import time

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("north_star", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def run(cases_path, output, live, max_calls):
    cases = json.loads(cases_path.read_text())
    if not 1 <= max_calls <= 40 or len(cases) > max_calls:
        raise ValueError("Call budget exceeded")
    key = ns.credentials()
    for case in cases:
        state = json.dumps(case["view"], ensure_ascii=False)
        if len(state.encode()) > 24000 or (key and key in state):
            raise ValueError("Unsafe or oversized payload")
    seal = {
        "cases_sha256": ns.digest(cases_path.read_bytes()),
        "source_sha256": ns.digest((REPO / "hooks/north-star/north_star.py").read_bytes()),
        "policy": ns.DEFAULTS, "cases": len(cases), "max_calls": max_calls,
        "request_schema_sha256": ns.digest(ns.request_body({}, ns.DEFAULTS["model"])),
        "request_schemas_sha256": {event: ns.digest(ns.request_body({"event": event}, ns.DEFAULTS["model"]))
                                   for event in ("Stop", "UserPromptSubmit")},
    }
    if not live:
        return seal
    if not key:
        raise ValueError("Existing credential unavailable")
    if output.exists():
        raise ValueError("Existing run must not be repeated or overwritten")
    report = {"seal": seal, "started": time.time(), "attempts": [], "results": []}
    ns.atomic(output, report)
    for case in cases:
        # Persist before sending. An unknown charged outcome is never retried.
        body = ns.request_body(case["view"], ns.DEFAULTS["model"])
        request_sha = ns.digest(body)
        report["attempts"].append({"id": case["id"], "time": time.time(), "request_sha256": request_sha})
        ns.atomic(output, report)
        try:
            j, metrics = ns.ask(body, key, 8)
        except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
            report["failure"] = {"case": case["id"], "kind": type(exc).__name__,
                                 "note": "No retry; request outcome may be unknown"}
            ns.atomic(output, report)
            raise SystemExit("Evaluation stopped; see sanitized failure metadata")
        outcome = ns.action(j, case["view"], ns.DEFAULTS)
        expected = case.get("expected_actions")
        result = {
            "id": case["id"], "cohort": case["cohort"], "action": outcome,
            "expected_actions": expected, "action_ok": outcome in expected if expected else None,
            "judgment": j, "metrics": metrics, "view_sha256": ns.digest(case["view"]),
            "request_sha256": request_sha,
        }
        report["results"].append(result)
        ns.atomic(output, report)
        print(json.dumps({"id": case["id"], "action": outcome, "ok": result["action_ok"]}), flush=True)
    report["finished"] = time.time()
    ns.atomic(output, report)
    return {"calls": len(report["attempts"]), "responses": len(report["results"]),
            "output": str(output), "seal": seal}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.cases, args.output, args.live, args.max_calls), indent=2))
