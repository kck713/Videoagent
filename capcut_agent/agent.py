"""캡컷 자동 편집 에이전트 CLI

  python agent.py run     --clips <원본폴더> [--broll <B롤폴더>] [--bgm <음악파일>] --name 1007_인터뷰 [--brief "..."] [--target 45]
  python agent.py analyze --clips <원본폴더> [--broll <B롤폴더>] --work work/
  python agent.py plan    --work work/ [--brief "..."] [--target 45] [--prompt-only]
  python agent.py build   --plan work/edit_plan.json --name 1007_인터뷰 [--bgm <음악파일>]

실행 전 캡컷을 완전히 종료하세요. 생성 후 캡컷을 열면 프로젝트 목록 맨 앞에 나타납니다.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from capcut_draft import Draft, face_for_range, framing  # noqa: E402

DEFAULT_ROOT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft")
STYLE_DIR = os.path.join(HERE, "styles")
DEFAULT_STYLE = "target"


def load_style(name_or_path=None):
    """스타일 프리셋 이름(styles/<이름>.json) 또는 JSON 경로."""
    p = name_or_path or DEFAULT_STYLE
    if not os.path.exists(p):
        p = os.path.join(STYLE_DIR, f"{p}.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def role_style(style, role):
    roles = style.get("roles") or {}
    return dict(roles.get(role) or roles.get("normal") or style.get("ko") or {})


def line_role(s):
    if s.get("role"):
        return s["role"]
    return "emphasis" if s.get("emphasis") else "normal"


def build_from_plan(plan, name, drafts_root=None, style=None, bgm=None, path_map=None, canvas=(1080, 1920), fps=30.0):
    """edit_plan → 캡컷 프로젝트.

    plan 키:
      main[]   {src, in, out, subs[]|lines[], zoom?, face?}
               subs[] {start, end(원본 시간), ko, en?, role?(normal|quote|emphasis|alert|aside), highlight[], label?}
      labels[] {text, at, dur, kind: "context"|"top"}           (타임라인 시간)
      broll[]  {src, at, dur, in?, fit: fill|fit|pip, pip?{scale,x,y}, caption?, ai?, top_label?, volume?}
      ending   {text, dur}                                        마지막 dur초 동안 중앙 검정 박스
      bgm, layout, faces{src:{x,y,h}}, media{src:info}, style?
    """
    style = style or load_style(plan.get("style"))
    drafts_root = drafts_root or DEFAULT_ROOT
    media = plan.get("media", {})
    faces = plan.get("faces", {})
    cw, ch = plan.get("canvas") or canvas
    d = Draft(cw, ch, fps=fps)

    def win(p):
        p = p.replace("\\", "/")
        for a, b in (path_map or {}).items():
            if p.startswith(a):
                return b + p[len(a):]
        return p

    def info(p):
        return media.get(p) or media.get(win(p))

    lay = dict(style.get("layout") or {}, **(plan.get("layout") or {}))
    mode = lay.get("mode", "fixed")
    zooms = lay.get("zoom_pattern", [1.0])
    group_ko, group_en = "ko-KR_agent", "en-US_agent"
    en_style = style.get("en")
    timeline_subs = []   # (t0, t1, sub) — 라벨 배치용

    # 1) 메인 컷 + 자막
    at = 0.0
    prev_z = None
    for i, clip in enumerate(plan["main"]):
        src, a, b = clip["src"], float(clip["in"]), float(clip["out"])
        inf = info(src) or {}
        if mode == "fixed":
            scale, tx, ty = float(lay.get("scale", 1.0)), float(lay.get("x", 0.0)), float(lay.get("y", 0.0))
        else:
            if not inf.get("width"):
                from capcut_draft import probe
                inf = probe(win(src))
                media[src] = inf
            if clip.get("zoom") is not None:
                z = float(clip["zoom"])
            else:  # 직전 컷과 다른 배율로 교차 (점프컷을 샷 변화로 보이게)
                cand = [x for x in zooms if prev_z is None or abs(x - prev_z) > 1e-3] or zooms
                z = float(cand[0])
            prev_z = z
            tgt = lay.get("closeup_face_target" if z > 1.05 else "face_target", [0.5, 0.40])
            face = clip.get("face") or face_for_range(faces.get(src) or faces.get(win(src)), a, b)
            scale, tx, ty = framing(inf, cw, ch, face, zoom=z, face_target=tuple(tgt))
        seg = d.add_video("main", win(src), a, b - a, at, info=inf or None, scale=scale, transform=(tx, ty))
        real = seg["target_timerange"]["duration"] / 1e6
        for s in clip.get("subs", []):
            s0, s1 = max(a, float(s["start"])), min(b, float(s["end"]))
            if s1 - s0 < 0.1:
                continue
            t0 = at + (s0 - a)
            role = line_role(s)
            st = role_style(style, role)
            st["_highlight"] = s.get("highlight") or []
            st["highlight_color"] = style.get("highlight_color", "#F2D475")
            text = s.get("ko", "")
            if st.get("wrap") and text and not text.startswith(st["wrap"][0]):
                text = f"{st['wrap'][0]}{text}{st['wrap'][1]}"
            if text:
                d.add_text("sub_ko", text, t0, s1 - s0, st, group_id=group_ko)
            if s.get("en") and en_style:
                es = dict(en_style)
                if role in ("emphasis", "alert"):
                    es["size"] = style.get("emphasis_en_size", es.get("size", 6))
                d.add_text("sub_en", s["en"], t0, s1 - s0, es, group_id=group_en)
            timeline_subs.append((t0, t0 + (s1 - s0), s))
        at += real
    total = at

    # 2) 라벨: 자막 줄에 붙은 맥락 라벨 + 타임라인 라벨
    labels = []
    for t0, t1, s in timeline_subs:
        if s.get("label"):
            labels.append({"text": s["label"], "at": t0, "dur": t1 - t0, "kind": "context"})
    labels += plan.get("labels", [])

    # 3) B롤 (겹치면 두 번째 오버레이 트랙)
    layers = [[], []]
    for br in sorted(plan.get("broll", []), key=lambda x: x["at"]):
        t0, dur = float(br["at"]), float(br["dur"])
        if t0 >= total:
            continue
        dur = min(dur, total - t0)
        li = 0 if all(t0 >= e or t0 + dur <= s for s, e in layers[0]) else 1
        layers[li].append((t0, t0 + dur))
        binf = info(br["src"])
        if br.get("fit") == "pip":
            pip = br.get("pip") or {}
            scale, tx, ty = float(pip.get("scale", 0.6)), float(pip.get("x", 0.0)), float(pip.get("y", 0.25))
            d.add_video(f"broll{li + 1}", win(br["src"]), float(br.get("in", 0)), dur, t0, overlay=True,
                        volume=float(br.get("volume", 0.0)), info=binf, scale=scale, transform=(tx, ty))
        else:
            d.add_video(f"broll{li + 1}", win(br["src"]), float(br.get("in", 0)), dur, t0, overlay=True,
                        volume=float(br.get("volume", 0.0)), fit=br.get("fit", "fill"), info=binf)
        if br.get("caption"):
            d.add_text("pip_caption", br["caption"], t0, dur, dict(style.get("pip_caption") or {}))
        top = br.get("top_label") or (style.get("ai_image_label") if br.get("ai") else None)
        if top:
            labels.append({"text": top, "at": t0, "dur": dur, "kind": "top"})

    for lb in labels:
        kind = "top_label" if lb.get("kind") == "top" else "label"
        t0 = float(lb["at"])
        dur = min(float(lb["dur"]), total - t0)
        if dur > 0.1:
            _add_nonoverlap(d, kind, lb["text"], t0, dur, dict(style.get(kind) or {}))

    # 4) 엔딩 카드
    ending = plan.get("ending")
    if ending and ending.get("text"):
        dur = min(float(ending.get("dur", 2.5)), total)
        d.add_text("ending", ending["text"], total - dur, dur, dict(style.get("ending") or {}))

    # 5) BGM
    bg = bgm or plan.get("bgm")
    if bg:
        if isinstance(bg, str):
            bg = {"src": bg}
        bstyle = style.get("bgm", {})
        d.add_audio("bgm", win(bg["src"]), float(bg.get("in", 0)), total, 0.0,
                    volume=float(bg.get("volume", bstyle.get("volume", 0.03))),
                    fade_in=float(bg.get("fade_in", 0)), fade_out=float(bg.get("fade_out", bstyle.get("fade_out", 3))),
                    name=bg.get("name"), info=bg.get("info") or info(bg["src"]),
                    music_template=bool(bg.get("music_template")))

    folder = d.save(drafts_root, name, path_map={drafts_root: win(drafts_root)} if path_map else None)
    try:  # 프로젝트 목록용 썸네일
        import subprocess
        first = plan["main"][0]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(float(first["in"]) + 1), "-i", first["src"],
                        "-frames:v", "1", "-vf", "scale=540:-2", os.path.join(folder, "draft_cover.jpg")],
                       timeout=60, capture_output=True)
    except Exception:
        pass
    n_sub = len(d.tracks.get("sub_ko", {}).get("segments", []))
    n_lab = sum(len(d.tracks[k]["segments"]) for k in ("label", "top_label") if k in d.tracks)
    print(f"드래프트 생성 완료: {folder}\n  길이 {total:.1f}s / 메인 컷 {len(plan['main'])} / 자막 {n_sub} / "
          f"라벨 {n_lab} / B롤 {sum(map(len, layers))} / 엔딩 {'O' if ending else 'X'}")
    return folder


def _add_nonoverlap(d, track, text, t0, dur, style):
    """같은 트랙에서 겹치지 않게 시작을 뒤로 밀어 추가."""
    tr = d.tracks.get(track)
    if tr:
        for s in tr["segments"]:
            a = s["target_timerange"]["start"] / 1e6
            b = a + s["target_timerange"]["duration"] / 1e6
            if a < t0 + dur and t0 < b:
                cut = b - t0
                t0, dur = b, dur - cut
        if dur <= 0.1:
            return
    d.add_text(track, text, t0, dur, style)


def main():
    ap = argparse.ArgumentParser(description="캡컷 자동 편집 에이전트")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "analyze", "plan", "build"):
        p = sub.add_parser(c)
        p.add_argument("--work", default="work")
        if c in ("run", "analyze"):
            p.add_argument("--clips", required=True)
            p.add_argument("--broll")
            p.add_argument("--whisper", default="large-v3")
            p.add_argument("--device", default="auto", help="cpu / cuda / auto")
        if c in ("run", "plan"):
            p.add_argument("--brief", default="")
            p.add_argument("--target", type=float)
            p.add_argument("--model")
            p.add_argument("--prompt-only", action="store_true")
        if c in ("run", "build"):
            p.add_argument("--name", required=True)
            p.add_argument("--bgm")
            p.add_argument("--drafts-root", default=DEFAULT_ROOT)
            p.add_argument("--style", help="스타일 프리셋 이름(target, interview_1006) 또는 JSON 경로")
        if c == "build":
            p.add_argument("--plan", default=None)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    analysis = os.path.join(a.work, "analysis.json")
    plan_path = getattr(a, "plan", None) or os.path.join(a.work, "edit_plan.json")

    if a.cmd in ("run", "analyze"):
        from analyze import analyze
        analyze(a.clips, a.work, a.broll, a.whisper, a.device)
    if a.cmd in ("run", "plan"):
        import planner
        if a.prompt_only or not os.environ.get("ANTHROPIC_API_KEY"):
            planner.write_prompt_only(analysis, os.path.join(a.work, "plan_prompt.txt"), a.brief, a.target)
            print("ANTHROPIC_API_KEY가 없어 프롬프트만 저장했습니다. Claude 응답 JSON을 work/edit_plan.json 으로 저장 후 build 하세요.")
            return
        planner.plan(analysis, plan_path, a.brief, a.target, a.model)
    if a.cmd in ("run", "build"):
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        if any("lines" in c and not c.get("subs") for c in plan["main"]):
            import subtimer
            speech = {}
            if os.path.exists(analysis):
                with open(analysis, encoding="utf-8") as f:
                    for c in json.load(f)["clips"]:
                        speech[c["src"]] = [(s["start"], s["end"]) for s in c["transcript"]]
            subtimer.apply(plan, speech)
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=1)
        if os.path.exists(analysis):
            with open(analysis, encoding="utf-8") as f:
                an = json.load(f)
            plan.setdefault("faces", an.get("faces", {}))
            for k, v in an.get("media", {}).items():
                plan.setdefault("media", {}).setdefault(k, v)
        build_from_plan(plan, a.name, a.drafts_root, load_style(a.style or plan.get("style")), bgm=a.bgm)


if __name__ == "__main__":
    main()
