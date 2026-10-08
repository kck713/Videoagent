"""2단계: Claude가 전사본을 읽고 편집 계획(edit_plan.json)을 만듭니다.

- 메인 컷: NG/반복/말 더듬기/긴 무음 제거, 목표 길이에 맞게 핵심 발언 선택
- 자막: 한 줄 8~14자, 역할(흰/노랑/강조/경고/괄호) 지정, 맥락 라벨, 엔딩 카드 문장
- B롤: 발언 내용과 맞는 B롤 배치
API 키: 환경변수 ANTHROPIC_API_KEY
"""
import json
import os
import re

SYSTEM = """당신은 한국어 인터뷰 숏폼(9:16, 약 60~90초) 전문 영상 편집자이자 숏폼 채널 편집장입니다.
주어진 원본 클립 전사본(단어 단위 타임스탬프 포함)으로 캡컷 가편집 계획을 JSON으로만 출력합니다.
목표 스타일: 화자 얼굴 위주(배율 고정), 한 줄 한글 자막(흰색/노란색), 자막 위 검정 박스 맥락 라벨, 훅 카드, 메시지 카드, 마지막 핵심 메시지 카드.
좋은 숏폼의 기준: ①첫 3초 안에 멈출 이유를 준다 ②영상 전체가 핵심 메시지 하나를 향한다 ③강조는 드물어서 강하다.

작업 순서(출력 전에 머릿속으로 반드시 거친다)
A. 핵심 메시지(key_message) 먼저: 이 영상을 본 사람이 기억해야 할 한 문장(20자 안팎)을 화자의 말에서 뽑는다. 모든 컷은 이 문장을 뒷받침해야 하며, 뒷받침하지 않는 컷은 뺀다.
B. 훅(hook) 후보 3개를 전사본에서 고른다. 후보는 반드시 다음 중 하나의 패턴이어야 한다:
   질문(시청자가 답을 알고 싶어짐) / 숫자·구체(금액·기간·횟수) / 반전·대비("~인 줄 알았는데") / 고백·충격("솔직히 ~") / 경고("이거 모르면 ~").
   세 후보를 비교해 가장 멈추게 하는 하나를 고르고, notes에 세 후보와 고른 이유를 한 줄씩 적는다.
   훅은 전사 순서와 상관없이 영상 어디서든 가져올 수 있다(콜드 오픈). 뒤에서 가져오면 그 다음 컷부터 사연을 시작한다.
C. 그 다음에 컷을 고른다: 훅 → 고민/경험 → 계기 → 메시지(핵심 문장이 직접 나오는 컷) → 엔딩 한마디. 목표 길이(target_seconds)에 맞춘다.

편집 원칙
1. 메인 컷(main): 같은 말을 다시 한 NG 테이크는 마지막(가장 매끄러운) 테이크만 남깁니다. "어", "음", 말 더듬기, 0.3초 넘는 무음, 촬영 신호("지금 시작합니다" 등)는 잘라냅니다. 한 컷은 최소 1초.
2. 같은 테이크에서 이어지는 문장(0.5초 이하 숨)은 한 컷으로 묶습니다. 컷 경계는 단어 타임스탬프 기준(앞 0.08초, 뒤 0.12초 여유).
3. 첫 컷(훅)은 4초 이내로 짧고 강하게. 첫 컷의 자막 역할은 emphasis/alert/quote 중 하나. 첫 3초 안에 인사말·자기소개·배경 설명은 금지.
4. 자막(lines): 한 줄 한국어 8~14자, 의미 단위. 음성인식 오타는 문맥으로 교정하되, 확신이 없는 단어는 지어내지 말고 "○○"로 두고 notes에 적습니다. 말버릇은 뺍니다.
5. 자막 역할(role): normal(흰색, 기본) / quote(노란색: 속마음·인용·"~잖아요" 같은 공감 포인트·시청자에게 하는 말) / emphasis(크게, 단어 단위로 튀어나오며 등장: 관용구·결정적 한마디·숫자, 전체 3~5개) / alert(빨강 크게: 충격·경고, 0~2개) / aside(괄호 해설: 화자 말이 아닌 상황 설명). highlight에는 줄 안에서 노란색으로 바꿀 키워드(숫자·핵심어, 선택). emphasis가 8개를 넘으면 강조가 아니라 소음입니다.
6. 맥락 라벨(label): 새 이야기 단락이 시작되는 줄에 짧은 라벨(2~10자)을 붙입니다. 예: "실제 경험", "왜 이렇게 싸..?", "재수강하게 된 계기". 영상 전체에 4~7개. 라벨은 궁금증을 만드는 문장형("왜 ~?", "~한 이유")이 명사형보다 낫습니다.
7. 훅 카드(hook): 첫 2~3초 상단에 뜨는 큰 글씨 {text(8~16자, 훅 문장을 자막보다 더 자극적으로 압축), sub?(작은 보조 문구 4~12자, 예: "미용문신 수강 후기")}. 자막과 똑같은 문장을 반복하지 말고, 질문형·숫자형·대비형으로 다듬습니다. 과장·허위 금지.
8. 메시지 카드(message_cards): 핵심 메시지가 말로 나오는 순간과 숫자가 나오는 순간에 화면 가운데 큰 글씨 카드를 1~2개 넣습니다.
   {at(타임라인 초), dur(2.5~3.5), text(10~18자, 줄바꿈 \\n 가능), highlight[]} 또는 숫자형 {at, dur, kind: "stat", value: "50~70만 원", caption: "수강료 차이"}.
   at은 그 말이 시작되는 타임라인 시각(앞 컷들의 길이를 합산). 카드 문장은 화자의 말을 압축한 것이어야 하며 새 주장을 만들지 않습니다. 첫 5초와 엔딩 카드 구간에는 넣지 않습니다.
9. 엔딩(ending): key_message를 그대로 또는 더 짧게 다듬은 한 문장(최대 2줄, 줄바꿈 \\n). 마지막 컷은 말이 끝난 뒤 1.5~2.5초 여유를 둬 카드가 보이게 합니다.
10. 줌(zoom): 펀치인 줌(컷마다 배율 교차)은 쓰지 않습니다. zoom은 특정 부위를 짚는 극단 확대(16번)에만 씁니다.
11. B롤(broll): 제공된 B롤 중 발언과 맞는 것만. 2~5초, 첫 3초·마지막 3초 금지. 이미지는 fit "fill"(전체) 또는 "pip"(제품 사진 등, pip {scale, x, y}, caption 가능). AI로 만든 이미지는 "ai": true(상단 고지 라벨 자동). 이미지 B롤은 자동으로 천천히 확대(켄 번스)됩니다.
12. B롤이 부족하면 broll_ideas에 재연 장면 아이디어(at, dur, 장면 설명=이미지 생성 프롬프트)를 적습니다.
13. 영어(en)는 요청이 있을 때만 넣습니다. 넣을 때는 직역 금지, 관용구는 의미로.
14. 스타일에 상단 고정 제목이 있으면 title {line1, line2}를 제안합니다(아래 스타일 지침 참고). 이때 line2가 훅 역할을 하므로 hook 카드는 생략합니다. 영상 내용 안에서만, 과장·허위 금지.
15. 화자가 여럿이거나 소개가 필요하면 speakers {"A": {"name", "title"}}를 만들고 컷마다 "speaker": "A". 이름을 모르면 "○○○".
16. 특정 부위·물건을 짚는 말("이 근육", "여기")에는 극단 확대 컷(zoom 2.0~2.5, focus {x,y} 원본 좌표 0~1)과 callouts [{at, dur, x, y}](화면 좌표 0~1)를 쓸 수 있습니다.
17. 멀티캠(sync가 있는 경우): 컷마다 "angle": "<다른 카메라 src>"로 화면만 바꿀 수 있습니다. in/out과 자막은 항상 기준 카메라(src) 시간입니다. 와이드(여럿)↔클로즈업을 교차합니다.
18. 의료·시술·금융 정보는 disclaimer(하단 면책 문구)를 넣습니다. 스티커·이모지가 어울리는 지점은 sticker_notes [{at, text}].
19. 모션(강조 자막 팝·라벨 슬라이드·카드 페이드·효과음)은 빌더가 역할(role)과 카드에 맞춰 자동으로 넣습니다. 플래너는 역할을 정확히 고르는 데 집중합니다.

출력 형식(JSON만, 설명 금지):
{
 "key_message": "영상이 남길 한 문장",
 "hook": {"text": "8~16자 훅 문장", "sub": "보조 문구(선택)"},
 "main": [ {"src": "<클립 경로 그대로>", "in": 초, "out": 초,
            "lines": [ {"ko": "...", "role": "normal", "highlight": [], "label": "실제 경험"} ] } ],
 "message_cards": [ {"at": 타임라인초, "dur": 3, "text": "핵심 문장", "highlight": []},
                    {"at": 타임라인초, "dur": 3, "kind": "stat", "value": "50~70만 원", "caption": "수강료 차이"} ],
 "broll": [ {"src": "<B롤 경로>", "at": 타임라인초, "dur": 초, "in": 0, "fit": "fill"} ],
 "broll_ideas": [ {"at": 타임라인초, "dur": 3, "prompt": "..."} ],
 "ending": {"text": "...", "dur": 2.5},
 "title": {"line1": "...", "line2": "..."},
 "speakers": {"A": {"name": "...", "title": "..."}},
 "callouts": [], "disclaimer": null, "sticker_notes": [],
 "notes": "훅 후보 3개와 선택 이유, 뺀 내용, 확인이 필요한 단어"
}
- 스타일에 없는 항목(title, ending, hook 등)은 생략해도 됩니다.
- lines는 그 컷에서 말하는 내용을 순서대로 자막 줄로 나눈 것입니다. 시간은 적지 않습니다(음성에 맞춰 자동 배분됨).
- 한 컷 안의 말은 lines에 빠짐없이, 말한 순서대로 넣습니다. 컷 밖의 말은 넣지 않습니다.
- label, highlight는 필요할 때만 넣습니다. zoom은 극단 확대 컷에만."""


