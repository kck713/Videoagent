# Videoagent — 캡컷 자동 편집 에이전트

인터뷰 원본 영상을 넣으면 **렌더링 직전 단계의 CapCut 프로젝트(드래프트)**를 자동으로 만드는 에이전트입니다.
사용자가 Windows + CapCut 9.4.0에서 사용합니다. 응답과 문서는 **한국어**로 작성합니다.

## 목표

- 최종 목표 스타일: `docs/target-style.md` (목표 샘플 분석, 측정값, 로드맵). **새 기능은 이 문서의 로드맵 순서를 따른다.**
- 캡컷 포맷 지식: `docs/capcut-draft-format.md`. 포맷을 건드리기 전에 반드시 읽는다.
- 지금까지의 진행과 결정: `docs/progress.md`. 작업을 마치면 여기에 한 줄씩 추가한다.

## 구조

```
capcut_agent/
  agent.py          CLI (run | analyze | plan | build) + build_from_plan()
  analyze.py        ffprobe + faster-whisper 전사(단어 타임스탬프) + 무음 구간 → work/<이름>/analysis.json
  planner.py        Claude API로 편집 계획 생성 (SYSTEM 프롬프트 = 편집 원칙). 키 없으면 프롬프트 파일만 출력
  subtimer.py       컷 경계를 음성 에너지로 보정 + 자막 줄(lines)을 발화 시간/숨 지점에 맞춰 자동 배분
  capcut_draft.py   Draft 클래스: template_pack.json 복제 방식으로 세그먼트/머티리얼 생성, 검증, 저장, 목록 등록
  make_template.py  실제 캡컷 프로젝트에서 template_pack.json 추출 + sanitize
  style.json        자막/강조/BGM/화면 배치 스타일
examples/edit_plan_example.json   합성 예시 플랜
tests/test_build.py               스모크 테스트 (미디어/캡컷 없이 실행)
scripts/setup.bat, run.bat        Windows 원클릭 설치/실행 (원본/, B롤/, BGM/ 폴더는 레포 루트에, gitignore)
```

## 파이프라인과 edit_plan.json

1. `analyze` → `analysis.json` (clips[].transcript[{start,end,text,words}], silences, broll[], media{})
2. 편집 계획 → `edit_plan.json`
   - `main[]`: `{src, in, out, lines:[{ko, en, emphasis, highlight[]}]}` — in/out은 **원본 클립 시간**, 순서대로 이어 붙음
   - `lines`에는 시간을 적지 않는다. build 시 `subtimer.apply()`가 `subs[]`(start/end 포함)로 변환
   - `broll[]`: `{src, at(타임라인 초), dur, in, fit:"fill"}` / `bgm`: `{src, volume, fade_out}` / `layout`: `{scale, x, y}`
3. `build` → 캡컷 프로젝트 폴더 + `root_meta_info.json` 등록 (등록 전 자동 백업)

## Claude Code에서 작업하는 법

- **편집 실행:** `/edit <원본폴더> <프로젝트이름> [요청]` — Claude가 직접 플래너 역할을 한다(API 키 불필요). `.claude/commands/edit.md` 참고
- **결과 검증:** `/verify-draft <프로젝트이름>` — 캡컷이 연 뒤 다시 저장한 파일과 비교
- **테스트:** `python tests/test_build.py` (빌더를 고치면 반드시 실행)
- 플랜을 손으로 고치고 `python capcut_agent/agent.py build --plan <경로> --name <새이름>`으로 재생성할 수 있다(같은 이름은 거부됨 → 새 이름 사용).

## 반드시 지킬 것

- **캡컷이 실행 중이면 드래프트를 쓰지 않는다.** 사용자에게 종료를 요청한다(종료 시 목록 파일을 덮어씀).
- 사용자의 기존 캡컷 프로젝트(예: `0915`)는 읽기만 한다. 수정·삭제 금지.
- **이 레포는 public이다.** 원본/결과 영상, 전사 텍스트, 인터뷰 대상자 정보, 사용자 PC 경로·장치 ID를 커밋하지 않는다. `work/`, `원본/`, `B롤/`, `BGM/`, `samples/`는 gitignore. 템플릿을 다시 뽑으면 `sanitize()`가 적용됐는지 테스트로 확인한다.
- 미디어 분석에 묶인 부가 머티리얼(loudness, vocal_beautify, smart_relight, effects, denoise, beats)은 복제하지 않는다.
- 새 세그먼트 종류를 추가할 때는 **캡컷에서 실제로 그 기능을 쓴 프로젝트를 저장 → JSON을 보고 복제**한다. 추측으로 필드를 만들지 않는다.

## 편집 원칙 (요약 — 전문은 planner.py SYSTEM)

- NG 테이크는 마지막 매끄러운 테이크만, 반복·필러("어", "음")·0.3초 넘는 무음 제거, 한 컷 최소 1초
- 같은 테이크에서 이어지는 문장(0.5초 이하 숨)은 한 컷으로 묶는다
- 자막 한 줄 8~16자, 음성인식 오타는 문맥으로 교정, 말버릇은 자막에서 뺌
- 영어는 직역 금지(관용구는 의미로). 목표 스타일은 **한글만**이므로 `target` 프리셋에서는 영어 생략
- 흐름: 훅 → 고민/경험 → 계기 → 메시지 → 엔딩 한마디

## 알려진 이슈

- 클라우드 샌드박스에서는 Hugging Face가 막혀 faster-whisper 모델을 받을 수 없다. 이때는 GitHub `k2-fsa/sherpa-onnx` 릴리스의 `sherpa-onnx-whisper-turbo`로 대체했다(음절 누락이 잦음). 사용자 PC에서는 faster-whisper `large-v3` 권장
- 자막 타이밍은 글자 수 비례 + 숨 지점 스냅 방식이라 줄마다 0.2~0.3초 오차가 날 수 있다. 개선안: faster-whisper 단어 타임스탬프로 줄 경계를 직접 정하기
- 화면 배치는 고정값(`layout`)이다. 얼굴 위치 기반 자동 크롭/펀치인은 로드맵에 있다
