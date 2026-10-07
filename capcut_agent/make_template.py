"""기존 캡컷 프로젝트에서 '템플릿 팩'을 추출합니다.

캡컷 드래프트 포맷은 비공개라, 실제 캡컷이 저장한 세그먼트/머티리얼을 복제하는 것이
가장 안전합니다. 이 스크립트는 프로젝트 하나에서 종류별 샘플 1개씩을 뽑아
template_pack.json 으로 저장합니다. (캡컷 버전이 바뀌면 새 프로젝트로 다시 추출)

사용법:
    python make_template.py "<캡컷 프로젝트 폴더>" [출력경로]
"""
import copy
import re
import json
import os
import sys

# 미디어 분석 결과에 묶여 있어 다른 파일에 재사용하면 안 되는 부가 머티리얼
MEDIA_BOUND = {"loudnesses", "vocal_beautifys", "smart_relights", "effects", "realtime_denoises", "beats"}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def index_materials(d):
    m = {}
    for k, v in d["materials"].items():
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and "id" in x:
                    m[x["id"]] = (k, x)
    return m


def first_seg(d, ttype, flag=None):
    for t in d["tracks"]:
        if t["type"] == ttype and (flag is None or t.get("flag") == flag) and t["segments"]:
            return t, t["segments"][0]
    return None, None


def extras_of(seg, M, skip=MEDIA_BOUND):
    out = []
    for r in seg.get("extra_material_refs", []):
        if r in M and M[r][0] not in skip:
            out.append({"kind": M[r][0], "data": copy.deepcopy(M[r][1])})
    return out


def main(folder, out_path):
    d = load(os.path.join(folder, "draft_content.json"))
    meta = load(os.path.join(folder, "draft_meta_info.json"))
    M = index_materials(d)
    pack = {"source_project": os.path.basename(folder.rstrip("/\\")),
            "app_version": d.get("platform", {}).get("app_version")}

    # 드래프트 골격: 트랙/머티리얼 비우기
    skel = copy.deepcopy(d)
    skel["tracks"] = []
    for k, v in skel["materials"].items():
        if isinstance(v, list):
            skel["materials"][k] = []
    skel["config"]["subtitle_taskinfo"] = []
    skel["config"]["subtitle_recognition_id"] = ""
    skel["extra_info"] = None
    pack["draft_skeleton"] = skel

    t, s = first_seg(d, "video", 0)
    pack["track_skeleton"] = {k: v for k, v in t.items() if k != "segments"}
    pack["video_seg"] = copy.deepcopy(s)
    pack["video_mat"] = copy.deepcopy(M[s["material_id"]][1])
    pack["video_extras"] = extras_of(s, M)

    t2, s2 = first_seg(d, "video", 2)
    if s2:
        pack["overlay_seg"] = copy.deepcopy(s2)
        pack["overlay_track"] = {k: v for k, v in t2.items() if k != "segments"}
    else:  # 오버레이 샘플이 없으면 메인 세그먼트로 대체
        pack["overlay_seg"] = copy.deepcopy(s)
        pack["overlay_track"] = dict(pack["track_skeleton"], flag=2, attribute=1)

    tt, ts = first_seg(d, "text")
    if ts:
        pack["text_track"] = {k: v for k, v in tt.items() if k != "segments"}
        pack["text_seg"] = copy.deepcopy(ts)
        pack["text_mat"] = copy.deepcopy(M[ts["material_id"]][1])
        pack["text_extras"] = extras_of(ts, M)

    ta, sa = first_seg(d, "audio")
    if sa:
        pack["audio_track"] = {k: v for k, v in ta.items() if k != "segments"}
        pack["audio_seg"] = copy.deepcopy(sa)
        pack["audio_mat"] = copy.deepcopy(M[sa["material_id"]][1])
        pack["audio_extras"] = extras_of(sa, M)

    mskel = copy.deepcopy(meta)
    for g in mskel.get("draft_materials", []):
        if g.get("type") == 0 and g.get("value"):
            pack["meta_material_sample"] = copy.deepcopy(g["value"][-1])
            g["value"] = []
    pack["meta_skeleton"] = mskel

    for name in ("draft_agency_config.json", "timeline_layout.json"):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            pack[name] = load(p)
    p = os.path.join(folder, "Timelines", "project.json")
    if os.path.exists(p):
        pack["timelines_project"] = load(p)

    pack = sanitize(pack)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=1)
    print("template pack ->", out_path)


def sanitize(pack):
    """공개 레포에 올려도 되도록 PC 고유값/사용자 경로/원본 내용 제거.
    LOCALAPPDATA 경로는 ${LOCALAPPDATA} 로 바꾸고, 빌드할 때 실제 경로로 되돌립니다."""
    for key in ("platform", "last_modified_platform"):
        p = pack["draft_skeleton"].get(key)
        if isinstance(p, dict):
            for k in ("device_id", "hard_disk_id", "mac_address"):
                if k in p:
                    p[k] = ""
    for k in ("video_mat",):
        pack[k].update({"path": "", "material_name": "", "local_material_id": "", "unique_id": ""})
    if "text_mat" in pack:
        pack["text_mat"].update({"content": "", "base_content": "", "recognize_text": "", "recognize_task_id": "",
                                 "words": {"start_time": [], "end_time": [], "text": []}})
    if "audio_mat" in pack:
        pack["audio_mat"].update({"path": "", "name": "", "request_id": ""})
    if "meta_material_sample" in pack:
        pack["meta_material_sample"].update({"file_Path": "", "extra_info": "", "id": ""})
    for k in ("draft_fold_path", "draft_root_path", "draft_name", "draft_id"):
        if k in pack.get("meta_skeleton", {}):
            pack["meta_skeleton"][k] = ""
    s = json.dumps(pack, ensure_ascii=False)
    s = re.sub(r'[A-Za-z]:/Users/[^/"]+/AppData/Local', "${LOCALAPPDATA}", s)
    s = re.sub(r'[A-Za-z]:/Users/[^/"]+/', "${USERPROFILE}/", s)
    return json.loads(s)


if __name__ == "__main__":
    folder = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "template_pack.json")
    main(folder, out)
