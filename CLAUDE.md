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
  planner.py        Claude API로 편집 계획 생성 (SYSTEM 프롬프트 = 편집 원칙, 스트리밍 호출, validate_plan 검사 후 1회 재시도, 비용 표시). 키 없으면 프롬프트 파일만 출력
  subtimer.py       컷 경계를 음성 에너지로 보정 + 자막 줄(lines)을 발화 시간/숨 지점에 맞춰 자동 배분(+단어 타임스탬프 부착)
  motion.py         모션 그래픽: 캡컷 키프레임(common_keyframes) 생성 — 팝/페이드/슬라이드/켄 번스/단어 단위 등장(reveal)
  capcut_draft.py   Draft 클래스: template_pack.json 복제 방식으로 세그먼트/머티리얼 생성, 검증, 저장, 목록 등록
  make_template.py  실제 캡컷 프로젝트에서 template_pack.json 추출 + sanitize
  preview.py        드래프트 대략 미리보기(스틸 컷 모음) — 캡컷 없이 구도/자막/라벨 확인
  assets.py         스타일 그래픽 PNG 생성(테두리, 강조 원, 카드 배경 띠/그라데이션) — 캡컷 도형/스티커 대신 사진 오버레이로 사용
  sync.py           멀티캠 오디오 동기화(카메라 간 오프셋)
  styles/target.json         목표 스타일(기본): 9:16 꽉 채움 + 얼굴 기준 크롭(배율 고정), 흰/노랑 자막, 라벨, 훅 카드, 메시지 카드, 엔딩 카드, 모션
  styles/talk_short.json     토크형 빠른 숏폼(샘플 2): 상단 고정 제목, 테두리, 괄호 자막, 이름표, 면책, 빠른 컷(tighten)
  styles/interview_1006.json 1006 가편집 스타일(가로 원본 + 위아래 여백, 한/영 자막)
