// Synthetic rollouts isolate completion-evidence gaps without tools or API calls.
import { evidenceFromCodex } from "../../hooks/jev-belay/codex-evidence.mjs";
import * as core from "../../hooks/jev-belay/upstream/belay.mjs";

let sequence = 0;
const start = () => [
  { type: "event_msg", payload: { type: "task_started", turn_id: "synthetic-turn" } },
  { type: "event_msg", payload: { type: "user_message", message: "Synthetic diagnostic: update helper" } },
];
const tool = (name, args, output) => {
  const id = String(++sequence);
  return [
    { type: "response_item", payload: { type: "function_call", call_id: id, name, arguments: JSON.stringify(args) } },
    { type: "response_item", payload: { type: "function_call_output", call_id: id, output: JSON.stringify(output) } },
  ];
};
const edit = () => tool("apply_patch", {}, "Success. Updated helper.py");
const cases = [
  ["npm_test_control", [...start(), ...edit(), ...tool("exec_command", { cmd: "npm test" },
    { output: "Tests: 5 passed, 5 total", exit_code: 0 })], { mutations: 1, fresh_checks: 1 }],
  ["unittest_success", [...start(), ...edit(), ...tool("exec_command", { cmd: "python -m unittest discover -s tests -v" },
    { output: "Ran 5 tests in 0.01s\n\nOK", exit_code: 0 })], { mutations: 1, fresh_checks: 1 }],
  ["read_old_pytest_log", [...start(), ...edit(), ...tool("exec_command", { cmd: "Get-Content prior-test-log.txt" },
    { output: "==================== 5 passed in 0.42s ====================", exit_code: 0 })], { mutations: 1, fresh_checks: 0 }],
  ["powershell_write", [...start(), ...tool("exec_command", { cmd: "Set-Content -LiteralPath helper.py -Value 'new content'" },
    { output: "", exit_code: 0 })], { mutations: 1, fresh_checks: 0 }],
];

let failures = 0;
for (const [label, records, expected] of cases) {
  const evidence = evidenceFromCodex(records, core);
  const actual = { mutations: evidence.mutations, fresh_checks: core.freshChecks(evidence).length };
  const matches = actual.mutations === expected.mutations && actual.fresh_checks === expected.fresh_checks;
  if (!matches) failures++;
  console.log(JSON.stringify({ label, expected, actual, matches_expected: matches,
    would_evaluate: core.needsDoneCheck(evidence) }));
}
process.exitCode = failures ? 1 : 0;
