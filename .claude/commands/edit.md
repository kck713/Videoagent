---
description: 원본 인터뷰 폴더로 캡컷 가편집 프로젝트를 만든다 (Claude가 직접 편집 계획)
argument-hint: <원본폴더> <프로젝트이름> [편집 요청]
---

인자: $ARGUMENTS
(첫 번째 = 원본 폴더, 두 번째 = 캡컷 프로젝트 이름, 나머지 = 편집 요청/목표 길이)

다음 순서로 진행한다. 단계마다 결과를 짧게 보고한다.

1. **준비 확인**
   - 캡컷이 실행 중인지 확인한다(`tasklist | findstr /I CapCut`). 실행 중이면 종료를 요청하고 기다린다.
   - `docs/target-style.md`와 `capcut_agent/planner.py`의 SYSTEM(편집 원칙)을 읽는다.

2. **분석**
   `python capcut_agent/agent.py analyze --clips "<원본폴더>" --broll B롤 --work "work/<이름>"`
   (GPU가 없으면 `--device cpu --whisper medium`)

3. **편집 계획 (Claude가 직접)**
   - `work/<이름>/analysis.json`의 전사를 읽고, 편집 원칙에 따라 `work/<이름>/edit_plan.json`을 작성한다.
   - 형식: CLAUDE.md의 edit_plan 설명을 따른다. `main[].lines`에는 시간을 적지 않는다.
   - 음성인식 오타는 문맥으로 교정한다. 확신이 없는 단어는 플랜의 `notes`에 적어 사용자에게 알린다.
   - 컷을 고른 이유(뺀 부분 포함)를 사용자에게 3~5줄로 요약한다.

4. **컷 검증**
   각 컷 구간을 다시 전사해서 앞뒤 음절이 잘리거나 다음 문장이 섞이지 않았는지 확인하고, 문제가 있으면 in/out을 고친다.

5. **생성**
   `python capcut_agent/agent.py build --work "work/<이름>" --name "<이름>"`
   생성 후 `python tests/test_build.py`도 통과하는지 확인한다.

6. **보고**
   길이, 컷 수, 자막 수, 뺀 내용, 확인이 필요한 부분을 알리고, 캡컷을 열어 확인해 달라고 요청한다.
   `docs/progress.md`에 한 줄 기록한다.
