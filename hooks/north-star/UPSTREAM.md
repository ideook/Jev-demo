# North Star for Codex

Adapted from https://github.com/dolevhayut/north-star, commit `467742606738df988b545bfdb63c94848f60ce54`, retrieved 2026-10-20. Original SKILL.md, automation guidance and MIT license are retained in `upstream/`. Copyright 2026 Dolev Hayut.

Local changes: Codex native hooks; thread-scoped source references and versioned goal graph; six typed relation, evidence, reminder, relevant report-omission, report-scope and contradiction checks; conditional reminders; no periodic goal recital or mandatory recovery approval. The original Claude hook examples are reference material only.

October 21 legacy Windows ACL migration: Store initialization automatically
enables inheritance on protected North Star state paths before reading an
existing ledger. Installation also migrates existing ledgers. Explicit ACEs
and ownership are preserved; permissions come from the existing managed parent,
without adding accounts or resetting ACLs. Original protected descriptors are
backed up under `north-star/acl-backups/` before any changes. Reparse points,
junctions and unreadable subtrees abort migration; source/state bytes, goal
versions, call budgets and recovery markers are not rewritten. POSIX keeps its
existing permissions. See the Windows
[SetNamedSecurityInfo documentation](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)
for inheritance propagation.

October 21 automatic lifecycle: `automatic.py` captures the complete first real
human prompt in a private source journal before any API call, creates a literal
goal, and supplies silent skill context. PostToolUse reviews the latest assistant
intent after any local tool type. Tool arguments/results remain local. Native
human-source backfill supports resumed threads; explicit source-backed pivots and
returns preserve prior roots and graph revisions. A target-goal Choice on later
human prompts identifies a new or prior root with confidence at least 0.8.

Strong drift can request immediate internal recovery at PostToolUse or one
bounded Stop continuation. The ledger closes recovery only after aligned intent
and an observed successful local tool result (explicit integer exit code 0).
That condition does not prove the operation served the goal or completed the
parent task. Codex must compare actual effects locally; unknown tool result
formats remain unverified. An uncertain/unavailable check requests one local
source/effect review per status, goal version and 15-minute cooldown, without
claiming drift or adding an API retry. A shared 24-call/thread/hour budget,
8-second timeout, 60-second failure backoff and unchanged-work cache bound cost.

Native unattended verification exposed stdout-only Bash callbacks. Printed JSON
and exit-code headers cannot confirm a process exit. The internal
`verify-execution` CLI runs the next already-authorized local check in the same
sandbox (60 seconds maximum), records the real child exit code and binds a
receipt to the recovery, active goal, anchor version and fresh nonce. The native
Bash invocation must contain that nonce; receipts expire after 120 seconds and
are consumed with aligned intent. No stdout or command body is exported or
stored in the audit. Unknown/failed execution stays unverified. If recovery is
still open at Stop, one guarded continuation requests that verification; a
reentrant Stop never loops or adds authorization.

On Windows new state/source/history directories inherit the parent's existing
capability ACLs. POSIX keeps mode 700. Python's Windows mode-700 protected DACL
prevented the sandboxed agent from reading its own ledger, even when the runtime
granted the thread directory. No new Windows users, groups or Everyone grants
are added. Existing protected directories are not rewritten by this change.

When Jev abstains after execution, Codex can acknowledge its own local review
through the versioned anchor CLI: `review_recovery` must match the pending
observation hash; the same active goal must have completed claims and result
refs matching the hook's successful `execution_observation.intent_ref`. Missing
or failed execution and stale versions cannot close recovery. The distinct
`agent_reviewed_execution` status preserves the verdict's provenance. No Jev
retry or lower alignment threshold is used. The native source resolver accepts
only identity-checked canonical rollouts in configured roots when a client
supplies a temporary projection; structured approval replies cannot bootstrap
an independent goal when an original task is available.

Windows compatibility (2026-10-21): the local handler uses nonblocking `msvcrt`
byte-range locking on Windows and retains `fcntl.flock` on macOS/POSIX. Closing
the descriptor releases either lock. State and audit writes use UTF-8; Windows
file replacement retries sharing/access denials at most five times with 150 ms
total backoff. Persistent errors preserve the old state and are returned to the
caller. Platforms without `O_NOFOLLOW` check the opened file's identity and
symlink status before use. The installer emits a UTF-8 Windows hook command and
recognizes either slash style in existing registrations. See the
[Windows verification report](../../experiments/north-star/windows-compatibility-2026-10-21.md).

The global skill is installed once, never copied into project AGENTS.md. Code maintains source hashes/offsets and state; Codex maintains summaries and result claims; Jev classifies the supplied bounded evidence without generating goals or proving execution.

