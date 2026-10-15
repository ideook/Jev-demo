#!/usr/bin/env node
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { projectEvidence, readCodexEvidence } from "./codex-evidence.mjs";

const DIRECTORY = dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.JEV_BELAY_HOME || join(homedir(), ".codex", "belay");
process.env.JEV_BELAY_HOME = ROOT;
const core = await import("./upstream/belay.mjs");
export const DEFAULTS = { threshold: 0.75, log: true, shadow: true, model: "jev-1.14.0", allow_prompt_export: false,
  env_file: join(homedir(), ".config", "typesafe", "env") };

export function settings() {
  try { return { ...DEFAULTS, ...JSON.parse(readFileSync(join(ROOT, "config.json"), "utf8")) }; }
  catch { return { ...DEFAULTS }; }
}

export function credential(env, path) {
  for (const name of ["TYPESAFE_API_KEY", "JEV_API_KEY"]) {
    if (env[name]?.trim()) return { key: env[name].trim(), source: name };
  }
  try {
    for (const line of readFileSync(path, "utf8").split("\n")) {
      const match = /^\s*(?:export\s+)?(TYPESAFE_API_KEY|JEV_API_KEY)\s*=\s*(.*?)\s*$/.exec(line);
      if (!match) continue;
      let value = match[2];
      if (["'", '"'].includes(value[0]) && value.at(-1) === value[0]) value = value.slice(1, -1);
      else value = value.replace(/\s+#.*$/, "").trim();
      if (value) return { key: value, source: "existing private environment file" };
    }
  } catch { /* A GUI launch need not have inherited the login shell. */ }
  return { key: undefined, source: "missing" };
}

function saveStatus(result, payload, config, evidence) {
  try {
    mkdirSync(ROOT, { recursive: true, mode: 0o700 });
    writeFileSync(join(ROOT, "last-status.json"), JSON.stringify({ at: new Date().toISOString(),
      session: payload?.session_id, why: result.why,
      ...(evidence ? { mutations: evidence.mutations, fresh_checks: core.freshChecks(evidence).length } : {}),
      threshold: config.threshold, shadow: config.shadow, log: config.log }) + "\n", { mode: 0o600 });
  } catch { /* Status reporting must not break a turn. */ }
  return result;
}

export async function handle(payload, { env = process.env, config = settings(), fetchImpl = fetch } = {}) {
  const done = (result, evidence) => saveStatus(result, payload, config, evidence);
  if (payload?.hook_event_name !== "Stop" || payload.stop_hook_active) return done({ exit: 0, why: "inactive event" });
  if (config.allow_prompt_export !== true) return done({ exit: 0, why: "external evaluation disabled" });
  const auth = credential(env, config.env_file);
  if (!auth.key && !env.JEV_BELAY_TEST_BASE_URL) return done({ exit: 0, why: "no key" });
  let directory;
  try {
    const evidence = readCodexEvidence(payload.transcript_path, core);
    if (typeof payload.last_assistant_message === "string") evidence.finalMessage = payload.last_assistant_message;
    directory = mkdtempSync(join(tmpdir(), "jev-belay-codex-"));
    const transcript = join(directory, "projection.jsonl");
    writeFileSync(transcript, projectEvidence(evidence), { mode: 0o600 });
    const hookEnv = { TYPESAFE_API_KEY: auth.key, JEV_MODEL: config.model,
      JEV_BELAY_THRESHOLD: String(config.threshold), JEV_BELAY_LOG: config.log ? "1" : "0",
      JEV_BELAY_SHADOW: config.shadow ? "1" : "0", JEV_BELAY_CHECK: config.check,
      JEV_BELAY_TIMEOUT_MS: "12000" };
    // An endpoint override is restricted to loopback fixtures, never an ambient gateway.
    if (/^http:\/\/127\.0\.0\.1:\d+$/.test(env.JEV_BELAY_TEST_BASE_URL || "")) hookEnv.JEV_BASE_URL = env.JEV_BELAY_TEST_BASE_URL;
    const result = await core.runHook({ env: hookEnv, stdin: JSON.stringify({ ...payload,
      prompt_id: evidence.promptId, transcript_path: transcript, last_assistant_message: evidence.finalMessage }), fetchImpl });
    return done(result, evidence);
  } catch { return done({ exit: 0, why: "unreadable or unsupported Codex transcript" }); }
  finally { if (directory) rmSync(directory, { recursive: true, force: true }); }
}

async function doctor(live) {
  const config = settings();
  const auth = credential(process.env, config.env_file);
  let registered = false;
  try {
    const hooks = JSON.parse(readFileSync(join(homedir(), ".codex", "hooks.json"), "utf8"));
    registered = hooks.hooks?.Stop?.some((group) => group.hooks?.some((h) => h.command?.includes(join(DIRECTORY, "codex.mjs")))) === true;
  } catch { /* Report false below. */ }
  const report = { version: "0.2.0", upstream_commit: "c59f030032baedb3a3e5acefd3ead19d9dcde84c", host: "Codex",
    node: process.versions.node, key_present: Boolean(auth.key), key_source: auth.source,
    registered, threshold: config.threshold, decision_log: config.log, shadow: config.shadow,
    model: config.model, allow_prompt_export: config.allow_prompt_export, log_path: join(ROOT, "decisions.jsonl") };
  if (live && auth.key) {
    const answer = await core.ask({ task: "Add retry handling to a fetch helper.",
      final_message: "Done. The helper is updated and all tests pass.", run: { file_changes: 1, checks_run: [] } },
      core.QUESTIONS, { env: { TYPESAFE_API_KEY: auth.key, JEV_MODEL: config.model }, timeoutMs: 12000 });
    report.live = { model: answer.model, latency_ms: answer.elapsedMs,
      answers_present: Object.keys(answer.answers || {}).length, usage: answer.usage || {} };
  }
  console.log(JSON.stringify(report, null, 2));
  if (!auth.key || !registered) process.exitCode = 1;
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] === "doctor") return doctor(args.includes("--live"));
  if (["stats", "last", "watch", "--replay"].includes(args[0])) {
    const { run } = await import("./upstream/tui.mjs"); return run(args);
  }
  let result;
  try { result = await handle(JSON.parse(readFileSync(0, "utf8"))); }
  catch { result = { exit: 0, why: "invalid hook input" }; }
  if (result.systemMessage) process.stdout.write(JSON.stringify({ systemMessage: result.systemMessage }) + "\n");
  if (result.exit === 2) { process.stderr.write(result.reason + "\n"); process.exitCode = 2; }
  if (process.env.JEV_BELAY_DEBUG === "1") process.stderr.write("jev-belay: " + result.why + "\n");
}

if (core.isEntryPoint(import.meta.url)) main().catch(() => { process.exitCode = 1; });
