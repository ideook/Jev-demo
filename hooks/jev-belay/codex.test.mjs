import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { evidenceFromCodex, projectEvidence } from "./codex-evidence.mjs";

const root = mkdtempSync(join(tmpdir(), "belay-codex-test-"));
process.env.JEV_BELAY_HOME = root;
const core = await import("./upstream/belay.mjs");
const { handle, credential, DEFAULTS } = await import("./codex.mjs");
const start = (id = randomUUID(), task = "Add retry handling") => [
  { type: "event_msg", payload: { type: "task_started", turn_id: id } },
  { type: "event_msg", payload: { type: "user_message", message: task } },
];
const tool = (name, args, output, id = randomUUID(), custom = false) => [
  { type: "response_item", payload: { type: custom ? "custom_tool_call" : "function_call", call_id: id, name,
    ...(custom ? { input: args } : { arguments: JSON.stringify(args) }) } },
  { type: "response_item", payload: { type: custom ? "custom_tool_call_output" : "function_call_output", call_id: id,
    output: typeof output === "string" ? output : JSON.stringify(output) } },
];
const patch = () => tool("functions.apply_patch", "*** Begin Patch", "Success. Updated the following files:\nM helper.js", undefined, true);
const check = (code = 0) => tool("functions.exec_command", { cmd: "npm test" }, { output: code ? "Tests: 1 failed, 1 total" : "Tests: 1 passed, 1 total", exit_code: code });
const evidence = (records) => evidenceFromCodex(records, core);
const config = { ...DEFAULTS, env_file: "/missing", log: true, shadow: true, allow_prompt_export: true };
const answers = { claims_done: { noul: 0.95 }, claims_verified: { noul: 0.9 }, verification_applies: { noul: 0.9 },
  outcome: { choice: "complete", confidence: 0.9 } };
const fake = async () => new Response(JSON.stringify({ model: "fixture-only", answers }), { status: 200 });
async function run(records, extra = {}) {
  const path = join(root, randomUUID() + ".jsonl");
  writeFileSync(path, records.map((r) => JSON.stringify(r)).join("\n"));
  return handle({ hook_event_name: "Stop", session_id: randomUUID(), transcript_path: path,
    last_assistant_message: "Done. All tests pass.", ...extra }, { env: { TYPESAFE_API_KEY: "fixture-secret" }, config, fetchImpl: fake });
}

