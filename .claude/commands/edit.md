---
description: 원본 인터뷰 폴더로 캡컷 가편집 프로젝트를 만든다 (Claude가 직접 편집 계획)
argument-hint: <원본폴더> <프로젝트이름> [스타일: target|talk_short] [편집 요청]
---

인자: $ARGUMENTS
(첫 번째 = 원본 폴더, 두 번째 = 캡컷 프로젝트 이름, 나머지 = 편집 요청/목표 길이)

다음 순서로 진행한다. 단계마다 결과를 짧게 보고한다.

1. **준비 확인**
   - 캡컷이 실행 중인지 확인한다(`tasklist | findstr /I CapCut`). 실행 중이면 종료를 요청하고 기다린다.
   - `docs/target-style.md`와 `capcut_agent/planner.py`의 SYSTEM(편집 원칙)을 읽는다.

2. **분석**
   `python capcut_agent/agent.py analyze --clips "<원본폴더>" --broll B롤 --work "work/<이름>"`
   (GPU가 없으면 `--device cpu --whisper medium`, 같은 장면을 여러 카메라로 찍었으면 `--multicam`)

3. **편집 계획 (Claude가 직접)**
   - `work/<이름>/analysis.json`의 전사를 읽고, 편집 원칙에 따라 `work/<이름>/edit_plan.json`을 작성한다.
   - **순서를 지킨다:** ① `key_message`(영상이 남길 한 문장)를 먼저 정한다 → ② 훅 후보 3개를 전사에서 뽑아(질문/숫자/반전·대비/고백/경고 패턴) 사용자에게 보여 주고 가장 멈추게 하는 것을 고른다(뒤쪽 문장을 앞으로 가져오는 콜드 오픈 가능, 첫 컷 4초 이내, 인사·소개 금지) → ③ 컷을 고른다(핵심 메시지를 뒷받침하지 않는 컷은 뺀다).
   - target 스타일이면 `hook {text(8~16자, 자막보다 더 압축·자극적), sub}`를 넣고, 핵심 문장·숫자가 말로 나오는 시각에 `message_cards` 1~2개(`at`은 앞 컷 길이 합산)를 넣는다. 엔딩은 key_message를 되풀이한다. emphasis 3~5개, alert 0~2개.
   - 형식: CLAUDE.md의 edit_plan 설명을 따른다. `main[].lines`에는 시간을 적지 않는다.
   - 음성인식 오타는 문맥으로 교정한다. 확신이 없는 단어는 플랜의 `notes`에 적어 사용자에게 알린다.
   - 스타일 지침은 `python -c "import sys;sys.path.insert(0,'capcut_agent');import planner;print(planner.system_prompt('<스타일>'))"`로 확인한다.
   - 기본 스타일은 `target`(docs/target-style.md). talk_short면 상단 제목(title) 2줄을 2~3개 후보로 사용자에게 제안하고 하나를 고른다. 역할(role), 맥락 라벨(label), 엔딩(ending)을 채운다. 영어는 요청 시에만.
   - B롤이 부족하면 `broll_ideas`에 재연 이미지 아이디어를 적고 사용자에게 알려 준다.
   - 컷을 고른 이유(뺀 부분 포함)를 사용자에게 3~5줄로 요약한다.
   - **자기 점검:** `python capcut_agent/agent.py critique --work "work/<이름>"`을 실행해 경고가 없을 때까지 플랜을 고친다(길이·훅 패턴·강조 개수·라벨·16자 넘는 자막). 의도적으로 남기는 경고는 이유를 사용자에게 말한다.

4. **컷 검증**
   각 컷 구간을 다시 전사해서 앞뒤 음절이 잘리거나 다음 문장이 섞이지 않았는지 확인하고, 문제가 있으면 in/out을 고친다.

5. **생성**
   `python capcut_agent/agent.py build --work "work/<이름>" --name "<이름>"`
   생성 후 `python tests/test_build.py`도 통과하는지 확인한다.
   `python capcut_agent/preview.py "%LOCALAPPDATA%/CapCut/User Data/Projects/com.lveditor.draft/<이름>" --out "work/<이름>/preview.jpg"`
   로 미리보기를 만들고 **직접 이미지를 열어** 얼굴이 잘리지 않았는지, 자막·라벨·훅 카드·메시지 카드가 겹치지 않는지 확인한다(`--at 1.0,<카드 시각>,...`로 특정 시점을 볼 수 있다).
   레포 루트에 `SFX/` 폴더(pop/hit/whoosh 파일)가 있으면 효과음이 자동으로 들어간다. 없으면 생략된다고 사용자에게 알린다.

6. **보고**
   길이, 컷 수, 자막 수, 훅(선택 이유), 메시지 카드 위치, 뺀 내용, 확인이 필요한 부분을 알리고, 캡컷을 열어 확인해 달라고 요청한다.
   키프레임 모션은 캡컷 검증 전이므로, 캡컷이 프로젝트를 못 열면 스타일의 `motion.enabled`를 false로 바꿔 다시 만들고 `make_template.py --inspect`로 실제 포맷을 확인하자고 안내한다.
   `docs/progress.md`에 한 줄 기록한다.
