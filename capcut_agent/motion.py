"""모션 그래픽: 캡컷 키프레임(common_keyframes)으로 세그먼트에 움직임을 넣습니다.

캡컷 스티커·텍스트 애니메이션은 서버 리소스(resource_id)가 필요해 자동 삽입이 불가능합니다.
대신 드래프트 안에 그대로 저장되는 **키프레임**(위치·배율·투명도)으로 같은 효과를 만듭니다.
- pop:        강조 자막·카드가 살짝 크게 나타났다가 제자리로 (scale 1.25 → 1.0)
- fade:       카드·라벨이 부드럽게 나타나고 사라짐 (alpha)
- slide_in:   라벨·이름표가 옆에서 밀려 들어옴 (position + alpha)
- rise:       자막이 아래에서 살짝 떠오름 (position y + alpha)
- ken_burns:  이미지 B롤을 천천히 확대 (scale)
- reveal:     한 줄 자막을 단어(어절) 단위로 하나씩 쌓아 올림 (세그먼트 분할, 각 조각 pop)

키프레임 포맷은 캡컷/JianYing 드래프트에서 널리 확인된 형식(pyJianYingDraft 등)을 따릅니다.
time_offset은 세그먼트 시작 기준 마이크로초, values는 [값] 한 개.
※ 2026-10-08 기준 사용자 PC 캡컷 9.4.0에서 재저장 검증 전 — 스타일의 "motion": {"enabled": false}로 끌 수 있고,
  검증은 `python capcut_agent/make_template.py --inspect <캡컷이 키프레임을 쓴 프로젝트>`로 실제 포맷과 비교합니다.
"""
import copy
import uuid

US = 1_000_000

PROP = {"x": "KFTypePositionX", "y": "KFTypePositionY", "scale_x": "KFTypeScaleX", "scale_y": "KFTypeScaleY",
        "alpha": "KFTypeAlpha", "rotation": "KFTypeRotation"}


def _id():
    return str(uuid.uuid4()).upper()


def add_keyframes(seg, prop, points):
    """seg['common_keyframes']에 속성 하나의 키프레임 열을 추가.
    prop: PROP 키("x","y","scale","alpha","rotation"), points: [(초, 값), ...] 세그먼트 시작 기준."""
    if prop == "scale":                       # 균등 배율은 X/Y 둘 다 같은 값으로
        add_keyframes(seg, "scale_x", points)
        add_keyframes(seg, "scale_y", points)
        return seg
    dur_us = seg["target_timerange"]["duration"]
    kfs = []
    for t, v in sorted(points):
        off = max(0, min(int(round(t * US)), dur_us))
        kfs.append({"id": _id(), "curveType": "Line", "graphID": "", "left_control": {"x": 0.0, "y": 0.0},
                    "right_control": {"x": 0.0, "y": 0.0}, "time_offset": off, "values": [float(v)]})
    seg.setdefault("common_keyframes", []).append(
        {"id": _id(), "material_id": "", "property_type": PROP[prop], "keyframe_list": kfs})
    return seg


def _dur(seg):
    return seg["target_timerange"]["duration"] / US


def pop(seg, scale_from=1.25, dur=0.12, base=None):
    """살짝 크게 나타나 제자리로. base: 세그먼트의 기본 배율(clip.scale.x)."""
    base = base if base is not None else seg["clip"]["scale"]["x"]
    d = min(dur, _dur(seg) * 0.5)
    if d <= 0:
        return seg
    return add_keyframes(seg, "scale", [(0.0, base * scale_from), (d, base)])


def fade(seg, fade_in=0.2, fade_out=0.0):
    total = _dur(seg)
    pts = []
    fi = min(fade_in, total * 0.45)
    fo = min(fade_out, total * 0.45)
    if fi > 0:
        pts += [(0.0, 0.0), (fi, 1.0)]
    if fo > 0:
        pts += [(total - fo, 1.0), (total, 0.0)]
    if not pts:
        return seg
    if fi <= 0:
        pts.insert(0, (0.0, 1.0))
    return add_keyframes(seg, "alpha", pts)


