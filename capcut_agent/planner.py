"""2단계: Claude가 전사본을 읽고 편집 계획(edit_plan.json)을 만듭니다.

- 메인 컷: NG/반복/말 더듬기/긴 무음 제거, 목표 길이에 맞게 핵심 발언 선택
- 자막: 한 줄 8~14자, 역할(흰/노랑/강조/경고/괄호) 지정, 맥락 라벨, 엔딩 카드 문장
- B롤: 발언 내용과 맞는 B롤 배치
API 키: 환경변수 ANTHROPIC_API_KEY
"""
import json
import os
import re

SYSTEM = """당신은 한국어 인터뷰 숏폼(9:16, 약 60~90초) 전문 영상 편집자입니다.
주어진 원본 클립 전사본(단어 단위 타임스탬프 포함)으로 캡컷 가편집 계획을 JSON으로만 출력합니다.
목표 스타일: 화자 얼굴 위주(배율 고정), 한 줄 한글 자막(흰색/노란색), 자막 위 검정 박스 맥락 라벨, 마지막 핵심 메시지 카드.

편집 원칙
1. 메인 컷(main): 같은 말을 다시 한 NG 테이크는 마지막(가장 매끄러운) 테이크만 남깁니다. "어", "음", 말 더듬기, 0.3초 넘는 무음, 촬영 신호("지금 시작합니다" 등)는 잘라냅니다. 한 컷은 최소 1초.
2. 같은 테이크에서 이어지는 문장(0.5초 이하 숨)은 한 컷으로 묶습니다. 컷 경계는 단어 타임스탬프 기준(앞 0.08초, 뒤 0.12초 여유).
3. 구성: 훅(가장 강한 한 문장, 0~3초) → 고민/경험 → 계기 → 지금/메시지 → 엔딩 한마디. 목표 길이(target_seconds)에 맞춰 고릅니다.
4. 자막(lines): 한 줄 한국어 8~14자, 의미 단위. 음성인식 오타는 문맥으로 교정하되, 확신이 없는 단어는 지어내지 말고 "○○"로 두고 notes에 적습니다. 말버릇은 뺍니다.
5. 자막 역할(role): normal(흰색, 기본) / quote(노란색: 속마음·인용·"~잖아요" 같은 공감 포인트·시청자에게 하는 말) / emphasis(크게: 관용구·결정적 한마디, 전체 2~3개) / alert(빨강 크게: 충격·경고, 0~1개) / aside(괄호 해설: 화자 말이 아닌 상황 설명). highlight에는 줄 안에서 노란색으로 바꿀 키워드(선택).
6. 맥락 라벨(label): 새 이야기 단락이 시작되는 줄에 짧은 라벨(2~10자)을 붙입니다. 예: "실제 경험", "왜 이렇게 싸..?", "재수강하게 된 계기". 영상 전체에 4~7개.
7. 엔딩(ending): 영상의 핵심 메시지를 한 문장(최대 2줄, 줄바꿈 \n)으로. 화자의 말을 바탕으로 쓰고 새로운 주장을 만들지 않습니다. 마지막 컷은 말이 끝난 뒤 1.5~2.5초 여유를 둬 카드가 보이게 합니다.
8. 줌(zoom): 펀치인 줌(컷마다 배율 교차)은 쓰지 않습니다. zoom은 특정 부위를 짚는 극단 확대(14번)에만 씁니다.
9. B롤(broll): 제공된 B롤 중 발언과 맞는 것만. 2~5초, 첫 3초·마지막 3초 금지. 이미지는 fit "fill"(전체) 또는 "pip"(제품 사진 등, pip {scale, x, y}, caption 가능). AI로 만든 이미지는 "ai": true(상단 고지 라벨 자동).
10. B롤이 부족하면 broll_ideas에 재연 장면 아이디어(at, dur, 장면 설명=이미지 생성 프롬프트)를 적습니다.
11. 영어(en)는 요청이 있을 때만 넣습니다. 넣을 때는 직역 금지, 관용구는 의미로.
12. 스타일에 상단 고정 제목이 있으면 title {line1, line2}를 제안합니다(아래 스타일 지침 참고). 영상 내용 안에서만, 과장·허위 금지.
13. 화자가 여럿이거나 소개가 필요하면 speakers {"A": {"name", "title"}}를 만들고 컷마다 "speaker": "A". 이름을 모르면 "○○○".
14. 특정 부위·물건을 짚는 말("이 근육", "여기")에는 극단 확대 컷(zoom 2.0~2.5, focus {x,y} 원본 좌표 0~1)과 callouts [{at, dur, x, y}](화면 좌표 0~1)를 쓸 수 있습니다.
15. 멀티캠(sync가 있는 경우): 컷마다 "angle": "<다른 카메라 src>"로 화면만 바꿀 수 있습니다. in/out과 자막은 항상 기준 카메라(src) 시간입니다. 와이드(여럿)↔클로즈업을 교차합니다.
16. 의료·시술·금융 정보는 disclaimer(하단 면책 문구)를 넣습니다. 스티커·이모지가 어울리는 지점은 sticker_notes [{at, text}].

출력 형식(JSON만, 설명 금지):
{
 "main": [ {"src": "<클립 경로 그대로>", "in": 초, "out": 초,
            "lines": [ {"ko": "...", "role": "normal", "highlight": [], "label": "실제 경험"} ] } ],
 "broll": [ {"src": "<B롤 경로>", "at": 타임라인초, "dur": 초, "in": 0, "fit": "fill"} ],
 "broll_ideas": [ {"at": 타임라인초, "dur": 3, "prompt": "..."} ],
 "ending": {"text": "...", "dur": 2.5},
 "title": {"line1": "...", "line2": "..."},
 "speakers": {"A": {"name": "...", "title": "..."}},
 "callouts": [], "disclaimer": null, "sticker_notes": [],
 "notes": "편집 의도와 확인이 필요한 단어"
}
- 스타일에 없는 항목(title, ending 등)은 생략해도 됩니다.
- lines는 그 컷에서 말하는 내용을 순서대로 자막 줄로 나눈 것입니다. 시간은 적지 않습니다(음성에 맞춰 자동 배분됨).
- 한 컷 안의 말은 lines에 빠짐없이, 말한 순서대로 넣습니다. 컷 밖의 말은 넣지 않습니다.
- label, highlight는 필요할 때만 넣습니다. zoom은 극단 확대 컷에만."""


