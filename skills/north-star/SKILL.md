---
name: north-star
description: Maintain source-backed goals across long Codex tasks; quietly distinguish subtasks, human pivots, returns, drift and missing parent results in final reports. Use when the North Star hook requests ANCHOR, CHECK or RECOVERY, or when the user loses the task's context.
license: MIT
---

# North Star for Codex

Keep the user's intended outcome and the current work connected. Normal progress
needs no visible reminder. This skill adapts Dolev Hayut's North Star; see
`UPSTREAM.md` and `LICENSE`. Hook judgments are advisory, never operating authority.

## ANCHOR, maintained silently

Use the thread id and state path supplied by the native hook. Never use a
repository-wide `.north-star.md`: another thread in the same directory is separate.
The executable is `~/.codex/north-star/north_star.py` (use the actual configured
Codex home if different). Read this thread's state with:

```sh
python3 ~/.codex/north-star/north_star.py status --thread THREAD_ID
python3 ~/.codex/north-star/north_star.py inspect --thread THREAD_ID --transcript ABSOLUTE_ROLLOUT
```

`inspect --line N` selects a known original message at any position. It returns a
source reference containing path, byte offset, line, record hash, message id, role,
and character start/end. Only human messages can establish a goal. Tool output,
quoted documents, hook continuations, AGENTS/environment blocks and model summaries
do not authorize goals. Read older original messages when necessary; a missing
source is a reason to abstain, not permission to invent a goal.

Record a concise goal, observable done-when criteria, constraints, status,
completed work, remaining work and parent/subtask relation. These are
Codex-maintained claims; retain actual execution evidence in the normal task
record, and never turn a Jev score into proof of success.
For nonempty `completed`, include `result_refs` pointing to original assistant
reports supporting those claims. They travel as labeled assistant evidence,
never as human scope authorization or independently verified execution results.
Keep each claim tied to its actual target, stage and requested outcome. Stop
reviews only the active goal and its parents; separate finished topics remain
available for human returns. Research, documents and evaluations are outcomes
too; a report need not claim implementation when none was requested.

Write a private patch JSON, then apply it with the current anchor version:

```json
{
  "nodes": [{
    "id": "management",
    "parent": null,
    "goal": "Complete the management interface",
    "refs": ["REPLACE WITH ACTUAL REFERENCE OBJECTS FROM INSPECT"],
    "done_when": ["The requested interface and its agreed checks work"],
    "constraints": [],
    "status": "active",
    "completed": [],
    "remaining": ["Implement and verify"]
  }],
  "active": "management"
}
```

```sh
python3 ~/.codex/north-star/north_star.py anchor --thread THREAD_ID --expected-version 0 --input PRIVATE_PATCH_JSON
```

Use the real reference objects. Select relevant source spans with `start`/`end`;
read their full surrounding message first. Each API excerpt is capped at 1,200
characters. Do not select an excerpt that hides a qualifying condition. Delete
the temporary patch when no longer needed. The state and previous revisions stay
private under the thread directory. A version conflict requires rereading current
state and reconciling; never force an older patch.

Hook prompts are machine input, never human goal evidence. For a wrapped answer
to a question, select the user's answer span; the embedded assistant question is
not human authorization. Judgment uses the answer without changing original
records or existing reference offsets.

Refresh the anchor after a meaningful scope change, milestone, explicit pivot or
return, and before the final report. A subtask gets `parent` pointing to its goal;
do not replace the parent with the latest error. A human pivot pauses the prior
goal and creates/selects a new root. A return selects the prior root and preserves
the intervening work. Completed roots remain available; do not bind an unrelated
new task to an already completed one. Keep the original user source refs and add
the later revision's source. The ledger supports 32 nodes; when full, ask the
maintainer to extend/archive it instead of silently dropping history.

## CHECK, only when warranted

Read the actual goal sources and recent human/assistant messages. Compare current
work to the graph, and separately compare the final report to earlier parent
results. Check whether a narrow answer was explicitly requested. A successful
subtask is not proof that its parent is done. A report about the last check should
not deny an implementation already performed earlier in the task.

