# Jev 1.14 전환 및 검증

## 목적과 범위

2026-10-15, Asia/Seoul. Windows / Python 3.12.10 / Node 24.18.0.
현재 사용하는 Jev 모델을 `jev-1.14.0`으로 고정했다.
공식 모델 및 API 문서: https://docs.typesafe.ai/models, https://docs.typesafe.ai/api.

변경 대상은 Explore, Skill Picker, Belay, 합성 커버리지 훅, Jev Ultrafast다.
실행 코드, 설치 기본값, 관련 테스트 입력, 브라우저 `.env`와 `.env.example`, 표시 문구를 갱신했다.
과거 측정 결과와 2026-10-14 점검 기록은 당시 모델을 그대로 보존했다.
기존 작업 변경사항을 보존했고 커밋이나 푸시는 하지 않았다.

## 실제 설치

`~/.codex/hooks/jev-skill-pick.py`와 JSON 설정, `~/.codex/skills/jev-explore/scripts/jev_rank.py`,
`~/.codex/belay/`의 어댑터·원본·설정·설치 해시·출처 문서를 갱신했다.
등록된 커버리지 훅이 참조하는 이전 작업 폴더의 핸들러도 갱신했다.
변경 전 설치 코드가 저장소와 일치함을 확인하고 백업한 후 적용했다.

`hooks.json`의 SHA-256은 변경 전후 동일하다. 외부 전송 동의와 임계값은 보존했다.
Skill Picker는 `min_confidence: 0.8`, Belay는 `threshold: 0.75`, `shadow: true`다.
두 설치 설정의 기존 `allow_prompt_export: true`도 그대로다.
새 샌드박스 설치는 두 도구 모두 `jev-1.14.0`, `allow_prompt_export: false`로 생성됐다.

실제 Codex `hooks/list`에서 Explore, Skill Picker, Belay가 enabled / trusted이며,
커버리지 훅은 기존과 같이 disabled / trusted다. 경고·로딩 오류는 없었다.
설치된 Belay 파일 6개의 해시가 설치 manifest와 일치한다.
남아 있는 Jev 브라우저 데모·runner 프로세스는 없었다.

## 오프라인 및 빌드 검증

- `python -m unittest discover -s tests -v`: 42 통과.
- `python -m unittest discover -s hooks/jev-hook-demo -p test_access_control.py -v`: 5 통과.
- `node --test hooks/jev-belay/codex.test.mjs`: 25 통과.
- 브라우저 가상환경의 `python -m ruff check .`: 통과.
- 브라우저 가상환경의 `python -m pytest`: 31 통과.
- `node --check jev_ultrafast/static/app.js` 및 `snapshot.js`: 통과.
- `uv build`: sdist와 wheel 생성 성공. wheel 내부 모델 기본값과 표시 문구도 확인했다.
- `git diff --check`: 통과.

`uv`가 PATH에 없어 기존 설치 실행 파일을 찾았고, Ruff/Pytest는 동일한 프로젝트 가상환경에서 실행했다.
기본 임시 경로, browser-harness 설정 경로, uv 캐시에 대한 샌드박스 거절은
실험 폴더의 `TMP`/`TEMP`, `BH_HOME`, `UV_CACHE_DIR`로 격리해 해결했다.
빌드에 필요한 hatchling 의존성은 실험 캐시에 받았으며 전역 패키지를 설치하지 않았다.

Belay 원본 전체 검사는 루프백 모의 서버의 샌드박스 제한을 해제한 뒤,
서로 다른 새 `JEV_BELAY_HOME`에서 변경 전 1.13 기준본과 변경 후 1.14를 비교했다.
두 실행 모두 **118개 중 103 통과, 10 실패, 5 스킵**이며 실패 이름 집합이 정확히 같다.
10개는 Windows 심볼릭 링크·chmod 차이와 HOME 기반 CLI/TUI fixture 및 격리 경로 문제다.
유료 원본 검사는 `JEV_LIVE_URL`을 비워 실행하지 않았다.
중간 실행에서 재사용한 로그 경로로 발생한 추가 실패는 새 경로 대조 결과와 구분한다.

## 실제 API 검증

대상: `POST https://api.typesafe.ai/v1/systemone`.
합성 입력만 사용해 각 사용처당 1회, 총 **5회** 호출했다. 재시도와 리디렉션은 허용하지 않았다.
기존 키는 인증 헤더에만 사용했고 저장·출력하지 않았다.
실제 소스, 대화, 스킬 카탈로그, 개인정보, 브라우저 세션은 전송하지 않았다.