def slide_in(seg, dx=-0.08, dy=0.0, dur=0.22):
    """옆(또는 위아래)에서 밀려 들어오며 나타남. dx/dy는 캡컷 transform 단위(반 화면)."""
    d = min(dur, _dur(seg) * 0.5)
    if d <= 0:
        return seg
    x0, y0 = seg["clip"]["transform"]["x"], seg["clip"]["transform"]["y"]
    if dx:
        add_keyframes(seg, "x", [(0.0, x0 + dx), (d, x0)])
    if dy:
        add_keyframes(seg, "y", [(0.0, y0 + dy), (d, y0)])
    return add_keyframes(seg, "alpha", [(0.0, 0.0), (d, 1.0)])


def rise(seg, dy=-0.04, dur=0.16):
    """아래에서 살짝 떠오르며 나타남(자막용)."""
    return slide_in(seg, dx=0.0, dy=dy, dur=dur)


def ken_burns(seg, scale_from=1.0, scale_to=1.08):
    """이미지 B롤을 천천히 확대(또는 축소). 기본 배율에 곱함."""
    base = seg["clip"]["scale"]["x"]
    total = _dur(seg)
    if total <= 0.2:
        return seg
    return add_keyframes(seg, "scale", [(0.0, base * scale_from), (total, base * scale_to)])


def split_reveal(text, start, end, words=None, tail=0.0):
    """한 줄을 어절 단위로 쌓아 올리는 조각으로 나눔.
    words: [(w_start, w_end, w_text), ...] 그 줄 구간의 단어 타임스탬프(없으면 균등 배분).
    반환: [(조각 시작, 조각 끝, 보일 텍스트)] — 마지막 조각은 전체 문장, end까지."""
    chunks = [c for c in text.replace("\n", " ").split(" ") if c]
    if len(chunks) < 2 or end - start < 0.6:
        return [(start, end, text)]
    n = len(chunks)
    speak_end = end - tail if tail and end - tail > start + 0.3 else end
    if words:
        ws = sorted(w for w in words if start - 0.05 <= w[0] <= speak_end)
    else:
        ws = []
    if len(ws) >= 2:
        # 어절 i가 나타나는 시각 = 단어 목록을 비례로 대응
        starts = [ws[min(len(ws) - 1, round(i * len(ws) / n))][0] for i in range(n)]
    else:
        step = (speak_end - start) / n
        starts = [start + i * step for i in range(n)]
    starts[0] = start
    for i in range(1, n):                       # 단조 증가 + 최소 간격
        starts[i] = max(starts[i], starts[i - 1] + 0.08)
    out = []
    for i in range(n):
        a = starts[i]
        b = starts[i + 1] if i + 1 < n else end
        if b - a < 0.08 and i + 1 < n:
            continue
        out.append((round(a, 3), round(b, 3), " ".join(chunks[: i + 1])))
    if out:
        out[-1] = (out[-1][0], end, text)
    return out or [(start, end, text)]


def apply_style(seg, spec, base_scale=None):
    """스타일 JSON의 모션 지정 하나를 세그먼트에 적용.
    spec 예: {"pop": {"scale_from": 1.25, "dur": 0.12}, "fade": {"in": 0.2, "out": 0.2},
             "slide": {"dx": -0.08, "dur": 0.22}, "rise": {"dy": -0.04, "dur": 0.16}}"""
    if not spec:
        return seg
    if spec.get("pop"):
        p = spec["pop"] if isinstance(spec["pop"], dict) else {}
        pop(seg, p.get("scale_from", 1.25), p.get("dur", 0.12), base_scale)
    if spec.get("fade"):
        f = spec["fade"] if isinstance(spec["fade"], dict) else {}
        fade(seg, f.get("in", 0.2), f.get("out", 0.2))
    if spec.get("slide"):
        s = spec["slide"] if isinstance(spec["slide"], dict) else {}
        slide_in(seg, s.get("dx", -0.08), s.get("dy", 0.0), s.get("dur", 0.22))
    if spec.get("rise"):
        r = spec["rise"] if isinstance(spec["rise"], dict) else {}
        rise(seg, r.get("dy", -0.04), r.get("dur", 0.16))
    if spec.get("ken_burns"):
        k = spec["ken_burns"] if isinstance(spec["ken_burns"], dict) else {}
        ken_burns(seg, k.get("from", 1.0), k.get("to", 1.08))
    return seg


def strip(seg):
    """키프레임 제거(모션 끔)."""
    seg["common_keyframes"] = []
    return copy.deepcopy(seg)
