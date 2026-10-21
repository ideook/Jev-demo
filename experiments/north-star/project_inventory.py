"""Inventory conversational records for specified project roots; no API calls."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ns", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)
CORRECTION = re.compile(r"(?:딴|다른|엉뚱|이탈|원래|주제|방향|요청한|말한|뭘 한|뭐 하는|왜.*(?:했|하는)|아니|돌아|다시|내가 원|의도)")


def inventory(projects, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "project-inventory.json").exists():
        raise ValueError("Use a fresh inventory directory")
    roots = [Path(p).resolve() for p in projects]
    files, candidates, counts = [], [], Counter()
    key = ns.credentials()
    for directory in (Path.home() / ".codex/sessions", Path.home() / ".codex/archived_sessions"):
        for path in directory.rglob("*.jsonl"):
            try:
                with path.open("rb") as f:
                    meta = json.loads(f.readline(2 * 1024 * 1024))["payload"]
                cwd = Path(meta.get("cwd", "")).resolve()
                if isinstance(meta.get("source"), dict) or meta.get("is_subagent"):
                    continue
                project = next((i for i, root in enumerate(roots) if cwd.is_relative_to(root)), None)
                if project is None:
                    continue
                rows, offset = [], 0
                with path.open("rb") as f:
                    for line, raw in enumerate(f, 1):
                        pos, offset = offset, offset + len(raw)
                        try:
                            record = json.loads(raw)
                            if record.get("type") != "response_item":
                                continue
                            m = ns.message(record)
                            if m:
                                rows.append({**m, "text": ns.clean(m["text"], [key]),
                                             "line": line, "offset": pos, "sha256": ns.digest(raw)})
                        except (ValueError, KeyError, TypeError):
                            continue
                alias = f"P{project + 1}-T{sum(x['project'] == project for x in files) + 1:03d}"
                files.append({"alias": alias, "project": project, "thread": meta.get("id"),
                              "path": str(path), "messages": len(rows)})
                counts[f"P{project + 1}_threads"] += 1
                counts[f"P{project + 1}_messages"] += len(rows)
                for i, row in enumerate(rows):
                    if row["role"] == "user" and CORRECTION.search(row["text"]):
                        candidates.append({"thread": meta.get("id"), "alias": alias,
                                           "path": str(path), "index": i,
                                           "context": rows[max(0, i - 4):i + 5]})
            except (OSError, ValueError, KeyError, TypeError):
                continue
    ns.atomic(output / "project-inventory.json", {"projects": [str(p) for p in roots],
              "files": files, "counts": dict(counts), "api_calls": 0})
    ns.atomic(output / "correction-candidates.json", candidates)
    print(json.dumps({"counts": dict(counts), "candidate_windows": len(candidates), "api_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory(args.project, args.output)
