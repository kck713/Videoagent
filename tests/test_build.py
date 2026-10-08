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
    reviewed = dict(good, key_message="핵심 한 문장", hook={"text": "왜 이렇게 싸..?"},
                    main=[dict(good["main"][0], lines=[{"ko": "왜 이렇게 싼 걸까요?", "role": "emphasis"}])])
    replies = ["설명 먼저... ```json\n" + json.dumps(bad) + "\n```", json.dumps(good, ensure_ascii=False),
               "검토했습니다.\n```json\n" + json.dumps(reviewed, ensure_ascii=False) + "\n```"]
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
        assert len(seen) == 3                                   # 한 번 재시도 + 편집장 리뷰 패스
        assert "WRONG.MP4" in seen[1]["messages"][-1]["content"]  # 오류 내용을 돌려줌
        assert "자동 점검" in seen[2]["messages"][-1]["content"] and "편집장" in seen[2]["system"]
        assert p["main"][0]["src"] == "C:/v/A.MP4" and p["style"] == "talk_short"
        assert p["key_message"] == "핵심 한 문장" and p["hook"]["text"] == "왜 이렇게 싸..?"   # 리뷰 결과 반영
        assert os.path.exists(os.path.join(d, "edit_plan_raw.txt"))
        # review=False면 두 번만 호출
        seen.clear()
        planner.plan(ap, out, style="talk_short", client=Client(), review=False)
        assert len(seen) == 2


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


def _segments(d, pred):
    return [s for t in d["tracks"] for s in t["segments"] if pred(t, s)]


def test_hook_message_cards_and_motion():
    p = _plan()
    with tempfile.TemporaryDirectory() as root:
        folder = build_from_plan(copy.deepcopy(p), "motion", root, load_style("target"))
        d = _load(folder)
        mats = {m["id"]: m for m in d["materials"]["texts"]}
        by_text = {}
        for t in d["tracks"]:
            if t["type"] != "text":
                continue
            for s in t["segments"]:
                by_text.setdefault(json.loads(mats[s["material_id"]]["content"])["text"], []).append(s)
        # 훅 카드: 0초부터, 장식 텍스트(type text), 팝 키프레임
        hk = by_text["처음엔 정말 막막했어요"][0]
        assert hk["target_timerange"]["start"] == 0 and mats[hk["material_id"]]["type"] == "text"
        props = {k["property_type"] for k in hk["common_keyframes"]}
        assert {"KFTypeScaleX", "KFTypeScaleY"} <= props
        kf = next(k for k in hk["common_keyframes"] if k["property_type"] == "KFTypeScaleX")["keyframe_list"]
        assert kf[0]["time_offset"] == 0 and kf[0]["values"][0] > kf[-1]["values"][0] == 1.0
        assert "현장 인터뷰" in by_text
        # 메시지 카드(문장형 + 숫자형)와 배경 띠, 노란 키워드
        assert "하나씩 쌓아 올린 경험" in by_text and "3년" in by_text and "배우러 다닌 시간" in by_text
        card = json.loads(mats[by_text["하나씩 쌓아 올린 경험"][0]["material_id"]]["content"])
        assert any(abs(r["fill"]["content"]["solid"]["color"][2] - 117 / 255) < 0.02 for r in card["styles"])
        assert abs(by_text["3년"][0]["target_timerange"]["start"] / 1e6 - 12.0) < 1e-6
        vids = {v["id"]: v for v in d["materials"]["videos"]}
        bands = _segments(d, lambda t, s: t["type"] == "video" and "band" in vids.get(s["material_id"], {}).get("path", ""))
        grads = _segments(d, lambda t, s: t["type"] == "video" and "gradient" in vids.get(s["material_id"], {}).get("path", ""))
        assert len(bands) == 2 and len(grads) == 1
        assert all(any(k["property_type"] == "KFTypeAlpha" for k in s["common_keyframes"]) for s in bands + grads)
        for s in bands + grads:   # 배경 PNG는 캔버스 크기 그대로(배율 1)
            assert s["clip"]["scale"]["x"] == 1.0 and os.path.exists(vids[s["material_id"]]["path"])
        # emphasis 자막은 단어 단위로 쌓이며 등장 (마지막 조각이 전체 문장)
        assert "정말" in by_text and "정말 막막했어요" in by_text
        a, b = by_text["정말"][0], by_text["정말 막막했어요"][0]
        assert a["target_timerange"]["start"] + a["target_timerange"]["duration"] == b["target_timerange"]["start"]
        assert mats[a["material_id"]]["type"] == "subtitle" and a["common_keyframes"]
        # 일반 자막은 키프레임 없음, 엔딩은 페이드 인, 이미지 B롤은 켄 번스
        assert not by_text["처음 이 일을 시작했을 때는"][0]["common_keyframes"]
        end = by_text["혼자 할 수 있을 때까지\n같이 고민하겠습니다."][0]
        assert any(k["property_type"] == "KFTypeAlpha" for k in end["common_keyframes"])
        ai = _segments(d, lambda t, s: vids.get(s["material_id"], {}).get("path", "").endswith("scene_ai.png"))[0]
        sx = next(k for k in ai["common_keyframes"] if k["property_type"] == "KFTypeScaleX")["keyframe_list"]
        assert sx[-1]["values"][0] > sx[0]["values"][0] and sx[-1]["time_offset"] == ai["target_timerange"]["duration"]
        # 키프레임 포맷 필드
        for k in hk["common_keyframes"]:
            assert set(k) == {"id", "material_id", "property_type", "keyframe_list"}
            for f in k["keyframe_list"]:
                assert set(f) == {"id", "curveType", "graphID", "left_control", "right_control", "time_offset", "values"}
        assert d["duration"] == sum(s["target_timerange"]["duration"] for s in
                                    next(t for t in d["tracks"] if t["type"] == "video" and t["flag"] == 0)["segments"])


