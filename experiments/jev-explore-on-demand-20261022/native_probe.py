"""Windows native dispatch regression: shell burst, then installed Explore dry-run.

Uses normal trusted global hooks. No handler calls or synthetic hook events.
Global hooks retain their previously authorized export settings; the rank command
uses --dry-run and sends no source excerpts to TypeSafe.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run(output):
    output = output.resolve()
    if os.name != "nt" or not output.is_relative_to(ROOT / ".runtime/experiments"):
        raise ValueError("Use Windows and a fresh output folder under .runtime/experiments")
    output.mkdir(parents=True, exist_ok=False)
    fixture = output / "한글 user's source"
    fixture.mkdir()
    source = fixture / "급여.py"
    source.write_text("def find_employee_pay():\n    return 42\n", encoding="utf-8")
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    rank = home / "skills/jev-explore/scripts/jev_rank.py"
    command = (f"& {quote(sys.executable)} -X utf8 {quote(rank)} "
               f"'Where is employee pay implemented?' --root {quote(fixture)} "
               "--keyword employee_pay --dry-run")
    spec = importlib.util.spec_from_file_location("native_client", ROOT / "experiments/north-star/unattended.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.Client(output)
    report = {"rank_source_export": False, "native_dispatch": True}
    try:
        client.request("initialize", {"clientInfo": {"name": "explore_on_demand_probe", "version": "1.0"},
                                      "capabilities": {"experimentalApi": True}})
        client.send({"method": "initialized"})
        report["hook_catalog"] = client.request("hooks/list", {"cwds": [str(fixture)]})
        catalog = [h for entry in report["hook_catalog"].get("data", []) for h in entry.get("hooks", [])]
        report["enabled_hooks_trusted"] = all(h.get("trustStatus") == "trusted" for h in catalog if h.get("enabled"))
        thread = client.request("thread/start", {"cwd": str(fixture), "approvalPolicy": "never", "sandbox": "workspace-write",
            "developerInstructions": "This is a bounded synthetic hook-dispatch test. Execute the eight requested Write-Output commands in separate parallel tool calls, then the supplied installed Explore command, then read the one discovered source file. Allow a normal shell timeout of 120 seconds for exploration. Do not edit files, settings, hooks, ledgers manually, or call APIs or handlers directly, ask questions or spawn agents. The supplied --dry-run must stay enabled. Follow source-backed North Star maintenance if supplied; do not fabricate evidence."})["thread"]
        report["thread_id"] = thread["id"]
        turn = client.request("turn/start", {"threadId": thread["id"], "input": [{"type": "text", "text":
            "Run exactly eight separate shell commands Write-Output HOOK_ON_DEMAND_1 through "
            "Write-Output HOOK_ON_DEMAND_8 concurrently. Then find the employee pay implementation "
            "in this synthetic source folder using this exact command:\n" + command +
            "\nRead the discovered source file and report its function name. Do nothing else."}],
            "sandboxPolicy": {"type": "workspaceWrite", "writableRoots": [str(output)], "networkAccess": False}})["turn"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                event = client.messages.get(timeout=2)
            except queue.Empty:
                continue
            if event is None:
                raise RuntimeError("Native server exited")
            if event.get("method") == "turn/completed":
                report["turn_status"] = event["params"]["turn"]["status"]
                break
        else:
            client.request("turn/interrupt", {"threadId": thread["id"], "turnId": turn["id"]})
            report["error"] = "180-second diagnostic deadline"
    finally:
        client.close()
    events = [json.loads(line)["message"] for line in (output / "native-events.jsonl").read_text(encoding="utf-8").splitlines()]
    commands = [e["params"]["item"] for e in events if e.get("method") == "item/completed"
                and e["params"]["item"].get("type") == "commandExecution"]
    hooks = [e["params"]["run"] for e in events if e.get("method") == "hook/completed"]
    burst = [c for c in commands if re.search(r"Write-Output HOOK_ON_DEMAND_[1-8]", c["command"])]
    ranking = [c for c in commands if "jev_rank.py" in c["command"]]
    report.update(shell_commands=len(commands), burst_commands=len(burst),
                  post_tool_hook_runs=sum(h.get("eventName") == "postToolUse" for h in hooks),
                  explore_hooks=[h for h in hooks if h.get("statusMessage") == "Jev Explore: source reading priorities"],
                  failed_hooks=[h for h in hooks if h.get("status") == "failed"],
                  failed_commands=[c for c in commands if c.get("exitCode") != 0],
                  rank_commands=[{k: c.get(k) for k in ("command", "exitCode", "aggregatedOutput")} for c in ranking])
    active = set()
    maximum = 0
    for event in events:
        item = event.get("params", {}).get("item", {})
        if item.get("type") != "commandExecution" or not re.search(r"Write-Output HOOK_ON_DEMAND_[1-8]", item.get("command", "")):
            continue
        if event.get("method") == "item/started":
            active.add(item["id"])
            maximum = max(maximum, len(active))
        elif event.get("method") == "item/completed":
            active.discard(item["id"])
    report["maximum_concurrent_burst_commands"] = maximum
    rank_ok = len(ranking) == 1 and ranking[0].get("exitCode") == 0
    if rank_ok:
        text = ranking[0].get("aggregatedOutput", "")
        rank_ok = all(value in text for value in ("0 API calls", "급여.py:1", "Read the listed source files first", "JEV_EXPLORE_RESULT="))
    report["rank_output_verified"] = rank_ok
    report["source_read_verified"] = any("Get-Content" in c["command"] and "급여.py" in c["command"]
                                         and "def find_employee_pay" in c.get("aggregatedOutput", "") for c in commands)
    report["passed"] = (report.get("turn_status") == "completed" and len(burst) == 8 and maximum >= 2
                        and not report["explore_hooks"] and not report["failed_hooks"] and not report["failed_commands"]
                        and report["enabled_hooks_trusted"] and report["post_tool_hook_runs"] >= len(commands)
                        and rank_ok and report["source_read_verified"])
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "shell_commands", "burst_commands", "maximum_concurrent_burst_commands", "rank_output_verified", "source_read_verified")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
