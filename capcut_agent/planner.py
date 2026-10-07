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


def make_user_prompt(analysis, brief="", target_seconds=None):
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
            words = " ".join(f"{w[2]}@{w[0]}" for w in s["words"]) if s.get("words") else ""
            lines.append(f"  {s['start']:.2f}-{s['end']:.2f}: {s['text']}" + (f"\n    words: {words}" if words else ""))
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
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Claude 응답에서 JSON을 찾지 못했습니다:\n" + text[:500])
    return json.loads(m.group(0))


def plan(analysis_path, out_path, brief="", target_seconds=None, model=None, style=None):
    import anthropic
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    client = anthropic.Anthropic()
    model = model or os.environ.get("CAPCUT_AGENT_MODEL", "claude-opus-5-5")
    print(f"편집 계획 생성 중 ({model})...")
    msg = client.messages.create(
        model=model, max_tokens=16000, system=system_prompt(style),
        messages=[{"role": "user", "content": make_user_prompt(analysis, brief, target_seconds)}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    p = extract_json(text)
    p["media"] = analysis.get("media", {})
    p.setdefault("faces", analysis.get("faces", {}))
    if analysis.get("sync"):
        p["sync"] = analysis["sync"]
    if style:
        p["style"] = style
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    print("편집 계획 ->", out_path)
    if p.get("notes"):
        print("  메모:", p["notes"])
    return out_path


def write_prompt_only(analysis_path, out_path, brief="", target_seconds=None, style=None):
    """API 키 없이 쓰는 경우: 프롬프트를 파일로 저장 → Claude 앱에 붙여넣고 결과 JSON을 edit_plan.json으로 저장."""
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(system_prompt(style) + "\n\n---\n\n" + make_user_prompt(analysis, brief, target_seconds))
    print("프롬프트 저장 ->", out_path)
