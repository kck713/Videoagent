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

from agent import build_from_plan  # noqa: E402
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
