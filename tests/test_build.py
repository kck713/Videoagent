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
        # 메인은 9:16 꽉 채움(3.16배), 펀치인 줌 없음(모든 컷 같은 배율)
        main = next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)
        sc = [s["clip"]["scale"]["x"] for s in main["segments"]]
        assert all(abs(x - 3.1605) < 0.01 for x in sc), sc
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


def test_talk_short_features():
    p = _plan()
    p["style"] = "talk_short"
    p["title"] = {"line1": "테스트 대상 상황", "line2": "반전 결말...!"}
    p["speakers"] = {"A": {"name": "홍길동", "title": "원장"}}
    p["main"][0]["speaker"] = "A"
    p["callouts"] = [{"at": 1.0, "dur": 1.0, "x": 0.4, "y": 0.6}]
    p["disclaimer"] = "본 콘텐츠는 정보 전달 목적입니다."
    p["main"][1]["focus"] = {"x": 0.45, "y": 0.6}
    p["main"][1]["zoom"] = 2.2
    with tempfile.TemporaryDirectory() as root:
        folder = build_from_plan(copy.deepcopy(p), "talk", root, load_style("talk_short"))
        d = _load(folder)
        mats = {m["id"]: m for m in d["materials"]["texts"]}
        texts = {json.loads(m["content"])["text"]: m for m in mats.values()}
        for t in ("테스트 대상 상황", "반전 결말...!", "홍길동", "원장", "본 콘텐츠는 정보 전달 목적입니다.", "(실제 경험)"):
            assert t in texts, t
        # 제목은 영상 전체, 일반 텍스트 타입(자막 일괄 편집 대상 아님)
        assert texts["반전 결말...!"]["type"] == "text" and texts["(실제 경험)"]["type"] == "text"
        assert texts["정말 막막했어요"]["type"] == "subtitle"
        tt = [s for t in d["tracks"] if t["type"] == "text" for s in t["segments"]
              if s["material_id"] == texts["반전 결말...!"]["id"]][0]["target_timerange"]
        assert tt["start"] == 0 and tt["duration"] == d["duration"]
        # 테두리 PNG 오버레이 + 원형 강조 생성
        assert os.path.exists(os.path.join(folder, "assets", "frame.png"))
        assert os.path.exists(os.path.join(folder, "assets", "ring.png"))
        paths = [v["path"] for v in d["materials"]["videos"]]
        assert any(x.endswith("frame.png") for x in paths) and any(x.endswith("ring.png") for x in paths)
        # 극단 확대 컷
        main = next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)
        assert main["segments"][1]["clip"]["scale"]["x"] > 6.5


def test_tighten_splits_long_cut_and_pauses():
    plan = {"main": [{"src": "x", "in": 0.0, "out": 9.0, "subs": [
        {"ko": "a", "start": 0.0, "end": 3.0}, {"ko": "b", "start": 3.0, "end": 6.0}, {"ko": "c", "start": 6.0, "end": 9.0}]}]}
    subtimer.tighten(plan, max_cut=2.5)
    assert len(plan["main"]) == 3
    assert [c["subs"][0]["ko"] for c in plan["main"]] == ["a", "b", "c"]
    assert plan["main"][0]["in"] == 0.0 and plan["main"][-1]["out"] == 9.0


def test_multicam_angle_offset():
    p = _plan()
    cam2 = "C:/Videos/interview/B001.MP4"
    p["media"][cam2] = {"duration": 70.0, "width": 1920, "height": 1080, "has_audio": True, "has_video": True}
    p["sync"] = {p["main"][0]["src"]: 0.0, cam2: -2.5}
    p["main"][1]["angle"] = cam2
    with tempfile.TemporaryDirectory() as root:
        d = _load(build_from_plan(copy.deepcopy(p), "mc", root, load_style("target")))
        vids = {v["id"]: v for v in d["materials"]["videos"]}
        main = next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)
        s1 = main["segments"][1]
        assert vids[s1["material_id"]]["path"] == cam2
        assert abs(s1["source_timerange"]["start"] / 1e6 - (p["main"][1]["in"] - 2.5)) < 0.05


