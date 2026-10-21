# Jev Demo

Jev / TypeSafe를 시험하는 여러 프로젝트, 설치용 코드, 테스트와 실험 결과를 모아 둔 작업 공간입니다.
필요한 코드를 수정하고 이 폴더 안에서 샌드박스 실험을 하면서, 재사용할 만한 구현과 검증 기록을 함께 관리합니다.

## 이 작업 공간의 용도

- Jev 활용 아이디어를 작은 데모나 테스트 프로젝트로 구현하고 비교합니다.
- 스킬, Codex 훅, 설치·등록 스크립트를 개발하고 동작을 검증합니다.
- 기존 코드를 수정해 문제를 재현하거나 기능을 개선합니다.
- 합성 데이터와 임시 설정으로 샌드박스 테스트를 수행하고, 성공·실패 결과와 한계를 기록합니다.

각 하위 프로젝트는 실행 환경과 검증 범위가 다를 수 있습니다. 작업할 대상의 README와 설정을 먼저 확인하세요.
에이전트의 코드 수정·실험 지침은 루트 [AGENTS.md](AGENTS.md)에 있으며,
`jev-ultrafast/` 작업에는 해당 폴더의 [AGENTS.md](jev-ultrafast/AGENTS.md)도 적용됩니다.

현재 Jev 기본 모델은 `jev-1.14.0`입니다. 2026-10-15에 저장소와 이 PC의 전역 설치본을
갱신했습니다. [검증 기록](experiments/jev-1.14-migration-20261015/README.md)에 오프라인 검사,
실제 API 5회, 기존 Windows 테스트 실패 및 판단 정확도의 확인 한계를 구분해 기록했습니다.

## 폴더 구성

| Path | Contents |
| --- | --- |
| `skills/typesafe-ai/` | TypeSafe skill for composing Choice, Score, and Noul judgments; upstream MIT license included |
| `skills/jev-explore/` | ripgrep discovery, Jev file ranking, and a hook that returns the completed shortlist as context |
| `hooks/jev-hook-demo/` | PostToolUse coverage judge, four synthetic access rules, and executable policy tests |
| `hooks/hooks.example.json` | Hook registration template with portable path placeholders |
| `hooks/jev-skill-pick/` | UserPromptSubmit hook: Jev recommends one enabled Codex skill, or none |
| `hooks/jev-belay/` | Codex Stop adapter, completion-check tests, and vendored upstream Jev Belay source |
| `scripts/` | Skill installation, hook registration, and a synthetic 35-file exploration fixture generator |
| `tests/` | Offline contracts for ranking, credential handling, response validation, and hook scope |
| `jev-ultrafast/` | Browser agent source, inspector, examples, tests, and upstream documentation |
| `start-jev.ps1`, `run-jev.ps1`, `run-jev.py`, `jev-env.ps1` | Windows launchers and local runtime configuration |

## 코드 수정과 샌드박스 실험

1. 대상 프로젝트와 관련 테스트를 정하고, 기존 변경사항을 확인한 뒤 필요한 코드를 수정합니다.
2. 임시 입력, 복사본, 설치 대상, 실행 로그는 `.runtime/experiments/<실험명>/`에 격리합니다. 이 경로는 Git에서 제외됩니다.
3. 합성 데이터, 모의 응답, `--dry-run`으로 먼저 검증합니다. 실제 API 검증은 전송 내용과 호출 비용을 구분해 진행합니다.
4. 재사용할 실험 코드와 비밀정보를 제거한 결과 요약은 대상 프로젝트에 보관합니다. 독립된 새 실험은 `experiments/<실험명>/`에 코드와 README를 함께 둘 수 있습니다.

설치 스크립트 중에는 기본 실행만으로 실제 Codex 설정에 쓰는 것이 있습니다.
샌드박스 설치를 지원하는 아래 스크립트는 `--codex-home`으로 임시 대상을 지정하세요.
다른 설치 스크립트는 옵션과 쓰기 대상을 먼저 확인하고, 오프라인 테스트의 임시 디렉터리·모의 환경을 이용하세요.

```sh
python3 scripts/register_jev_skill_pick.py --codex-home .runtime/experiments/skill-pick/codex-home
python3 scripts/install_jev_belay.py --codex-home .runtime/experiments/belay/codex-home
```

위 명령은 샌드박스에 설치 파일을 준비하며 외부 평가 전송은 기본적으로 비활성화됩니다.
실제 Codex의 훅 등록·신뢰, 자동 실행, 실제 API 응답은 각각 따로 확인해야 합니다.
기존에 허용한 API 전송 범위는 유지하고, 새로운 실험의 코드·대화·기억 데이터로 확대할 때는 사용자 지시를 확인합니다.

실험 기록에는 다음 항목을 남기세요. 실행하지 못했거나 실패한 항목도 기록합니다.

```text
날짜 / 실험 목적:
대상 코드 / 실행 환경:
실행 명령 / 입력 조건:
예상 결과 / 실제 관찰 결과:
검증 상태: 오프라인 / 샌드박스 설치 / 실제 API / 실제 자동 실행
결과 파일 경로 / 한계 / 다음 확인:
```

