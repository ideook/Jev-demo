# Automation — wiring the north star into hooks

Manual invocation works. Automatic re-injection works better — the goal cannot drift past a turn that re-anchors it on every prompt.

This file shows two automation patterns:
1. **Auto re-inject** — prepend the north star to every user prompt
2. **Auto check** — run CHECK mode every N turns

Both use Claude Code's hook system. Hooks are configured in `~/.claude/settings.json` (global) or `.claude/settings.json` (per project).

## 1. Auto re-inject on every prompt

Adds the contents of `.north-star.md` as `additionalContext` on every user prompt. The goal is now at the most recent position in context for every turn.

### `UserPromptSubmit` hook config

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "test -f .north-star.md && cat .north-star.md || true"
          }
        ]
      }
    ]
  }
}
```

The `cat` output is appended to the user's prompt as additional context, invisibly. If `.north-star.md` doesn't exist, the hook outputs nothing and is a no-op.

### Cost note

The north star block is cheap (typically <500 tokens) and the same block on every turn is excellent for prompt caching — it sits at the cache prefix boundary and stays cached across the session. Net cost over a 50-turn session: a few cents.

### Variant: only re-inject after compaction

If you don't want the north star on *every* turn, you can have it injected only when a compaction event happened:

```bash
# in the hook command
if [ -f .north-star.md ] && [ -f .last-compact.flag ]; then
  cat .north-star.md
  rm .last-compact.flag
fi
```

(Requires a separate hook on the compaction event to write the flag — see your harness's hook documentation.)

## 2. Auto-CHECK every N turns

Runs the CHECK mode of the skill every N turns. Drift surfaces on its own without the user having to remember to ask.

### Pattern: turn counter via filesystem

There's no built-in "turn counter" in Claude Code, but a hook can maintain one:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "scripts/north-star-tick.sh"
          }
        ]
      }
    ]
  }
}
```

```bash
#!/usr/bin/env bash
# scripts/north-star-tick.sh
COUNTER_FILE=".north-star.counter"
INTERVAL=10  # check every 10 turns

count=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$COUNTER_FILE"

if [ $((count % INTERVAL)) -eq 0 ]; then
  cat .north-star.md 2>/dev/null
  echo ""
  echo "[north-star: turn $count — please run a CHECK pass before continuing]"
fi
```

The model sees the inserted CHECK request and runs the procedure from `SKILL.md`.

## 3. Per-project vs global

- **Per-project** (`.claude/settings.json` in the repo) — recommended. Different projects have different north stars; keep the anchor next to the project.
- **Global** (`~/.claude/settings.json`) — only useful for the *check-frequency* setting. The actual `.north-star.md` should always be per-project.

## 4. Compaction protection

Before `/compact`, the conversation is summarized. Specific constraints can be paraphrased away. Add a hook on the pre-compaction event (if your harness exposes one) to write the north star block to `.north-star.md` first:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '[north-star auto-saved before compaction]' >&2"
          }
        ]
      }
    ]
  }
}
```

(The actual `.north-star.md` should already exist; this hook is a safety net that confirms the file is present before the lossy compaction step.)

## 5. Sub-agent prompts

If you frequently dispatch sub-agents, write a wrapper in your project that prepends `.north-star.md` to every sub-agent's prompt:

```ts
function dispatchAgent(taskPrompt: string) {
  const northStar = fs.readFileSync('.north-star.md', 'utf8');
  return Task({
    prompt: `${northStar}\n\nWithin that goal:\n\n${taskPrompt}`
  });
}
```

The sub-agent now has the same anchor as the parent.

## Verifying the automation works

Quick sanity check after wiring up the hook:

1. Create `.north-star.md` with a `<north-star>` block.
2. Start a session.
3. Run any prompt.
4. Ask Claude: "Quote back the north star you're working under."
5. Claude should quote your block verbatim. If not, the hook isn't injecting — debug the hook command in isolation.
