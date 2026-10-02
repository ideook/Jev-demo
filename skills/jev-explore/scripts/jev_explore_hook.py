"""Return a completed Jev Explore shortlist to Codex without another API call."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time

CACHE_ROOT = Path(tempfile.gettempdir()) / "codex-jev-explore"
SCHEMA = "codex.jev-explore.v1"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def feedback(event: dict) -> dict:
    if event.get("hook_event_name") != "PostToolUse" or event.get("tool_name") not in ("Bash", "exec_command", "shell", "shell_command"):
        return {}
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    command = tool_input.get("command", tool_input.get("cmd", ""))
    if not isinstance(command, str) or not re.search(r"(?:^|[/\\\s\"'])jev_rank\.py(?:[\s\"']|$)", command):
        return {}
    text = "\n".join(strings(event.get("tool_response", "")))
    if len(text) > 2_000_000:
        return {}
    markers = re.findall(r"^JEV_EXPLORE_RESULT=(.+)$", text, re.M)
    if len(markers) != 1:
        return {}
    path = Path(markers[0].strip())
    if not path.is_absolute() or path.is_symlink() or not re.fullmatch(r"result-[0-9a-f-]{36}\.json", path.name) or path.resolve().parent != CACHE_ROOT.resolve():
        return {}
    if path.stat().st_size > 1_000_000 or not -5 <= time.time() - path.stat().st_mtime <= 600:
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema") != SCHEMA or Path(report["root"]).resolve() != Path(event["cwd"]).resolve():
        return {}
    root = Path(report["root"]).resolve()
    top = report.get("top")
    if isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= 15:
        return {}
    lines = [f"Jev Explore reading priorities ({report['status']}; {report['candidate_count']} candidates):"]
    if report.get("message"):
        lines.append(str(report["message"])[:300])
    stale = False
    for row in report.get("ranked", [])[:top]:
        relative = Path(row["path"])
        source = (root / relative).resolve()
        score = row.get("score")
        if relative.is_absolute() or not source.is_relative_to(root) or not source.is_file() or isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1 or not isinstance(row.get("line"), int) or row["line"] < 1:
            return {}
        stat = source.stat()
        if stat.st_size != row.get("size") or stat.st_mtime_ns != row.get("mtime_ns"):
            stale = True
            continue
        lines.append(f"{score:.3f} {json.dumps(source.as_posix(), ensure_ascii=False)}:{row['line']}")
    if stale:
        lines.append("Some ranked files changed after evaluation; rerun exploration for fresh priorities.")
    if report.get("shortlist_truncated") or report.get("lexical_scan_truncated"):
        lines.append("Candidate discovery was capped; broaden the search if the listed files do not answer the question.")
    lines.append("Read the listed source files first, then trace references as needed. These ranks guide reading; they do not establish implementation facts.")
    result = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(lines)}}
    receipt = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "invocation": "supplied_test_event" if event.get("_test_event") else "hook_event", "tool_name": event["tool_name"], "result_file": str(path)}
    path.with_suffix(".hook.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    try:
        event = json.load(sys.stdin)
        output = feedback(event) if isinstance(event, dict) else {}
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        output = {}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
