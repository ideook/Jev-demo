---
name: north-star
description: Detects and corrects goal drift in long Claude sessions. Use at the start of work to anchor intent, periodically mid-session to audit alignment, or whenever a response feels subtly off-target. Especially valuable past ~30 turns, after compaction, or when picking up a session from yesterday.
risk: safe
---

# North Star — כוכב הצפון

> A skill for keeping Claude pointed at the goal you actually came with — not the goal the conversation slowly mutated into.

## The problem this skill solves

Long Claude sessions drift. This is not a bug in any single response — it's a property of how transformer-based LLMs handle long contexts. Six independent forces push the model off-target:

1. **Recency bias.** The most recent user turn dominates attention weight. After 40 turns, the original instruction has the same weight as a passing comment from three turns ago.
2. **Sycophancy gradient.** Claude is RLHF'd to agree with and extend the user's most recent framing. If you spent 10 turns exploring a tangent, the model now treats the tangent as the topic.
3. **Lost-in-the-middle.** Information placed in the middle of a long context is attended to less than information at the start or end. The original goal, stated at turn 1, is now in the middle.
4. **Compaction loss.** When Claude Code auto-compacts, summaries paraphrase. Specific constraints ("never use Bash", "must work offline") soften into "be careful with tools".
5. **Scope-expansion reflex.** Claude is trained to be helpful. When it sees an adjacent issue, the default is to fix it. Three "while I'm here" fixes in a row = a different project.
6. **Resolution drift.** A goal stated at high abstraction ("build a chat app") gets refined into low-level decisions ("use SSE not websockets") that, two refinements later, no longer obviously serve the original goal.

This skill doesn't prevent drift — drift is structural. It detects drift, names it, and pulls the conversation back.

## When to invoke

**Always, at the start of:**
- A new session continuing yesterday's work
- A session resumed after `/compact` or `/clear`
- Any task expected to run >20 turns

**On demand, when you notice:**
- "Wait, why are we doing this?"
- A response that's technically correct but feels orthogonal to the ask
- Three "while I'm here" suggestions in a row
- The model arguing for a solution to a problem you didn't mention
- You re-explaining the original goal for the second time

**Automatically, every N turns** if you've wired this skill into a hook (see `references/automation.md`).

## The three modes

This skill operates in three modes. Pick one based on where you are.

### 1. ANCHOR mode — start of session

Establish the north star before work begins. Outputs an anchor block that gets written to `.north-star.md` (or appended to `CLAUDE.md`) and re-injected every turn via the harness or by manual reference.

**Trigger:** new session, no `.north-star.md` present.

**Output:**
```
<north-star>
GOAL: [one sentence — what changes in the world when this is done]
USER: [who benefits — be specific, not "users"]
DONE-WHEN: [observable signal, not an opinion]
NON-GOALS: [3 specific things this is NOT — to defuse scope creep]
HARD-CONSTRAINTS: [anything non-negotiable, with the reason]
</north-star>
```

The XML wrapping is deliberate. Claude treats `<tags>` as elevated-priority structure. Re-quoting the block in any later response immediately restores attention weight.

### 2. CHECK mode — mid-session audit

The default mode. Read the current `.north-star.md`, audit the last few turns, surface drift.

**Trigger:** user invokes the skill, or every N turns automatically.

**Procedure:**
1. Read the north star block. If missing → switch to ANCHOR mode.
2. List the last 3–5 substantive decisions (not every message — actual choices that changed direction).
3. Score each one against the GOAL and NON-GOALS. Use one of three labels:
   - ✅ **On-target** — directly serves the goal.
   - ⚠️ **Adjacent** — useful but not what was asked. Common signal: the user didn't ask for this, you offered it.
   - ❌ **Drift** — solves a different problem, or violates a NON-GOAL.
4. If anything is ⚠️ or ❌, propose the smallest correction.
5. End the response by re-quoting the `<north-star>` block.

### 3. RECOVERY mode — pull back after detected drift

When the user signals drift directly ("we lost the plot", "this isn't what I asked for", or a frustrated "no, I want X").

