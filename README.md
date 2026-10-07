# Videoagent — 캡컷 자동 편집 에이전트

인터뷰 원본 영상을 넣으면 **컷 편집, 한글/영어 자막, 강조 자막, B롤, BGM이 들어간 CapCut 프로젝트**를 만들어 줍니다.
렌더링 직전 단계까지 자동화하고, 캡컷에서 바로 수정·내보내기할 수 있습니다.

- 대상: Windows + CapCut 9.4.0 (드래프트 = 평문 JSON)
- 방식: 실제 캡컷 프로젝트에서 뽑은 템플릿을 복제해 드래프트 생성 → 캡컷 프로젝트 목록에 자동 등록

## 사용 방식

| 방식 | 비용 | 실행 |
|---|---|---|
| **Claude Code + Pro 계정 (권장)** | Pro/Max 구독에 포함 | `Claude_Code_시작.bat` → `/edit 원본 <이름> <스타일>` |
| Claude API | 사용한 만큼 (영상 1편 약 $0.1~0.3) | `API키_설정.bat` 후 `실행.bat` — 완전 자동 |
| 무료 모드 | 무료 (claude.ai 무료 계정) | `실행_무료.bat` — 편집 계획만 claude.ai 대화창에 복사·붙여넣기 |

받아쓰기·얼굴 검출·캡컷 프로젝트 생성·미리보기는 모든 방식에서 PC가 무료로 처리합니다. 편집 계획(어디를 자르고 자막을 어떻게 쓸지)만 Claude가 합니다.

## Claude Code + Pro 계정으로 쓰기 (권장)

1. `설치.bat` 실행 (Python 패키지·ffmpeg 설치, `/edit` 명령 등록)
2. **`Claude_Code_시작.bat`** 실행 → Claude Code가 없으면 자동 설치 후 이 폴더에서 시작합니다.
   처음이면 브라우저가 열리니 **Claude Pro 계정으로 로그인**하세요.
3. 캡컷을 끄고 Claude Code에 입력:
   - `/edit 원본 1010_인터뷰 talk_short` — 토크형 숏폼
   - `/edit 원본 1010_인터뷰 target 60초로, 계기 위주` — 인터뷰형, 요청 추가
4. Claude가 받아쓰기 → 편집 계획(talk_short는 제목 후보를 물어봄) → 컷 검증 → 캡컷 프로젝트 생성 → 미리보기 확인까지 진행합니다.

- Pro 구독 사용량 한도 안에서 추가 비용 없이 쓸 수 있습니다. 한도에 걸리면 잠시 후 다시 하세요.
- 이 PC에 `ANTHROPIC_API_KEY`가 설정돼 있으면 Claude Code가 그 키를 쓸지 묻습니다. **No**를 골라야 API 요금이 아니라 Pro 구독으로 처리됩니다.
- 터미널 대신 화면으로 쓰고 싶으면 Claude 데스크톱 앱의 **Code** 탭에서 이 폴더를 열어도 같습니다.
- Git for Windows를 설치해 두면 Claude Code가 더 안정적으로 명령을 실행합니다(선택).

## 무료 모드 (claude.ai 무료 계정)

1. 캡컷을 끄고 **`실행_무료.bat`** 실행 → 이름 / 스타일 / 목표 길이 / 요청 입력
2. 분석이 끝나면 프롬프트가 **클립보드에 복사**되고 claude.ai 새 대화가 열립니다 → `Ctrl+V`로 붙여넣고 보내기
3. 답변 아래 **복사** 버튼 → 자동으로 열리는 메모장에 붙여넣고 **저장 후 닫기**
4. 계획을 자동으로 검사합니다. 문제가 있으면 고칠 내용이 클립보드에 복사되니, 같은 대화에 보내고 새 답변을 다시 붙여넣으세요.
5. 캡컷 프로젝트와 미리보기가 만들어집니다.

- 원본 5분 기준 프롬프트는 약 5천 자입니다. 원본이 아주 길면(30분 이상) 무료 플랜에서 잘릴 수 있으니 나눠서 진행하세요.
- claude.ai 무료 플랜은 사용량 한도가 있습니다. 한도에 걸리면 잠시 후 다시 하세요.

## Claude API로 쓰기 (Claude Code 없이)

`실행.bat` 하나로 받아쓰기 → **Claude가 편집 계획** → 캡컷 프로젝트 생성 → 미리보기까지 자동으로 진행합니다.

