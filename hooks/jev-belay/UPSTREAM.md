# Jev Belay for Codex

Upstream: https://github.com/valentynkit/jev-belay

Version 0.2.0, commit `c59f030032baedb3a3e5acefd3ead19d9dcde84c`, checked on
2026-10-09. The original project supports Claude Code. This local adapter supports
Codex's Stop payload and rollout records; it is not an upstream Codex release.

`upstream/belay.mjs` has two small patches: `BELAY_HOME` accepts `JEV_BELAY_HOME`, keeping
Codex decisions and session guards in `~/.codex/belay`; text caps include the three
ellipsis characters, strictly preserving the consented 1,500/2,000 character limits.
Upstream judgment, redaction,
thresholds, guard caps, HTTP retry budget and rendering are retained. Upstream tests
and MIT license are included.

The redaction tests assemble their invented Stripe keys at runtime, preserving the
same test inputs without storing key-shaped literals that GitHub push protection
rejects.

The adapter maps completed Codex calls to a private, temporary evidence projection.
It accepts prompts recorded as legacy `user_message` events or Desktop `response_item`
messages, excluding injected instruction and Page context blocks. `last-status.json`
also records skip reasons without task or final-response text.
It tracks edits, shell exits, runner summaries, long-running shell sessions, direct
tools and code-mode batches. Checks before the last edit are stale. When a batch
contains both changes and checks, their internal order is unknown; its check is
conservatively treated as stale. Computed JavaScript commands are not evaluated.
Delegated work is not read from separate Codex subagent histories. Turns whose start
cannot be found in the last 16 MiB fail open. Shell writes through unrecognised
commands may not count as edits; a decision log is advisory evidence, not proof that
all changes were tested. The adapter's Korean judgments have not been calibrated.

Settings are `threshold: 0.75`, `log: true`, `shadow: true`, model `jev-1.13.0`.
The threshold is a probability, corresponding to 75 in the screenshot. Shadow mode
records would-block decisions and displays a hook message without blocking a turn.
Network errors fail open. The API budget is 12 seconds within a 20-second Stop hook.

Credentials come from `TYPESAFE_API_KEY` / `JEV_API_KEY`, then the existing private
`~/.config/typesafe/env` file for GUI launches. That file is parsed as data, never
sourced. Keys are not copied into settings, hooks, manifests or source code.
Requests go to `https://api.typesafe.ai/v1/systemone`. The request contains a redacted
task (up to 1,500 characters), final answer (up to 2,000 characters), change count and
fresh check summaries. It excludes file contents, diffs and raw transcripts. The local
decision log contains these redacted excerpts, model answers, usage and latency;
it rotates after 5 MiB, retaining one previous file.

Install with `python3 scripts/install_jev_belay.py --allow-prompt-export` after explicit
consent to that payload. Without the flag the hook is dormant and sends nothing.
Review and trust the exact Stop
definition through Codex's native hook configuration. The installer preserves
other hooks and backs up `hooks.json`. It refuses conflicting existing files.

After installation:

```sh
node ~/.codex/belay/codex.mjs doctor
node ~/.codex/belay/codex.mjs doctor --live  # one synthetic paid request
node ~/.codex/belay/codex.mjs stats
node ~/.codex/belay/codex.mjs last
node ~/.codex/belay/codex.mjs watch
```

Offline tests: `node --test hooks/jev-belay/codex.test.mjs`, plus `npm test` in
`hooks/jev-belay/upstream`. The upstream tests use loopback fixture servers.
To remove the installation, remove its Stop group from `~/.codex/hooks.json` and
delete `~/.codex/belay` when its logs and backup are no longer needed.
