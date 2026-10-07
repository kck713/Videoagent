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
- 캡컷이 실행 중이면 종료할 때 `root_meta_info.json`을 메모리 상태로 덮어씁니다. **생성 전 캡컷 종료 필수.**

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

## 템플릿 재추출

캡컷 업데이트 후에는 새 버전에서 프로젝트 하나를 만들어 저장한 뒤 아래 명령을 실행합니다.
```
python capcut_agent/make_template.py "%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<프로젝트>"
```
`sanitize()`가 장치 ID, 사용자 경로, 자막 내용을 제거하고 `${LOCALAPPDATA}` 자리표시자로 바꿉니다.
