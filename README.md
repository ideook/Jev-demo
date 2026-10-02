# Jev Demo

Jev / TypeSafe skills, Codex hooks, offline tests, and the local Jev Ultrafast browser demo.

| Path | Contents |
| --- | --- |
| `skills/typesafe-ai/` | TypeSafe skill for composing Choice, Score, and Noul judgments; upstream MIT license included |
| `skills/jev-explore/` | ripgrep discovery, Jev file ranking, and a hook that returns the completed shortlist as context |
| `hooks/jev-hook-demo/` | PostToolUse coverage judge, four synthetic access rules, and executable policy tests |
| `hooks/hooks.example.json` | Hook registration template with portable path placeholders |
| `scripts/` | Skill installation, hook registration, and a synthetic 35-file exploration fixture generator |
| `tests/` | Offline contracts for ranking, credential handling, response validation, and hook scope |
| `jev-ultrafast/` | Browser agent source, inspector, examples, tests, and upstream documentation |
| `start-jev.ps1`, `run-jev.ps1`, `run-jev.py`, `jev-env.ps1` | Windows launchers and local runtime configuration |

## Skills and hooks

Use Python 3.12+ and install [ripgrep](https://github.com/BurntSushi/ripgrep). The skills and hook scripts use the Python standard library.

Install the exploration skill and register its hook from the repository root:

```powershell
python scripts/install_jev_explore.py
```

To use the general TypeSafe skill, copy `skills/typesafe-ai` into your Codex skills directory (`$CODEX_HOME/skills`, or `~/.codex/skills` when `CODEX_HOME` is unset). Both skill directories can also be copied manually.

Optionally register the synthetic coverage judge:

```powershell
python scripts/register_jev_hook.py
```

The scripts merge their own hook definitions into `$CODEX_HOME/hooks.json` (default `~/.codex/hooks.json`), preserve unrelated hooks, and refuse conflicting registrations or exploration skill files. They write installation records under the ignored `.runtime/` directory. Keep this checkout available while the judge hook is registered: its command points to `hooks/jev-hook-demo/jev_judge_hook.py` here.

Inspect and enable/trust the registrations in the Codex client's hook interface where supported. Automatic hook dispatch depends on the client and its tool names; the registrations use `^Bash$` for exploration and `^apply_patch$` for the judge. Handler contract tests alone do not establish automatic dispatch in a desktop chat.

Run exploration from a target repository, using the installed skill path or this checkout's absolute script path:

```powershell
python "<REPO>/skills/jev-explore/scripts/jev_rank.py" "Where do employees see their pay?" --root . --keyword payroll --keyword payslip --top 5 --dry-run
```

Remove `--dry-run` to request Jev rankings. Credentials come from `JEV_API_KEY` or `TYPESAFE_API_KEY` in the process environment, the target repository's `.env`, or the Windows user environment. Source excerpts go to the TypeSafe API during ranking. The exploration hook reads that completed report and makes no additional API calls.

The judge only evaluates edits to its own `rules.md`, `access_control.py`, and `test_access_control.py`. It asks one Noul question per access rule about executable test coverage, then returns additional context. Its example thresholds are 0.8 for covered and 0.2 for missing; intermediate answers need review. Execute the policy tests separately. A direct live evaluation is available through:

```powershell
python hooks/jev-hook-demo/jev_judge_hook.py --check
```

Live ranking and judging require a TypeSafe key and may incur API costs. No key is included in this repository. Configure credentials locally; `.env`, reports, runtime browser profiles, and traces are ignored.

Generate the optional exploration example:

```powershell
python scripts/build_explore_fixture.py
python skills/jev-explore/scripts/jev_rank.py "Where do employees see their pay?" --root .runtime/jev-explore-fixture --keyword employee --keyword payroll --dry-run
```

## Browser demo on Windows

Install [uv](https://docs.astral.sh/uv/) and Google Chrome, then:

```powershell
cd jev-ultrafast
uv sync
cd ..
./start-jev.ps1
```

Open `http://127.0.0.1:8766`. Set `JEV_API_KEY` or `TYPESAFE_API_KEY` and, for text generation, `TEXT_MODEL_API_KEY` or `OPENROUTER_API_KEY` in your process or Windows user environment. Additional model settings are read by `jev-env.ps1`. See `jev-ultrafast/.env.example` for the upstream configuration example.

The Windows launcher uses its own ignored Chrome profile and loopback debugging port 9227. The local browser adaptation honors `JEV_BACKGROUND_TABS`; the launcher uses foreground tabs. The rest of the vendored source and its published measurements come from [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast), commit `1231850`. Those historical measurements are upstream evidence, not measurements of this package.

## Offline verification

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s hooks/jev-hook-demo -p test_access_control.py -v
cd jev-ultrafast
$env:PYTHONUTF8 = '1'
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
```

These tests do not call paid model APIs. Browser examples and live check commands do.

## Licenses

The TypeSafe skill retains its [MIT license](skills/typesafe-ai/LICENSE). The browser demo retains its [MIT license](jev-ultrafast/LICENSE).
