# 캡컷 9.4.0 (Windows) 드래프트 포맷 메모

실제 PC에서 확인한 사실들입니다. 캡컷 업데이트 후에는 다시 검증하세요.

## 위치

- 프로젝트 루트: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`
- 프로젝트 목록: 위 폴더의 `root_meta_info.json` (`all_draft_store[]`)
- 캡컷 앱 리소스: `%LOCALAPPDATA%\CapCut\Apps\9.4.0.4015\Resources\` (기본 폰트 `Font/SystemFont/en.ttf`)

## 암호화 여부

- **9.4.0의 `draft_content.json`은 평문 JSON**입니다. `crypto_key_store.dat`가 있지만 타임라인 파일은 암호화되어 있지 않습니다.
- `version: 360000`, `new_version: "185.0.0"`, `platform.app_version: "9.4.0"`

## 프로젝트 폴더 구성 (에이전트가 쓰는 것)

```
<이름>/
  draft_content.json                  ← 타임라인 본체
  Timelines/project.json              ← main_timeline_id = draft_content.id
  Timelines/<timeline id>/draft_content.json   ← 본체와 동일한 미러 (9.x 필수)
  draft_meta_info.json                ← draft_id, 경로, 미디어 풀(draft_materials type 0)
  timeline_layout.json, draft_settings, draft_virtual_store.json, key_value.json, draft_agency_config.json
  draft_cover.jpg
```
캡컷이 열면 `draft.extra`, `Resources/`, `common_attachment/`, `template-2.tmp`, `.bak` 등을 스스로 추가합니다.

## 검증된 동작

- 에이전트가 생성한 `1006_auto`를 캡컷 9.4.0이 정상적으로 열고 다시 저장했습니다(트랙·자막·B롤·BGM 유지).
- 프로젝트 폴더 안의 미디어는 캡컷이 `##_draftpath_placeholder_<UUID>_##/media/...`로 상대경로화합니다.
- `1007_auto_원본편집`(10컷, 9:16 배치, 자막 72개)도 캡컷이 열고 재저장 — 구조 유지 확인.
- 캡컷 실행 중에 프로젝트와 목록을 써도, 캡컷이 목록을 다시 읽어 바로 반영·저장하는 것이 관찰됐습니다(1007). 그래도 종료할 때 메모리 상태로 목록을 덮어쓸 수 있으므로 **가능하면 캡컷을 끄고 생성**합니다.
- 사진 머티리얼: `materials.videos[].type = "photo"`, 길이 10800초(3시간)로 둡니다(JianYing/CapCut 관례, 9.4.0 실제 검증 전).

- **글자 크기 실측(2026-10-07):** 사용자가 `1007_target_스타일`을 캡컷에서 열어 본 자막을 9 → 5.5로 줄였다. 캡컷의 글자 크기 1 ≈ 1920px 캔버스에서 약 9px로 보고 전체 스타일을 ×0.61로 보정했다(`preview.py` PX_PER_SIZE=9).
- **자막 일괄 편집 주의:** 캡컷에서 자막 스타일을 일괄로 바꾸면 `type: "subtitle"`인 텍스트가 **전부** 같은 스타일(크기·색)로 덮어써진다. 그래서 라벨·제목·엔딩·이름표 같은 장식 텍스트는 `type: "text"`로 만들고, 본 자막만 `subtitle`(group_id 있음)로 둔다.
- 캡컷이 다시 저장한 텍스트 `content`는 `{"text", "styles":[{fill(color만), font, size, range}]}` 형태로 정리된다(alpha 키 제거). 우리가 쓴 형식도 그대로 읽힌다(1007_auto에서 크기·색 유지 확인).

## 핵심 규칙

- 시간 단위: 마이크로초(int). fps 30 기준 프레임 경계에 맞춤(시작과 끝을 각각 반올림해야 1프레임 겹침이 안 생김).
- 트랙: `type` video/text/audio, `flag` 0 = 메인, 2 = 오버레이(video), 1 = 텍스트. 오버레이는 `attribute: 1`.
- 세그먼트 `clip.transform`: x는 반 화면 폭, y는 반 화면 높이 단위, **y는 위가 +**.
- `clip.scale`: 1.0 = 캔버스 안에 맞춤(contain). 16:9를 9:16에 꽉 채우려면 약 3.16.
- 텍스트 머티리얼 `content`는 JSON 문자열: `{"text": ..., "styles":[{"range":[a,b], "size", "fill", "font", "bold", "strokes"}]}`. range는 UTF-16 단위.
- `check_flag`: 7 기본, +8 외곽선, +16 배경, +32 그림자.
- 같은 `group_id` + `type: "subtitle"`이면 캡컷 자막 일괄 편집 대상이 됩니다.
- 부가 머티리얼(speeds, canvases, sound_channel_mappings, material_colors, vocal_separations, material_animations, placeholder_infos)은 세그먼트마다 새 ID로 복제합니다.
- **복제하면 안 되는 것:** loudnesses, vocal_beautifys, smart_relights, effects(스마트 색보정/시선보정), realtime_denoises, beats. 원본 미디어 분석 결과에 묶여 있습니다.

## 키프레임 (모션) — 검증 전

`motion.py`가 세그먼트 `common_keyframes[]`에 아래 형식으로 씁니다(JianYing/CapCut 드래프트에서 널리 확인된 형식, pyJianYingDraft와 동일). 캡컷 9.4.0에서 열어 재저장하는 검증은 아직 전입니다.
```json
{"id": "<UUID>", "material_id": "", "property_type": "KFTypeScaleX",
 "keyframe_list": [{"id": "<UUID>", "curveType": "Line", "graphID": "", "left_control": {"x": 0, "y": 0},
                    "right_control": {"x": 0, "y": 0}, "time_offset": 0, "values": [1.3]}, ...]}
```
- `property_type`: KFTypePositionX / KFTypePositionY / KFTypeScaleX / KFTypeScaleY / KFTypeAlpha / KFTypeRotation
- `time_offset`: 세그먼트 시작 기준 마이크로초. `values`: 값 하나(배율은 clip.scale과 같은 단위, 위치는 transform 단위)
- 균등 배율은 ScaleX/ScaleY 둘 다 같은 값으로 씁니다(`uniform_scale.on` 유지).
- 검증 방법: 캡컷에서 텍스트에 키프레임을 찍고 저장한 프로젝트를 `python capcut_agent/make_template.py --inspect <폴더>`로 열어 필드를 비교. 다르면 motion.py `add_keyframes()`만 고치면 됩니다.
- 캡컷 내장 텍스트 애니메이션(`material_animations.animations[]`)과 트랜지션·스티커는 `resource_id`/다운로드 경로가 필요해 만들지 않습니다.

## 템플릿 재추출

캡컷 업데이트 후에는 새 버전에서 프로젝트 하나를 만들어 저장한 뒤 아래 명령을 실행합니다.
```
python capcut_agent/make_template.py "%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<프로젝트>"
```
`sanitize()`가 장치 ID, 사용자 경로, 자막 내용을 제거하고 `${LOCALAPPDATA}` 자리표시자로 바꿉니다.
