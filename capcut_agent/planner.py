"""2단계: Claude가 전사본을 읽고 편집 계획(edit_plan.json)을 만듭니다.

- 메인 컷: NG/반복/말 더듬기/긴 무음 제거, 목표 길이에 맞게 핵심 발언 선택
- 자막: 한 줄 8~16자 내외로 분할, 오탈자 교정, 문맥 맞는 영어 번역
- 강조 자막: 관용구/핵심 키워드
- B롤: 발언 내용과 맞는 B롤 배치
API 키: 환경변수 ANTHROPIC_API_KEY
"""
import json
import os
import re

SYSTEM = """당신은 한국어 인터뷰 숏폼(9:16) 전문 영상 편집자입니다.
주어진 원본 클립 전사본(단어 단위 타임스탬프 포함)으로 캡컷 가편집 계획을 JSON으로만 출력합니다.

편집 원칙
1. 메인 컷(main): 같은 말을 다시 한 NG 테이크는 마지막(가장 매끄러운) 테이크만 남깁니다. "어", "음", 말 더듬기, 0.3초 넘는 무음은 컷으로 잘라냅니다. 단, 문장 중간을 너무 잘게 자르면 점프컷이 거슬리므로 한 컷은 최소 1초 이상으로 합니다.
2. 컷 경계는 단어 타임스탬프 기준으로 잡되 앞 0.08초, 뒤 0.12초 여유를 둡니다.
3. 목표 길이(target_seconds)가 있으면 이야기 흐름(소개 → 계기/고민 → 해결/메시지 → 마무리)이 유지되도록 핵심 발언을 고릅니다.
4. 자막(lines): 한 자막은 한국어 8~16자 내외, 의미 단위로 끊습니다. 음성 인식 오타는 문맥에 맞게 고칩니다. 말버릇("어", "네 네")은 자막에서 뺍니다.
5. 영어(en): 직역 금지. 관용구는 의미로 번역합니다(예: "낙동강 오리알" → "left out in the cold", "시행착오" → "trial and error"). 짧고 자연스러운 구어체로.
6. 강조(emphasis): 관용구·결정적 한마디 등 전체에서 2~4개만 true. highlight에는 그 자막 안에서 색을 바꿀 키워드를 넣습니다(없으면 빈 배열).
7. B롤(broll): 제공된 B롤 목록 중 발언 내용과 맞는 것만, 타임라인 시간(at) 기준으로 배치합니다. 한 B롤은 2~5초, 영상 첫 3초와 마지막 2초에는 넣지 않습니다(얼굴이 보여야 함). 맞는 B롤이 없으면 빈 배열.

출력 형식(JSON만, 설명 금지):
{
 "main": [ {"src": "<클립 경로 그대로>", "in": 초, "out": 초,
            "lines": [ {"ko": "...", "en": "...", "emphasis": false, "highlight": []} ] } ],
 "broll": [ {"src": "<B롤 경로>", "at": 타임라인초, "dur": 초, "in": 0, "fit": "fill"} ],
 "notes": "편집 의도 한두 줄"
}
- lines는 그 컷에서 말하는 내용을 순서대로 자막 줄로 나눈 것입니다. 시간은 적지 않습니다(음성에 맞춰 자동 배분됨).
- 한 컷 안의 말은 lines에 빠짐없이, 말한 순서대로 넣습니다. 컷 밖의 말은 넣지 않습니다.
- 같은 테이크에서 이어지는 문장은 한 컷으로 묶습니다(0.5초 이하 숨은 자르지 않음)."""


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


def plan(analysis_path, out_path, brief="", target_seconds=None, model=None):
    import anthropic
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    client = anthropic.Anthropic()
    model = model or os.environ.get("CAPCUT_AGENT_MODEL", "claude-opus-5-5")
    print(f"편집 계획 생성 중 ({model})...")
    msg = client.messages.create(
        model=model, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": make_user_prompt(analysis, brief, target_seconds)}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    p = extract_json(text)
    p["media"] = analysis.get("media", {})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    print("편집 계획 ->", out_path)
    if p.get("notes"):
        print("  메모:", p["notes"])
    return out_path


def write_prompt_only(analysis_path, out_path, brief="", target_seconds=None):
    """API 키 없이 쓰는 경우: 프롬프트를 파일로 저장 → Claude 앱에 붙여넣고 결과 JSON을 edit_plan.json으로 저장."""
    with open(analysis_path, encoding="utf-8") as f:
        analysis = json.load(f)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(SYSTEM + "\n\n---\n\n" + make_user_prompt(analysis, brief, target_seconds))
    print("프롬프트 저장 ->", out_path)
