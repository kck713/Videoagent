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


def build_from_plan(plan, name, drafts_root=None, style=None, bgm=None, path_map=None, canvas=(1080, 1920), fps=30.0,
                    sfx_dir=None):
    """edit_plan → 캡컷 프로젝트.

    plan 키:
      main[]   {src, in, out, subs[]|lines[], zoom?, face?}
               subs[] {start, end(원본 시간), ko, en?, role?(normal|quote|emphasis|alert|aside), highlight[], label?,
                       reveal?(단어 단위 등장), words?[(s,e,text)]}
      hook     {text, sub?, dur?}                                  첫 dur초 상단 훅 카드 (스타일 hook_card)
      message_cards[] {at, dur?, text | value+caption(kind: stat), replace_subs?}  중앙 띠 메시지 카드
      labels[] {text, at, dur, kind: "context"|"top"}           (타임라인 시간)
      broll[]  {src, at, dur, in?, fit: fill|fit|pip, pip?{scale,x,y}, caption?, ai?, top_label?, volume?}
      ending   {text, dur}                                        마지막 dur초 동안 중앙 검정 박스
      sfx[]    {at, kind|src, volume?}  (+ 스타일 sfx로 훅·카드·강조에 자동 배치, SFX 폴더 필요)
      bgm, layout, faces{src:{x,y,h}}, media{src:info}, style?
    """
    import motion as mo

    style = style or load_style(plan.get("style"))
    drafts_root = drafts_root or DEFAULT_ROOT
    media = plan.get("media", {})
    faces = plan.get("faces", {})
    cw, ch = plan.get("canvas") or canvas
    d = Draft(cw, ch, fps=fps)
    assets_dir = os.path.join(drafts_root, name, "assets")

    def win(p):
        p = p.replace("\\", "/")
        for a, b in (path_map or {}).items():
            if p.startswith(a):
                return b + p[len(a):]
        return p

    def info(p):
        return media.get(p) or media.get(win(p))

    motion_cfg = style.get("motion") or {}
    motion_on = bool(motion_cfg.get("enabled", True)) and plan.get("motion", True) and bool(motion_cfg)

    def move(seg, key):
        """스타일 motion[key] 지정을 세그먼트에 적용(모션이 켜져 있을 때)."""
        if motion_on and seg is not None and motion_cfg.get(key):
            mo.apply_style(seg, motion_cfg[key])
        return seg

    lay = dict(style.get("layout") or {}, **(plan.get("layout") or {}))
    mode = lay.get("mode", "fixed")
    zooms = lay.get("zoom_pattern", [1.0])
    group_ko, group_en = "ko-KR_agent", "en-US_agent"
    en_style = style.get("en")
    timeline_subs = []   # (t0, t1, sub) — 라벨 배치용
    sfx_marks = []       # (t, kind) — 효과음 자동 배치 후보

    # 메시지 카드 시간표 (자막 대체 여부 판단용)
    cards = []
    mc_style = style.get("message_card") or {}
    for c in plan.get("message_cards") or []:
        try:
            t0 = float(c["at"])
        except (KeyError, TypeError, ValueError):
            continue
        cards.append((t0, t0 + float(c.get("dur", mc_style.get("dur", 3.0))), c))

    def replaced_by_card(t0, t1):
        return any(c.get("replace_subs") and a - 0.05 <= t0 and t1 <= b + 0.05 for a, b, c in cards)

    reveal_roles = set(motion_cfg.get("reveal_roles") or []) if motion_on else set()
    role_motion = motion_cfg.get("roles") or {}

    # 1) 메인 컷 + 자막
    at = 0.0
    prev_z = None
    sync = plan.get("sync", {})          # 멀티캠: {카메라 src: 기준 대비 오프셋(초)} (sync.py)
    speakers = plan.get("speakers", {})  # {"A": {"name": "...", "title": "..."}}
    name_tags = []                       # (t0, dur, speaker)
    prev_speaker = None
    for i, clip in enumerate(plan["main"]):
        src, a, b = clip["src"], float(clip["in"]), float(clip["out"])
        # 멀티캠: 자막·컷 시간은 기준 카메라(src) 기준, 화면은 angle 카메라로
        vsrc, va = src, a
        if clip.get("angle") and clip["angle"] != src:
            vsrc = clip["angle"]
            va = a + float(sync.get(vsrc, sync.get(win(vsrc), 0.0))) - float(sync.get(src, 0.0))
        inf = info(vsrc) or {}
        if mode == "fixed":
            scale, tx, ty = float(lay.get("scale", 1.0)), float(lay.get("x", 0.0)), float(lay.get("y", 0.0))
        else:
            if not inf.get("width"):
                from capcut_draft import probe
                inf = probe(win(vsrc))
                media[vsrc] = inf
            if clip.get("zoom") is not None:
                z = float(clip["zoom"])
            else:  # 직전 컷과 다른 배율로 교차 (점프컷을 샷 변화로 보이게)
                cand = [x for x in zooms if prev_z is None or abs(x - prev_z) > 1e-3] or zooms
                z = float(cand[0])
            prev_z = z
            tgt = lay.get("closeup_face_target" if z > 1.05 else "face_target", [0.5, 0.40])
            if clip.get("focus"):            # 특정 부위(원본 좌표 0~1)를 화면 가운데로 — 극단 확대용
                face, tgt = clip["focus"], [0.5, 0.5]
            else:
                face = clip.get("face") or face_for_range(faces.get(vsrc) or faces.get(win(vsrc)), va, va + b - a)
            scale, tx, ty = framing(inf, cw, ch, face, zoom=z, face_target=tuple(tgt))
        seg = d.add_video("main", win(vsrc), va, b - a, at, info=inf or None, scale=scale, transform=(tx, ty))
        if clip.get("focus") and clip.get("zoom"):
            move(seg, "focus")
        spk = clip.get("speaker")
        if spk and spk in speakers and (spk != prev_speaker or clip.get("name_tag")):
            name_tags.append((at, spk))
        prev_speaker = spk or prev_speaker
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
            timeline_subs.append((t0, t0 + (s1 - s0), s))
            if role in ("emphasis", "alert"):
                sfx_marks.append((t0, role))
            if text and not replaced_by_card(t0, t0 + (s1 - s0)):
                do_reveal = s.get("reveal") if s.get("reveal") is not None else (role in reveal_roles)
                if do_reveal:
                    words = [(w[0] - a + at, w[1] - a + at, w[2]) for w in (s.get("words") or [])]
                    pieces = mo.split_reveal(text, t0, t0 + (s1 - s0), words,
                                             tail=float(motion_cfg.get("reveal_tail", 0.4)))
                else:
                    pieces = [(t0, t0 + (s1 - s0), text)]
                for k, (p0, p1, ptxt) in enumerate(pieces):
                    pst = dict(st)
                    if len(pieces) > 1:
                        pst["_highlight"] = [h for h in pst["_highlight"] if h in ptxt]
                    tseg = d.add_text("sub_ko", ptxt, p0, p1 - p0, pst, group_id=group_ko)
                    if motion_on:
                        if len(pieces) > 1:
                            rp = motion_cfg.get("reveal_pop") or {"scale_from": 1.12, "dur": 0.1}
                            mo.pop(tseg, rp.get("scale_from", 1.12), rp.get("dur", 0.1))
                        elif role_motion.get(role):
                            mo.apply_style(tseg, role_motion[role])
            if s.get("en") and en_style:
                es = dict(en_style)
                if role in ("emphasis", "alert"):
                    es["size"] = style.get("emphasis_en_size", es.get("size", 6))
                d.add_text("sub_en", s["en"], t0, s1 - s0, es, group_id=group_en)
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
            bseg = d.add_video(f"broll{li + 1}", win(br["src"]), float(br.get("in", 0)), dur, t0, overlay=True,
                               volume=float(br.get("volume", 0.0)), info=binf, scale=scale, transform=(tx, ty))
            move(bseg, "pip")
        else:
            bseg = d.add_video(f"broll{li + 1}", win(br["src"]), float(br.get("in", 0)), dur, t0, overlay=True,
                               volume=float(br.get("volume", 0.0)), fit=br.get("fit", "fill"), info=binf)
            from capcut_draft import is_image
            if is_image(br["src"]) and br.get("motion", True):
                move(bseg, "broll_image")
        if br.get("caption"):
            move(d.add_text("pip_caption", br["caption"], t0, dur, dict(style.get("pip_caption") or {})), "pip_caption")
        top = br.get("top_label") or (style.get("ai_image_label") if br.get("ai") else None)
        if top:
            labels.append({"text": top, "at": t0, "dur": dur, "kind": "top"})

    for lb in labels:
        kind = "top_label" if lb.get("kind") == "top" else "label"
        t0 = float(lb["at"])
        dur = min(float(lb["dur"]), total - t0)
        if dur > 0.1:
            move(_add_nonoverlap(d, kind, lb["text"], t0, dur, dict(style.get(kind) or {})), kind)

    # 3-1) 화자 이름표 (화자가 바뀔 때 첫 dur초)
    nt = style.get("name_tag")
    if nt:
        for t0, spk in name_tags:
            sp = speakers[spk]
            dur = min(float(nt.get("dur", 2.5)), total - t0)
            if sp.get("title"):
                move(_add_nonoverlap(d, "name_title", sp["title"], t0, dur, dict(nt["title"])), "name_tag")
            if sp.get("name"):
                move(_add_nonoverlap(d, "name_tag", sp["name"], t0, dur, dict(nt["name"])), "name_tag")

    # 3-2) 원형 강조 표시 (callouts: 화면 좌표 x,y 0~1, 위가 0)
    if plan.get("callouts"):
        from assets import ring
        co = style.get("callout") or {}
        ring_png = ring(os.path.join(assets_dir, "ring.png"), color=co.get("ring_color", "#FFD43B"))
        for c in plan["callouts"]:
            t0, dur = float(c["at"]), min(float(c.get("dur", 1.5)), total - float(c["at"]))
            if dur <= 0.1:
                continue
            cseg = d.add_video("callout", win(ring_png), 0.0, dur, t0, overlay=True, volume=0.0,
                               info={"width": 400, "height": 400, "image": True},
                               scale=float(c.get("size", co.get("ring_scale", 0.35))),
                               transform=((float(c["x"]) - 0.5) * 2, (0.5 - float(c["y"])) * 2))
            move(cseg, "callout")

    # 3-3) 훅 카드 (첫 몇 초, 상단) — 스타일에 hook_card가 있을 때
    hook = plan.get("hook")
    hc = style.get("hook_card")
    if hook and hc and (hook.get("text") if isinstance(hook, dict) else hook):
        if isinstance(hook, str):
            hook = {"text": hook}
        dur = min(float(hook.get("dur", hc.get("dur", 2.8))), total)
        _backdrop(d, "hook_bg", hc.get("backdrop"), 0.0, dur, assets_dir, cw, ch, win, move)
        move(d.add_text("hook_text", hook["text"], 0.0, dur, dict(hc.get("text") or {})), "hook_text")
        if hook.get("sub") and hc.get("sub"):
            move(d.add_text("hook_sub", hook["sub"], 0.0, dur, dict(hc["sub"])), "hook_sub")
        sfx_marks.insert(0, (0.0, "hook"))

    # 3-4) 메시지 카드 (중앙 띠 + 큰 글씨) — 핵심 문장·숫자를 화면 가운데에 박아 넣음
    if cards and mc_style:
        for t0, t1, c in cards:
            if t0 >= total - 0.3:
                continue
            t1 = min(t1, total)
            _backdrop(d, "card_bg", mc_style.get("backdrop"), t0, t1 - t0, assets_dir, cw, ch, win, move)
            if c.get("kind") == "stat" and c.get("value"):
                move(d.add_text("card_value", str(c["value"]), t0, t1 - t0,
                                dict(mc_style.get("stat_value") or mc_style.get("text") or {})), "card_text")
                if c.get("caption"):
                    move(d.add_text("card_caption", c["caption"], t0, t1 - t0,
                                    dict(mc_style.get("stat_caption") or {})), "card_caption")
            elif c.get("text"):
                st = dict(mc_style.get("text") or {})
                st["_highlight"] = c.get("highlight") or []
                st["highlight_color"] = mc_style.get("highlight_color", style.get("highlight_color", "#F2D475"))
                move(d.add_text("card_text", c["text"], t0, t1 - t0, st), "card_text")
            sfx_marks.append((t0, "card"))

    # 3-5) 상단 고정 제목 (영상 전체)
    title = plan.get("title")
    if title and style.get("title"):
        for k in ("line1", "line2"):
            if title.get(k):
                move(d.add_text(f"title_{k}", title[k], 0.0, total, dict(style["title"][k])), "title")

    # 3-6) 테두리 (맨 위 오버레이, 영상 전체)
    if style.get("frame") and plan.get("frame", True):
        from assets import frame_border
        fr = style["frame"]
        png = frame_border(os.path.join(assets_dir, "frame.png"), cw, ch,
                           fr.get("inset", 0.028), fr.get("width", 6), fr.get("radius", 0.035),
                           tuple(fr.get("colors", ["#FFA237", "#F5C760"])))
        d.add_video("frame", win(png), 0.0, total, 0.0, overlay=True, volume=0.0,
                    info={"width": cw, "height": ch, "image": True}, scale=1.0)

    # 3-7) 하단 면책 문구
    disc = plan.get("disclaimer")
    if disc and style.get("disclaimer"):
        if isinstance(disc, str):
            disc = {"text": disc}
        dur = min(float(disc.get("dur", 4.0)), total)
        d.add_text("disclaimer", disc["text"], total - dur if not disc.get("all") else 0.0,
                   total if disc.get("all") else dur, dict(style["disclaimer"]))

    # 4) 엔딩 카드
    ending = plan.get("ending")
    if ending and ending.get("text"):
        dur = min(float(ending.get("dur", 2.5)), total)
        move(d.add_text("ending", ending["text"], total - dur, dur, dict(style.get("ending") or {})), "ending")

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

    # 6) 효과음 (SFX 폴더가 있을 때만): 플랜 sfx[] + 훅/카드/강조 자동 배치
    n_sfx = _add_sfx(d, plan, style, sfx_marks, total, sfx_dir or plan.get("sfx_dir"), win, info)

    folder = d.save(drafts_root, name, path_map={drafts_root: win(drafts_root)} if path_map else None)
    try:  # 프로젝트 목록용 썸네일
        import subprocess
        first = plan["main"][0]
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(float(first["in"]) + 1), "-i", first["src"],
                        "-frames:v", "1", "-vf", "scale=540:-2", os.path.join(folder, "draft_cover.jpg")],
                       timeout=60, capture_output=True)
    except Exception:
        pass
    if plan.get("sticker_notes"):
        notes = os.path.join(folder, "스티커_메모.txt")
        with open(notes, "w", encoding="utf-8") as f:
            for n in plan["sticker_notes"]:
                f.write(f"{float(n['at']):6.1f}s  {n.get('text', '')}\n")
        print(f"  스티커 넣을 위치 {len(plan['sticker_notes'])}곳 → {notes}")
    n_sub = len(d.tracks.get("sub_ko", {}).get("segments", []))
    n_lab = sum(len(d.tracks[k]["segments"]) for k in ("label", "top_label") if k in d.tracks)
    n_kf = sum(1 for tr in d.d["tracks"] for s in tr["segments"] if s.get("common_keyframes"))
    n_cards = len(d.tracks.get("card_bg", {}).get("segments", []))
    print(f"드래프트 생성 완료: {folder}\n  길이 {total:.1f}s / 메인 컷 {len(plan['main'])} / 자막 {n_sub} / "
          f"라벨 {n_lab} / B롤 {sum(map(len, layers))} / 훅 카드 {'O' if 'hook_text' in d.tracks else 'X'} / "
          f"메시지 카드 {n_cards} / 엔딩 {'O' if ending else 'X'} / 모션 세그먼트 {n_kf} / 효과음 {n_sfx}")
    return folder