REVIEW_SYSTEM = """당신은 조회수 높은 한국어 숏폼 채널의 편집장입니다. 편집자가 낸 계획(JSON)을 검토하고 더 강하게 고쳐서 JSON 전체를 다시 출력합니다.
점검 항목(각각 구체적으로 고친다):
1. 훅: 첫 컷이 4초 이내이고, 인사·배경 설명이 아니라 질문/숫자/반전/고백/경고 중 하나인가? hook.text가 자막을 그대로 베끼지 않고 더 멈추게 하는가? 더 강한 문장이 전사본 뒤쪽에 있으면 콜드 오픈으로 앞에 가져온다.
2. 메시지: key_message가 한 문장으로 선명한가? 그 문장이 말로 나오는 컷이 main에 있고, 그 시각에 message_cards가 있는가? ending이 key_message와 같은 말을 하는가? 메시지를 뒷받침하지 않는 컷은 뺀다.
3. 템포: 평균 컷 3~6초, 10초 넘는 컷은 쪼개거나 줄인다. 문장 사이 군더더기를 뺀다. 목표 길이를 지킨다.
4. 강조의 경제: emphasis 3~5개, alert 0~2개. 남발이면 줄이고, 숫자·결정적 한마디에만 남긴다. highlight로 숫자·핵심어를 노랗게.
5. 라벨: 단락마다 궁금증을 만드는 라벨(4~7개). 명사 나열("경험")보다 문장형("왜 다시 배웠나").
6. 형식: 클립 경로·in/out·lines 규칙(원 계획과 같은 형식)을 지키고, 컷 밖의 말을 자막에 넣지 않는다. 전사본에 없는 말은 만들지 않는다.
출력은 수정된 계획 JSON 하나만(설명 금지). notes에 무엇을 왜 바꿨는지 2~4줄로 추가한다."""


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
    hook = p.get("hook")
    if hook is not None and not (isinstance(hook, str) or (isinstance(hook, dict) and str(hook.get("text", "")).strip())):
        errs.append("hook은 {\"text\": \"...\", \"sub\": \"...\"} 형식이어야 합니다(text 필수).")
    mcs = p.get("message_cards")
    if mcs is not None and not isinstance(mcs, list):
        errs.append("message_cards는 배열이어야 합니다.")
    for i, c in enumerate(mcs or []):
        if not isinstance(c, dict):
            errs.append(f"message_cards[{i}]는 객체여야 합니다.")
            continue
        try:
            t0 = float(c["at"])
        except (KeyError, TypeError, ValueError):
            errs.append(f"message_cards[{i}].at(타임라인 초)이 없습니다.")
            continue
        if total and t0 >= total - 1:
            errs.append(f"message_cards[{i}].at={t0}가 영상 길이({total:.1f}초)를 넘습니다. 앞 컷 길이를 합산한 타임라인 시각이어야 합니다.")
        if c.get("kind") == "stat":
            if not str(c.get("value", "")).strip():
                errs.append(f"message_cards[{i}]: kind가 stat이면 value가 필요합니다.")
        elif not str(c.get("text", "")).strip():
            errs.append(f"message_cards[{i}].text가 비어 있습니다.")
    try:
        from agent import load_style
        st = load_style(style or p.get("style"))
        if st.get("title") and not (p.get("title") or {}).get("line1"):
            errs.append("이 스타일은 상단 제목이 필요합니다: title {line1, line2}를 넣으세요.")
    except Exception:
        pass
    return errs


