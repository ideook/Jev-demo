// Codex rollouts stay local. Only completed calls contribute evidence.
import { closeSync, openSync, readSync, statSync } from "node:fs";
import { createHash } from "node:crypto";

const MAX_BYTES = 16 * 1024 * 1024;
const textOf = (value) => typeof value === "string" ? value : Array.isArray(value)
  ? value.map((part) => part?.text || "").join("\n") : "";

function parse(value) {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value); } catch { return undefined; }
}

function toolName(name) { return String(name || "").split(/[./]/).at(-1); }

// Read string literals as data, never evaluate the JavaScript in a code-mode call.
function literal(source, start) {
  const quote = source[start];
  if (!['"', "'", "`"].includes(quote)) return undefined;
  let value = "";
  for (let i = start + 1; i < source.length; i++) {
    const char = source[i];
    if (char === quote) return value;
    if (quote === "`" && char === "$" && source[i + 1] === "{") return undefined;
    if (char !== "\\") { value += char; continue; }
    const escaped = source[++i];
    const controls = { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v" };
    if (escaped === "u" || escaped === "x") {
      const length = escaped === "u" ? 4 : 2;
      const digits = source.slice(i + 1, i + 1 + length);
      if (!new RegExp(`^[0-9a-f]{${length}}$`, "i").test(digits)) return undefined;
      value += String.fromCharCode(parseInt(digits, 16)); i += length;
    } else value += controls[escaped] ?? escaped ?? "";
  }
  return undefined;
}

function commandsOf(call) {
  const name = toolName(call.name);
  const args = parse(call.arguments ?? call.input);
  if (["exec_command", "shell", "shell_command", "Bash"].includes(name)) {
    const command = args?.cmd ?? args?.command;
    if (typeof command === "string") return [command];
    if (Array.isArray(command)) {
      const index = command.findIndex((part) => part === "-c" || part === "-lc");
      return index >= 0 ? [command[index + 1] || ""] : [];
    }
  }
  if (name !== "exec") return [];
  const source = String(call.input ?? call.arguments ?? "");
  const commands = [];
  for (const match of source.matchAll(/tools\.exec_command\(\s*\{[\s\S]*?\b(?:cmd|command)["']?\s*:\s*/g)) {
    const value = literal(source, match.index + match[0].length);
    if (value !== undefined) commands.push(value);
  }
  return commands;
}

function outputsOf(output) {
  const parsed = parse(output);
  if (Array.isArray(parsed)) return parsed.flatMap(outputsOf);
  if (parsed && typeof parsed === "object") {
    if (parsed.value !== undefined) return outputsOf(parsed.value);
    if (Array.isArray(parsed.content)) return parsed.content.flatMap((part) => outputsOf(part.text ?? ""));
    if (typeof parsed.output === "string") return [{ text: parsed.output, exit: parsed.exit_code,
      session: parsed.session_id, failed: parsed.isError === true || parsed.success === false }];
    if (parsed.result !== undefined) return outputsOf(parsed.result);
    return [{ text: textOf(parsed.text), failed: parsed.isError === true || parsed.success === false }];
  }
  const text = textOf(output);
  // Code mode prints one JSON item per line, sometimes beside plain-text items.
  const lines = text.split("\n");
  if (lines.some((line) => line.trim().startsWith("{"))) {
    const items = lines.map((line) => parse(line)).filter((item) => item && typeof item === "object");
    const structured = items.flatMap(outputsOf);
    if (structured.some((item) => item.exit !== undefined || item.session !== undefined)) return structured;
  }
  const exit = /(?:Process exited with code|exit code|Exit code:)\s*(-?\d+)/i.exec(text);
  const session = /(?:session ID|session_id)\s*:?\s*(\d+)/i.exec(text);
  return [{ text, exit: exit ? Number(exit[1]) : undefined, session: session?.[1],
    failed: /(?:apply_patch verification failed|Failed to apply patch|Error parsing function call)/i.test(text) }];
}

function mutationIntent(call, commands) {
  const name = toolName(call.name);
  if (["apply_patch", "Write", "Edit", "MultiEdit", "NotebookEdit"].includes(name)) return true;
  if (name === "exec" && /\btools\.apply_patch\s*\(/.test(call.input || "")) return true;
  return commands.some((cmd) => /(?:\b(?:write_text|write_bytes|writeFileSync|appendFileSync|copyfile|copy2)\s*\(|\b(?:sed\s+-i|perl\s+-pi|tee|cp|mv|rm|touch|install)\s|(?:^|\n)\s*(?:cat|printf|echo)\b[^\n]*>{1,2})/.test(cmd));
}

export function evidenceFromCodex(records, { classifyToolResult, checkSummary, redact }) {
  let task = "", promptId, finalMessage = "", boundary = false;
  let mutations = 0, checks = [], checksBeforeMutation = 0;
  const pending = new Map(), sessions = new Map();
  const prompts = new Set();
  const addPrompt = (message) => {
    const text = textOf(message).trim();
    // Desktop records prompts beside injected instructions and Page context.
    if (!text || /^(?:# AGENTS\.md instructions|<environment_context>|<external_codex_apps_open_page>|<turn_aborted>|<permissions instructions>|<INSTRUCTIONS>)/.test(text)) return;
    if (prompts.has(text)) return;
    prompts.add(text);
    task = task ? `${task}\n${text}` : text;
  };
  const reset = (id, stamp) => {
    if (boundary && id && id === promptId) return;
    boundary = true; task = ""; finalMessage = ""; mutations = 0; checks = []; checksBeforeMutation = 0;
    pending.clear(); sessions.clear(); prompts.clear();
    promptId = id || createHash("sha256").update(String(stamp)).digest("hex");
  };
  for (const record of records) {
    const p = record?.payload || {};
    if (record.type === "event_msg" && p.type === "task_started") {
      reset(p.turn_id, record.timestamp); continue;
    }
    if (record.type === "turn_context" && p.turn_id) {
      reset(p.turn_id, record.timestamp); continue;
    }
    if (record.type === "event_msg" && p.type === "user_message") {
      if (!boundary) reset(undefined, record.timestamp);
      addPrompt(p.message);
      continue;
    }
    if (record.type === "compacted") {
      // A compacted history cannot establish the order of earlier edits and checks.
      pending.clear(); sessions.clear(); mutations = 0; checks = []; checksBeforeMutation = 0;
      continue;
    }
    if (record.type !== "response_item" || !boundary) continue;
    if (p.type === "message" && p.role === "user") {
      addPrompt(p.content);
      continue;
    }
    if (p.type === "message" && p.role === "assistant" && p.phase !== "commentary" && p.channel !== "analysis" && p.channel !== "commentary") {
      const text = textOf(p.content).trim();
      if (text) finalMessage = text;
    }
    if (["function_call", "custom_tool_call"].includes(p.type)) {
      pending.set(p.call_id, p); continue;
    }
    if (!["function_call_output", "custom_tool_call_output"].includes(p.type)) continue;
    let call = pending.get(p.call_id);
    if (!call) continue;
    pending.delete(p.call_id);
    const name = toolName(call.name);
    if (name === "write_stdin") {
      const args = parse(call.arguments ?? call.input);
      call = sessions.get(String(args?.session_id)) || call;
    }
    const commands = commandsOf(call);
    const outputs = outputsOf(p.output);
    const changing = mutationIntent(call, commands);
    const completed = outputs.filter((item) => item.session === undefined || item.exit !== undefined);
    for (const item of outputs) {
      if (item.session !== undefined && item.exit === undefined) sessions.set(String(item.session), call);
      if (item.session !== undefined && item.exit !== undefined) sessions.delete(String(item.session));
    }
    for (let i = 0; i < completed.length; i++) {
      const item = completed[i];
      const failed = item.failed || (typeof item.exit === "number" && item.exit !== 0);
      // A named runner counts only with an observed successful process exit. Summary
      // belt 2 can independently establish the outcome when code mode prints text only.
      const command = commands.length === outputs.length ? commands[i] : commands.length === 1 ? commands[0] : "";
      const summary = checkSummary(item.text);
      const outcome = command && typeof item.exit === "number"
        ? classifyToolResult("Bash", { command }, failed, item.text)
        : summary ? (failed || summary === "fail" ? "check-fail" : "check-pass") : "unknown";
      if (outcome === "check-pass" || outcome === "check-fail") {
        checks.push({ call: redact(command || "check (runner summary)").slice(0, 200), passed: outcome === "check-pass" });
      }
    }
    if (changing && completed.some((item) => !item.failed && (item.exit === undefined || item.exit === 0))) {
      mutations++;
      // A combined patch/check program has uncertain internal order. Conservatively
      // make its check stale rather than treat a pre-edit run as verification.
      checksBeforeMutation = checks.length;
    }
  }
  if (!boundary || !task.trim()) throw new Error("no complete Codex turn in transcript tail");
  return { task, promptId, finalMessage, mutations, checks, checksBeforeMutation, lineCount: records.length };
}

export function readCodexEvidence(path, core) {
  const size = statSync(path).size;
  const offset = Math.max(0, size - MAX_BYTES);
  const fd = openSync(path, "r");
  let text;
  try {
    const buffer = Buffer.alloc(Math.min(size, MAX_BYTES));
    text = buffer.subarray(0, readSync(fd, buffer, 0, buffer.length, offset)).toString("utf8");
  } finally { closeSync(fd); }
  if (offset) text = text.slice(text.indexOf("\n") + 1);
  const records = text.split("\n").flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
  return evidenceFromCodex(records, core);
}

export function projectEvidence(evidence) {
  const lines = [{ type: "user", promptId: evidence.promptId,
    message: { content: [{ type: "text", text: evidence.task }] } }];
  let id = 0;
  const tool = (name, input, output, failed = false) => {
    const ref = `codex-${++id}`;
    lines.push({ type: "assistant", message: { content: [{ type: "tool_use", id: ref, name, input }] } });
    lines.push({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: ref, is_error: failed }] },
      toolUseResult: { stdout: output, stderr: "" } });
  };
  for (let i = 0; i < evidence.mutations; i++) tool("Edit", {}, "");
  for (const check of evidence.checks.slice(evidence.checksBeforeMutation)) {
    tool("Bash", { command: check.call }, check.passed ? "All checks passed!" : "Found 1 error", !check.passed);
  }
  lines.push({ type: "assistant", message: { content: [{ type: "text", text: evidence.finalMessage }] } });
  return lines.map((line) => JSON.stringify(line)).join("\n") + "\n";
}