def test_sync_offset_detection():
    import numpy as np
    from sync import offset
    rng = np.random.default_rng(0)
    sr = 8000
    env = np.repeat(rng.random(400) > 0.6, sr // 20).astype(np.float32)  # 말소리처럼 켜졌다 꺼지는 신호
    ref = env * rng.standard_normal(len(env)).astype(np.float32)
    shift = int(1.7 * sr)
    cam = np.concatenate([np.zeros(shift, np.float32), ref])[: len(ref)] * 0.5
    cam = cam + 0.01 * rng.standard_normal(len(cam)).astype(np.float32)
    off, conf = offset(ref, cam, sr)
    assert abs(off - 1.7) < 0.02, off


def test_planner_validates_and_retries():
    import planner

    class Usage:
        input_tokens, output_tokens = 1000, 500

    class Block:
        type = "text"

        def __init__(self, t):
            self.text = t

    class Msg:
        def __init__(self, t):
            self.content, self.usage = [Block(t)], Usage()

    good = {"main": [{"src": "C:/v/A.MP4", "in": 1.0, "out": 4.0, "lines": [{"ko": "안녕하세요", "role": "normal"}]}],
            "title": {"line1": "제목 1", "line2": "제목 2"}}
    bad = {"main": [{"src": "C:/v/WRONG.MP4", "in": 5.0, "out": 4.0, "lines": []}]}
    replies = ["설명 먼저... ```json\n" + json.dumps(bad) + "\n```", json.dumps(good, ensure_ascii=False)]
    seen = []

    class Stream:
        def __init__(self, kw):
            seen.append(kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return Msg(replies[len(seen) - 1])

    class Client:
        class messages:
            @staticmethod
            def stream(**kw):
                return Stream(kw)

    analysis = {"clips": [{"src": "C:/v/A.MP4", "duration": 30.0, "transcript": [], "silences": []}],
                "media": {"C:/v/A.MP4": {"duration": 30.0, "width": 1920, "height": 1080}}}
    with tempfile.TemporaryDirectory() as d:
        ap = os.path.join(d, "analysis.json")
        json.dump(analysis, open(ap, "w", encoding="utf-8"))
        out = os.path.join(d, "edit_plan.json")
        planner.plan(ap, out, style="talk_short", client=Client())
        p = json.load(open(out, encoding="utf-8"))
        assert len(seen) == 2                                   # 한 번 재시도
        assert "WRONG.MP4" in seen[1]["messages"][-1]["content"]  # 오류 내용을 돌려줌
        assert p["main"][0]["src"] == "C:/v/A.MP4" and p["style"] == "talk_short"
        assert os.path.exists(os.path.join(d, "edit_plan_raw.txt"))


def test_free_mode_import_plan():
    import planner
    analysis = {"clips": [{"src": "C:/v/A.MP4", "duration": 30.0, "transcript": [], "silences": []}],
                "media": {"C:/v/A.MP4": {"duration": 30.0, "width": 1920, "height": 1080}}}
    good = {"main": [{"src": "C:/v/A.MP4", "in": 1.0, "out": 4.0, "lines": [{"ko": "안녕하세요"}]}],
            "title": {"line1": "a", "line2": "b"}}
    with tempfile.TemporaryDirectory() as d:
        ap, pp = os.path.join(d, "analysis.json"), os.path.join(d, "edit_plan.json")
        json.dump(analysis, open(ap, "w", encoding="utf-8"))
        open(pp, "w", encoding="utf-8").write("")
        assert planner.import_plan(ap, pp, "talk_short")                       # 빈 파일
        open(pp, "w", encoding="utf-8").write('{"main": [{"src": "C:/v/A.MP4", "in": 9, "out": 2, "lines": []}]}')
        assert planner.import_plan(ap, pp, "talk_short")                       # 값 오류
        assert os.path.exists(os.path.join(d, "edit_plan_fix.txt"))
        # claude.ai 답변처럼 설명 + 코드블록 + BOM
        open(pp, "w", encoding="utf-8-sig").write("네, 계획입니다.\n```json\n" + json.dumps(good, ensure_ascii=False) + "\n```\n끝")
        assert planner.import_plan(ap, pp, "talk_short") == []
        p = json.load(open(pp, encoding="utf-8"))
        assert p["style"] == "talk_short" and p["media"] and not os.path.exists(os.path.join(d, "edit_plan_fix.txt"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
