#!/usr/bin/env python3
"""Run synthetic observer cases. Only --live allows up to three paid calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

import observer

BASE = "def total(quantity, price):\n    return quantity * price\n"
FIXED = "def total(quantity, price):\n    if quantity < 0:\n        raise ValueError('negative quantity')\n    return quantity * price\n"
CHECK = "from pricing import total; assert total(2, 3) == 6"
FULL_CHECK = CHECK + ";\ntry:\n    total(-1, 3)\n    raise AssertionError('negative quantity accepted')\nexcept ValueError:\n    pass\n"


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def case(directory, name, live):
    root = directory / name
    root.mkdir(parents=True)
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".runtime/\n__pycache__/\n", encoding="utf-8")
    (root / "pricing.py").write_text(BASE, encoding="utf-8")
    git(root, "add", ".gitignore", "pricing.py")
    git(root, "-c", "user.name=Observer Demo", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
        "-c", "core.hooksPath=" + str(root / "no-hooks"), "commit", "-qm", "synthetic baseline")
    plan = {"title": "음수 수량 입력 거부", "message": "fix: reject negative quantities", "acceptance": [
        "수량이 음수이면 ValueError를 발생시킨다.", "0 이상 수량의 기존 곱셈 결과를 유지한다."],
        "files": ["pricing.py"] + (["banner.py"] if name == "mixed" else []),
        "checks": [["{python}", "-B", "-c", CHECK if name == "incomplete" else FULL_CHECK]]}
    path = observer.session_path(root, "pricing")
    observer.begin(root, path, plan)
    (root / "pricing.py").write_text(BASE + "\n# TODO: reject negative quantities\n" if name == "incomplete" else FIXED, encoding="utf-8")
    if name == "mixed":
        (root / "banner.py").write_text("def homepage_banner():\n    return 'Summer sale'\n", encoding="utf-8")
    state = observer.read_state(root, path)
    observer.verify(root, path, state)
    if name == "stale":
        (root / "pricing.py").write_text(FIXED + "\n# changed after verification\n", encoding="utf-8")
    before = observer.snapshot(root)
    index = (root / ".git/index").read_bytes()
    report = observer.observe(root, path, state, live, live)
    after = observer.snapshot(root)
    if before != after or index != (root / ".git/index").read_bytes():
        raise RuntimeError("Observer modified Git or source state")
    return {"case": name, "expected": "would_commit" if name == "complete" else "hold", "report": report,
            "head_index_worktree_preserved": True, "runtime": str(root)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    directory = repo / ".runtime/experiments/jev-commit-observer" / ("demo-" + uuid.uuid4().hex[:12])
    rows = []
    for name in ("complete", "incomplete", "mixed", "stale"):
        row = case(directory, name, a.live)
        rows.append(row)
        observer.write_json(directory / "results.json", rows)
        print(observer.encode({"case": name, "decision": row["report"]["decision"], "reasons": row["report"]["reasons"],
                              "probabilities": row["report"].get("probabilities"), "metrics": row["report"].get("metrics"),
                              "preserved": True}), flush=True)
    summary = {"live": a.live, "cases": len(rows), "api_attempts": sum(r["report"]["api_attempted"] for r in rows),
               "matched_expected": sum(r["report"]["decision"] == r["expected"] for r in rows),
               "all_git_and_source_preserved": all(r["head_index_worktree_preserved"] for r in rows),
               "results": str(directory / "results.json")}
    observer.write_json(directory / "summary.json", summary)
    print(observer.encode(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
