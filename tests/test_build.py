"""드래프트 빌더 스모크 테스트 (캡컷/미디어 파일 없이 실행 가능).

    python -m pytest tests -q        또는        python tests/test_build.py
"""
import copy
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "capcut_agent"))

from agent import build_from_plan, load_style  # noqa: E402
from capcut_draft import face_for_range, framing  # noqa: E402
import subtimer  # noqa: E402


def _plan():
    with open(os.path.join(ROOT, "examples", "edit_plan_example.json"), encoding="utf-8") as f:
        p = json.load(f)
    speech = {c["src"]: [(c["in"] + 0.1, c["out"] - 0.1)] for c in p["main"]}
    for c in p["main"]:
        c["refine"] = False  # 오디오 없이 테스트
    subtimer.apply(p, speech)
    return p


def _load(folder):
    with open(os.path.join(folder, "draft_content.json"), encoding="utf-8") as f:
        return json.load(f)


def test_build_creates_valid_draft():
    p = _plan()
    with tempfile.TemporaryDirectory() as root:
        folder = build_from_plan(copy.deepcopy(p), "test_draft", root)
        d = _load(folder)
        kinds = [(t["type"], t["flag"]) for t in d["tracks"]]
        assert ("video", 0) in kinds and ("text", 1) in kinds and ("video", 2) in kinds
        main = next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)
        assert len(main["segments"]) == len(p["main"])
        # 메인 컷은 빈틈 없이 이어져야 함
        end = 0
        for s in main["segments"]:
            assert s["target_timerange"]["start"] == end
            end += s["target_timerange"]["duration"]
        assert d["duration"] == end
        # Timelines 미러 파일과 동일해야 함 (캡컷 9.x)
        with open(os.path.join(folder, "Timelines", d["id"], "draft_content.json"), encoding="utf-8") as f:
            assert json.load(f) == d
        # 프로젝트 목록 등록
        with open(os.path.join(root, "root_meta_info.json"), encoding="utf-8") as f:
            assert json.load(f)["all_draft_store"][0]["draft_name"] == "test_draft"


def test_subtitles_cover_cut_without_overlap():
    p = _plan()
    for c in p["main"]:
        subs = c["subs"]
        assert len(subs) == len(c["lines"])
        for a, b in zip(subs, subs[1:]):
            assert a["end"] <= b["start"] + 1e-6
        assert subs[-1]["end"] <= c["out"] + 1e-6


def test_template_has_no_personal_data():
    with open(os.path.join(ROOT, "capcut_agent", "template_pack.json"), encoding="utf-8") as f:
        s = f.read()
    assert "C:/Users/" not in s
    pack = json.loads(s)
    assert pack["draft_skeleton"]["platform"].get("device_id", "") == ""


def _texts(d, folder_track_index):
    return d["tracks"][folder_track_index]


def test_target_style_features():
    p = _plan()
    with tempfile.TemporaryDirectory() as root:
        folder = build_from_plan(copy.deepcopy(p), "target_draft", root, load_style("target"))
        d = _load(folder)
        mats = {m["id"]: m for m in d["materials"]["texts"]}
        vids = {m["id"]: m for m in d["materials"]["videos"]}
        texts = [t for t in d["tracks"] if t["type"] == "text"]
        contents = [json.loads(mats[s["material_id"]]["content"]) for t in texts for s in t["segments"]]
        all_text = [c["text"] for c in contents]
        # 영어 자막 없음, 라벨/고지/엔딩/PIP 캡션 존재
        assert not any("When" in t for t in all_text)
        assert "실제 경험" in all_text and "AI로 생성한 이미지 입니다." in all_text
        assert any("같이 고민하겠습니다" in t for t in all_text) and "정품: 대문자" in all_text
        # quote 역할은 노란색
        yellow = [c for c in contents if c["text"] == "하나씩 쌓아 왔거든요"][0]
        assert any(abs(r["fill"]["content"]["solid"]["color"][2] - 117 / 255) < 0.02 for r in yellow["styles"])
        # 엔딩은 타임라인 끝에서 끝남
        end_tr = [t for t in texts if any("같이 고민" in json.loads(mats[s["material_id"]]["content"])["text"]
                                          for s in t["segments"])][0]
        e = end_tr["segments"][-1]["target_timerange"]
        assert e["start"] + e["duration"] == d["duration"]
        # 메인은 9:16 꽉 채움(3.16배 이상), 첫 컷 클로즈업
        main = next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)
        sc = [s["clip"]["scale"]["x"] for s in main["segments"]]
        assert sc[0] > 4.0 and sc[1] > 3.1 and sc[1] < sc[0]
        # 이미지 B롤은 photo 타입
        assert any(v["type"] == "photo" for v in vids.values())


def test_framing_never_shows_black_edges():
    for face in ({"x": 0.05, "y": 0.9}, {"x": 0.95, "y": 0.05}, None):
        for z in (1.0, 1.3):
            k, tx, ty = framing({"width": 3840, "height": 2160}, 1080, 1920, face, z)
            dw, dh = 1080 * k, 1080 * 9 / 16 * k
            assert abs(tx) * 540 <= (dw - 1080) / 2 + 1 and abs(ty) * 960 <= (dh - 1920) / 2 + 1


def test_face_track_per_cut():
    face = {"x": 0.5, "y": 0.4, "h": 0.3, "track": [[10, 0.3, 0.4, 0.3], [100, 0.7, 0.45, 0.3]]}
    assert face_for_range(face, 8, 12)["x"] == 0.3
    assert face_for_range(face, 98, 104)["x"] == 0.7
    assert face_for_range(face, 50, 55)["x"] == 0.5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
