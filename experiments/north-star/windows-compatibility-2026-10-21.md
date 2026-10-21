# North Star Windows 호환성, 2026-10-21

## 원인과 수정

Windows / Python 3.12.10에서 North Star와 이력 평가 모듈을 로드하면
`ModuleNotFoundError: No module named 'fcntl'`로 종료됐다.
`python -m unittest discover -s tests -p 'test_north_star*.py' -v`로
수정 전 테스트 모듈 2개가 모두 로드 실패함을 재현했다.
새 플랫폼 회귀 검사도 수정 전에 같은 오류로 실패함을 확인했다.

`hooks/north-star/north_star.py`의 OS 의존 코드만 분리했다.

- Windows는 표준 라이브러리 `msvcrt.LK_NBLCK`로 잠금 파일의 첫 바이트를 잠근다.
  macOS/POSIX는 기존 `fcntl.LOCK_EX | LOCK_NB`를 유지한다.
  Windows의 잠금 경합 오류는 기존 호출자와 같은 `BlockingIOError`로 처리한다.
  파일 디스크립터를 닫으면 잠금이 해제된다.
- Windows에 없는 `O_NOFOLLOW`를 직접 참조하지 않는다. 심볼릭 링크 검사와
  열린 디스크립터·경로의 파일 식별 정보 비교 후 잠금·감사 기록에 사용한다.
  해당 플래그가 있는 플랫폼에서는 플래그도 계속 적용한다.
- 상태·감사 JSON은 UTF-8로 기록하고, 설정·입력 JSON의 UTF-8 BOM도 처리한다.
- 일반 Windows 실행에서도 일부 상태 파일 교체에서 간헐적인 `WinError 5`를 관찰했다.
  파일 공유 핸들로 교체를 차단하는 별도 회귀 검사에서도 재현했다.
  정확히 같은 외부 프로세스가 관측된 간헐 오류를 일으켰는지는 확인하지 않았다.
  Windows의 `WinError 5/32/33`에만 교체를 최대 5회 시도한다.
  대기는 10/20/40/80 ms, 합계 150 ms이며 계속 실패하면 오류를 반환한다.
  실패 시 기존 상태를 보존하고 임시 파일을 정리한다.

`scripts/install_north_star.py`는 한글·공백·작은따옴표 경로와 UTF-8 stdin/stdout을
보존하는 PowerShell `EncodedCommand` 및 Python `-X utf8` 명령을 생성한다.
기존 훅 검색은 두 경로 구분자를 인식하며 JSON 입출력 인코딩을 명시한다.
새 설치의 외부 전송은 기존과 같이 기본 비활성화다. 판단 정책·모델·예산은 변경하지 않았다.

## 검증

합성 입력·모의 판단만 사용했고 유료 API 호출은 없다.
임시 파일과 설치 대상은 `.runtime/experiments/north-star-windows-20261021/`에 격리했다.

```powershell
$env:PYTHONUTF8 = '1'
$taskRun = Join-Path $PWD '.runtime/experiments/north-star-windows-20261021'
$env:TMP = Join-Path $taskRun 'tmp'
$env:TEMP = $env:TMP
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_north_star_platform.py -v
git diff --check
```

- 루트 Python 검사: **179개 실행, 176개 통과, 3개 스킵**.
- 새 플랫폼 회귀 검사: **6개 모두 통과**. 생성한 Windows 명령의 실제 훅 5종 실행 포함.
- 실제 별도 프로세스가 잠금 소유 중에는 다른 프로세스의 저장이 즉시 거절되고 상태가 유지됐다.
  정상 종료·예외·잠금 소유 프로세스 강제 종료 후 다시 저장할 수 있었다.
- 기본 UTF-8 모드를 끈 별도 프로세스에서도 한글·이모지 상태와 감사 파일이
  UTF-8로 기록됐고 원문이 보존됐다.
- 대상 파일을 읽는 핸들이 교체를 막을 때 기존 상태는 유지됐다.
  핸들을 해제한 다음 재시도가 성공했고, 영구 거절에서는 오류와 기존 상태를 보존했다.
- 한글·공백·작은따옴표를 포함한 임시 경로에서 설치·재설치, UTF-8 BOM 훅 설정,
  기존 훅 보존과 입력 JSON·CLI 인자 보존을 검증했다.
- 설치본의 실제 생성 명령을 `cmd.exe`로 실행해 `SessionStart`, `UserPromptSubmit`,
  `PreCompact`, `PostCompact`, `Stop`의 종료·출력·bootstrap·체크포인트를 확인했다.
  그때 외부 전송은 비활성이고 합성 transcript만 사용했다.
- `git diff --check`와 수정한 Python 파일 문법 검사 통과.

스킵 3개는 POSIX 권한 비트 검사 1개와 Windows 심볼릭 링크 생성 권한이 없는
환경의 검사 2개다. 심볼릭 링크를 만들 수 있는 Windows 환경에서는 그 2개도 실행된다.
Windows의 `chmod`는 POSIX 모드의 비공개 권한을 보장하지 않으며 파일 접근은 상속된 ACL을 따른다.

## 확인 범위와 결과 파일

이번 결과는 Windows 로컬·프로세스 간 잠금과 격리 설치 실행의 증거다.
macOS는 이 PC에서 실행하지 못했으며 기존 POSIX 잠금 분기는 코드 검토만 했다.
전역 North Star 설치·신뢰 등록 및 Codex 앱의 자동 이벤트 전달은 이번 작업 범위에 포함하지 않았다.
기존의 Jev 판단 정확도·보고 보완 효과를 새로 평가한 결과도 아니다.

로컬 결과 파일은 위 실험 폴더에 보관한다.

- `before.txt`, `regression-before.txt`: 수정 전 import 실패.
- `after-first.txt`, `north-star-tests.txt`, `north-star-tests-native.txt`: 후속 Windows 실패 진단.
- `replace-regression-before.txt`: 교체 대상 읽기 핸들로 유도한 실패.
- `all-python-tests.txt`: 최종 루트 검사 179개 결과.
- `platform-tests.txt`: 실제 생성 훅 명령 실행을 포함한 최신 플랫폼 검사 6개 결과.