def test_motion_can_be_disabled_and_cards_replace_subs():
    p = _plan()
    p["motion"] = False
    p["message_cards"][0]["replace_subs"] = True
    p["message_cards"][0]["at"] = p["main"][0]["subs"][1]["start"] - p["main"][0]["in"] - 0.1
    p["message_cards"][0]["dur"] = 5.0
    with tempfile.TemporaryDirectory() as root:
        d = _load(build_from_plan(copy.deepcopy(p), "nomotion", root, load_style("target")))
        assert not any(s.get("common_keyframes") for t in d["tracks"] for s in t["segments"])
        mats = {m["id"]: m for m in d["materials"]["texts"]}
        texts = [json.loads(m["content"])["text"] for m in mats.values()]
        assert "정말 막막했어요" not in texts and "정말" not in texts      # 카드가 자막을 대체
        assert "하나씩 쌓아 올린 경험" in texts


def test_split_reveal():
    from motion import split_reveal
    words = [(10.0, 10.3, "정말"), (10.35, 10.9, "막막했어요"), (10.95, 11.3, "그때는")]
    pieces = split_reveal("정말 막막했어요 그때는", 10.0, 12.0, words, tail=0.4)
    assert [t for _, _, t in pieces] == ["정말", "정말 막막했어요", "정말 막막했어요 그때는"]
    assert pieces[0][0] == 10.0 and pieces[-1][1] == 12.0
    for (a0, b0, _), (a1, b1, _) in zip(pieces, pieces[1:]):
        assert b0 == a1 and b0 > a0
    assert split_reveal("한마디", 0.0, 2.0, []) == [(0.0, 2.0, "한마디")]
    assert len(split_reveal("너무 짧은 줄", 0.0, 0.3, [])) == 1
    even = split_reveal("가 나 다 라", 0.0, 2.0, None)
    assert len(even) == 4 and even[1][0] > even[0][0]


def test_sfx_auto_placement():
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return
    p = _plan()
    with tempfile.TemporaryDirectory() as root:
        sfx = os.path.join(root, "SFX")
        os.makedirs(sfx)
        for n in ("pop.wav", "hit.wav", "whoosh.wav"):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=800:duration=0.3",
                            os.path.join(sfx, n)], check=True)
        d = _load(build_from_plan(copy.deepcopy(p), "sfx", root, load_style("target"), sfx_dir=sfx))
        aud = {m["id"]: m for m in d["materials"]["audios"]}
        segs = [s for t in d["tracks"] if t["type"] == "audio" for s in t["segments"]]
        names = sorted(os.path.basename(aud[s["material_id"]]["path"]) for s in segs)
        assert "whoosh.wav" in names and "hit.wav" in names and "pop.wav" in names, names
        first = min(segs, key=lambda s: s["target_timerange"]["start"])
        assert aud[first["material_id"]]["path"].endswith("whoosh.wav") and first["target_timerange"]["start"] == 0
        for t in d["tracks"]:   # 한 트랙 안에서는 겹치지 않음
            end = -1
            for s in t["segments"]:
                assert s["target_timerange"]["start"] >= end
                end = s["target_timerange"]["start"] + s["target_timerange"]["duration"]


def test_critique_flags_weak_plan_and_passes_strong_one():
    import planner
    weak = {"main": [{"src": "x", "in": 0, "out": 7.0, "lines": [{"ko": "안녕하세요 저는 원장입니다"}]},
                     {"src": "x", "in": 10, "out": 22.0, "lines": [{"ko": "이러저러한 이야기를 아주 길게 했습니다"}]}]}
    r = planner.critique(weak, load_style("target"))
    w = "\n".join(r["warnings"])
    assert "첫 컷이" in w and "인사" in w and "key_message" in w and "hook" in w and "emphasis/alert가" in w
    assert "16자 넘는 자막" in w and "12.0초짜리" in w and r["facts"]["컷 수"] == 2
    strong = {"key_message": "가격보다 안전이 중요합니다",
              "hook": {"text": "왜 이렇게 싸..?", "sub": "실제 경험"},
              "main": [{"src": "x", "in": 0, "out": 3.0, "lines": [{"ko": "왜 이렇게 싼 걸까요?", "role": "emphasis", "label": "왜 이렇게 싸..?"}]},
                       {"src": "x", "in": 5, "out": 9.5, "lines": [{"ko": "50만 원 차이가 났어요", "role": "normal", "label": "실제 경험"},
                                                                  {"ko": "그게 함정이었죠", "role": "quote"}]},
                       {"src": "x", "in": 12, "out": 17.0, "lines": [{"ko": "가격보다 안전이 중요해요", "role": "emphasis", "label": "깨달은 것"}]}],
              "message_cards": [{"at": 8.0, "dur": 3, "text": "가격보다 안전"}],
              "ending": {"text": "가격보다 더 중요한 건 안전입니다.", "dur": 2.5}}
    r2 = planner.critique(strong, load_style("target"))
    assert r2["warnings"] == [], r2["warnings"]
    assert "질문" in r2["facts"]["훅 패턴"]
    assert "강도 문제 없음" in planner.format_critique(r2)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
