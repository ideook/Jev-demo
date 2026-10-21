"""Replay the current message-length gates locally at frozen transcript offsets."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("north_star", REPO / "hooks/north-star/north_star.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def assess(current, tail):
    recent = [ns.clean(m["text"]) for m in tail]
    current = ns.clean(current)
    blockers = []
    if len(current) > 2000:
        blockers.append("current_over_2000")
    if any(len(text) > 1200 for text in recent):
        blockers.append("recent_over_1200")
    # Sensitivity analysis only. The installed hook does not strip this footer.
    body = lambda text: text.split("<oai-mem-citation>")[0].strip()
    return {
        "text_caps_pass": not blockers, "blockers": blockers,
        "current_chars": len(current), "recent_chars": [len(text) for text in recent],
        "without_citation_caps_pass": len(body(current)) <= 2000
        and all(len(body(text)) <= 1200 for text in recent),
    }


def assess_current(current, tail, role):
    if ns.INJECTED.match(current.lstrip()):
        return {"text_caps_pass": False, "blockers": ["injected_current"], "current_chars": len(current),
                "recent_chars": [], "without_citation_caps_pass": False}
    current = ns.judgment_text(current, role)
    texts = [{"role": m["role"], "text": ns.judgment_text(m["text"], m["role"])} for m in tail]
    if texts and texts[-1] == {"role": role, "text": current}:
        texts.pop()
    return assess(current, texts)


def replay(inventory_path, messages_path, output, current_policy=False):
    if output.exists():
        raise ValueError("Preserve the existing replay; choose another output")
    inventory = json.loads(inventory_path.read_text())
    messages = json.loads(messages_path.read_text())
    targets = {r["id"]: r for r in messages
               if r["role"] == "user" or r["phase"] == "final_answer"}
    key, results = ns.credentials(), []
    output.parent.mkdir(parents=True, exist_ok=True)
    # The real recent() parser reads a growing local prefix. Future messages
    # and tool output cannot enter the snapshot for an earlier event.
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        for source in inventory["files"]:
            staged = Path(temporary) / "prefix.jsonl"
            staged.touch(mode=0o600)
            with Path(source["path"]).open("rb") as src, staged.open("wb") as dst:
                offset, line = 0, 0
                hasher = hashlib.sha256()
                while offset < source["snapshot_bytes"]:
                    raw = src.readline(source["snapshot_bytes"] - offset)
                    if not raw:
                        raise ValueError("Source shortened since inventory")
                    dst.write(raw)
                    hasher.update(raw)
                    line += 1
                    ident = f"{source['alias']}:{line}"
                    row = targets.get(ident)
                    if row:
                        if offset != row["source"]["offset"] or ns.digest(raw) != row["source"]["record_sha256"]:
                            raise ValueError("Historical source changed")
                        dst.flush()
                        tail, partial = ns.recent(staged, inventory["thread"])
                        tail = [{**m, "text": ns.clean(m["text"], [key])} for m in tail]
                        result = (assess_current(row["text"], tail, row["role"]) if current_policy
                                  else assess(row["text"], tail))
                        results.append({
                            "id": ident, "event": "Stop" if row["role"] == "assistant" else "UserPromptSubmit",
                            "tail_partial": partial, "tail_messages": len(tail), **result,
                        })
                    offset += len(raw)
                if hasher.hexdigest() != source["snapshot_sha256"]:
                    raise ValueError("Historical source changed outside a target record")
    groups = {}
    for event in ("Stop", "UserPromptSubmit"):
        rows = [r for r in results if r["event"] == event]
        groups[event] = {
            "events": len(rows), "text_caps_pass": sum(r["text_caps_pass"] for r in rows),
            "blocker_counts_overlapping": dict(Counter(b for r in rows for b in r["blockers"])),
            "without_citation_caps_pass": sum(r["without_citation_caps_pass"] for r in rows),
            "partial_tail": sum(r["tail_partial"] for r in rows),
        }
    report = {
        "source_sha256": ns.digest((REPO / "hooks/north-star/north_star.py").read_bytes()),
        "inventory_sha256": ns.digest(inventory_path.read_bytes()),
        "method": "Actual recent() on each prefix immediately after the original message record",
        "text_policy": "current" if current_policy else "legacy_caps",
        "limitation": "Text-cap upper bound only; anchors, evidence quality, state byte budget, cooldown, rate limit and dispatch excluded",
        "api_calls": 0, "groups": groups, "results": results,
    }
    ns.atomic(output, report)
    return groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--messages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--current-policy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(replay(args.inventory, args.messages, args.output, args.current_policy), indent=2))
