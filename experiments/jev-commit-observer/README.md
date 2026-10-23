# Jev 커밋 관찰기, 첫 단계

작업 단위의 실제 검사가 끝난 뒤 **커밋했을 단위·파일·메시지와 보류 사유**를 기록한다. 관찰기 자체는 Git 읽기 명령만 사용한다. add, commit, push, reset 기능과 전역 훅 설치는 없다.

첫 버전에서는 주 에이전트가 단위를 등록하고 `check`를 실행한다. 임의 작업에서 단위를 자동 발굴하거나 Codex 도구 호출을 상시 감시하는 버전은 아니다. 앞선 [기획·공개 소스 조사](../jev-commit-research-20261023/README.md)의 관찰 모드에 해당한다.

## 바로 실행하는 합성 데모

저장소 루트에서 실행한다. Python 3.12+와 Git을 사용하며 별도 패키지는 필요 없다.

```sh
python3 experiments/jev-commit-observer/demo.py
python3 experiments/jev-commit-observer/demo.py --live
```

첫 명령은 API를 부르지 않는다. 두 번째 명령만 TypeSafe Jev를 최대 **3회** 호출하며 합성 소스·단위 설명·후보 diff·검사 상태만 보낸다. 실제 프로젝트 소스나 대화를 읽어 전송하지 않는다. 기존 `TYPESAFE_API_KEY` 또는 `JEV_API_KEY`, 비공개 `~/.config/typesafe/env`, Windows 사용자 환경변수 순으로 기존 자격증명을 사용하며 새 키 파일을 만들지 않는다.

데모는 `.runtime/experiments/jev-commit-observer/demo-<ID>/`에 합성 저장소와 결과를 남긴다. 각 합성 저장소에 초기 기준 커밋을 만드는 것은 **fixture 준비 단계**다. 그 뒤 관찰 전후 HEAD·index 바이트·파일 상태가 보존되는지 확인한다. 원래 프로젝트에는 커밋하지 않는다.

## 실제 작업 단위에 연결하기

1. 시작할 작업 저장소가 깨끗한 상태일 때 [example-plan.json](example-plan.json)을 작업에 맞춰 준비한다. `title`, `message`, `acceptance`, 명시적인 상대 파일 경로 `files`, 검사 argv 배열 `checks`가 필요하다. 비밀정보를 계획이나 명령 인자에 넣지 않는다.
2. 작업 시작 전에 `begin`으로 기준 상태를 저장한다. 이미 다른 변경이나 staging이 있으면 이후 관찰은 보류한다. 기존 세션을 덮어쓰지 않으며 다음 단위는 새 세션 이름을 쓴다.
3. 에이전트가 단위를 수정한 뒤 `check`를 실행한다. 이 명령이 등록한 검사 프로그램을 실행하고 그 결과로 관찰한다. 검사 명령은 shell 문자열이 아닌 argv이며 `{python}`은 현재 Python 실행 경로로 치환된다. **검사 프로그램은 실행 가능한 코드**이므로 검토한 명령만 등록한다. 테스트가 스스로 수행하는 부작용까지 관찰기가 차단하지는 않는다.

```sh
python3 "<JEV_DEMO>/experiments/jev-commit-observer/observer.py" begin --root "<TARGET_REPO>" --session pricing-01 --plan "<PLAN_JSON>"
python3 "<JEV_DEMO>/experiments/jev-commit-observer/observer.py" check --root "<TARGET_REPO>" --session pricing-01
```

Windows에서는 `python3` 대신 `python`을 사용하고 경로를 따옴표로 감싼다. 계획의 파일 경로는 OS와 무관하게 `src/feature.py`처럼 슬래시를 사용한다. glob, 상위 경로, 절대 경로는 받지 않는다.

오프라인 결과는 의미 판단 전이면 `awaiting_judgment`다. **동의한 프로젝트의 단위·후보 diff를 TypeSafe로 전송할 때만** 아래 두 플래그를 함께 지정한다. 두 플래그 중 하나라도 빠지면 호출하지 않는다.

```sh
python3 "<JEV_DEMO>/experiments/jev-commit-observer/observer.py" check --root "<TARGET_REPO>" --session pricing-01 --live --allow-diff-export
```

이미 검사한 상태를 재관찰하려면 `observe`를 사용한다. 동일 상태·동일 판단 모드의 결과는 재사용하여 중복 호출하지 않는다. API 오류도 자동 재시도하지 않으며 한 세션은 최대 **8회** 시도한다. HTTP timeout은 **8초**, 각 검사 timeout은 **30초**다. 고정 목적지는 `https://api.typesafe.ai/v1/systemone`이고 리다이렉트를 따르지 않는다. ambient endpoint override는 사용하지 않는다.

## 결과와 사람 평가

출력 JSON과 세션 디렉터리의 `observations.jsonl`에서 다음을 확인한다.

- `would_commit`: 로컬 조건과 임시 Jev 임계값을 통과한 **관찰상의 추천**. 실제 커밋·배포·성공 판정이 아니다.
- `hold`: 보류. `reasons`에 변경 혼입, 검사 실패·재수정, API 오류, 의미 판단 미달 등 코드로 정한 사유를 남긴다.
- `awaiting_judgment`: 로컬 검사는 통과했지만 외부 의미 판단을 하지 않은 상태다.

`candidate_files`, `excluded_files`, `suggested_message`, 검사별 종료 상태, 변경 fingerprint, 확률과 호출 metrics를 기록한다. 소스·diff·검사 stdout/stderr·인증 헤더는 결과 로그에 남기지 않는다. 세션 파일에는 등록한 계획과 검사 argv가 포함된다. 런타임 파일은 Git에서 제외되는 `.runtime/experiments/jev-commit-observer/<세션>/`에 저장한다.

