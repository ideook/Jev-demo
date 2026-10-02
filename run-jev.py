"""Run the installed Jev Ultrafast loop and keep an inspectable local trace."""
import argparse
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from jev_ultrafast import Agent

parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument("--goal", required=True)
parser.add_argument("--max-steps", type=int, default=20)
parser.add_argument("--keep-open", action="store_true")
args = parser.parse_args()
run_dir = Path(__file__).parent / ".runtime" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
run_dir.mkdir(parents=True, exist_ok=True)
agent = Agent(args.url, args.goal, screenshots=False)
error = None
try:
    for step in range(args.max_steps):
        state = agent.command("tick")
        decision = state["decisions"][-1]
        action = state["history"][-1]["action"] if decision["operation"] not in {"DONE", "BLOCKED"} and state["history"] else ""
        print(json.dumps({"step": step + 1, "model": decision["request"]["model"], "operation": decision["operation"], "target": decision["target"], "action": action, "confidence": decision["confidence"], "status": state["status"]}, ensure_ascii=False), flush=True)
        if state["status"] in {"done", "blocked"}:
            break
except Exception as exc:
    error = f"{type(exc).__name__}: {exc}"
    print(error, flush=True)
finally:
    state = agent.snapshot()
    (run_dir / "trace.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "page.txt").write_text(state["page"]["text"], encoding="utf-8")
    try:
        page = agent.browser.observe(screenshot=True)
        (run_dir / "final.jpg").write_bytes(base64.b64decode(page["screenshot"]))
    except Exception:
        pass
    print(json.dumps({"status": state["status"], "error": error, "url": state["page"]["url"], "title": state["page"]["title"], "trace_directory": str(run_dir)}, ensure_ascii=False), flush=True)
    print(state["page"]["text"][:18000], flush=True)
    if not args.keep_open:
        agent.close()