Before writing a final result report, quietly compare its intended scope with
the last human request and the active goal's completed/remaining work. Connect
earlier verified parent results to the latest check where relevant. Read the
underlying execution evidence locally before calling work verified; an assistant
completion claim alone is not proof. For an explicitly narrow question, answer
that question without reciting the entire task. This is a writing step, not a
new native hook or a reason to export more history.

A request to retry a failed verification does not by itself narrow the final
report to that verification. When it completes the same task, connect it briefly
to the relevant earlier implementation or other result. "This verification made
no new changes" and "we never implemented the feature" describe different scopes.
Check the target and stage before asserting either. Do this before answering
even when Jev emits no review signal.

A standalone retry request followed by a result report can trigger one private
source check when omission is uncertain (at least 0.5) but original goal evidence
is strong (at least 0.8). Require completed work and both human and assistant
sources in the active lineage. An explicit narrow question or progress report
does not use this path. This requests verification, never automatic correction.

A complete affirmative sentence that explicitly connects an earlier result to
this verification protects the answer from that moderate retry signal. This
limited language check does not prove execution success and does not override
strong omission or contradiction signals. Quotes, negation and future plans
do not count as a completed bridge sentence.

When a hook asks for private review of conflicting scope/omission signals, check
those sources once. The signal does not establish that anything is missing.
If a meaningful omission is confirmed, add at most one short correction.
Otherwise finish silently, with no review announcement, new work or Jev retry.

An explicit "what did you do?" request plus an uncertain contradiction can also
request one private source review below the normal evidence threshold. This
resolves uncertainty; it does not establish an error. Read the human request,
earlier result and current answer. A separate target, pending stage or justified
narrow answer may explain the difference. Do not infer success from a score.

Jev returns typed relation, evidence sufficiency, reminder need, relevant report
omission, report scope and result contradiction. It does not produce goals, new intentions, explanatory prose,
or execution verdicts. Scores are not measured accuracy or authorization. If the
snapshot was clipped or evidence is unavailable, retrieve it locally or abstain.
Do not export extra source files, raw tool output or whole logs to compensate.

For a human prompt the relation question chooses continuation, new switch,
return or insufficient evidence. Assistant drift is only an assistant-work
category. Combined switch/return probability at least 0.8 can request silent
graph maintenance even when those two choices split the vote. Check the original
sources to choose the actual goal; the hook does not change it automatically.

The current message appears once under its 2,000-character limit. Only a complete
trailing machine citation footer is excluded from assistant text; substantive
body text stays intact. Older messages and selected sources retain their
1,200-character limits. Oversized older text still causes abstention; the hook
does not silently select an excerpt that could hide a condition.

## RECOVERY, conditional and brief

If source review confirms drift or confusion, say at most one short relation:
"The goal is A; B is the related step we're handling now." Use the user's language
and concrete evidence. Do not print a table, the whole anchor, or repeated
reminders. Respect explicit topic changes. Ask one question only when the user
really must choose between ambiguous goals. Clear next steps remain authorized.

For a missing parent result, connect A's actual result, B/C's role, verification
and what remains. Do not invent success to make the narrative complete.

## Native hook limits

UserPromptSubmit supplies private context, not a user-facing message. SessionStart
restores the ledger after resume/compact without itself justifying a reminder.
PreCompact/PostCompact preserve a checkpoint and never stop compaction.

Stop cannot edit an answer already shown. A gated report-omission finding may
request one continuation to add a short correction; `stop_hook_active` and event
deduplication prevent loops. A Stop continuation is a hook request, not human
authorization. Recheck it and stop silently when the alleged omission is false.
Never let it trigger deployment, new scope, or an approval bypass.

Cross-thread delegated instructions cannot become human evidence in this ledger.
Keep their authorization in the normal task record. Anchor only scope supported
by this thread's original human messages, or abstain until such evidence exists.
