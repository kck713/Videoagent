---
description: 생성한 캡컷 프로젝트를 캡컷이 정상적으로 열었는지 검증한다
argument-hint: <프로젝트이름>
---

프로젝트: $ARGUMENTS

1. `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<프로젝트>`를 확인한다.
   - `draft.extra`나 `Resources/`가 생겼으면 캡컷이 열었다는 뜻이다. 없으면 사용자에게 캡컷에서 열어 달라고 요청한다.
2. 캡컷이 다시 저장한 `draft_content.json`을 `work/<프로젝트>/edit_plan.json`(의도)과 비교한다.
   - 트랙 수, 트랙별 세그먼트 수, 전체 길이, 비디오 머티리얼 경로, 텍스트 개수가 유지됐는지 확인
   - 캡컷이 바꾼 필드가 있으면 목록으로 정리한다. 반복적으로 바꾸는 필드는 template/빌더에 반영할 후보다.
3. `root_meta_info.json`에 프로젝트가 등록돼 있는지 확인한다.
4. 결과를 요약하고, 새로 알게 된 포맷 사실은 `docs/capcut-draft-format.md`에 추가한다.