def _backdrop(d, track, spec, t0, dur, assets_dir, cw, ch, win, move):
    """카드 배경(반투명 띠/그라데이션) PNG를 만들어 오버레이로 깜. spec: {kind: band|gradient_top, ...}"""
    if not spec or dur <= 0.1:
        return None
    import assets
    kind = spec.get("kind", "band")
    if kind == "gradient_top":
        png = assets.gradient_top(os.path.join(assets_dir, f"{track}_gradient.png"), cw, ch,
                                  spec.get("height", 0.42), spec.get("alpha", 0.82), spec.get("color", "#000000"))
    else:
        tag = f"{spec.get('y', 0.5)}_{spec.get('height', 0.26)}".replace(".", "p")
        png = assets.band(os.path.join(assets_dir, f"{track}_band_{tag}.png"), cw, ch, spec.get("y", 0.5),
                          spec.get("height", 0.26), spec.get("alpha", 0.78), spec.get("color", "#000000"),
                          spec.get("radius", 0.0), spec.get("inset", 0.0), spec.get("feather", 0))
    tr = d.tracks.get(track)
    if tr:  # 같은 트랙에서 겹치면 뒤로 민다
        for s in tr["segments"]:
            a = s["target_timerange"]["start"] / 1e6
            b = a + s["target_timerange"]["duration"] / 1e6
            if a < t0 + dur and t0 < b:
                t0, dur = b, dur - (b - t0)
        if dur <= 0.1:
            return None
    seg = d.add_video(track, win(png), 0.0, dur, t0, overlay=True, volume=0.0,
                      info={"width": cw, "height": ch, "image": True}, scale=1.0)
    return move(seg, "backdrop")


