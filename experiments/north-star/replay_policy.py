"""Replay policy only when every exact provider request still matches."""
import argparse
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("north_star", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def replay(cases_path, results_path, output):
    if output.exists():
        raise ValueError("Preserve the existing replay")
    cases = {case["id"]: case for case in json.loads(cases_path.read_text())}
    report = json.loads(results_path.read_text())
    if ns.digest(cases_path.read_bytes()) != report["seal"]["cases_sha256"]:
        raise ValueError("Cases changed")
    rows = []
    for result in report["results"]:
        case = cases[result["id"]]
        body = ns.request_body(case["view"], report["seal"]["policy"]["model"])
        if (ns.digest(case["view"]) != result["view_sha256"]
                or ns.digest(body) != result.get("request_sha256")):
            raise ValueError("Exact request changed; judgments cannot be reused")
        rows.append({
            "id": case["id"], "cohort": case["cohort"], "category": case.get("category"),
            "live_action": result["action"],
            "final_action": ns.action(result["judgment"], case["view"], ns.DEFAULTS),
            "expected_actions": case.get("expected_actions"),
        })
    ns.atomic(output, {
        "api_calls": 0, "all_request_hashes_match": True,
        "source_sha256": ns.digest((REPO / "hooks/north-star/north_star.py").read_bytes()),
        "cases_sha256": ns.digest(cases_path.read_bytes()),
        "results_sha256": ns.digest(results_path.read_bytes()),
        "policy": ns.DEFAULTS, "rows": rows,
    })
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = replay(args.cases, args.results, args.output)
    print(json.dumps([row for row in rows if row["live_action"] != row["final_action"]], indent=2))
