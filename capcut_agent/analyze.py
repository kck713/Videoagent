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


def transcribe(path, model, language="ko"):
    segs, _ = model.transcribe(path, language=language, word_timestamps=True, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 300})
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or [])]})
    return out


def analyze(clips_dir, out_dir, broll_dir=None, model_size="large-v3", device="auto", language="ko"):
    os.makedirs(out_dir, exist_ok=True)
    clips = list_media(clips_dir, VIDEO_EXT)
    if not clips:
        raise SystemExit(f"영상이 없습니다: {clips_dir}")
    from faster_whisper import WhisperModel
    compute = "int8" if device == "cpu" else "default"
    print(f"Whisper 모델 로딩: {model_size} ({device})")
    model = WhisperModel(model_size, device=device, compute_type=compute)

    result = {"clips": [], "broll": [], "media": {}}
    for c in clips:
        info = probe(c)
        result["media"][c] = info
        print(f"전사 중: {os.path.basename(c)} ({info['duration']:.1f}s)")
        result["clips"].append({"src": c, "duration": round(info["duration"], 2),
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