def _find_sfx(folder, kind):
    """SFX 폴더에서 이름이 kind로 시작하는 파일(예: pop.mp3, hit_2.wav)."""
    if not folder or not os.path.isdir(folder) or not kind:
        return None
    for f in sorted(os.listdir(folder)):
        if f.lower().startswith(str(kind).lower()) and f.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
            return os.path.join(folder, f).replace("\\", "/")
    return None


def _add_sfx(d, plan, style, marks, total, sfx_dir, win, info):
    sx = style.get("sfx") or {}
    items = list(plan.get("sfx") or [])
    if sx and marks:
        auto, used = [], []
        for t, kind in sorted(marks):
            if t >= total - 0.2 or any(abs(t - u) < float(sx.get("min_gap", 0.6)) for u in used):
                continue
            if sx.get(kind):
                auto.append({"at": t, "kind": kind})
                used.append(t)
        items += auto[: int(sx.get("max_auto", 10))]
    if not items:
        return 0
    folder = sfx_dir or ("SFX" if os.path.isdir("SFX") else None)
    n = 0
    for it in items:
        src = it.get("src") or _find_sfx(folder, sx.get(it.get("kind"), it.get("kind")))
        if not src:
            continue
        try:
            inf = info(src) or __import__("capcut_draft").probe(src)
        except Exception:
            continue
        t0 = float(it["at"])
        dur = min(float(inf.get("duration", 1.0)), float(it.get("max_dur", sx.get("max_dur", 2.0))), total - t0)
        if dur <= 0.05:
            continue
        key = "sfx"
        for k in ("sfx", "sfx2", "sfx3"):   # 겹치면 다음 트랙
            tr = d.tracks.get(k)
            if not tr or all(not (s["target_timerange"]["start"] / 1e6 < t0 + dur
                                  and t0 < (s["target_timerange"]["start"] + s["target_timerange"]["duration"]) / 1e6)
                             for s in tr["segments"]):
                key = k
                break
        else:
            continue
        d.add_audio(key, win(src), 0.0, dur, t0, volume=float(it.get("volume", sx.get("volume", 0.6))), info=inf)
        n += 1
    if items and n == 0 and not folder:
        print("  (효과음: SFX 폴더가 없어 생략 — 레포 루트 SFX/ 에 pop.mp3, hit.mp3, whoosh.mp3 등을 넣으면 자동 배치)")
    return n