def style_hints(style_name=None):
    try:
        from agent import load_style
        st = load_style(style_name)
        return st.get("planner_hints", ""), st
    except Exception:
        return "", {}


def system_prompt(style_name=None):
    hints, st = style_hints(style_name)
    extra = f"\n\n스타일 지침\n{hints}" if hints else ""
    if not st.get("title"):
        extra += "\n- 이 스타일은 상단 고정 제목을 쓰지 않습니다(title 생략)."
    if not st.get("ending"):
        extra += "\n- 이 스타일은 엔딩 카드를 쓰지 않습니다(ending 생략)."
    return SYSTEM + extra


def make_user_prompt(analysis, brief="", target_seconds=None, words=True):
    lines = []
    if brief:
        lines.append(f"[편집 요청]\n{brief}")
    if target_seconds:
        lines.append(f"[목표 길이] target_seconds = {target_seconds}")
    for c in analysis["clips"]:
        lines.append(f"\n[클립] {c['src']} (길이 {c['duration']}s)")
        if c.get("silences"):
            lines.append("무음: " + ", ".join(f"{a}-{b}" for a, b in c["silences"]))
        for s in c["transcript"]:
            ws = " ".join(f"{w[2]}@{w[0]}" for w in s["words"]) if (words and s.get("words")) else ""
            lines.append(f"  {s['start']:.2f}-{s['end']:.2f}: {s['text']}" + (f"\n    words: {ws}" if ws else ""))
    if analysis.get("sync"):
        lines.append("\n[멀티캠 동기화] 기준 대비 오프셋(초): " + json.dumps(analysis["sync"], ensure_ascii=False))
    if analysis.get("faces"):
        lines.append("[얼굴 위치] " + ", ".join(f"{k}: x={v['x']} y={v['y']}" for k, v in analysis["faces"].items()))
    if analysis.get("broll"):
        lines.append("\n[B롤 목록]")
        for b in analysis["broll"]:
            lines.append(f"  {b['src']} ({b['duration']}s, {b['orientation']}): {b['description']}")
    return "\n".join(lines)