**Procedure:**
1. **Stop adding.** Do not propose another solution yet.
2. **Acknowledge the drift in one sentence.** Name the specific point where direction changed. Don't generalize, don't apologize at length.
3. **Restate the north star verbatim** from `.north-star.md`.
4. **Ask one targeted question** to recover: "Should we revert the last 3 changes, keep them and pivot, or re-anchor on a different goal?"
5. **Wait.** Do not act until the user picks.

## Anti-patterns to flag explicitly

These are drift signatures Claude produces. The skill should call them by name when detected:

| Signature | What it looks like |
|---|---|
| **Helpful expansion** | "While I'm here, I also noticed…" / "I went ahead and also…" |
| **Best-practice substitution** | User asked X; response delivers a "better" Y because Y is more idiomatic |
| **Defensive over-engineering** | Adding error handling, validation, or abstractions for cases the user didn't mention |
| **Recency hijack** | Treating the last 3 turns as the spec, ignoring the goal stated 30 turns ago |
| **Demo drift** | Building the demo / test / example instead of the real thing |
| **Tool-shaped response** | Doing what's easy with available tools instead of what was asked |
| **Premature abstraction** | Generalizing a one-off into a framework before the one-off works |
| **Resolution slip** | Drilling into low-level details before confirming the high-level decision |

When the skill detects one of these, it names it. "This is helpful expansion — you asked for X, I added Y unprompted."

## Output shape (CHECK mode)

Always render exactly this structure. Brevity matters — a long check report is itself drift.

```
## 🧭 North Star Check

<north-star>
GOAL: …
DONE-WHEN: …
</north-star>

### Last decisions
| # | Decision | Verdict | Note |
|---|---|---|---|
| 1 | … | ✅ | on-goal |
| 2 | … | ⚠️ | helpful expansion: <name> |
| 3 | … | ❌ | drift: <name> |

### Realignment
[one concrete next action — not a paragraph]

### Re-anchor
> GOAL: [verbatim from north-star block]
```

## Integration with the rest of Claude Code

- **CLAUDE.md.** If a project has a `CLAUDE.md`, look for a `## North Star` section first; only fall back to `.north-star.md` if absent.
- **Memory.** If using auto-memory, the north star is a `project` memory, not feedback. Title it `project_north_star.md`.
- **Hooks.** A `UserPromptSubmit` hook can re-inject the `<north-star>` block before every prompt — see `references/automation.md`.
- **Sub-agents.** When dispatching a sub-agent, pass the north star block in the sub-agent's prompt verbatim. Sub-agents have no conversation history; they need the goal stated explicitly.
- **Compaction.** Before `/compact`, write the north star block into `.north-star.md` so it survives compaction even if the summary paraphrases it.

## Why this works (mechanism, not magic)

Three reasons this skill actually pulls Claude back:

1. **Re-injection beats retention.** You can't make Claude "remember" — but re-quoting the goal puts it back at the end of context, where attention is highest.
2. **Naming the failure mode triggers correction.** Claude has been trained on enough examples of "scope creep" and "over-engineering" that labeling the behavior makes the model recognize and stop it. The taxonomy in this skill is the lever.
3. **Forced structure prevents fluent drift.** When Claude must produce a table with ✅/⚠️/❌ verdicts, it can't paper over a misalignment with confident prose. The structure forces a binary judgment.

## Reference material

- [`references/why-llms-drift.md`](references/why-llms-drift.md) — the mechanics in more depth
- [`references/drift-taxonomy.md`](references/drift-taxonomy.md) — full catalog with examples
- [`references/anchoring-techniques.md`](references/anchoring-techniques.md) — XML wrapping, hooks, sub-agent passing
- [`references/automation.md`](references/automation.md) — wiring this into a `UserPromptSubmit` hook
- [`examples/example-anchor.md`](examples/example-anchor.md) — a real `.north-star.md` from a shipped project
- [`examples/example-check.md`](examples/example-check.md) — a CHECK mode response on a session that drifted

## Credits

Built by [Dolev Hayut](https://www.linkedin.com/in/dolevhayut) — Bulldog Media Solutions. Born from the recurring frustration of explaining the same project goal to Claude for the third time in one session.
