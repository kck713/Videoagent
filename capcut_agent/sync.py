"""멀티캠 오디오 동기화.

카메라 여러 대가 같은 대화를 녹음했을 때, 각 카메라의 소리를 기준 카메라와 비교해
시간 차이(오프셋)를 찾습니다. 결과: {카메라 src: 오프셋(초)} — "카메라 시간 = 기준 시간 + 오프셋".

방법: 8kHz 모노로 디코드 → 10ms 음량 변화(onset) 포락선 상호상관으로 대략 위치 → 원파형 상호상관으로 ±0.1초 정밀화.
마이크·거리·게인이 달라도 말소리의 리듬은 같아서 맞출 수 있습니다.

    python capcut_agent/sync.py 기준.mp4 카메라2.mp4 [카메라3.mp4 ...]
"""
import json
import subprocess
import sys

import numpy as np

SR = 8000


def load_audio(path, sr=SR, max_sec=None):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(sr)]
    if max_sec:
        cmd += ["-t", str(max_sec)]
    raw = subprocess.run(cmd + ["-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def onset_env(a, sr=SR, hop=0.01):
    h = int(sr * hop)
    n = len(a) // h
    e = np.log(np.sqrt((a[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-4)
    d = np.maximum(0, np.diff(e, prepend=e[0]))
    d -= d.mean()
    return d / (d.std() + 1e-9)


def _xcorr(a, b):
    """b가 a보다 lag만큼 늦게 시작한다고 볼 때의 상관 (전 구간). 반환: (lags, corr)"""
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)), nfft)
    c = np.concatenate([c[-(len(b) - 1):], c[:len(a)]])
    lags = np.arange(-(len(b) - 1), len(a))
    return lags, c


def offset(ref, cam, sr=SR):
    """cam 시간 = ref 시간 + offset. (offset, 신뢰도)"""
    ea, eb = onset_env(ref, sr), onset_env(cam, sr)
    lags, c = _xcorr(eb, ea)          # ea를 eb 위에서 밀어 봄
    i = int(np.argmax(c))
    coarse = lags[i] * 0.01
    # 신뢰도: 1등 피크 / (1등 주변 ±0.5초 제외한 2등 피크)
    mask = np.abs(lags - lags[i]) > 50
    conf = float(c[i] / (c[mask].max() + 1e-9)) if mask.any() else 1.0
    # 정밀화: ±0.1초 원파형 상관 (ref 중간 20초 구간)
    mid = len(ref) // 2
    seg = ref[max(0, mid - 10 * sr): mid + 10 * sr]
    s0 = max(0, mid - 10 * sr)
    best, best_v = coarse, -1e9
    for d in np.arange(-0.1, 0.1001, 1 / sr * 8):
        st = int(round((s0 / sr + coarse + d) * sr))
        if st < 0 or st + len(seg) > len(cam):
            continue
        v = float(np.dot(seg, cam[st:st + len(seg)]))
        if v > best_v:
            best_v, best = v, coarse + d
    return round(float(best), 3), round(conf, 2)


def sync_clips(ref_path, others):
    ref = load_audio(ref_path)
    out = {ref_path: 0.0}
    conf = {}
    for p in others:
        off, c = offset(ref, load_audio(p))
        out[p], conf[p] = off, c
        flag = "" if c >= 1.3 else "  ← 신뢰도 낮음, 확인 필요"
        print(f"  {p}: 오프셋 {off:+.3f}s (신뢰도 {c}){flag}")
    return out, conf


if __name__ == "__main__":
    res, _ = sync_clips(sys.argv[1], sys.argv[2:])
    print(json.dumps(res, ensure_ascii=False, indent=1))