def extract_json(text):
    """응답에서 JSON 객체 추출 (```json 코드블록/앞뒤 설명 허용)."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claude 응답에서 JSON을 찾지 못했습니다:\n" + text[:500])
    return json.loads(m.group(1) if m.lastindex else m.group(0))


ROLES = {"normal", "quote", "emphasis", "alert", "aside"}
DEFAULT_MODEL = "claude-opus-5-5"
# 1M 토큰당 달러 (입력, 출력) — https://platform.claude.com/docs/en/models/overview (2026-10 기준)
PRICES = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10), "claude-fable-5-1": (10, 50),
          "claude-haiku-4-5-20251001": (1, 5)}


def validate_plan(p, analysis, style=None, target_seconds=None):
    """플랜 형식/값 검사. 문제 목록(한국어)을 반환 — 비어 있으면 통과."""
    errs = []
    clips = {c["src"]: c for c in analysis.get("clips", [])}
    others = set(analysis.get("media", {}))
    main = p.get("main")
    if not isinstance(main, list) or not main:
        return ["main이 비어 있습니다."]
    total = 0.0
    for i, c in enumerate(main):
        tag = f"main[{i}]"
        src = c.get("src")
        if src not in clips:
            errs.append(f"{tag}.src '{src}'가 클립 목록에 없습니다. 클립 경로를 그대로 쓰세요: {list(clips)}")
            continue
        try:
            a, b = float(c["in"]), float(c["out"])
        except (KeyError, TypeError, ValueError):
            errs.append(f"{tag}: in/out이 숫자가 아닙니다.")
            continue
        if not (0 <= a < b <= clips[src]["duration"] + 0.05):
            errs.append(f"{tag}: in={a}, out={b}가 클립 길이(0~{clips[src]['duration']}) 밖이거나 in>=out입니다.")
        if b - a < 0.5:
            errs.append(f"{tag}: 컷이 너무 짧습니다({b - a:.2f}초).")
        total += max(0.0, b - a)
        lines = c.get("lines")
        if not isinstance(lines, list) or not lines:
            errs.append(f"{tag}.lines가 비어 있습니다.")
            continue
        for j, l in enumerate(lines):
            if not str(l.get("ko", "")).strip():
                errs.append(f"{tag}.lines[{j}].ko가 비어 있습니다.")
            if l.get("role", "normal") not in ROLES:
                errs.append(f"{tag}.lines[{j}].role '{l.get('role')}'는 {sorted(ROLES)} 중 하나여야 합니다.")
        if c.get("angle") and c["angle"] not in others:
            errs.append(f"{tag}.angle '{c['angle']}'가 미디어 목록에 없습니다.")
    for i, br in enumerate(p.get("broll") or []):
        if br.get("src") not in others:
            errs.append(f"broll[{i}].src '{br.get('src')}'가 B롤 목록에 없습니다.")
    if target_seconds and total and not (0.6 * target_seconds <= total <= 1.4 * target_seconds):
        errs.append(f"전체 길이 {total:.1f}초가 목표 {target_seconds}초와 많이 다릅니다(±40% 이내로).")
    try:
        from agent import load_style
        st = load_style(style or p.get("style"))
        if st.get("title") and not (p.get("title") or {}).get("line1"):
            errs.append("이 스타일은 상단 제목이 필요합니다: title {line1, line2}를 넣으세요.")
    except Exception:
        pass
    return errs


def _call(client, model, system, messages, max_tokens=32000):
    """스트리밍으로 호출(긴 응답 시간 초과 방지). (텍스트, usage) 반환."""
    with client.messages.stream(model=model, max_tokens=max_tokens, system=system, messages=messages) as st:
        msg = st.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return text, msg.usage


def plan(analysis_path, out_path, brief="", target_seconds=None, model=None, style=None, client=None, retries=1):
    """Claude API로 편집 계획 생성 → 검증 → 문제 있으면 오류를 알려 주고 다시 생성(최대 retries회)."""
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    model = model or os.environ.get("CAPCUT_AGENT_MODEL", DEFAULT_MODEL)
    system = system_prompt(style)
    messages = [{"role": "user", "content": make_user_prompt(analysis, brief, target_seconds)}]
    raw_path = os.path.splitext(out_path)[0] + "_raw.txt"
    tin = tout = 0
    p = errs = None
    for attempt in range(retries + 1):
        print(f"편집 계획 생성 중 ({model}){' — 재시도' if attempt else ''}...")
        text, usage = _call(client, model, system, messages)
        tin += getattr(usage, "input_tokens", 0) or 0
        tout += getattr(usage, "output_tokens", 0) or 0
        with open(raw_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 시도 {attempt + 1} =====\n{text}\n")
        try:
            p = extract_json(text)
            errs = validate_plan(p, analysis, style, target_seconds)
        except (ValueError, json.JSONDecodeError) as e:
            p, errs = None, [f"JSON 형식 오류: {e}"]
        if not errs:
            break
        print("  계획에 문제가 있어 다시 요청합니다:\n   - " + "\n   - ".join(errs[:8]))
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "다음 문제를 고쳐서 JSON 전체를 다시 출력하세요(설명 없이 JSON만):\n- "
                      + "\n- ".join(errs)}]
    if p is None:
        raise SystemExit(f"편집 계획을 만들지 못했습니다. 응답 원문: {raw_path}")
    if errs:
        print("  ⚠ 남은 문제(그대로 진행, 캡컷에서 확인 필요):\n   - " + "\n   - ".join(errs))
    finalize(p, analysis, style)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    pin, pout = PRICES.get(model, (0, 0))
    cost = (tin * pin + tout * pout) / 1e6
    print(f"편집 계획 -> {out_path}\n  토큰: 입력 {tin:,} / 출력 {tout:,}" + (f" (약 ${cost:.2f})" if cost else ""))
    if p.get("title"):
        print(f"  제목: {p['title'].get('line1', '')} / {p['title'].get('line2', '')}")
    if p.get("notes"):
        print("  메모:", p["notes"])
    return out_path


def finalize(p, analysis, style=None):
    """분석 결과(미디어 정보·얼굴·멀티캠)를 플랜에 합침."""
    p["media"] = analysis.get("media", {})
    p.setdefault("faces", analysis.get("faces", {}))
    if analysis.get("sync"):
        p["sync"] = analysis["sync"]
    if style:
        p["style"] = style
    return p


def import_plan(analysis_path, plan_path, style=None, target_seconds=None):
    """무료 모드: claude.ai 답변을 붙여넣은 파일을 읽어 JSON 추출·검사·정리.
    반환: 문제 목록(비어 있으면 성공). 문제가 있으면 claude.ai에 다시 보낼 문구를 *_fix.txt로 저장."""
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    with open(plan_path, encoding="utf-8-sig") as f:
        text = f.read()
    if not text.strip():
        return ["파일이 비어 있습니다. Claude 답변(JSON)을 붙여넣고 저장하세요."]
    try:
        p = extract_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        errs = [f"JSON 형식 오류: {e}. 답변 전체를 빠짐없이 복사했는지 확인하세요."]
    else:
        errs = validate_plan(p, analysis, style, target_seconds)
    fix = os.path.splitext(plan_path)[0] + "_fix.txt"
    if errs:
        with open(fix, "w", encoding="utf-8") as f:
            f.write("다음 문제를 고쳐서 JSON 전체를 다시 출력하세요(설명 없이 JSON만):\n- " + "\n- ".join(errs))
        return errs
    finalize(p, analysis, style)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    if os.path.exists(fix):
        os.remove(fix)
    return []


def write_prompt_only(analysis_path, out_path, brief="", target_seconds=None, style=None):
    """API 키 없이 쓰는 경우(무료 모드): 프롬프트를 파일로 저장 → claude.ai에 붙여넣고 답변을 edit_plan.json에 붙여넣기."""
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    with open(out_path, "w", encoding="utf-8") as f:
        # 무료 모드는 붙여넣기 길이를 줄이려고 단어 타임스탬프 생략(컷 경계는 build 때 음성으로 자동 보정)
        text = (system_prompt(style) + "\n\n---\n\n" + make_user_prompt(analysis, brief, target_seconds, words=False)
                + "\n\n---\n위 규칙대로 편집 계획 JSON만 출력하세요. 설명은 쓰지 마세요.")
        f.write(text)
    print(f"프롬프트 저장 -> {out_path} ({len(text):,}자)")
    if len(text) > 60000:
        print("  ⚠ 프롬프트가 깁니다. claude.ai 무료 플랜에서 잘리면 원본을 나눠서(10분 이하씩) 진행하세요.")
