"""1단계: 원본 클립 분석 — 미디어 정보 + 음성 전사(단어 타임스탬프) + 무음 구간.

faster-whisper 를 로컬에서 돌립니다(첫 실행 시 모델 자동 다운로드).
결과: <out>/analysis.json
"""
import json
import os
import re
import subprocess

from capcut_draft import probe

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def list_media(folder, exts):
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, f).replace("\\", "/") for f in os.listdir(folder)
                  if f.lower().endswith(exts) and not f.startswith("."))


def silences(path, noise_db=-35, min_dur=0.35):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_dur}", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return [[round(s, 2), round(e, 2)] for s, e in zip(starts, ends)]


def detect_face(path, duration, samples=None):
    """영상 여러 지점에서 얼굴을 찾아 화면 내 중심/크기의 중앙값을 반환 ({x, y, h}, 원본 기준 0~1).
    OpenCV(4.x)가 없거나 얼굴을 못 찾으면 None → 가운데 기준으로 크롭."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if not hasattr(cv2, "CascadeClassifier"):
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    samples = samples or int(min(40, max(7, duration / 6)))   # 약 6초 간격, 최대 40장
    found, track = [], []
    for k in range(samples):
        t = duration * (k + 0.5) / samples
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-map", "0:v:0", "-frames:v", "1",
                              "-vf", "scale=640:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True).stdout
        if not raw:
            continue
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        H, W = img.shape
        faces = cascade.detectMultiScale(img, 1.1, 5, minSize=(max(24, W // 20),) * 2)
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            found.append(((x + w / 2) / W, (y + h / 2) / H, h / H))
            track.append([round(t, 2), round((x + w / 2) / W, 3), round((y + h / 2) / H, 3), round(h / H, 3)])
    if not found:
        return None
    a = np.median(np.array(found), axis=0)
    return {"x": round(float(a[0]), 3), "y": round(float(a[1]), 3), "h": round(float(a[2]), 3), "samples": len(found),
            "track": track}


def transcribe(path, model, language="ko"):
    segs, _ = model.transcribe(path, language=language, word_timestamps=True, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 300})
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or [])]})
    return out


def analyze(clips_dir, out_dir, broll_dir=None, model_size="large-v3", device="auto", language="ko", multicam=False):
    """multicam=True: 원본 폴더의 영상들을 같은 장면을 찍은 카메라들로 보고,
    가장 긴 영상을 기준(전사 대상)으로 나머지의 오프셋을 계산(sync)."""
    os.makedirs(out_dir, exist_ok=True)
    clips = list_media(clips_dir, VIDEO_EXT)
    if not clips:
        raise SystemExit(f"영상이 없습니다: {clips_dir}")
    from faster_whisper import WhisperModel
    compute = "int8" if device == "cpu" else "default"
    print(f"Whisper 모델 로딩: {model_size} ({device})")
    model = WhisperModel(model_size, device=device, compute_type=compute)

    result = {"clips": [], "broll": [], "media": {}}
    infos = {c: probe(c) for c in clips}
    if multicam and len(clips) > 1:
        from sync import sync_clips
        ref = max(clips, key=lambda c: infos[c]["duration"])
        print(f"멀티캠 동기화 (기준: {os.path.basename(ref)})")
        result["sync"], result["sync_confidence"] = sync_clips(ref, [c for c in clips if c != ref])
        result["reference"] = ref
        for c in clips:   # 기준 외 카메라는 화면용: 얼굴 위치만
            if c != ref:
                result["media"][c] = infos[c]
                face = detect_face(c, infos[c]["duration"])
                if face:
                    result.setdefault("faces", {})[c] = face
        clips = [ref]
    for c in clips:
        info = infos[c]
        result["media"][c] = info
        print(f"전사 중: {os.path.basename(c)} ({info['duration']:.1f}s)")
        face = detect_face(c, info["duration"])
        if face:
            result.setdefault("faces", {})[c] = face
            print(f"  얼굴 위치: x={face['x']} y={face['y']} 크기={face['h']}")
        result["clips"].append({"src": c, "duration": round(info["duration"], 2), "face": face,
                                "transcript": transcribe(c, model, language),
                                "silences": silences(c)})
    for b in list_media(broll_dir, VIDEO_EXT + IMAGE_EXT):
        info = probe(b)
        result["media"][b] = info
        desc = ""
        side = os.path.splitext(b)[0] + ".txt"   # 같은 이름의 .txt에 설명을 적어두면 B롤 매칭에 사용
        if os.path.exists(side):
            desc = open(side, encoding="utf-8").read().strip()
        result["broll"].append({"src": b, "duration": round(info["duration"], 2),
                                "orientation": "portrait" if info["height"] > info["width"] else "landscape",
                                "description": desc or os.path.basename(b)})
    p = os.path.join(out_dir, "analysis.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("분석 완료 ->", p)
    return p
