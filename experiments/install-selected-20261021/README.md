# Coverage Judge를 제외한 사용자 전역 설치

## 날짜 / 실험 목적

2026-10-21, Windows. 사용자가 요청한 Jev Explore, Skill Picker, Jev Belay,
North Star를 실제 Codex 사용자 폴더에 설치했다. 기존 TypeSafe AI 스킬은
유지했으며 Coverage Judge와 별도 브라우저 데모는 설치하지 않았다.

아래 결과는 당시 커밋 `dc7f666`에서 관찰한 설치·검증 기록이다.
현재 설치 상태를 다시 검사한 결과로 해석하지 않는다. 이후 Explore의 동작과
설치기 변경은 [2026-10-22 요청 시 실행 전환 기록](../jev-explore-on-demand-20261022/README.md)을 참고한다.

## 대상 코드 / 실행 환경

- 대상: `scripts/install_jev_explore.py`, `scripts/register_jev_skill_pick.py`,
  `scripts/install_jev_belay.py`, `scripts/install_north_star.py`.
- 실제 설치 루트: `C:\Users\Dukhyun\.codex`.
- Python 3.12.14: Codex에 번들된 실행 파일의 절대 경로를 사용했다.
  PATH의 WindowsApps `python` 별칭은 실행되지 않아 사용하지 않았다.
- Node 24.18.0: `C:\Program Files\nodejs\node.exe`.
- macOS 실행은 미검증이다.

## 실행 명령 / 입력 조건

먼저 `.runtime/experiments/install-selected-20261021/codex-home`을 대상으로
`CODEX_HOME`을 지정해 네 설치 스크립트를 순서대로 실행했다. Explore 설치기는
`--codex-home` 옵션이 없으므로 환경변수로 대상을 격리했다. 나머지는
`--codex-home`을 사용했다. 실제 설치에도 같은 스크립트와 런타임을 사용했다.

`--allow-prompt-export`와 `--allow-export`는 사용하지 않았다. 설치기와
등록된 명령은 기존 환경변수를 이용하며 인증정보를 새로 복사하거나 저장하지 않았다.

## 예상 결과 / 실제 관찰 결과

- 샌드박스 및 실제 설치 모두 네 스크립트가 종료 코드 0으로 완료됐다.
- 설치 파일 16개가 저장소 소스와 바이트 단위로 일치한다.
- 기존 `config.toml`과 `skills/typesafe-ai/SKILL.md`의 설치 전후 SHA-256이 같다.
- native `skills/list`: `typesafe-ai`, `jev-explore`, `north-star` 모두
  user scope이며 `enabled: true`; 로딩 오류가 없다.
- native `hooks/list`: 훅 9개 모두 user scope, `enabled: true`,
  **`trustStatus: untrusted`**. 등록 오류와 경고는 없다.
- 이벤트별 훅 수: PostToolUse 2, UserPromptSubmit 2, Stop 2,
  SessionStart 1, PreCompact 1, PostCompact 1. Coverage Judge 등록은 없다.
- Skill Picker·Belay의 `allow_prompt_export`, North Star의 `allow_export`는
  모두 `false`다. Belay는 `shadow: true`, 임계값 0.75다.
- 설치된 Belay의 `doctor`가 종료 코드 0으로 키 존재와 등록 상태를 확인했다.
  `--live`는 사용하지 않았다.

## 검증 상태

| 구분 | 관찰 범위 |
| --- | --- |
| 오프라인 | `python -B -m unittest discover -s tests -v`: 216개 실행, 214개 통과, 2개 건너뜀. `node --test hooks/jev-belay/codex.test.mjs`: 25개 통과. 유료 API 호출 없음. |
| 샌드박스 설치 | 네 설치기 성공, 훅 9개 생성 및 외부 평가 비활성 확인. |
| 실제 설치 | 파일 일치, 기존 설정 보존, native 스킬·훅 카탈로그와 Belay doctor 확인. |
| 실제 API | 실행하지 않음. |
| 실제 자동 실행 | 실행하지 않음. 새 훅은 신뢰 승인 대기 상태다. |

## 결과 파일 경로 / 한계 / 다음 확인

로컬 로그와 설치 영수증은 Git에서 제외되는
`.runtime/experiments/install-selected-20261021/`에 있다.

- `sandbox-installation.json`, `installed-installation.json`: 설치 결과와 설정 보존 확인.
- `installed-hashes.json`: 설치 파일 16개 일치 확인.
- `python-tests.log`, `belay-tests.log`: 오프라인 검사 결과.
- `native-catalog.json`: 모델 턴을 시작하지 않은 `hooks/list`, `skills/list` 응답.
- `belay-doctor.json`: 설치된 Belay 진단 결과.

샌드박스 안에서 native app-server를 처음 조회할 때는 실제 Codex SQLite
상태 디렉터리 쓰기 제한으로 초기화에 실패했다. 허용된 설치 검증 범위에서
권한을 올려 카탈로그만 다시 조회했고 성공했다. 모델 요청은 시작하지 않았다.

다음 단계는 Codex CLI `/hooks`에서 실제 훅 정의를 검토하고 Trust하는 것이다.
설치기는 신뢰 기록을 만들거나 우회하지 않았다. 외부 자동 평가를 사용하려면
별도로 전송 범위를 허용하고 설치 설정을 활성화해야 한다. 설치·등록 결과는
실제 자동 실행이나 Jev 판단 정확도의 증거가 아니다.

## 사용자 전역 키 교체

같은 날 사용자 요청에 따라 프로젝트 `.env`의 `TYPESAFE_API_KEY`를 읽어
Windows 사용자 환경변수 `HKCU\Environment\TYPESAFE_API_KEY`의 기존 값을
교체했다. 저장 후 다시 읽은 값이 `.env`와 일치하며 이전 값과 다른 것을
확인했고, Windows 환경 변경 알림도 전송했다. 키 값은 로그·기록·별도
설정 파일에 복사하지 않았고 API 호출은 하지 않았다.

이미 실행 중인 Codex 프로세스의 환경은 자동으로 갱신되지 않으므로 새 키를
확실히 사용하려면 Codex를 완전히 종료한 뒤 다시 실행해야 한다. 이번 변경은
사용자 환경변수에만 적용했으며 외부 평가 활성화 설정은 변경하지 않았다.
값을 포함하지 않는 결과는 로컬 `user-key-update.json`에 남겼다.