5회 모두 HTTP 200, 응답 모델 `jev-1.14.0`, 각 기존 응답 파서 호환성을 확인했다.
총 입력 사용량은 2,546토큰이다. 개별 결과는 다음과 같다.

- Skill Picker: 합성 코드 검색 요청에서 `code_search` 선택. 신뢰도 1.0, 219 ms.
- Explore: 합성 코드 후보의 원본 Score 2.19/3, 정규화 점수 0.73, 신뢰도 0.2, 188 ms.
- 커버리지 훅: 합성 익명 접근 거절 테스트의 Noul 0.68, 기존 기준상 `review`, 203 ms.
- 브라우저 모델: 합성 완료 화면에서 `DONE`, 신뢰도 0.98, 187 ms. 브라우저 조작은 실행하지 않았다.
- Belay: 검사 없이 테스트 성공을 주장한 합성 완료 응답에서 `would_block: true`,
  `false_claim: true`, 257 ms. 기존 shadow 설정에서는 경고 대상이다. Stop 핸들러를 실행하지 않았다.

초기 진단 스크립트는 Explore의 정규화된 0..1 점수에 원본 척도의 `>= 2`를 적용해 실패했다.
이 비교는 `>= 2/3`으로 수정하고 저장된 응답만으로 재검증했다. 추가 API 호출은 없었다.
커버리지 사례는 형식 오류가 아니라 `0.8` 통과 기준 미달이다. 이를 통과 사례로 바꾸지 않았고
`review` 결과를 그대로 남겼다. 초기 실패 결과도 보존했다.

이 검증은 모델 선택, 연결, 응답 형식과 제한된 합성 사례를 확인한다.
Explore 신뢰도 0.2와 커버리지 `review`를 포함해, 일반 정확도 향상이나 임계값 보정은 입증하지 않는다.
Codex 자동 이벤트의 실제 전달, 실제 웹사이트에서의 브라우저 작업, macOS 실행은 이번에 검증하지 않았다.
모델 버전 변경으로 기존 Belay 근거 수집 문제를 수정했다고 주장하지 않는다.

## 결과 파일과 재현

로컬 결과는 `.runtime/experiments/jev-1.14-migration-20261015/`에 있다.

- `repo-before/`, `installed-before/`, `installed-update.json`: 변경 전 백업과 적용 대상.
- `python-tests.txt`, `belay-tests.txt`, `browser-tests.txt`: 주요 오프라인 검사.
- `upstream-fresh-113.txt`, `upstream-fresh-114.txt`, `upstream-baseline-comparison.json`: 동일 실패 대조.
- `sandbox-codex/`: 새 설치 기본값 검증용 격리 설치본.
- `native-catalog.jsonl`, `hook-state.json`: 설치 후 실제 카탈로그·훅 상태.
- `synthetic-requests.json`, `synthetic-belay-request.json`: 인증정보 없는 합성 전송 본문.
- `live-python-results.json`, `live-belay-result.json`: 초기 실호출 원본 결과.
- `live-validation.json`: 추가 호출 없는 파서 재검증과 판단 제한 기록.
- `dist/`: 빌드된 sdist와 wheel.

합성 실호출 스크립트 `live_smoke.py`와 `live_belay.mjs`는 기본 실행 시 본문만 준비한다.
`--live`는 각각 최대 4회와 1회의 유료 API 호출을 실행하므로 명시적으로 요청할 때만 사용한다.
다음 품질 검증은 대표 사례를 모아 1.13/1.14의 정확도와 기존 임계값을 별도로 비교하는 것이다.

## 후속 변경: Explore 영어 질문

2026-10-15에 저장소와 전역 설치본의 `jev-explore/SKILL.md`를 수정했다.
Codex가 사용자 의도에서 간결한 영어 검색 질문을 바로 작성하며 범위·제외 조건을 보존한다.
별도 번역 도구나 API 호출은 추가하지 않는다. 식별자·경로·정확한 UI 문구·소스 원문은 유지하고,
한글 코드나 문구 검색에 필요한 원어 키워드는 사용할 수 있다. 사용자에게는 선호 언어로 답한다.

다른 사용처의 고정 질문과 판단 기준은 이미 영어임을 확인했다.
Skill Picker의 사용자 입력, Belay의 작업·답변, 브라우저의 페이지 내용은 원문 그대로다.
이 변경은 에이전트의 질문 작성 지침이며 CLI가 입력 언어를 강제로 변환하거나 차단하지 않는다.
검증 범위는 스킬 validator, 설치본 일치 및 `git diff --check`다. 추가 API 호출은 하지 않았다.