1. [console.anthropic.com](https://console.anthropic.com)에서 API 키를 발급받고 크레딧을 충전합니다(결제 수단 등록 필요).
2. **`API키_설정.bat`** 실행 → 키를 붙여넣으면 이 PC에 저장되고 연결을 바로 확인합니다.
   (키는 폴더가 아니라 PC 환경변수에 저장됩니다. 다른 PC에서는 그 PC에서 다시 설정하세요.)
3. 캡컷을 끄고 **`실행.bat`** → 이름 / 스타일(1=인터뷰, 2=토크 숏폼) / 목표 길이 / 요청 / 멀티캠 여부 입력
4. 끝나면 미리보기 이미지가 열리고, 캡컷 목록 맨 앞에 프로젝트가 생깁니다.

- 기본 모델은 `claude-opus-5-5`입니다. 바꾸려면 환경변수 `CAPCUT_AGENT_MODEL`을 설정하세요(예: `claude-sonnet-5-5`).
- 비용은 영상 1편(원본 5분 안팎) 기준 대략 $0.1~0.3입니다. 실행이 끝나면 실제 토큰 수와 예상 비용이 표시됩니다.
- Claude가 낸 계획은 자동으로 검사합니다(클립 경로, 컷 시간, 자막, 제목). 문제가 있으면 오류를 알려 주고 한 번 다시 받습니다. 응답 원문은 `work\<이름>\edit_plan_raw.txt`에 남습니다.
- 설치나 설정에 문제가 있는지는 `python capcut_agent\agent.py check`로 점검합니다.

## 폴더로 전달받은 경우 (GitHub 없이)

이 폴더를 통째로 복사해서 받았다면 아래만 하면 됩니다.

1. **Python 3.10 이상** 설치 (설치 화면에서 "Add python.exe to PATH" 체크)
2. **CapCut 데스크톱** 설치 후 한 번 실행 (9.4.0 권장)
3. 폴더 안의 **`설치.bat`** 더블클릭 → ffmpeg와 필요한 패키지 설치, Claude Code 명령(`claude_commands` → `.claude\commands`) 등록
4. `원본` 폴더에 인터뷰 영상, (선택) `B롤`, `BGM` 폴더에 파일 넣기
5. **캡컷을 끄고** 사용
   - **Claude Code + Pro 계정(권장):** `Claude_Code_시작.bat` → `/edit 원본 <프로젝트이름> talk_short` (위 "Claude Code + Pro 계정으로 쓰기" 참고)
   - **무료:** `실행_무료.bat` (위 "무료 모드" 참고)
   - **Claude API:** `API키_설정.bat`으로 키를 한 번 등록한 뒤 `실행.bat` 더블클릭 (위 "Claude API로 쓰기" 참고)
6. 캡컷을 열면 목록 맨 앞에 새 프로젝트가 있습니다.

캡컷 버전이 9.4.0이 아니면, 그 캡컷에서 아무 프로젝트나 하나 만들어 저장한 뒤 이렇게 실행해 템플릿을 다시 뽑으세요.
`python capcut_agent\make_template.py "%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<그 프로젝트 이름>"`

## 빠른 시작 (Windows, GitHub)

```
git clone https://github.com/kck713/Videoagent
cd Videoagent
scripts\setup.bat            :: ffmpeg + faster-whisper + anthropic + opencv 설치
```
1. 레포 루트에 `원본\`(인터뷰 원본), `B롤\`(선택, 같은 이름 .txt로 설명), `BGM\`(선택) 폴더를 만들고 파일을 넣습니다.
2. **캡컷을 종료**한 뒤 `scripts\run.bat` 실행 → 이름/목표 길이/요청 입력
3. 캡컷을 열면 목록 맨 앞에 새 프로젝트가 있습니다.

Claude API 키(`ANTHROPIC_API_KEY`)가 없으면 편집 계획 단계는 프롬프트 파일만 만듭니다.
**Claude Code에서는 키 없이** `/edit <원본폴더> <이름> [요청]`으로 Claude가 직접 계획을 짭니다.

## 스타일

기본은 `target` 프리셋입니다([docs/target-style.md](docs/target-style.md)). 9:16 꽉 채움, 얼굴 기준 크롭, 클로즈업/미디엄 교차, 흰/노랑 한글 자막, 검정 박스 라벨, 엔딩 카드를 씁니다.
토크형 빠른 숏폼은 `--style talk_short`입니다. 상단 고정 제목(자동 제안), 테두리, 괄호 자막, 이름표, 면책 문구, 빠른 컷이 들어갑니다. 여러 카메라로 찍었다면 `analyze --multicam`을 씁니다.
예전 1006 가편집 스타일(한/영 자막, 위아래 여백)은 `--style interview_1006` 옵션으로 씁니다. 미리보기는 `python capcut_agent/preview.py <드래프트 폴더>`로 만듭니다.

## 파이프라인

| 단계 | 파일 | 내용 |
|---|---|---|
| 분석 | `analyze.py` | 미디어 정보, Whisper 전사(단어 시간), 무음 구간 |
| 계획 | `planner.py` / Claude Code | NG·필러 제거, 컷 선택, 자막 줄 나누기, 의역, 강조, B롤 배치 |
| 타이밍 | `subtimer.py` | 컷 경계를 실제 말 시작/끝에 보정, 자막을 발화·숨 지점에 맞춰 배분 |
| 생성 | `capcut_draft.py` | 캡컷 프로젝트 폴더 + 목록 등록 (생성 전 검증, 목록 백업) |

명령:
```
python capcut_agent/agent.py run     --clips 원본 --broll B롤 --name 1007_인터뷰 --target 60 --brief "..."
python capcut_agent/agent.py analyze --clips 원본 --work work/1007
python capcut_agent/agent.py plan    --work work/1007 --brief "..."
python capcut_agent/agent.py build   --work work/1007 --name 1007_인터뷰 [--bgm BGM\song.mp3]
python tests/test_build.py
```

## 문서

- [docs/target-style.md](docs/target-style.md) — 목표 결과물 스타일과 로드맵
- [docs/capcut-draft-format.md](docs/capcut-draft-format.md) — 캡컷 9.4.0 드래프트 포맷 메모
- [docs/progress.md](docs/progress.md) — 진행 기록
- [CLAUDE.md](CLAUDE.md) — Claude Code 작업 지침

## 주의

- 생성 전 캡컷을 반드시 종료하세요(실행 중이면 종료할 때 프로젝트 목록을 덮어씀).
- 캡컷 업데이트로 포맷이 바뀌면 새 버전에서 저장한 프로젝트로 `make_template.py`를 다시 실행하세요.
- 노이즈 제거·시선 보정·스마트 색보정은 캡컷에서 원클릭으로 적용하세요(미디어 분석에 묶여 복제 불가).