HOOK_PATTERNS = (
    ("질문", re.compile(r"[?？]|왜|어떻게|뭘까|일까|아세요|있을까")),
    ("숫자", re.compile(r"\d|백만|천만|억|만 원|만원|배|년|개월|번째|%")),
    ("반전·대비", re.compile(r"줄 알았|근데|그런데|하지만|반대로|오히려|사실은|알고 보니")),
    ("고백·충격", re.compile(r"솔직히|충격|망했|실패|후회|부끄|진짜|미쳤")),
    ("경고", re.compile(r"절대|조심|주의|하지 마|모르면|위험|당하")),
)


def _timeline(p):
    """각 컷의 타임라인 시작 시각과 길이. [(t0, dur, clip), ...]"""
    out, at = [], 0.0
    for c in p.get("main") or []:
        try:
            dur = max(0.0, float(c["out"]) - float(c["in"]))
        except (KeyError, TypeError, ValueError):
            dur = 0.0
        out.append((at, dur, c))
        at += dur
    return out


def critique(p, style=None, target_seconds=None, analysis=None):
    """편집 계획의 '강도' 점검 — 훅·메시지·템포·강조·라벨·자막 길이. 형식 오류(validate_plan)와 별개로
    더 강하게 만들 수 있는 점을 경고 목록으로 돌려줍니다. Claude Code /edit의 자기 점검과 API 리뷰 패스에 씁니다."""
    style = style or {}
    tl = _timeline(p)
    total = sum(d for _, d, _ in tl)
    warns, facts = [], {}
    if not tl:
        return {"warnings": ["main이 비어 있습니다."], "facts": {}}
    durs = [d for _, d, _ in tl]
    facts["길이"] = round(total, 1)
    facts["컷 수"] = len(tl)
    facts["평균 컷"] = round(total / len(tl), 1)
    facts["최장 컷"] = round(max(durs), 1)
    lines = [(t0, l) for t0, _, c in tl for l in (c.get("lines") or c.get("subs") or [])]
    roles = [l.get("role", "normal") for _, l in lines]
    n_emp, n_alert = roles.count("emphasis"), roles.count("alert")
    facts["emphasis"] = n_emp
    facts["alert"] = n_alert
    labels = [l.get("label") for _, l in lines if l.get("label")] + [x.get("text") for x in p.get("labels") or []
                                                                     if x.get("kind") != "top"]
    facts["라벨"] = len(labels)
    facts["메시지 카드"] = len(p.get("message_cards") or [])
    long_lines = [l.get("ko", "") for _, l in lines if len(str(l.get("ko", "")).replace(" ", "")) > 16]
    facts["16자 넘는 자막"] = len(long_lines)

    # 훅
    first_t0, first_dur, first = tl[0]
    first_lines = first.get("lines") or first.get("subs") or []
    first_text = " ".join(str(l.get("ko", "")) for l in first_lines)
    hook = p.get("hook")
    hook_text = hook.get("text", "") if isinstance(hook, dict) else (hook or "")
    probe_text = f"{hook_text} {first_text}"
    patt = [name for name, rx in HOOK_PATTERNS if rx.search(probe_text)]
    facts["훅 패턴"] = ", ".join(patt) or "없음"
    if first_dur > 4.5:
        warns.append(f"첫 컷이 {first_dur:.1f}초로 깁니다(4초 이내). 훅 문장만 남기고 나머지는 다음 컷으로 나누세요.")
    if re.search(r"안녕|반갑|소개|저는 .*입니다|입니다\.?$", first_text[:30]) and not hook_text:
        warns.append("첫 컷이 인사·자기소개로 시작합니다. 가장 강한 문장(질문/숫자/반전/고백/경고)을 앞으로 가져오세요(콜드 오픈).")
    if not any(r in ("emphasis", "alert", "quote") for r in [l.get("role", "normal") for l in first_lines]):
        warns.append("첫 컷 자막에 emphasis/alert/quote 역할이 없습니다. 훅 문장은 강조 역할로 지정하세요.")
    if style.get("hook_card") and not hook_text:
        warns.append("hook(훅 카드)이 없습니다. 첫 2~3초 상단에 뜰 8~16자 훅 문장을 넣으세요.")
    if hook_text and first_text and hook_text.replace(" ", "") in first_text.replace(" ", ""):
        warns.append("hook.text가 첫 자막과 같은 문장입니다. 질문형·숫자형·대비형으로 더 압축하세요.")
    if not patt:
        warns.append("훅에 질문/숫자/반전/고백/경고 패턴이 보이지 않습니다. 멈추게 할 이유가 있는지 다시 보세요.")
    # 메시지
    km = str(p.get("key_message") or "").strip()
    if not km:
        warns.append("key_message(영상이 남길 한 문장)가 없습니다. 먼저 정하고 모든 컷이 그 문장을 향하게 하세요.")
    if style.get("message_card") and total >= 40 and not p.get("message_cards"):
        warns.append("message_cards가 없습니다. 핵심 문장이 말로 나오는 순간과 숫자가 나오는 순간에 1~2개 넣으세요.")
    if len(p.get("message_cards") or []) > 3:
        warns.append("message_cards가 4개 이상입니다. 카드가 많으면 하나도 기억되지 않습니다(1~2개).")
    ending = (p.get("ending") or {}).get("text", "") if isinstance(p.get("ending"), dict) else ""
    if style.get("ending") and not ending:
        warns.append("ending(엔딩 카드)이 없습니다. key_message를 한 문장으로 넣으세요.")
    if km and ending and not _overlap(km, ending):
        warns.append("ending이 key_message와 다른 말을 합니다. 엔딩은 핵심 메시지를 되풀이해야 기억에 남습니다.")
    # 강조·라벨·템포
    if n_emp + n_alert == 0:
        warns.append("emphasis/alert가 하나도 없습니다. 결정적 한마디·숫자 3~5곳을 emphasis로 지정하세요.")
    elif n_emp > 8:
        warns.append(f"emphasis가 {n_emp}개로 너무 많습니다(3~5개). 남발하면 강조가 아니라 소음입니다.")
    if n_alert > 2:
        warns.append(f"alert가 {n_alert}개입니다(0~2개). 가장 충격적인 한 곳만 남기세요.")
    if total >= 40 and len(labels) < 3:
        warns.append(f"맥락 라벨이 {len(labels)}개입니다(4~7개). 단락이 바뀌는 줄에 궁금증을 만드는 라벨을 붙이세요.")
    if max(durs) > 10:
        warns.append(f"{max(durs):.1f}초짜리 컷이 있습니다. 10초가 넘으면 중간 군더더기를 빼 쪼개세요.")
    if total / len(tl) > 7:
        warns.append(f"평균 컷이 {total / len(tl):.1f}초입니다(3~6초 권장). 문장 사이 숨·군더더기를 더 빼세요.")
    if long_lines:
        warns.append(f"16자 넘는 자막 {len(long_lines)}줄: " + " / ".join(long_lines[:3]))
    if target_seconds and not (0.8 * target_seconds <= total <= 1.2 * target_seconds):
        warns.append(f"길이 {total:.1f}초가 목표 {target_seconds}초와 다릅니다(±20%).")
    return {"warnings": warns, "facts": facts}