examples/edit_plan_example.json   합성 예시 플랜
tests/test_build.py               스모크 테스트 (미디어/캡컷 없이 실행)
scripts/setup.bat, run.bat        Windows 원클릭 설치/실행 (원본/, B롤/, BGM/, SFX/ 폴더는 레포 루트에, gitignore)
```

## 파이프라인과 edit_plan.json

1. `analyze` → `analysis.json` (clips[].transcript[{start,end,text,words}], silences, broll[], media{}, faces{src:{x,y,h,track}})
2. 편집 계획 → `edit_plan.json`
   - `main[]`: `{src, in, out, zoom?, lines:[{ko, role, highlight[], label?, en?}]}` — in/out은 **원본 클립 시간**, 순서대로 이어 붙음
     - `role`: normal(흰) / quote(노랑) / emphasis(크게) / alert(빨강) / aside(괄호 해설)
     - `label`: 그 줄 동안 자막 위에 뜨는 검정 박스 맥락 라벨
     - `zoom`: 쓰지 않음(사용자 요청으로 펀치인 줌 제거, 배율 1.0 고정). 극단 확대(`focus`)에만 사용. 얼굴 위치는 컷 구간의 face track으로 계산
   - `lines`에는 시간을 적지 않는다. build 시 `subtimer.apply()`가 `subs[]`(start/end 포함, 단어 타임스탬프 `words`)로 변환
   - **훅·메시지 장치(v0.5):** `key_message`(영상이 남길 한 문장) / `hook {text, sub?}`(첫 2.8초 상단 훅 카드, 스타일에 `hook_card`가 있을 때. talk_short는 title.line2가 훅이라 생략) / `message_cards [{at, dur, text, highlight[]} | {at, dur, kind:"stat", value, caption}]`(화면 띠 위 큰 글씨 카드, `replace_subs: true`면 그 구간 자막 대체)
   - 모션은 플랜이 아니라 **스타일 `motion`**이 결정한다(역할별 팝, reveal_roles=단어 단위 등장, 라벨 슬라이드, 카드 페이드, 이미지 B롤 켄 번스). 플랜 `motion: false`나 줄별 `reveal: false`로 끌 수 있다
   - 효과음: 레포 루트 `SFX/`(또는 `--sfx`)에 `pop*`, `hit*`, `whoosh*` 파일이 있으면 훅·카드·emphasis/alert에 자동 배치(스타일 `sfx`). 플랜 `sfx [{at, kind|src}]`로 직접 지정도 가능
   - `broll[]`: `{src, at(타임라인 초), dur, in, fit: fill|fit|pip, pip{scale,x,y}?, caption?, ai?(상단 "AI로 생성한 이미지" 라벨), top_label?}` — 이미지(.png/.jpg)는 photo 세그먼트
   - `labels[]`: `{text, at, dur, kind: context|top}` / `ending`: `{text, dur}` / `broll_ideas[]`: 재연 이미지 아이디어(생성용 프롬프트)
   - `style`: 프리셋 이름(기본 `target`) / `bgm`: `{src, volume, fade_out}` / `layout`: 프리셋 덮어쓰기
   - talk_short 등: `title {line1, line2}`(플래너가 제안), `speakers {"A": {name, title}}` + `main[].speaker`, `disclaimer`, `sticker_notes [{at, text}]`
   - 극단 확대: `main[].focus {x,y}`(원본 좌표) + `zoom` 2~2.5, `callouts [{at, dur, x, y}]`(화면 좌표, 노란 원)
   - 멀티캠: analyze `--multicam` → `sync {src: offset}`; 컷별 `main[].angle`에 다른 카메라 src (in/out·자막은 기준 카메라 시간)
   - 스타일의 `tighten {max_pause, max_cut}`이 있으면 build 때 숨 제거(+선택: 긴 컷 분할)를 자동 적용. talk_short는 숨 제거만
3. `build` → 캡컷 프로젝트 폴더 + `root_meta_info.json` 등록 (등록 전 자동 백업)

## Claude Code에서 작업하는 법

- **편집 실행:** `/edit <원본폴더> <프로젝트이름> [요청]` — Claude가 직접 플래너 역할을 한다(API 키 불필요). `.claude/commands/edit.md` 참고
- **계획 점검:** `python capcut_agent/agent.py critique --work work/<이름>` — 훅 패턴·첫 컷 길이·key_message·메시지 카드·강조 개수·라벨·템포·자막 길이를 점검해 경고 목록 출력. **플랜을 쓴 뒤 반드시 실행하고 경고를 해소한다**
- **결과 검증:** `/verify-draft <프로젝트이름>` — 캡컷이 연 뒤 다시 저장한 파일과 비교. 키프레임은 `python capcut_agent/make_template.py --inspect <캡컷이 저장한 프로젝트>`로 실제 포맷과 비교
- **테스트:** `python tests/test_build.py` (빌더를 고치면 반드시 실행)
- **환경 점검:** `python capcut_agent/agent.py check` (패키지·ffmpeg·캡컷 폴더/버전·API 키 연결)
- **Claude Code 시작:** `scripts/claude_code.bat`(루트 `Claude_Code_시작.bat`) — 없으면 공식 설치 프로그램으로 설치 후 이 폴더에서 실행. 사용자는 Pro 계정으로 로그인해서 쓴다(권장 방식)
- **무료 모드:** `scripts/run_free.bat` — analyze → `plan --prompt-only`(단어 타임스탬프 생략한 짧은 프롬프트) → `agent.py clip`으로 클립보드 복사 → 사용자가 claude.ai에서 받은 답을 메모장으로 붙여넣기 → `agent.py import-plan`(JSON 추출·validate·정리, 실패 시 `edit_plan_fix.txt`) → build
- **API 모드:** `scripts/set_api_key.bat`(키를 PC 환경변수에 저장) → `scripts/run.bat`. 모델은 `CAPCUT_AGENT_MODEL`(기본 claude-opus-5-5). 계획 생성 뒤 **편집장 리뷰 패스**(critique 결과를 붙여 훅·메시지·템포 강화)가 한 번 더 돈다(`--no-review`로 생략)
- **미리보기:** `python capcut_agent/preview.py <드래프트폴더> --out preview.jpg` → 이미지를 직접 보고 구도·자막 위치를 확인한 뒤 사용자에게 넘긴다
- 플랜을 손으로 고치고 `python capcut_agent/agent.py build --plan <경로> --name <새이름>`으로 재생성할 수 있다(같은 이름은 거부됨 → 새 이름 사용).

## 반드시 지킬 것

- **펀치인 줌(컷마다 배율 교차)은 쓰지 않는다** (2026-10-07 사용자 요청).

- **캡컷이 실행 중이면 드래프트를 쓰지 않는다.** 사용자에게 종료를 요청한다(종료 시 목록 파일을 덮어씀).
- 사용자의 기존 캡컷 프로젝트(예: `0915`)는 읽기만 한다. 수정·삭제 금지.
- **이 레포는 public이다.** 원본/결과 영상, 전사 텍스트, 인터뷰 대상자 정보, 사용자 PC 경로·장치 ID를 커밋하지 않는다. `work/`, `원본/`, `B롤/`, `BGM/`, `samples/`는 gitignore. 템플릿을 다시 뽑으면 `sanitize()`가 적용됐는지 테스트로 확인한다.
- 미디어 분석에 묶인 부가 머티리얼(loudness, vocal_beautify, smart_relight, effects, denoise, beats)은 복제하지 않는다.
- 새 세그먼트 종류를 추가할 때는 **캡컷에서 실제로 그 기능을 쓴 프로젝트를 저장 → JSON을 보고 복제**한다. 추측으로 필드를 만들지 않는다.

## 편집 원칙 (요약 — 전문은 planner.py SYSTEM)

- **순서:** key_message 한 문장 → 훅 후보 3개(질문/숫자/반전·대비/고백/경고 패턴) 비교 후 선택(콜드 오픈 허용) → 컷 선택. 첫 컷은 4초 이내, 인사·자기소개 금지
- 강조의 경제: emphasis 3~5, alert 0~2, message_cards 1~2, 엔딩은 key_message 재진술
- NG 테이크는 마지막 매끄러운 테이크만, 반복·필러("어", "음")·0.3초 넘는 무음 제거, 한 컷 최소 1초
- 같은 테이크에서 이어지는 문장(0.5초 이하 숨)은 한 컷으로 묶는다
- 자막 한 줄 8~16자, 음성인식 오타는 문맥으로 교정, 말버릇은 자막에서 뺌
- 영어는 직역 금지(관용구는 의미로). 목표 스타일은 **한글만**이므로 `target` 프리셋에서는 영어 생략
- 흐름: 훅 → 고민/경험 → 계기 → 메시지 → 엔딩 한마디

## 알려진 이슈

- 클라우드 샌드박스에서는 Hugging Face가 막혀 faster-whisper 모델을 받을 수 없다. 이때는 GitHub `k2-fsa/sherpa-onnx` 릴리스의 `sherpa-onnx-whisper-turbo`로 대체했다(음절 누락이 잦음). 사용자 PC에서는 faster-whisper `large-v3` 권장
- 자막 타이밍은 글자 수 비례 + 숨 지점 스냅 방식이라 줄마다 0.2~0.3초 오차가 날 수 있다. 개선안: faster-whisper 단어 타임스탬프로 줄 경계를 직접 정하기
- 얼굴 검출은 OpenCV Haar(정면 얼굴)라 옆모습·가림에 약하다. 못 찾으면 가운데 기준으로 크롭한다
- 자막 글꼴은 캡컷 기본 시스템 폰트다. 목표 샘플의 둥근 손글씨체는 캡컷에서 폰트를 받은 뒤 그 경로를 styles/*.json `font_path`에 넣어야 한다
- 텍스트 외곽선(strokes)은 캡컷에서 아직 검증 전이라 그림자만 쓴다
- **키프레임 모션(motion.py)은 캡컷 9.4.0 재저장 검증 전**(2026-10-08). 포맷은 JianYing/CapCut 드래프트에서 널리 쓰이는 형식(pyJianYingDraft)과 같다. 캡컷이 열지 못하면 스타일 `motion.enabled: false`로 끄고, 캡컷에서 키프레임을 찍은 프로젝트를 `make_template.py --inspect`로 비교해 포맷을 맞춘다
- 캡컷 내장 텍스트 애니메이션·트랜지션·스티커는 서버 리소스 ID가 필요해 자동 삽입 불가 → 키프레임 + 생성 PNG(assets.py)로 대체
- 장식 텍스트(라벨·제목·엔딩·이름표)는 반드시 `type: "text"` — `subtitle`이면 캡컷 자막 일괄 편집에 같이 덮어써진다(group_id 없으면 자동으로 text)
- 캡컷 스티커/이모지는 자동 삽입 불가(서버 리소스 ID 필요). `sticker_notes`로 위치만 남긴다