def _add_nonoverlap(d, track, text, t0, dur, style):
    """같은 트랙에서 겹치지 않게 시작을 뒤로 밀어 추가. 추가한 세그먼트(또는 None) 반환."""
    tr = d.tracks.get(track)
    if tr:
        for s in tr["segments"]:
            a = s["target_timerange"]["start"] / 1e6
            b = a + s["target_timerange"]["duration"] / 1e6
            if a < t0 + dur and t0 < b:
                cut = b - t0
                t0, dur = b, dur - cut
        if dur <= 0.1:
            return None
    return d.add_text(track, text, t0, dur, style)


def check(model=None):
    """설치·설정 점검 (다른 PC에서 처음 쓸 때)."""
    import importlib
    import shutil
    ok = True

    def line(good, msg, fix=""):
        nonlocal ok
        ok = ok and good
        print(("  [OK]   " if good else "  [문제] ") + msg + ("" if good or not fix else f"\n         → {fix}"))

    print("환경 점검")
    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Python 3.10 이상을 설치하세요")
    for mod, pip in (("faster_whisper", "faster-whisper"), ("anthropic", "anthropic"), ("cv2", "opencv-python-headless<5"),
                     ("numpy", "numpy"), ("PIL", "pillow")):
        try:
            m = importlib.import_module(mod)
            good = not (mod == "cv2" and not hasattr(m, "CascadeClassifier"))
            line(good, f"패키지 {mod}", f'pip install "{pip}"')
        except ImportError:
            line(False, f"패키지 {mod} 없음", f'설치.bat 실행 또는 pip install "{pip}"')
    for exe in ("ffmpeg", "ffprobe"):
        line(bool(shutil.which(exe)), f"{exe}", "설치.bat 실행 후 창을 새로 여세요 (winget install Gyan.FFmpeg)")
    line(os.path.isdir(DEFAULT_ROOT), f"캡컷 프로젝트 폴더: {DEFAULT_ROOT}", "CapCut 데스크톱을 설치하고 한 번 실행하세요")
    apps = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "Apps")
    vers = sorted(d for d in os.listdir(apps)) if os.path.isdir(apps) else []
    with open(os.path.join(HERE, "template_pack.json"), encoding="utf-8") as f:
        tv = json.load(f).get("app_version")
    if vers:
        same = any(v.startswith(tv or "?") for v in vers)
        line(same, f"캡컷 버전 {vers[-1]} (템플릿 {tv})",
             "버전이 다릅니다. 이 캡컷에서 프로젝트를 하나 저장한 뒤 make_template.py로 템플릿을 다시 뽑으세요(README 참고)")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        line(False, "Claude API 키 없음 (Claude Code의 /edit 를 쓰면 필요 없음)", "API키_설정.bat 실행")
    else:
        model = model or os.environ.get("CAPCUT_AGENT_MODEL", "claude-opus-5-5")
        try:
            import anthropic
            r = anthropic.Anthropic().messages.create(model=model, max_tokens=16,
                                                      messages=[{"role": "user", "content": "ping"}])
            line(True, f"Claude API 연결 ({model}, 키 …{key[-4:]})")
        except Exception as e:  # noqa: BLE001
            msg = str(e).split("\n")[0][:160]
            low = msg.lower()
            fix = "인터넷 연결과 console.anthropic.com의 키·결제 상태를 확인하세요"
            if "401" in msg or "authentication" in low:
                msg, fix = "API 키가 올바르지 않습니다", "API키_설정.bat으로 키를 다시 입력하세요 (sk-ant-로 시작)"
            elif "credit" in low or "billing" in low:
                msg, fix = "크레딧/결제 문제", "console.anthropic.com → Billing에서 크레딧을 충전하세요"
            elif "model" in low:
                fix = "CAPCUT_AGENT_MODEL 환경변수의 모델 이름을 확인하세요"
            line(False, f"Claude API 연결 실패: {msg}", fix)
    print("\n모두 정상입니다." if ok else "\n[문제] 항목을 해결한 뒤 다시 점검하세요.")
    return ok


