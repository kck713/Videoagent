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


def inspect(folder, what=("keyframes", "animations", "stickers")):
    """캡컷이 실제로 저장한 프로젝트에서 키프레임·애니메이션·스티커 샘플을 뽑아 보여줍니다(검증용).

    사용법: python make_template.py --inspect "<캡컷 프로젝트 폴더>"
    - 캡컷에서 텍스트/사진에 키프레임(위치·배율·불투명도)을 찍고 저장한 프로젝트를 넣으면, 세그먼트의
      common_keyframes 원문을 출력합니다. motion.py가 쓰는 포맷(property_type, time_offset, values …)과 비교하세요.
    - 텍스트 애니메이션(material_animations)·스티커가 있으면 resource_id/path도 같이 보여줍니다."""
    d = load(os.path.join(folder, "draft_content.json"))
    M = index_materials(d)
    found = 0
    for t in d["tracks"]:
        for s in t["segments"]:
            kind = M.get(s["material_id"], ("?", {}))[0]
            if "keyframes" in what and s.get("common_keyframes"):
                found += 1
                print(f"\n[키프레임] 트랙 {t['type']}/flag {t.get('flag')} 세그먼트({kind}) "
                      f"@{s['target_timerange']['start'] / 1e6:.2f}s, uniform_scale={s.get('uniform_scale')}")
                for kf in s["common_keyframes"]:
                    print(f"  {kf.get('property_type')}: " + ", ".join(
                        f"{k.get('time_offset', 0) / 1e6:.2f}s={k.get('values')}" for k in kf.get("keyframe_list", [])))
                    extra = {k: v for k, v in kf.items() if k not in ("keyframe_list",)}
                    print("   필드:", json.dumps(extra, ensure_ascii=False)[:300])
                    if kf.get("keyframe_list"):
                        print("   키프레임 필드:", json.dumps(kf["keyframe_list"][0], ensure_ascii=False)[:300])
                if s.get("keyframe_refs"):
                    print("   keyframe_refs:", s["keyframe_refs"])
            if "animations" in what:
                for r in s.get("extra_material_refs", []):
                    k, m = M.get(r, (None, None))
                    if k == "material_animations" and m.get("animations"):
                        found += 1
                        print(f"\n[애니메이션] {kind} @{s['target_timerange']['start'] / 1e6:.2f}s")
                        for a in m["animations"]:
                            print("  ", json.dumps(a, ensure_ascii=False)[:400])
            if "stickers" in what and kind == "stickers":
                found += 1
                print(f"\n[스티커] @{s['target_timerange']['start'] / 1e6:.2f}s", json.dumps(M[s["material_id"]][1], ensure_ascii=False)[:400])
    if not found:
        print("키프레임/애니메이션/스티커를 쓴 세그먼트가 없습니다. 캡컷에서 텍스트에 키프레임을 하나 찍고 저장한 뒤 다시 실행하세요.")
    return found


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--inspect":
        inspect(sys.argv[2])
        sys.exit(0)
    folder = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "template_pack.json")
    main(folder, out)
