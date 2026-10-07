"""edit_plan.json -> 캡컷(9.x) 드래프트 프로젝트 생성기.

캡컷이 실제로 저장한 세그먼트/머티리얼(template_pack.json)을 복제해서 값만 바꿉니다.
생성 후 캡컷을 열면 프로젝트 목록에 나타나고, 모든 트랙이 편집 가능한 상태입니다.

※ 캡컷이 실행 중이면 종료 시 root_meta_info.json 을 덮어쓰므로, 반드시 캡컷을 끈 상태에서 실행하세요.
"""
import copy
import json
import os
import shutil
import subprocess
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
US = 1_000_000


def new_id():
    return str(uuid.uuid4()).upper()


def fwd(p):
    return p.replace("\\", "/")


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
PHOTO_DURATION = 10800.0  # 캡컷은 사진 머티리얼 길이를 3시간으로 둠


def is_image(path):
    return path.lower().endswith(IMAGE_EXT)


# ───────────────────────── 화면 배치 ─────────────────────────
def framing(info, W, H, face=None, zoom=1.0, face_target=(0.5, 0.40), mode="fill"):
    """원본(info: width/height)을 W×H 캔버스에 배치하는 캡컷 clip 값 계산.

    mode="fill": 캔버스를 꽉 채움(cover) × zoom. face={x,y}(원본 기준 0~1)가 있으면
    얼굴이 캔버스의 face_target 위치에 오도록 이동하되, 화면 밖 검은 여백이 생기지 않게 제한.
    반환: (scale, transform_x, transform_y)  — 캡컷 단위(scale 1 = contain, x/y = 반 화면 단위, y 위가 +)
    """
    w, h = info.get("width") or W, info.get("height") or H
    contain = min(W / w, H / h)
    cover = max(W / w, H / h)
    k = (cover / contain if mode == "fill" else 1.0) * zoom
    dw, dh = w * contain * k, h * contain * k          # 표시 크기(px)
    fx, fy = (face or {}).get("x", 0.5), (face or {}).get("y", 0.5)
    tx_px = (face_target[0] - 0.5) * W - (fx - 0.5) * dw   # 오른쪽 +
    ty_px = (face_target[1] - 0.5) * H - (fy - 0.5) * dh   # 아래쪽 +
    if face is None:
        tx_px = ty_px = 0.0
    mx, my = max(0.0, (dw - W) / 2), max(0.0, (dh - H) / 2)
    tx_px = max(-mx, min(mx, tx_px))
    ty_px = max(-my, min(my, ty_px))
    return round(k, 4), round(tx_px / (W / 2), 4), round(-ty_px / (H / 2), 4)