def main():
    ap = argparse.ArgumentParser(description="캡컷 자동 편집 에이전트")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check", help="설치·설정 점검 (API 키 연결 확인 포함)")
    pc.add_argument("--model")
    pk = sub.add_parser("clip", help="파일 내용을 클립보드로 복사(Windows, 한글 안전)")
    pk.add_argument("file")
    pq = sub.add_parser("critique", help="편집 계획 품질 점검: 훅·메시지·템포·자막 길이 (Claude Code /edit 자기 점검용)")
    pq.add_argument("--work", default="work")
    pq.add_argument("--plan")
    pq.add_argument("--style")
    pq.add_argument("--target", type=float)
    pi = sub.add_parser("import-plan", help="무료 모드: claude.ai 답변을 붙여넣은 edit_plan.json 검사·정리")
    pi.add_argument("--work", default="work")
    pi.add_argument("--style")
    pi.add_argument("--target", type=float)
    for c in ("run", "analyze", "plan", "build"):
        p = sub.add_parser(c)
        p.add_argument("--work", default="work")
        if c in ("run", "analyze"):
            p.add_argument("--clips", required=True)
            p.add_argument("--broll")
            p.add_argument("--whisper", default="large-v3")
            p.add_argument("--device", default="auto", help="cpu / cuda / auto")
            p.add_argument("--multicam", action="store_true", help="원본 폴더 영상들을 같은 장면의 여러 카메라로 보고 오디오로 동기화")
        if c in ("run", "plan"):
            p.add_argument("--style", help="스타일 프리셋 (target, talk_short, interview_1006)")
            p.add_argument("--brief", default="")
            p.add_argument("--target", type=float)
            p.add_argument("--model")
            p.add_argument("--prompt-only", action="store_true")
            p.add_argument("--no-review", action="store_true", help="편집장 리뷰 패스(훅·메시지·템포 보강) 생략")
        if c in ("run", "build"):
            p.add_argument("--name", required=True)
            p.add_argument("--bgm")
            p.add_argument("--drafts-root", default=DEFAULT_ROOT)
            p.add_argument("--sfx", help="효과음 폴더 (pop/hit/whoosh… 이름으로 시작하는 파일). 기본: 레포 루트 SFX/")
            if c == "build":
                p.add_argument("--style", help="스타일 프리셋 이름(target, talk_short, interview_1006) 또는 JSON 경로")
        if c == "build":
            p.add_argument("--plan", default=None)
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(0 if check(a.model) else 1)
    if a.cmd == "clip":
        import subprocess
        with open(a.file, encoding="utf-8-sig") as f:
            text = f.read()
        subprocess.run(["clip"], input=text.encode("utf-16"), check=True)  # BOM 포함 UTF-16 → 한글 안 깨짐
        print(f"클립보드에 복사했습니다 ({len(text):,}자).")
        sys.exit(0)
    if a.cmd == "critique":
        import planner
        pp = a.plan or os.path.join(a.work, "edit_plan.json")
        with open(pp, encoding="utf-8") as f:
            plan = json.load(f)
        an = None
        ap_ = os.path.join(a.work, "analysis.json")
        if os.path.exists(ap_):
            with open(ap_, encoding="utf-8") as f:
                an = json.load(f)
        report = planner.critique(plan, load_style(a.style or plan.get("style")), a.target, an)
        print(planner.format_critique(report))
        sys.exit(0 if not report["warnings"] else 2)
    if a.cmd == "import-plan":
        import planner
        errs = planner.import_plan(os.path.join(a.work, "analysis.json"), os.path.join(a.work, "edit_plan.json"),
                                   a.style, a.target)
        if errs:
            print("[문제] 붙여넣은 계획에 문제가 있습니다:\n - " + "\n - ".join(errs))
            print("\n같은 claude.ai 대화에 아래 파일 내용을 보내 다시 받은 뒤, 답변을 다시 붙여넣으세요:")
            print("  " + os.path.join(a.work, "edit_plan_fix.txt"))
            sys.exit(1)
        with open(os.path.join(a.work, "edit_plan.json"), encoding="utf-8") as f:
            plan = json.load(f)
        rep = planner.critique(plan, load_style(a.style or plan.get("style")), a.target)
        if rep["warnings"]:
            print("계획 확인 완료. 더 강하게 만들 수 있는 점(선택):\n - " + "\n - ".join(rep["warnings"]))
        else:
            print("계획 확인 완료.")
        sys.exit(0)
    os.makedirs(a.work, exist_ok=True)
    analysis = os.path.join(a.work, "analysis.json")
    plan_path = getattr(a, "plan", None) or os.path.join(a.work, "edit_plan.json")

    if a.cmd in ("run", "analyze"):
        from analyze import analyze
        analyze(a.clips, a.work, a.broll, a.whisper, a.device, multicam=a.multicam)
    if a.cmd in ("run", "plan"):
        import planner
        if a.prompt_only or not os.environ.get("ANTHROPIC_API_KEY"):
            planner.write_prompt_only(analysis, os.path.join(a.work, "plan_prompt.txt"), a.brief, a.target, a.style)
            print("ANTHROPIC_API_KEY가 없어 프롬프트만 저장했습니다. Claude 응답 JSON을 work/edit_plan.json 으로 저장 후 build 하세요.")
            return
        planner.plan(analysis, plan_path, a.brief, a.target, a.model, a.style, review=not a.no_review)
    if a.cmd in ("run", "build"):
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        if any("lines" in c and not c.get("subs") for c in plan["main"]):
            import subtimer
            speech, words = {}, {}
            if os.path.exists(analysis):
                with open(analysis, encoding="utf-8") as f:
                    for c in json.load(f)["clips"]:
                        speech[c["src"]] = [(s["start"], s["end"]) for s in c["transcript"]]
                        words[c["src"]] = [tuple(w) for s in c["transcript"] for w in (s.get("words") or [])]
            subtimer.apply(plan, speech, words=words)
            st = load_style(a.style or plan.get("style"))
            tg = st.get("tighten") or {}
            if tg:
                subtimer.tighten(plan, max_pause=tg.get("max_pause"), max_cut=tg.get("max_cut"))
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=1)
        if os.path.exists(analysis):
            with open(analysis, encoding="utf-8") as f:
                an = json.load(f)
            plan.setdefault("faces", an.get("faces", {}))
            if an.get("sync"):
                plan.setdefault("sync", an["sync"])
            for k, v in an.get("media", {}).items():
                plan.setdefault("media", {}).setdefault(k, v)
        folder = build_from_plan(plan, a.name, a.drafts_root, load_style(a.style or plan.get("style")), bgm=a.bgm,
                                 sfx_dir=a.sfx)
        try:  # 미리보기 (캡컷 없이 구도·자막 확인용)
            import preview
            pv = preview.preview(folder, os.path.join(a.work, "preview.jpg"))
            print(f"미리보기 -> {pv}")
            if a.cmd == "run" and os.name == "nt":
                os.startfile(pv)  # noqa: S606
        except Exception as e:  # noqa: BLE001
            print(f"(미리보기 생략: {e})")


if __name__ == "__main__":
    main()