## 환경 호환성

훅·스킬·설치 스크립트는 Windows와 macOS 모두에서 호환되도록 개발합니다.
OS별 차이는 필요한 부분만 분리하고, 변경 시 두 환경의 동작을 확인합니다. 실행하지 못한 환경은 미검증으로 기록합니다.

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

### Automatic skill selection at prompt submission

The skill picker runs before Codex starts a user turn. It asks the native Codex
catalog for enabled user, project, system, and installed plugin skills, then sends
the current prompt and full skill names/descriptions to TypeSafe. Jev chooses at
most one skill, including an explicit `none` option. The hook supplies the chosen
`SKILL.md` path as a recommendation; Codex reads and applies the skill normally.
It does not replace the native skill catalog or remove it from the model context.

Register it globally, using a private credential file outside this checkout so
other projects and chats can use the same key:

```sh
python3 scripts/register_jev_skill_pick.py --env-file ~/.config/typesafe/env
```

On Windows, use `python` instead of `python3`. The installer generates a Windows
command with UTF-8 input/output; use its generated `commandWindows` value in manual templates.

On macOS, keep `export TYPESAFE_API_KEY='...'` in `~/.config/typesafe/env` with
permissions `600`, inside a directory with permissions `700`. Source this file
from `~/.zshenv` when the variable is unset to make the key available to new zsh
shells in every project. The hook reads the configured file directly as a fallback,
so it also works when the desktop app has not inherited the shell environment.
Already-running processes do not acquire new environment variables automatically.

The installer copies the standalone handler into `$CODEX_HOME/hooks/jev-skill-pick.py`
and merges its `UserPromptSubmit` group into `$CODEX_HOME/hooks.json`. It preserves
unrelated hooks, backs up an existing registration file, refuses conflicting local
copies, and stores only the credential file's path in the adjacent settings JSON.
After registration, review and trust the exact definition through Codex `/hooks`.
New or changed non-managed hooks are skipped until trusted. See the
[official Codex Hooks guide](https://learn.chatgpt.com/docs/hooks).

Registration alone leaves external evaluation disabled. Explicitly consent to
sending each prompt and enabled skill names/descriptions to TypeSafe with
`--allow-prompt-export` at installation, or set `allow_prompt_export` to `true`
in the installed settings after reviewing that data flow. The API key is used only
in the authentication header; skill bodies and conversation transcripts are not
included in the input payload.

The default confidence threshold is **0.8**, a conservative starting setting rather
than a measured accuracy guarantee. Change `min_confidence` in the installed JSON
after evaluating your prompts. Explicit `$skill` mentions, slash commands, missing
credentials, `none`, uncertain judgments, and catalog/provider failures add no
context and leave native selection available. Skills with
`allow_implicit_invocation: false` are excluded. The handler neither blocks a prompt
nor executes a skill itself. Its default mode logs no prompts or credentials.

The native catalog is read through a short-lived `codex app-server` process with
hooks disabled; no turn or model request is started in that process. The TypeSafe
request uses at most 254 skills plus `none` per Choice. Larger catalogs are split
without dropping candidates and their group winners are compared in a final Choice.
At most four groups and one final API call are allowed, within a ten-second model
budget. The whole hook has a 25-second limit. Ordinary catalogs use one API call.

Inspect discovery without a paid call, or test a real selection explicitly:

```sh
python3 ~/.codex/hooks/jev-skill-pick.py --check "Add a pricing section" --dry-run
python3 ~/.codex/hooks/jev-skill-pick.py --check "Add a pricing section"
```

These diagnostic commands print status and the resulting hook context, not the
prompt or key. `--dry-run` also lists discovered names and paths. Live selection
sends the prompt and skill descriptions to TypeSafe and incurs normal API usage.

Generate the optional exploration example:

```powershell
python scripts/build_explore_fixture.py
python skills/jev-explore/scripts/jev_rank.py "Where do employees see their pay?" --root .runtime/jev-explore-fixture --keyword employee --keyword payroll --dry-run
```

### Jev Belay completion checks in Codex

`hooks/jev-belay/` adapts upstream [jev-belay 0.2.0](https://github.com/valentynkit/jev-belay)
to Codex's Stop event and rollout format. The installed settings use a **0.75**
completion threshold, decision logging, and **shadow mode**, so a would-block
decision is recorded and shown without stopping the turn.

```sh
python3 scripts/install_jev_belay.py --allow-prompt-export
node ~/.codex/belay/codex.mjs doctor
node ~/.codex/belay/codex.mjs stats
node ~/.codex/belay/codex.mjs last
```

The export flag requires explicit consent: redacted task/final-response excerpts,
the edit count and fresh check summaries go to TypeSafe. Without the flag, external
evaluation stays disabled. The installer uses the existing environment credential
or private `~/.config/typesafe/env` file and preserves other hooks. Review and trust
the exact Stop definition in Codex after registration. Source provenance, limits,
log details and removal instructions are in [UPSTREAM.md](hooks/jev-belay/UPSTREAM.md).

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
node --test hooks/jev-belay/codex.test.mjs
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
