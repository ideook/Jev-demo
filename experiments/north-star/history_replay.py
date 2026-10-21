"""Read-only historical message inventory; no API calls or target operations."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("north_star", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def inventory(thread, sessions, output):
    ns.thread_id(thread)
    if any((output / name).exists() for name in ("inventory.json", "messages.json", "overview.txt")):
        raise ValueError("Use a new output directory to preserve the existing snapshot")
    paths = sorted(sessions.rglob(f"*{thread}*.jsonl"))
    if not paths:
        raise ValueError("No matching transcripts")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    rows, files, seen = [], [], set()
    key = ns.credentials()
    for index, path in enumerate(paths, 1):
        alias = f"S{index}"
        limit = path.stat().st_size
        counts, hasher = Counter(), hashlib.sha256()
        first, last, offset, line = None, None, 0, 0
        with path.open("rb") as f:
            while offset < limit:
                raw = f.readline(limit - offset)
                line += 1
                hasher.update(raw)
                if not raw.endswith(b"\n"):
                    counts["incomplete_records"] += 1
                    break
                try:
                    record = json.loads(raw)
                except ValueError:
                    counts["malformed_records"] += 1
                    offset += len(raw)
                    continue
                counts["records"] += 1
                timestamp = record.get("timestamp")
                first = first or timestamp
                last = timestamp or last
                if line == 1 and (record.get("type") != "session_meta"
                                  or record.get("payload", {}).get("id") != thread):
                    raise ValueError("Transcript identity mismatch")
                if record.get("type") == "compacted":
                    counts["compactions"] += 1
                # response_item is the original conversational record. event_msg
                # mirrors are excluded, but repeated requests at new times remain.
                m = ns.message(record) if record.get("type") == "response_item" else None
                if m:
                    identity = ns.digest([timestamp, m])
                    if identity in seen:
                        counts["duplicate_messages"] += 1
                    else:
                        seen.add(identity)
                        counts[m["role"]] += 1
                        if m.get("phase") == "final_answer":
                            counts["finals"] += 1
                        rows.append({
                            "id": f"{alias}:{line}", "timestamp": timestamp,
                            "role": m["role"], "phase": m["phase"],
                            "text": ns.clean(m["text"], [key]),
                            "original_chars": len(m["text"]),
                            "source": {"path": str(path), "line": line, "offset": offset,
                                       "record_sha256": ns.digest(raw)},
                        })
                offset += len(raw)
        files.append({"alias": alias, "path": str(path), "snapshot_bytes": limit,
                      "snapshot_sha256": hasher.hexdigest(), "first": first, "last": last,
                      "counts": dict(counts)})
    rows.sort(key=lambda r: (r["timestamp"] or "", r["id"]))
    ns.atomic(output / "messages.json", rows)
    summary = {
        "thread": thread, "snapshot_utc": datetime.now(timezone.utc).isoformat(),
        "files": files, "messages": len(rows),
        "users": sum(r["role"] == "user" for r in rows),
        "finals": sum(r["phase"] == "final_answer" for r in rows),
        "source_sha256": ns.digest((REPO / "hooks/north-star/north_star.py").read_bytes()),
        "policy": ns.DEFAULTS, "api_calls": 0,
    }
    ns.atomic(output / "inventory.json", summary)
    overview = [
        f"{r['id']} {r['timestamp']} {r['role']} {r['phase'] or ''} "
        + r["text"].replace("\n", " ")[:200]
        for r in rows if r["role"] == "user" or r["phase"] == "final_answer"
    ]
    (output / "overview.txt").write_text("\n".join(overview) + "\n")
    (output / "overview.txt").chmod(0o600)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--thread", required=True)
    p.add_argument("--sessions", type=Path, default=Path.home() / ".codex/sessions")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if (args.output / "inventory.json").exists():
        p.error("Use a new output directory to preserve the existing snapshot")
    print(json.dumps(inventory(args.thread, args.sessions, args.output), ensure_ascii=False, indent=2))
