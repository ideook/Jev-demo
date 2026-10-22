# Explore on demand and Windows timeout regression

Date: 2026-10-22. Python 3.12, Windows, installed Codex app-server and the
user's normal trusted global hooks. No hook trust records were edited.

## Problem and change

The old `PostToolUse` matcher `^Bash$` started a second PowerShell/Python process
after every shell command. Its Python handler rejected non-exploration commands,
but that happened after process startup and after Codex created a hook-history row.
Native eight-command bursts reproduced **16 Explore timeouts in 16 dispatches**
across two runs, each at approximately five seconds. Two sequential dispatches
completed in 3.46 and 3.97 seconds. Opt-in startup tracing reached Python during
the sequential run but never reached its first marker in the parallel run before
cancellation. This isolates the observed delay to startup before that marker;
it does not establish an antivirus or a particular Windows service as the cause.

[Codex's hook matcher](https://learn.chatgpt.com/docs/hooks) selects the tool name,
not the shell command text. Explore now delivers its reading priorities in the
`jev_rank.py` tool output. The skill invokes ranking when locating an unknown
implementation, and reads known files directly. English queries, original source
excerpts, model `jev-1.14.0`, credential lookup and API budgets are unchanged.
Changed-file and capped-discovery warnings travel with the direct output.

The installer supports `--codex-home` and an explicit `--update`. It validates
destinations/configuration before changing files, backs up existing managed files
and hooks, and removes only the command pointing to its installed legacy handler.
It registers no replacement shell hook and needs no new hook trust approval.

**Native trust keys also contain group indexes.** Removing the entire legacy group
shifted North Star to the old Explore key, which Codex marked `modified` despite
unchanged command bytes. The installer now retains the vacated group with
`hooks: []`. This dispatches no Explore process and preserves following hooks'
keys. A regression test and native `hooks/list` verify this behavior.
Mixed custom groups sharing Explore and other callbacks are rejected before
changes, because removing an item there would shift another callback's key.

## Offline and sandbox evidence

- All Explore tests cover direct output with a mocked score response and exactly
  one mocked API attempt, dry-run with Korean/space/apostrophe paths, stale source
  warnings, capped discovery, fresh install, repeated install, backed-up updates,
  invalid configuration rejection and preservation of following native keys.
  All **18 Explore tests** pass.
- Full root suite initially hit sandbox temporary-directory ACL denial. An
  unrestricted run using a long isolated temp path then hit Windows path-length
  limits in existing North Star ACL backup tests. A short repository-local temp
  directory `.runtime/et` resolves both test-environment issues; no tests were
  weakened. The final root suite has **223 tests: 220 passed, 3 skipped**. The
  skips are POSIX mode-bit validation and two symlink tests unavailable under
  this Windows account's symlink permissions.
- Fresh sandbox installation creates the three managed skill files and no
  `hooks.json`. Repeating it changes neither files nor configuration.
- Skill validation and `git diff --check` pass. The unchanged legacy hook handler
  remains in the source tree for compatibility tests; new installs do not copy it.

## Global application and native checks

The installed skill was compared with the previous committed source before
replacement; differences were only line endings. The migration updated `SKILL.md`
and `scripts/jev_rank.py`. `agents/openai.yaml` already matched. Existing hook
definitions and `config.toml` were preserved, with the empty Explore slot keeping
North Star's original `post_tool_use:2:0` key. `hooks/list` reports all nine remaining
definitions trusted, including the six enabled North Star hooks. The coverage
demo remains disabled as before.

The first native test exposed an additional existing protected DACL on
`~/.codex/skills/north-star`: a sandboxed skill read was denied. Its descriptor
was backed up, parent ACL inheritance was restored only for that public skill
directory, and all file bytes were verified unchanged. No credential directory
or hook trust record was modified.

Global backups are under `~/.codex/backups/jev-explore/20261022T030651Z-2fe20b1a/`.
Private receipts and raw native events are under
`.runtime/experiments/jev-explore-on-demand-20261022/`. The original timeout
observations remain under `.runtime/experiments/explore-hook-timeout-20261022/`.

Reproduce the bounded Windows native check after global installation:

```powershell
python -X utf8 experiments/jev-explore-on-demand-20261022/native_probe.py --output .runtime/experiments/jev-explore-on-demand-20261022/native-new-run
```

Use a fresh output directory. The driver runs eight separate shell commands
concurrently, invokes installed Explore with `--dry-run`, and reads the discovered
synthetic source. It observes native hook completion and actual command exit codes,
checks that enabled hooks remain trusted and PostToolUse still dispatches, and
fails on an Explore callback, failed hook, failed command or missing reading output.
It never invokes a hook handler or fabricates a hook event.

The final native run completed successfully:

- Eight distinct ordinary shell commands ran with **maximum concurrency 8**.
  Explore callback dispatches: **0**. Failed hooks/commands: **0 / 0**.
- Installed ranking ran once with `--dry-run`, printed the Korean source path,
  line anchor, reading guidance and report marker, and exited **0**. The command
  reported **0 ranking API calls** and **1.74 seconds** internally.
- Codex read the discovered source and found `find_employee_pay`. There were
  **17 successful shell commands** in total, including skill reads and ordinary
  North Star internal maintenance.
- North Star's native PostToolUse callback completed **17 / 17** times; the eight
  burst callbacks took **4.30–4.48 seconds**, below their unchanged 12-second
  deadline. All enabled catalog entries remained trusted. The full model turn
  reached `completed`, without harness intervention.

The initial post-migration run is retained as `native-after/`: Explore routing
and ranking worked, but the newly shifted North Star key was skipped and reading
its protected skill failed. The corrected run is `native-final/`; the failed
attempt was not counted as successful integration evidence.

## Limits

Offline tests and the rank dry-run send no source excerpts or paid ranking
requests. The native model session uses normal global picker/North Star/Belay
settings and their previously authorized context export; it is not an API-free
session. Actual Jev relevance quality and live ranking latency were not retested.
Native macOS execution was not available. The shared installer/ranker use portable
Python and no new operating-system-specific launcher.
