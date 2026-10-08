"""생성한 캡컷 드래프트의 대략적인 미리보기(스틸 컷 모음) 렌더링.

캡컷 없이 구도·자막 위치·라벨·엔딩 카드를 눈으로 확인하는 용도입니다.
글꼴과 크기는 근사치입니다(캡컷 글자 크기 1 ≈ 1920px 캔버스에서 약 9px — 2026-10-07 사용자가 캡컷에서 9→5.5로 줄인 것으로 보정).

    python capcut_agent/preview.py <드래프트 폴더> [--out preview.jpg] [--frames 8] [--map "C:/=/mnt/c/"]
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

PX_PER_SIZE = 9.0


def _font(px, bold=False):
    for name in (["malgunbd.ttf", "NanumGothicBold.ttf"] if bold else []) + [
            "malgun.ttf", "NanumGothic.ttf", "NotoSansCJK-Regular.ttc", "NotoSansKR-Regular.otf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "C:/Windows/Fonts/malgun.ttf"]:
        try:
            return ImageFont.truetype(name, int(px))
        except OSError:
            continue
    return ImageFont.load_default()


def _frame(path, t, path_map):
    for a, b in (path_map or {}).items():
        if path.startswith(a):
            path = b + path[len(a):]
    if not os.path.exists(path):
        return None
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-map", "0:v:0", "-frames:v", "1",
                          "-vf", "scale=1280:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not raw:
        return None
    import io
    return Image.open(io.BytesIO(raw)).convert("RGB")


def render_at(d, mats, t_us, W, H, path_map=None, frame_override=None):
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    for tr in d["tracks"]:
        for s in tr["segments"]:
            tt = s["target_timerange"]
            if not (tt["start"] <= t_us < tt["start"] + tt["duration"]):
                continue
            kind, m = mats.get(s["material_id"], (None, None))
            if tr["type"] == "video" and m:
                src_t = (s["source_timerange"]["start"] + (t_us - tt["start"])) / 1e6
                img = None
                if m.get("type") == "photo":
                    pth = m["path"]
                    for a0, b0 in (path_map or {}).items():
                        if pth.startswith(a0):
                            pth = b0 + pth[len(a0):]
                    if os.path.exists(pth):
                        img = Image.open(pth).convert("RGBA")
                elif frame_override:
                    img = frame_override(m["path"], src_t)
                else:
                    img = _frame(m["path"], src_t, path_map)
                if img is None:
                    img = Image.new("RGB", (max(1, m["width"] // 4), max(1, m["height"] // 4)), (60, 60, 70))
                contain = min(W / m["width"], H / m["height"])
                k = s["clip"]["scale"]["x"]
                dw, dh = int(m["width"] * contain * k), int(m["height"] * contain * k)
                img = img.resize((max(1, dw), max(1, dh)))
                cx = W / 2 + s["clip"]["transform"]["x"] * W / 2
                cy = H / 2 - s["clip"]["transform"]["y"] * H / 2
                canvas.paste(img, (int(cx - dw / 2), int(cy - dh / 2)), img if img.mode == "RGBA" else None)
            elif tr["type"] == "text" and m:
                c = json.loads(m["content"])
                text = c["text"]
                st = c["styles"][0]
                px = st.get("size", 9) * PX_PER_SIZE
                font = _font(px, st.get("bold"))
                col = tuple(int(v * 255) for v in st["fill"]["content"]["solid"]["color"])
                draw = ImageDraw.Draw(canvas, "RGBA")
                lines = text.split("\n")
                lh = int(px * 1.3)
                tw = max(draw.textlength(l, font=font) for l in lines)
                cy = H / 2 - s["clip"]["transform"]["y"] * H / 2
                cxt = W / 2 + s["clip"]["transform"]["x"] * W / 2
                top = cy - lh * len(lines) / 2
                if m.get("background_color"):
                    a = int(255 * float(m.get("background_alpha", 1)))
                    pad = px * 0.35
                    draw.rectangle([cxt - tw / 2 - pad, top - pad * 0.6, cxt + tw / 2 + pad,
                                    top + lh * len(lines) + pad * 0.3], fill=(0, 0, 0, a))
                for j, l in enumerate(lines):
                    lw = draw.textlength(l, font=font)
                    xy = (cxt - lw / 2, top + j * lh)
                    if m.get("has_shadow"):
                        draw.text((xy[0] + 2, xy[1] + 2), l, font=font, fill=(0, 0, 0, 200))
                    draw.text(xy, l, font=font, fill=col)
    return canvas


def preview(folder, out, frames=8, path_map=None, times=None, frame_override=None):
    with open(os.path.join(folder, "draft_content.json"), encoding="utf-8") as f:
        d = json.load(f)
    W, H = d["canvas_config"]["width"], d["canvas_config"]["height"]
    mats = {m["id"]: (k, m) for k, v in d["materials"].items() if isinstance(v, list)
            for m in v if isinstance(m, dict) and "id" in m}
    if times is None:  # 훅 카드가 보이는 1초 + 나머지는 균등 분할
        times = [1.0] + [d["duration"] * (i + 0.5) / max(1, frames - 1) / 1e6 for i in range(max(1, frames - 1))]
    tiles = []
    for t in times:
        img = render_at(d, mats, int(t * 1e6), W, H, path_map, frame_override)
        img = img.resize((W // 4, H // 4))
        ImageDraw.Draw(img).text((6, 6), f"{t:.1f}s", fill=(255, 0, 0))
        tiles.append(img)
    cols = min(len(tiles), 6)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (W // 4), rows * (H // 4)), (30, 30, 30))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * (W // 4), (i // cols) * (H // 4)))
    sheet.save(out, quality=88)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default="preview.jpg")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--at", help="쉼표로 구분한 타임라인 초 (예: 1.5,10,30)")
    ap.add_argument("--map", action="append", default=[], help="경로 치환 '원래=바꿀' (예: C:/=/mnt/c/)")
    a = ap.parse_args()
    pm = dict(x.split("=", 1) for x in a.map)
    ts = [float(x) for x in a.at.split(",")] if a.at else None
    print(preview(a.folder, a.out, a.frames, pm, ts))
