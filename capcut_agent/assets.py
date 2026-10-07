"""스타일용 그래픽 에셋(투명 PNG) 생성.

- frame_border: 화면 가장자리 안쪽의 둥근 사각 테두리(그라데이션). 가운데는 투명 → 맨 위 오버레이로 깜
- ring: 강조용 원(노란 링). 특정 부위를 짚을 때 오버레이로 깜

캡컷 스티커/도형은 서버 리소스라 직접 만들 수 없어서, 이미지 오버레이(사진 세그먼트)로 대체합니다.
"""
import os

from PIL import Image, ImageDraw


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def frame_border(path, W=1080, H=1920, inset=0.028, width=6, radius=0.035, colors=("#FFA237", "#F5C760")):
    """세로 그라데이션 테두리. inset/radius는 화면 폭 대비 비율."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mask = Image.new("L", (W, H), 0)
    m = int(W * inset)
    r = int(W * radius)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([m, m, W - m, H - m], radius=r, outline=255, width=width)
    c0, c1 = _hex(colors[0]), _hex(colors[1])
    grad = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        t = y / (H - 1)
        gd.line([(0, y), (W, y)], fill=tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)) + (255,))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    out.save(path)
    return path


def ring(path, size=400, width=14, color="#FFD43B"):
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([width, width, size - width, size - width], outline=_hex(color) + (255,), width=width)
    im.save(path)
    return path