def _overlap(a, b):
    """두 문장이 핵심 어절을 공유하는지(엔딩 ↔ key_message)."""
    norm = lambda x: {w.strip(".,!?~)(") for w in re.split(r"\s+|\n", x) if len(w.strip(".,!?~)(")) >= 2}
    A, B = norm(a), norm(b)
    if not A or not B:
        return True
    return len(A & B) >= max(1, min(len(A), len(B)) // 3)


def format_critique(report):
    f = report.get("facts") or {}
    head = "계획 점검: " + ", ".join(f"{k} {v}" for k, v in f.items())
    if not report["warnings"]:
        return head + "\n  강도 문제 없음."
    return head + "\n  더 강하게 만들 수 있는 점:\n   - " + "\n   - ".join(report["warnings"])


def _call(client, model, system, messages, max_tokens=32000):
    """스트리밍으로 호출(긴 응답 시간 초과 방지). (텍스트, usage) 반환."""
    with client.messages.stream(model=model, max_tokens=max_tokens, system=system, messages=messages) as st:
        msg = st.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return text, msg.usage


def plan(analysis_path, out_path, brief="", target_seconds=None, model=None, style=None, client=None, retries=1,
         review=True):
    """Claude API로 편집 계획 생성 → 검증 → 문제 있으면 오류를 알려 주고 다시 생성(최대 retries회)
    → (review=True) 편집장 리뷰 패스: 훅·메시지·템포 점검 결과를 붙여 한 번 더 강화."""
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
    try:
        from agent import load_style
        st = load_style(style or p.get("style"))
    except Exception:
        st = {}
    rep = critique(p, st, target_seconds)
    print("  " + format_critique(rep).replace("\n", "\n  "))
    if review:
        print("편집장 리뷰 패스(훅·메시지·템포 강화)...")
        ask = ("아래는 편집자가 낸 계획과 자동 점검 결과입니다. 점검 항목을 반영해 더 강하게 고친 JSON 전체를 출력하세요.\n\n"
               "[자동 점검]\n- " + ("\n- ".join(rep["warnings"]) if rep["warnings"] else "형식상 문제 없음 — 그래도 훅·메시지·템포를 더 강하게.")
               + "\n\n[원본 전사·규칙]\n" + messages[0]["content"]
               + "\n\n[편집자 계획]\n" + json.dumps(p, ensure_ascii=False))
        text, usage = _call(client, model, REVIEW_SYSTEM + "\n\n[편집 규칙 원문]\n" + system, [{"role": "user", "content": ask}])
        tin += getattr(usage, "input_tokens", 0) or 0
        tout += getattr(usage, "output_tokens", 0) or 0
        with open(raw_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== 리뷰 =====\n{text}\n")
        try:
            p2 = extract_json(text)
            errs2 = validate_plan(p2, analysis, style, target_seconds)
        except (ValueError, json.JSONDecodeError) as e:
            p2, errs2 = None, [str(e)]
        if p2 is not None and not errs2:
            p = p2
            rep2 = critique(p, st, target_seconds)
            print("  리뷰 반영: " + format_critique(rep2).replace("\n", "\n  "))
        else:
            print("  리뷰 결과에 문제가 있어 원래 계획을 씁니다: " + "; ".join(errs2[:3]))
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
