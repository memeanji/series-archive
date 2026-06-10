"""repurely 내부 소재 AI 분석 — 성과 지표 기반 진단/추천.

GEMINI_API_KEY 가 있으면 Gemini로 자연어 분석, 없으면 규칙 기반 분석(키 없이도 동작).
읽기 전용 · 토큰값은 로그에 남기지 않음.
"""
from __future__ import annotations

import config


def enabled() -> bool:
    return bool(config.GEMINI_API_KEY)


def _ctx(r: dict) -> str:
    """소재 1건의 성과 컨텍스트를 텍스트로."""
    def g(k, d=0):
        return r.get(k, d)
    return (
        f"매체: {g('platform','')}\n"
        f"소재명: {g('creative_name','')}\n"
        f"캠페인: {g('campaign_name','')}\n"
        f"광고비: {int(g('spend')):,}원\n"
        f"매출: {int(g('revenue')):,}원\n"
        f"구매: {int(g('conversions'))}건\n"
        f"ROAS: {g('roas',0)}\n"
        f"CTR: {g('ctr',0)}%\n"
        f"CPC: {int(g('cpc')):,}원\n"
        f"CPM: {int(g('cpm')):,}원\n"
        f"자동 분류: {g('winning_label','')} / "
        f"{'OFF 후보' if g('is_off') else ''} {'피로도 의심' if g('is_fatigue') else ''} "
        f"{'신규 테스트' if g('is_new_test') else ''}".strip()
    )


_PROMPT = (
    "너는 퍼포먼스 마케팅 분석가다. 아래 repurely(자사) 광고 소재 1건의 성과 데이터를 보고 "
    "한국어로 간결하게 분석하라. 형식:\n"
    "**진단**: (1~2문장, 이 소재의 현재 상태)\n"
    "**근거**: (지표 근거 2~3개, bullet)\n"
    "**액션**: (지금 할 일 2~3개 — ON/OFF/증액/소재변경/타겟조정 등 구체적으로, bullet)\n"
    "추정/일반론 말고 주어진 숫자에 근거해 판단하라. 일별 추세 데이터는 없으니 누적 기준임을 감안하라.\n\n"
    "[소재 데이터]\n{ctx}"
)


def _gemini(prompt: str) -> str:
    import requests
    key = config.GEMINI_API_KEY
    model = config.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 700}}
    r = requests.post(url, params={"key": key}, json=body, timeout=40)
    r.raise_for_status()
    j = r.json()
    return j["candidates"][0]["content"]["parts"][0]["text"].strip()


def _rule_based(r: dict) -> str:
    """키 없을 때 — 우리가 계산한 분류/지표로 만든 휴리스틱 분석."""
    spend = r.get("spend", 0)
    conv = int(r.get("conversions", 0))
    roas = r.get("roas", 0)
    label = r.get("winning_label", "")
    diag, reasons, actions = "", [], []
    if r.get("is_off"):
        diag = "광고비 대비 성과가 나지 않아 **OFF 후보**입니다."
        if conv == 0:
            reasons.append(f"광고비 {int(spend):,}원 사용했지만 구매 0건")
        if roas == 0 and spend > 0:
            reasons.append("ROAS 0 — 전환 기여 없음")
        actions += ["소재를 OFF하거나 카피·후킹을 교체해 재테스트", "랜딩/타겟 적합도 점검"]
    elif label in ("위닝 소재", "위닝 후보"):
        diag = f"구매와 ROAS가 양호한 **{label}**입니다."
        reasons.append(f"구매 {conv}건 · ROAS {roas:.0f}")
        if r.get("ctr", 0):
            reasons.append(f"CTR {r.get('ctr',0)}% — 후킹 반응 확보")
        actions += ["예산 단계적 증액(20~30%)으로 확장 테스트", "유사 컨셉 소재로 변주 제작해 라인업 확대"]
    elif r.get("is_fatigue"):
        diag = "전환은 있으나 ROAS가 평균 대비 낮아 **피로도가 의심**됩니다."
        reasons.append(f"ROAS {roas:.0f} — repurely 평균 미만")
        actions += ["동일 컨셉 신규 소재로 교체(크리에이티브 리프레시)", "프리퀀시·노출 누적 확인 후 타겟 확장"]
    elif r.get("is_new_test"):
        diag = "데이터가 적은 **신규 테스트 소재**입니다."
        reasons.append(f"광고비 {int(spend):,}원 — 판단 표본 부족")
        actions += ["최소 검증 예산까지 노출 확보 후 재평가", "초기 CTR/CPC로 후킹 가능성만 우선 점검"]
    else:
        diag = "안정적으로 **운영 중**인 소재입니다."
        reasons.append(f"구매 {conv}건 · ROAS {roas:.0f} · CTR {r.get('ctr',0)}%")
        actions += ["현 예산 유지하며 추세 모니터링", "ROAS 하락 시 소재 리프레시 검토"]
    out = f"**진단**: {diag}\n\n**근거**:\n" + "\n".join(f"- {x}" for x in reasons)
    out += "\n\n**액션**:\n" + "\n".join(f"- {x}" for x in actions)
    return out


def analyze(r: dict) -> str:
    """소재 1건 분석 → 마크다운 텍스트. 키 있으면 Gemini, 없거나 실패 시 규칙 기반."""
    if enabled():
        try:
            return _gemini(_PROMPT.format(ctx=_ctx(r)))
        except Exception:  # noqa: BLE001
            pass
    return _rule_based(r)