API destination: https://api.typesafe.ai/v1/systemone. At most 24 calls per thread per hour, one call per eligible prompt/Stop, no HTTP retry, 8-second network timeout inside a 12-second native hook. Goals up to 300 characters each, selected original excerpts up to 1,200 characters each, latest six conversational messages up to 1,200 each, current request/final up to 2,000. The complete state is at most 24,000 UTF-8 bytes. Truncated source/current evidence suppresses judgment. Tool output, source files and complete transcripts are excluded. Credentials use the existing environment or private TypeSafe env file; common secret/identity shapes are redacted. Arbitrary personal names cannot be perfectly identified; use selected synthetic/deidentified evaluation material.

State is private JSON per thread, with source references, previous anchor revisions, CAS, event deduplication, a 15-minute reminder cooldown and 60-second provider-error backoff. Compaction does not reset reminder cooldown. Original sources must still exist and match their hashes. Missing/changed source, malformed response, timeout and unknown transcript identity fail open. Forks use a distinct ledger and do not inherit their parent's mutable state. The transcript format is not a stable Codex interface; unsupported formats abstain.

Stop cannot rewrite an answer already shown. A gated drift or parent-report finding can request one bounded continuation; reentrant Stop events are ignored. Hooks never authorize operations. New hooks require native trust review, which the installer never bypasses.

The normal advisory policy requires evidence >= 0.8. Drift additionally requires relation confidence >= 0.8 and reminder need >= 0.8. Report omission requires completed work in the active goal's ancestry, relevant omission >= 0.8, and result-report scope confidence >= 0.8. Contradiction >= 0.8 requests private review even for a narrow answer. Human pivot/return maintenance uses confidence >= 0.7 and stays private. Combined on-track/subtask probability >= 0.8 permits silent alignment when those compatible classes split the vote. Thresholds are not measured accuracy. See `experiments/north-star/README.md` for misses and verification boundaries.

A bounded conflict-review path requires evidence >= 0.8 and completed active-lineage work. When omission >= 0.8 but scope confidence < 0.8, either a result-scope choice or a recognized full-results request can trigger private review. It does not override a pivot/return or a confident narrow/progress classification. A separate clarification path requires an explicit standalone "what did you do?" question, original human and assistant sources, completed active-lineage work, and both evidence and contradiction >= 0.5. These uncertain signals request local verification only; they do not justify correction. Review shares report cooldown and continuation guards.

Stop exports only active ancestry, so separate completed topics do not become report obligations. Current text is not duplicated under the smaller recent-message cap. Complete trailing machine citation footers are removed; body paragraphs and qualifiers remain. Wrapped question replies contribute only human answers; native hook prompts cannot become human sources. Original reference offsets and hashes remain unchanged. Missing-key, clipped-evidence and stale-snapshot skips do not spend the provider-call budget; failed/unknown network attempts do.

The sixth question adds token cost within the same one-request-per-event budget. No extra API round trip, retry, provider or raw-history export is introduced. The October 20 v2 report separates the fresh 30-call comparison from later policy-only replay; one historical omission remains undetected.

October 20 v3 separates human navigation from assistant drift at the question
schema level. Human Choice has continue/switch/return/insufficient; Stop retains
work alignment and drift. The response distribution is validated against its
event's exact choices. Switch-plus-return probability >= 0.8 supports private
maintenance. In automatic mode an additional confident target selection can
select the source-backed human goal as described above, never issue a reprimand.

The omission question now checks the link between an earlier completed result
and resumed verification. A standalone retry request, result scope, original
human and assistant sources, completed active-lineage work, evidence >= 0.8 and
omission >= 0.5 can request one private source review. Narrow/progress answers,
quotes and compound scope restrictions do not enter this path. Existing cooldown
and continuation guards apply. The moderate score is uncertainty to inspect,
not proof of omission. See the v3 report for live results versus policy replay.

The moderate retry path also requires absence of a recognized, complete
affirmative parent-result bridge sentence. This high-precision local guard
rejects quoted, negated, conditional and future-tense statements; it only
protects against the weak retry signal. Strong omission/contradiction review
still applies. The paired correct-answer counterexample exposed the need for
this guard; the v3 report records its policy replay separately from live calls.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [TypeSafe API](https://docs.typesafe.ai/api/system-one), [Choice](https://docs.typesafe.ai/primitives/choice), [Noul](https://docs.typesafe.ai/primitives/noul), [source comparison cookbook](https://docs.typesafe.ai/cookbooks/citation_check).
