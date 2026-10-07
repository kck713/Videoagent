"""자막 자동 타이밍.

편집 계획에서 각 컷에 자막 줄(lines)만 주면, 실제 음성을 보고 시간을 배분합니다.
- 컷 안의 발화 구간(전사 세그먼트)만 따라 글자 수 비율로 배분
- 경계는 근처(±0.35초)의 숨 쉬는 지점(에너지가 낮은 구간)에 스냅
"""
import subprocess

import numpy as np

_cache = {}


def energy_db(path, sr=16000, hop=0.01):
    """원본 오디오의 10ms 단위 에너지(dB). ffmpeg로 디코드."""
    if path in _cache:
        return _cache[path]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    h = int(sr * hop)
    n = len(a) // h
    e = np.sqrt((a[:n * h].reshape(n, h) ** 2).mean(1))
    db = 20 * np.log10(e + 1e-6)
    _cache[path] = db
    return db


def _dips(db, s, t, min_len=0.06):
    seg = db[int(s * 100):int(t * 100)]
    if len(seg) == 0:
        return []
    thr = np.percentile(seg, 22)
    low = seg < thr
    out, i = [], 0
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]:
                j += 1
            if (j - i) / 100 >= min_len:
                out.append(s + (i + j) / 200)  # 숨 구간의 가운데
            i = j
        else:
            i += 1
    return out


def _weight(text):
    return max(1, sum(1 for ch in text if not ch.isspace() and ch not in ".,?!~"))


def energy_speech(db, s, t, thr=-45.0, min_gap=0.25):
    """에너지 기준 발화 구간(VAD보다 말 시작/끝이 정확)."""
    seg = db[int(s * 100):int(t * 100)]
    on = seg > thr
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            out.append([s + i / 100, s + j / 100])
            i = j
        else:
            i += 1
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] < min_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= 0.12]


def refine_cut(db, cut_in, cut_out, pad_in=0.08, pad_out=0.15, look=0.6):
    """컷 경계를 실제 말 시작/끝에 맞춤 (첫 음절이 잘리지 않게)."""
    sp = energy_speech(db, cut_in - look, cut_out + look)
    if not sp:
        return cut_in, cut_out
    # cut_in 직전/직후에서 시작하는 발화의 시작점
    starts = [a for a, b in sp if cut_in - look <= a <= cut_in + 0.3]
    ends = [b for a, b in sp if a < cut_out and cut_out - 0.3 <= b <= cut_out + look]
    first = next(((a, b) for a, b in sp if b > cut_in), None)
    dips = _dips(db, cut_in - 0.4, cut_out + 0.4)

    def snap(t):
        near = [d for d in dips if abs(d - t) <= 0.25]
        return min(near, key=lambda d: abs(d - t)) if near else None

    new_in = cut_in
    if first and first[0] < cut_in < first[1]:
        if cut_in - first[0] <= 0.35:            # 감지가 살짝 늦어 첫 음절이 잘린 경우 → 말 시작으로 당김
            new_in = first[0] - pad_in
        elif snap(cut_in) is not None:           # 일부러 문장 중간에서 자른 경우 → 숨 지점에 스냅
            new_in = snap(cut_in)
    elif starts:
        new_in = min(starts, key=lambda a: abs(a - cut_in)) - pad_in
    last = next(((a, b) for a, b in reversed(sp) if a < cut_out), None)
    new_out = cut_out
    if last and last[0] < cut_out < last[1]:
        s = snap(cut_out)                        # 끝점은 숨 지점 우선 (다음 문장 첫 음절 방지)
        if s is not None:
            new_out = s
        elif last[1] - cut_out <= 0.35:
            new_out = last[1] + pad_out
    elif ends:
        new_out = min(max(ends) + pad_out, cut_out + look)
    return round(new_in, 2), round(new_out, 2)


def time_lines(cut_in, cut_out, lines, speech, db):
    """lines: 자막 문자열 리스트, speech: [(start,end), ...] 원본 시간 발화 구간.
    반환: [(start, end), ...] 원본 시간."""
    if db is not None:
        es = energy_speech(db, cut_in, cut_out)
        if es:
            speech = es
    sp = [(max(a, cut_in), min(b, cut_out)) for a, b in speech if b > cut_in and a < cut_out]
    if not sp:
        sp = [(cut_in, cut_out)]
    total = sum(b - a for a, b in sp)

    def at(frac):  # 발화 시간 기준 비율 → 원본 시간
        x = frac * total
        for a, b in sp:
            if x <= b - a:
                return a + x
            x -= b - a
        return sp[-1][1]

    w = [_weight(t) for t in lines]
    cum = np.cumsum(w) / sum(w)
    dips = _dips(db, cut_in, cut_out) if db is not None else []
    bounds = [max(cut_in, sp[0][0] - 0.05)]
    for f in cum[:-1]:
        t = at(f)
        near = [d for d in dips if abs(d - t) <= 0.35 and d > bounds[-1] + 0.3]
        if near:
            t = min(near, key=lambda d: abs(d - t))
        # 발화 사이 무음에 걸리면 다음 발화 시작으로
        for (a0, b0), (a1, b1) in zip(sp, sp[1:]):
            if b0 < t < a1:
                t = a1 - 0.05
        bounds.append(max(t, bounds[-1] + 0.3))
    bounds.append(min(cut_out, sp[-1][1] + 0.4))   # 말이 끝나면 자막도 끝 (꼬리 무음 구간 제외)
    return [(round(bounds[i], 2), round(bounds[i + 1], 2)) for i in range(len(lines))]


def apply(plan, transcripts, audio_of=None):
    """plan['main'][i]['lines'] → plan['main'][i]['subs'] (시간 포함) 변환.
    transcripts: {src: [(start,end), ...]} 발화 구간."""
    for clip in plan["main"]:
        if "lines" not in clip or clip.get("subs"):
            continue
        src = clip["src"]
        db = None
        try:
            db = energy_db((audio_of or {}).get(src, src))
        except Exception:
            pass
        lines = clip["lines"]
        if db is not None and clip.get("refine", True):
            clip["in"], clip["out"] = refine_cut(db, float(clip["in"]), float(clip["out"]))
        times = time_lines(float(clip["in"]), float(clip["out"]), [l["ko"] for l in lines],
                           transcripts.get(src, []), db)
        clip["subs"] = [dict(l, start=a, end=b) for l, (a, b) in zip(lines, times)]
    return plan