최근 관찰에 사람 라벨을 붙여 비교할 수 있다. `accept`는 이 단위로 커밋할 수 있음, `defer`는 보류, `unsure`는 판단 불가다.

```sh
python3 "<JEV_DEMO>/experiments/jev-commit-observer/observer.py" review --root "<TARGET_REPO>" --session pricing-01 --label accept
```

Jev에는 완료 근거, 단일 목적에 속하는지, 메시지의 적합성, 남은 관련 작업을 각각 Noul로 묻는다. 임시 추천 조건은 앞의 세 확률이 각각 **0.85 이상**, 남은 관련 작업이 **0.15 이하**다. 측정으로 보정한 정확도 기준이 아니며 실제 자동 커밋 권한으로 사용할 수 없다. Noul에는 별도의 confidence 필드가 없다. [공식 API](https://docs.typesafe.ai/api/system-one), [Noul](https://docs.typesafe.ai/primitives/noul)

## 보류 조건과 한계

- 시작 전 변경, 기존 staging, merge/rebase/cherry-pick 진행, detached HEAD, 기준 HEAD/branch 변경은 보류한다. 작업 도중 외부 파일이 추가돼도 보류한다. 같은 파일의 다른 작성자 변경을 분리해 주지는 않는다.
- 검사가 성공했더라도 실행 중 파일이 바뀌었거나 이후 다시 수정되면 보류한다. Jev 응답이 오는 동안 상태가 바뀌어도 추천을 폐기한다. 검사와 모델 호출을 거친 작업 트리 관찰이며, 별도 격리 트리에서의 재현성 검증은 아니다.
- `.env`, 자격증명·secret 경로, 비공개 키, 빌드·의존성 디렉터리 등을 후보에서 제외한다. symlink/submodule, 비텍스트, 파일별 diff 16,000 bytes 초과, 전체 요청 32,000 bytes 초과는 일부만 잘라 보내지 않고 보류한다.
- 전송 전 비밀정보 패턴과 현재 사용 중인 인증키의 포함 여부를 검사한다. 모든 비밀정보를 탐지한다고 보장하지 않는다. 전체 대화, GBrain 기억, 기존 Belay transcript는 읽거나 전송하지 않는다.
- 세션별 잠금과 상태 fingerprint는 뒤늦은 결과 적용을 막지만, 다른 편집기·에이전트의 쓰기 자체를 막지는 않는다. 이 버전은 파일 단위 후보와 단일 작업자를 전제로 한다.
- `check`의 정상 종료 코드 0은 관찰을 완료했다는 뜻이다. 검사 성공 여부는 `checks`, 추천 여부는 `decision`을 읽는다. 도구 설정/읽기 오류는 종료 코드 2다.

## 2026-10-23 검증 기록

환경: macOS, Python 3.14.7, Jev `jev-1.14.0`. 실제 Windows 실행은 미검증이다.

실제 Jev 호출 **3회**, 입력 **2,576 tokens**, 출력 **216 tokens**를 관찰했다. 모델 요청 대기 시간은 각각 200/176/177ms이며 전체 명령 실행 시간이나 청구 금액은 아니다.

| 합성 사례 | 관찰 | 핵심 근거 |
| --- | --- | --- |
| 완성된 음수 수량 검사 | hold | 완료 0.78로 임시 기준 0.85 미달. 사전에 정한 추천 기대 결과와 불일치 |
| TODO만 남기고 양수 테스트만 통과 | hold | 완료 0.01, 남은 관련 작업 0.97 |
| 무관한 홈페이지 배너 변경 혼합 | hold | 응집성 0.02, 메시지 적합성 0.11 |
| 검사 뒤 재수정 | hold, API 호출 없음 | 로컬 fingerprint 불일치 |

4개 기대 결과 중 3개가 일치했다. **완료 사례의 과도한 보류 1건을 그대로 기록**하며 그 결과에 맞춰 임계값을 낮추지 않았다. 작은 합성 표본이며 실무 정확도를 뜻하지 않는다. 모든 사례에서 관찰 전후 HEAD·index·작업 트리를 보존했다.

실호출 원본 결과: `.runtime/experiments/jev-commit-observer/demo-865798b98175/results.json`. 재실행은 새 디렉터리를 만들며 이전 결과를 덮어쓰지 않는다.

오프라인 검사 명령:

```sh
python3 -m unittest discover -s tests -p test_jev_commit_observer.py -v
env TMPDIR=/private/tmp python3 -m unittest discover -s tests -v
git diff --check
```

전용 테스트 **18/18 통과**. 전체 테스트는 **234개 중 221개 통과, 13개 skip**이다. 전용 검사에는 실제 CLI 흐름, 한글 UTF-8 출력, 중복 호출 억제, 비밀정보 전송 억제, 기존 staging 보존과 모델 응답 중 재수정 폐기가 포함된다.

기존 테스트는 macOS의 `/var`와 `/private/var` 경로 비교 때문에 기본 임시 디렉터리에서 5건 실패했다. 기존 코드는 수정하지 않고 물리 경로인 `/private/tmp`로 재실행해 통과를 확인했다. Windows 전용 검사는 이 환경에서 skip되며 Windows 검증 완료로 세지 않는다.

검증 상태: **오프라인 + 합성 API 실호출 완료**. 전역 설치, Codex native hook 자동 전달, 실제 프로젝트에서의 상시 관찰, 자동 커밋은 미실행이다. 다음 평가는 사람 라벨을 더 모아 과도한 보류와 파일 혼입을 측정하는 것이다.