def face_for_range(face, a, b, margin=4.0):
    """얼굴 정보({x,y,h,track:[[t,x,y,h],...]})에서 컷 구간 [a,b] 근처 샘플의 중앙값. 없으면 전체 값."""
    if not face:
        return None
    pts = [p for p in face.get("track", []) if a - margin <= p[0] <= b + margin]
    if not pts:
        return face
    mid = lambda i: sorted(p[i] for p in pts)[len(pts) // 2]
    return {"x": mid(1), "y": mid(2), "h": mid(3)}


# ───────────────────────── 미디어 정보 ─────────────────────────
def probe(path):
    """ffprobe로 길이/해상도/오디오 유무 확인."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height:stream_tags=rotate:stream_side_data=rotation",
         "-of", "json", path], capture_output=True, text=True, encoding="utf-8")
    j = json.loads(out.stdout or "{}")
    if "format" not in j:
        raise RuntimeError(f"ffprobe 실패: {path}\n{out.stderr}")
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    w, h = (v or {}).get("width", 0), (v or {}).get("height", 0)
    rot = 0
    if v:
        rot = int(float((v.get("tags") or {}).get("rotate", 0) or 0))
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
    if abs(rot) in (90, 270):
        w, h = h, w
    if is_image(path):
        return {"duration": PHOTO_DURATION, "width": w, "height": h, "has_audio": False, "has_video": True,
                "image": True}
    return {"duration": float(j["format"]["duration"]), "width": w, "height": h,
            "has_audio": any(s.get("codec_type") == "audio" for s in j.get("streams", [])),
            "has_video": v is not None}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def u16len(s):
    return len(s.encode("utf-16-le")) // 2


# ───────────────────────── 드래프트 ─────────────────────────
class Draft:
    def __init__(self, width=1080, height=1920, fps=30.0, pack_path=None):
        with open(pack_path or os.path.join(HERE, "template_pack.json"), encoding="utf-8") as f:
            raw = f.read()
        # 템플릿의 ${LOCALAPPDATA} 등을 이 PC의 실제 경로로 (폰트·캐시 경로)
        lad = fwd(os.environ.get("CAPCUT_LOCALAPPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local"))
        up = fwd(os.environ.get("CAPCUT_USERPROFILE") or os.environ.get("USERPROFILE") or os.path.expanduser("~"))
        raw = raw.replace("${LOCALAPPDATA}", lad).replace("${USERPROFILE}", up)
        self.pack = json.loads(raw)
        self._fix_font_version()
        self.d = copy.deepcopy(self.pack["draft_skeleton"])
        self.d["id"] = new_id()
        self.d["fps"] = fps
        self.d["canvas_config"].update({"width": width, "height": height, "ratio": "original"})
        self.fps = fps
        self.W, self.H = width, height
        self.tracks = {}       # key -> track dict
        self.track_order = []
        self.media = {}        # path -> {meta, meta_id}
        self._text_index = 14000

    def _fix_font_version(self):
        """폰트 경로의 캡컷 버전 폴더(Apps/9.4.0.xxxx)가 업데이트로 바뀌었으면 최신 폴더로 교체."""
        tm = self.pack.get("text_mat") or {}
        fp = tm.get("font_path", "")
        if not fp or os.path.exists(fp) or "/Apps/" not in fp:
            return
        apps = fp.split("/Apps/")[0] + "/Apps"
        tail = fp.split("/Apps/")[1].split("/", 1)[1]
        try:
            vers = sorted(d for d in os.listdir(apps) if os.path.exists(f"{apps}/{d}/{tail}"))
        except OSError:
            return
        if vers:
            tm["font_path"] = f"{apps}/{vers[-1]}/{tail}"

    # 시간 → 마이크로초 (프레임 단위로 스냅)
    def t(self, sec):
        frames = round(sec * self.fps)
        return int(frames * US / self.fps)

    def mat(self, kind, data):
        self.d["materials"].setdefault(kind, []).append(data)
        return data["id"]

    def _extras(self, key, skip=()):
        ids = []
        for e in self.pack.get(key, []):
            if e["kind"] in skip:
                continue
            x = copy.deepcopy(e["data"])
            x["id"] = new_id()
            ids.append(self.mat(e["kind"], x))
        return ids

    def track(self, key, ttype, flag=0, attribute=0):
        if key not in self.tracks:
            base = {"video": self.pack["track_skeleton"], "overlay": self.pack["overlay_track"],
                    "text": self.pack.get("text_track"), "audio": self.pack.get("audio_track")}
            tpl = base["overlay" if (ttype == "video" and flag == 2) else ttype]
            tr = copy.deepcopy(tpl)
            tr.update({"id": new_id(), "type": ttype, "flag": flag, "attribute": attribute, "segments": []})
            self.tracks[key] = tr
            self.track_order.append(key)
        return self.tracks[key]

    def register_media(self, path, info=None):
        path = fwd(path)
        if path not in self.media:
            info = info or probe(path)
            self.media[path] = {"info": info, "meta_id": str(uuid.uuid4())}
        return self.media[path]

    # ── 비디오 (메인/오버레이)
    def add_video(self, track_key, path, src_in, dur, at, *, overlay=False, volume=1.0,
                  fit="fit", info=None, transform=(0.0, 0.0), scale=None):
        if is_image(path):
            info = dict(info or {}, duration=PHOTO_DURATION, has_audio=False, image=True)
            src_in = 0.0
        m = self.register_media(path, info)
        info = m["info"]
        src_in_us, dur_us, at_us = self.t(src_in), self.t(dur), self.t(at)
        max_us = int(info["duration"] * US)
        if src_in_us + dur_us > max_us:
            dur_us = max_us - src_in_us
        if dur_us <= 0:
            raise ValueError(f"구간 오류: {path} in={src_in} dur={dur}")

        vm = copy.deepcopy(self.pack["video_mat"])
        vm.update({"id": new_id(), "unique_id": uuid.uuid4().hex, "path": fwd(path),
                   "duration": max_us, "width": info["width"], "height": info["height"],
                   "has_audio": info.get("has_audio", True),
                   "material_name": os.path.basename(path), "local_material_id": m["meta_id"],
                   "type": "photo" if (info.get("image") or is_image(path)) else "video"})
        mid = self.mat("videos", vm)

        flag = 2 if overlay else 0
        tr = self.track(track_key, "video", flag=flag, attribute=1 if overlay else 0)
        seg = copy.deepcopy(self.pack["overlay_seg" if overlay else "video_seg"])
        if scale is None:
            scale = 1.0
        if fit == "fill" and info["width"] and info["height"]:
            contain = min(self.W / info["width"], self.H / info["height"])
            cover = max(self.W / info["width"], self.H / info["height"])
            scale = cover / contain
        seg.update({
            "id": new_id(), "material_id": mid,
            "source_timerange": {"start": src_in_us, "duration": dur_us},
            "target_timerange": {"start": at_us, "duration": dur_us},
            "extra_material_refs": self._extras("video_extras"),
            "volume": volume, "last_nonzero_volume": 1.0, "speed": 1.0,
            "common_keyframes": [], "keyframe_refs": [],
        })
        seg["clip"] = {"scale": {"x": scale, "y": scale}, "rotation": 0.0,
                       "transform": {"x": transform[0], "y": transform[1]},
                       "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
        seg["uniform_scale"] = {"on": True, "value": 1.0}
        tr["segments"].append(seg)
        return seg

    # ── 텍스트 (자막)
    def add_text(self, track_key, text, start, dur, style, group_id=None):
        w = style.get("wrap")
        if w and text and not text.startswith(w[0]):
            text = f"{w[0]}{text}{w[1]}"
        tm = copy.deepcopy(self.pack["text_mat"])
        color = hex_to_rgb(style.get("color", "#FFFFFF"))
        size = float(style.get("size", 10))
        font = fwd(style.get("font_path") or tm.get("font_path", ""))

        def style_run(a, b, rgb, sz, bold):
            r = {"fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": rgb}}},
                 "font": {"id": "", "path": font}, "range": [a, b], "size": sz}
            if bold:
                r["bold"] = True
            if style.get("stroke_color"):
                r["strokes"] = [{"content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": hex_to_rgb(style["stroke_color"])}},
                                 "width": float(style.get("stroke_width", 0.08))}]
            return r

        # 키워드 강조(부분 색상) 지원
        runs, pos = [], 0
        hl = style.get("_highlight") or []
        hl_color = hex_to_rgb(style.get("highlight_color", "#FF9A1F"))
        marks = []
        for kw in hl:
            i = text.find(kw)
            if i >= 0:
                marks.append((u16len(text[:i]), u16len(text[:i]) + u16len(kw)))
        marks.sort()
        for a, b in marks:
            if a > pos:
                runs.append(style_run(pos, a, color, size, style.get("bold")))
            runs.append(style_run(a, b, hl_color, size, True))
            pos = b
        if pos < u16len(text):
            runs.append(style_run(pos, u16len(text), color, size, style.get("bold")))

        content = json.dumps({"styles": runs, "text": text}, ensure_ascii=False)
        flag = 7
        tm.update({
            "id": new_id(), "content": content, "base_content": content,
            "recognize_text": text, "recognize_task_id": "",
            "words": {"start_time": [], "end_time": [], "text": []},
            "current_words": {"start_time": [], "end_time": [], "text": []},
            "type": "subtitle" if group_id else "text", "group_id": group_id or "", "language": style.get("language", "ko-KR"),
            "text_color": style.get("color", "#FFFFFF"), "font_size": size, "font_path": font,
            "bold_width": 0.008 if style.get("bold") else 0.0,
            "alignment": 1, "line_max_width": float(style.get("line_max_width", 0.82)),
            "letter_spacing": float(style.get("letter_spacing", 0.0)),
            "line_spacing": float(style.get("line_spacing", 0.02)),
        })
        if style.get("bg_color"):
            tm.update({"background_color": style["bg_color"], "background_alpha": float(style.get("bg_alpha", 1.0)),
                       "background_style": 1, "background_round_radius": float(style.get("bg_radius", 0.0)),
                       "background_width": 0.14, "background_height": 0.14})
            flag |= 16
        else:
            tm.update({"background_color": "", "background_alpha": 1.0})
        if style.get("shadow"):
            tm.update({"has_shadow": True, "shadow_color": style.get("shadow_color", "#000000"),
                       "shadow_alpha": float(style.get("shadow_alpha", 0.6)),
                       "shadow_smoothing": float(style.get("shadow_smoothing", 0.6)),
                       "shadow_distance": float(style.get("shadow_distance", 3.0))})
            flag |= 32
        else:
            tm["has_shadow"] = False
        if style.get("stroke_color"):
            tm.update({"border_color": style["stroke_color"], "border_width": float(style.get("stroke_width", 0.08)),
                       "border_alpha": 1.0})
            flag |= 8
        else:
            tm["border_color"] = ""
        tm["check_flag"] = flag
        mid = self.mat("texts", tm)

        tr = self.track(track_key, "text", flag=1)
        seg = copy.deepcopy(self.pack["text_seg"])
        self._text_index += 1
        seg.update({"id": new_id(), "material_id": mid,
                    "target_timerange": {"start": self.t(start), "duration": max(self.t(start + dur) - self.t(start), self.t(1 / self.fps))},
                    "extra_material_refs": self._extras("text_extras"),
                    "render_index": self._text_index})
        seg["clip"] = copy.deepcopy(seg["clip"])
        seg["clip"]["transform"] = {"x": float(style.get("x", 0.0)), "y": float(style.get("y", -0.75))}
        seg["clip"]["scale"] = {"x": 1.0, "y": 1.0}
        tr["segments"].append(seg)
        return seg

    # ── 오디오 (BGM)
    def add_audio(self, track_key, path, src_in, dur, at, *, volume=1.0, fade_in=0.0, fade_out=0.0,
                  name=None, info=None, music_template=False):
        info = info or probe(path)
        am = copy.deepcopy(self.pack["audio_mat"])
        max_us = int(info["duration"] * US)
        if not music_template:
            for k in ("music_id", "request_id", "category_id", "category_name"):
                if k in am:
                    am[k] = ""
            am["type"] = "extract_music"
        am.update({"id": new_id(), "path": fwd(path), "duration": max_us,
                   "name": name or os.path.splitext(os.path.basename(path))[0]})
        mid = self.mat("audios", am)
        src_us, dur_us = self.t(src_in), self.t(dur)
        dur_us = min(dur_us, max_us - src_us)
        extras = []
        for e in self.pack.get("audio_extras", []):
            x = copy.deepcopy(e["data"])
            x["id"] = new_id()
            if e["kind"] == "audio_fades":
                x["fade_in_duration"] = self.t(fade_in)
                x["fade_out_duration"] = self.t(fade_out)
            extras.append(self.mat(e["kind"], x))
        tr = self.track(track_key, "audio")
        seg = copy.deepcopy(self.pack["audio_seg"])
        seg.update({"id": new_id(), "material_id": mid,
                    "source_timerange": {"start": src_us, "duration": dur_us},
                    "target_timerange": {"start": self.t(at), "duration": dur_us},
                    "extra_material_refs": extras, "volume": volume, "last_nonzero_volume": 1.0})
        tr["segments"].append(seg)
        return seg

    # ── 마무리/검증
    def finalize(self):
        order = sorted(self.track_order, key=lambda k: {"video": 0, "text": 1, "audio": 2}[self.tracks[k]["type"]]
                       + (0.5 if self.tracks[k].get("flag") == 2 else 0))
        # 메인 비디오 → 오버레이들 → 텍스트 → 오디오
        self.d["tracks"] = []
        for i, k in enumerate(order):
            tr = self.tracks[k]
            tr["segments"].sort(key=lambda s: s["target_timerange"]["start"])
            for s in tr["segments"]:
                s["track_render_index"] = i
                if tr["type"] == "video":
                    s["render_index"] = i
                    s["track_attribute"] = tr.get("attribute", 0)
            self.d["tracks"].append(tr)
        end = 0
        for tr in self.d["tracks"]:
            if tr["type"] == "video" and tr.get("flag") == 0:
                for s in tr["segments"]:
                    end = max(end, s["target_timerange"]["start"] + s["target_timerange"]["duration"])
        if end == 0:
            for tr in self.d["tracks"]:
                for s in tr["segments"]:
                    end = max(end, s["target_timerange"]["start"] + s["target_timerange"]["duration"])
        self.d["duration"] = end
        self.validate()
        return self.d

    def validate(self):
        ids = {x["id"] for v in self.d["materials"].values() if isinstance(v, list) for x in v if isinstance(x, dict)}
        problems = []
        for tr in self.d["tracks"]:
            prev_end = -1
            for s in tr["segments"]:
                tt = s["target_timerange"]
                if tt["start"] < prev_end:
                    problems.append(f"트랙 {tr['type']} 세그먼트 겹침 @ {tt['start'] / US:.2f}s")
                prev_end = tt["start"] + tt["duration"]
                if s["material_id"] not in ids:
                    problems.append(f"머티리얼 누락 {s['material_id']}")
                for r in s.get("extra_material_refs", []):
                    if r not in ids:
                        problems.append(f"부가 머티리얼 누락 {r}")
        if problems:
            raise ValueError("드래프트 검증 실패:\n" + "\n".join(problems))

    # ── 저장
    def save(self, drafts_root, name, path_map=None, cover_from=None):
        """drafts_root: 캡컷 'com.lveditor.draft' 폴더(실제 기록 위치).
        path_map: (실행환경 경로 → 윈도우 경로) 치환이 필요할 때 {'/mnt/x': 'C:/Users/..'}"""
        self.finalize()
        win_root = fwd(path_map.get(drafts_root, drafts_root)) if path_map else fwd(drafts_root)
        folder = os.path.join(drafts_root, name)
        if os.path.exists(os.path.join(folder, "draft_content.json")):
            raise FileExistsError(f"이미 존재: {folder} (다른 이름을 쓰세요)")
        os.makedirs(os.path.join(folder, "Timelines", self.d["id"]), exist_ok=True)
        win_folder = f"{win_root}/{name}"
        now_us = int(time.time() * US)

        content = json.dumps(self.d, ensure_ascii=False, separators=(",", ":"))
        for p in (os.path.join(folder, "draft_content.json"),
                  os.path.join(folder, "Timelines", self.d["id"], "draft_content.json")):
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)

        proj = copy.deepcopy(self.pack.get("timelines_project") or {"config": {}, "timelines": [{}]})
        proj.update({"id": new_id(), "main_timeline_id": self.d["id"], "create_time": now_us, "update_time": now_us})
        proj["timelines"] = [{"create_time": now_us, "id": self.d["id"], "is_marked_delete": False,
                              "name": "타임라인 01", "update_time": now_us}]
        self._dump(os.path.join(folder, "Timelines", "project.json"), proj)

        layout = copy.deepcopy(self.pack.get("timeline_layout.json") or {})
        if layout.get("dockItems"):
            layout["dockItems"][0]["timelineIds"] = [self.d["id"]]
            layout["dockItems"][0]["timelineNames"] = ["타임라인 01"]
        self._dump(os.path.join(folder, "timeline_layout.json"), layout)
        if "draft_agency_config.json" in self.pack:
            self._dump(os.path.join(folder, "draft_agency_config.json"), self.pack["draft_agency_config.json"])

        meta = copy.deepcopy(self.pack["meta_skeleton"])
        draft_id = new_id()
        mats = []
        for path, m in self.media.items():
            x = copy.deepcopy(self.pack["meta_material_sample"])
            info = m["info"]
            x.update({"id": m["meta_id"], "file_Path": path, "extra_info": os.path.basename(path),
                      "duration": int(info["duration"] * US), "width": info["width"], "height": info["height"],
                      "create_time": int(time.time()), "import_time": int(time.time()), "import_time_ms": now_us,
                      "roughcut_time_range": {"duration": int(info["duration"] * US), "start": 0},
                      "metetype": "photo" if info.get("image") else "video"})
            mats.append(x)
        for g in meta.get("draft_materials", []):
            if g.get("type") == 0:
                g["value"] = mats
        meta.update({"draft_fold_path": win_folder, "draft_root_path": win_root, "draft_id": draft_id,
                     "draft_name": name, "tm_draft_create": now_us, "tm_draft_modified": now_us,
                     "tm_duration": self.d["duration"], "draft_cover": "draft_cover.jpg"})
        self._dump(os.path.join(folder, "draft_meta_info.json"), meta)
        self._dump(os.path.join(folder, "draft_virtual_store.json"),
                   {"draft_materials": [], "draft_virtual_store": [
                       {"type": 0, "value": [{"creation_time": 0, "display_name": "", "filter_type": 0, "id": "",
                                              "import_time": 0, "import_time_us": 0, "material_color_tag": "",
                                              "sort_sub_type": 0, "sort_type": 0, "subdraft_filter_type": 0}]},
                       {"type": 1, "value": [{"child_id": m["meta_id"], "parent_id": ""} for m in self.media.values()]},
                       {"type": 2, "value": []}]})
        self._dump(os.path.join(folder, "key_value.json"), {})
        with open(os.path.join(folder, "draft_settings"), "w", encoding="utf-8", newline="\r\n") as f:
            t = int(time.time())
            f.write(f"[General]\ndraft_create_time={t}\ndraft_last_edit_time={t}\nreal_edit_seconds=0\n"
                    f"real_edit_keys=0\ncloud_last_modify_platform=windows\n")
        if cover_from and os.path.exists(cover_from):
            shutil.copy(cover_from, os.path.join(folder, "draft_cover.jpg"))

        self._register_root(drafts_root, win_root, win_folder, name, draft_id, now_us)
        return folder

    def _register_root(self, drafts_root, win_root, win_folder, name, draft_id, now_us):
        p = os.path.join(drafts_root, "root_meta_info.json")
        root = {"all_draft_store": [], "draft_ids": 0, "root_path": win_root}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                root = json.load(f)
            shutil.copy(p, p + f".bak_{int(time.time())}")
        tpl = copy.deepcopy(root["all_draft_store"][0]) if root.get("all_draft_store") else {}
        tpl.update({"draft_cover": f"{win_folder}\\draft_cover.jpg", "draft_fold_path": win_folder,
                    "draft_id": draft_id, "draft_json_file": f"{win_folder}\\draft_content.json",
                    "draft_name": name, "draft_root_path": win_root, "tm_draft_create": now_us,
                    "tm_draft_modified": now_us, "tm_duration": self.d["duration"],
                    "draft_timeline_materials_size": 0, "streaming_edit_draft_ready": True,
                    "draft_is_invisible": False})
        root["all_draft_store"].insert(0, tpl)
        root["draft_ids"] = root.get("draft_ids", 0) + 1
        self._dump(p, root)

    @staticmethod
    def _dump(p, obj):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