test("direct edits and fresh passing checks preserve order", () => {
  const e = evidence([...start(), ...patch(), ...check()]);
  assert.equal(e.mutations, 1); assert.equal(core.needsDoneCheck(e), false);
});
test("a check before the last edit remains stale", () => {
  const e = evidence([...start(), ...check(), ...patch()]);
  assert.equal(core.needsDoneCheck(e), true);
});
test("a process exiting nonzero cannot pass", () => {
  const e = evidence([...start(), ...patch(), ...check(1)]);
  assert.equal(e.checks[0].passed, false);
});
test("a named runner without exit status or summary is unknown", () => {
  const e = evidence([...start(), ...patch(), ...tool("exec_command", { cmd: "npm test" }, "started")]);
  assert.equal(e.checks.length, 0);
});
test("running sessions wait for a completed poll", () => {
  const records = [...start(), ...patch(), ...tool("exec_command", { cmd: "npm test" }, { output: "running", session_id: 123 })];
  assert.equal(evidence(records).checks.length, 0);
  const e = evidence([...records, ...tool("write_stdin", { session_id: 123 }, { output: "", exit_code: 0 })]);
  assert.equal(e.checks[0].passed, true);
});
test("code-mode shell result objects count", () => {
  const program = 'const r = await tools.exec_command({cmd: "npm test"}); text(r);';
  const e = evidence([...start(), ...patch(), ...tool("functions.exec", program, JSON.stringify({ output: "", exit_code: 0 }), undefined, true)]);
  assert.equal(e.checks[0].passed, true);
});
test("code-mode result wrappers preserve nonzero exit codes", () => {
  const program = 'const r = await tools.exec_command({cmd: "npm test"}); text({i:0,value:r});';
  const e = evidence([...start(), ...patch(), ...tool("exec", program, JSON.stringify({ i: 0, value: { output: "", exit_code: 1 } }), undefined, true)]);
  assert.equal(e.checks[0].passed, false);
});
test("code-mode patch/check batches conservatively make checks stale", () => {
  const program = 'await tools.apply_patch("patch"); text(await tools.exec_command({cmd: "npm test"}));';
  const e = evidence([...start(), ...tool("exec", program, JSON.stringify({ output: "Tests: 1 passed, 1 total", exit_code: 0 }), undefined, true)]);
  assert.equal(e.mutations, 1); assert.equal(core.needsDoneCheck(e), true);
});
test("computed code-mode commands are never executed or inferred", () => {
  const program = 'text(await tools.exec_command({cmd: `npm ${process.env.SECRET}`}));';
  const e = evidence([...start(), ...patch(), ...tool("exec", program, JSON.stringify({ output: "", exit_code: 0 }), undefined, true)]);
  assert.equal(e.checks.length, 0);
});
test("failed patches do not count", () => {
  const e = evidence([...start(), ...tool("apply_patch", {}, "apply_patch verification failed")]);
  assert.equal(e.mutations, 0);
});
test("later turns reset previous verification", () => {
  const e = evidence([...start(), ...check(), ...start(), ...patch()]);
  assert.equal(e.checks.length, 0); assert.equal(e.mutations, 1);
});
test("a repeated turn context does not reset evidence", () => {
  const e = evidence([...start("turn-1"), ...patch(), { type: "turn_context", payload: { turn_id: "turn-1" } }]);
  assert.equal(e.mutations, 1);
});
test("steering extends the task without losing edits", () => {
  const e = evidence([...start(), ...patch(), { type: "event_msg", payload: { type: "user_message", message: "Use three retries" } }]);
  assert.equal(e.mutations, 1); assert.match(e.task, /three retries/);
});
test("a tail without the task is rejected", () => { assert.throws(() => evidence(patch()), /no complete/); });
test("Desktop prompts in response items establish the task", () => {
  const records = start("desktop-turn").slice(0, 1);
  records.push({ type: "turn_context", payload: { turn_id: "desktop-turn" } });
  records.push({ type: "response_item", payload: { type: "message", role: "user",
    content: [{ type: "input_text", text: '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>' }] } });
  records.push({ type: "response_item", payload: { type: "message", role: "user",
    content: [{ type: "input_text", text: "활성화 되었는지 확인해 줘." }] } });
  const e = evidence([...records, ...patch()]);
  assert.equal(e.task, "활성화 되었는지 확인해 줘."); assert.equal(e.mutations, 1);
});
test("mirrored event and response prompts are not duplicated", () => {
  const records = start("mirrored-turn");
  records.push({ type: "response_item", payload: { type: "message", role: "user",
    content: [{ type: "input_text", text: "Add retry handling" }] } });
  assert.equal(evidence(records).task, "Add retry handling");
});
test("injected user instructions do not become exported tasks", () => {
  const records = start("instructions-turn").slice(0, 1);
  for (const text of ["# AGENTS.md instructions\nprivate instructions", "<environment_context>private paths</environment_context>", "<INSTRUCTIONS>private instructions</INSTRUCTIONS>", "Fix the helper"])
    records.push({ type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_text", text }] } });
  assert.equal(evidence(records).task, "Fix the helper");
});
test("projection contains summaries rather than file contents", () => {
  const e = evidence([...start(), ...patch(), ...check()]);
  const projected = projectEvidence(e);
  assert.doesNotMatch(projected, /helper\.js/); assert.match(projected, /All checks passed/);
});
test("screenshot threshold is 0.75, so 0.74 does not block", () => {
  const e = evidence([...start(), ...patch()]);
  assert.equal(core.decide({ ...answers, claims_done: { noul: 0.74 } }, e, { threshold: DEFAULTS.threshold }).block, false);
  assert.equal(core.decide({ ...answers, claims_done: { noul: 0.75 } }, e, { threshold: DEFAULTS.threshold }).block, true);
});
test("export caps include the ellipsis characters", () => {
  const state = core.buildState("a".repeat(5000), "b".repeat(5000), { mutations: 1, checks: [] });
  assert.equal(state.task.length, 1500); assert.equal(state.final_message.length, 2000);
});
test("an unverified completion logs shadow and exits zero", async () => {
  const result = await run([...start(), ...patch()]);
  assert.equal(result.exit, 0); assert.match(result.systemMessage, /would have blocked/);
  const log = JSON.parse(readFileSync(join(root, "decisions.jsonl"), "utf8").trim().split("\n").at(-1));
  assert.equal(log.verdict, "shadow"); assert.equal(log.model, "fixture-only");
  assert.doesNotMatch(JSON.stringify(log), /fixture-secret/);
});
test("fresh verification skips the API and logs a free pass", async () => {
  const result = await run([...start(), ...patch(), ...check()]);
  assert.equal(result.exit, 0); assert.equal(result.systemMessage, undefined);
  const log = JSON.parse(readFileSync(join(root, "decisions.jsonl"), "utf8").trim().split("\n").at(-1));
  assert.equal(log.verdict, "passed");
});
test("bad input and recursive events fail open", async () => {
  assert.equal((await handle(null)).exit, 0);
  assert.equal((await run([...start(), ...patch()], { stop_hook_active: true })).exit, 0);
  assert.equal((await handle({ hook_event_name: "Stop", transcript_path: "/missing" }, { env: {}, config })).exit, 0);
});
test("external evaluation requires explicit consent", async () => {
  const result = await handle({ hook_event_name: "Stop" }, { env: { TYPESAFE_API_KEY: "fixture" }, config: DEFAULTS,
    fetchImpl: () => { throw new Error("must never call"); } });
  assert.equal(result.why, "external evaluation disabled");
});
test("GUI fallback parses the existing env file without executing it", () => {
  const path = join(root, "existing.env");
  writeFileSync(path, "export TYPESAFE_API_KEY='fixture-secret'\n");
  assert.deepEqual(credential({}, path), { key: "fixture-secret", source: "existing private environment file" });
  assert.equal(credential({ TYPESAFE_API_KEY: "inherited" }, path).key, "inherited");
});
test.after(() => rmSync(root, { recursive: true, force: true }));
