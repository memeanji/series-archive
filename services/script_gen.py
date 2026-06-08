"""
광고 영상 스크립트 생성 — 버튼 클릭 시에만 실행.
우선순위: ① YouTube 자막 → ② Gemini 영상 분석(YouTube) → ③ Gemini 추정(카피 기반).
결과는 ad_library_ads.script_* 에 저장되어 재호출 안 함('재생성' 시에만 다시).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import services.youtube as YT  # noqa: E402

PROMPT = """너는 퍼포먼스 마케팅 광고 분석가다.
아래 영상/광고 정보를 바탕으로 광고 스크립트를 한국어로 정리해줘.

반드시 아래 형식으로 출력해줘.

[영상 스크립트]
- 영상에서 들리는 말 또는 화면 자막을 최대한 실제 순서대로 정리
- 화자 멘트와 화면 자막을 구분하지 않아도 됨
- 광고 흐름이 보이도록 자연스럽게 문단화

[광고 구조]
1. 후킹:
2. 문제 제기:
3. 제품/혜택 제시:
4. 신뢰 요소:
5. CTA:

[핵심 소구]
- 이 광고가 강조하는 소비자 pain point
- 이 광고가 사용하는 후킹 방식
- 구매를 유도하는 주요 문장

주의:
- 영상에 없는 내용을 과하게 만들어내지 말 것
- 영상 확인이 불완전하면 "추정"이라고 표시할 것
- 광고 카피와 영상 내용이 다르면 둘을 구분해서 적을 것
"""


def _ctx(ad: dict) -> str:
    return (f"\n\n[참고 광고 정보]\n브랜드: {ad.get('brand_name','')}\n"
            f"광고 카피:\n{ad.get('ad_copy','') or '(없음)'}\nCTA: {ad.get('cta','') or '-'}")


def _gemini(parts: list) -> str:
    import requests
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}")
    try:
        r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=150)
        j = r.json()
        if "error" in j:
            return ""
        return " ".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"]).strip()
    except Exception:  # noqa: BLE001
        return ""


def generate(ad: dict) -> dict:
    """반환 {text, source, status, error}."""
    vid = (YT.extract_video_id(ad.get("social_source_url") or "")
           or YT.extract_video_id(ad.get("video_url") or ""))

    # ① YouTube 자막
    if vid:
        tr = YT.fetch_transcript(vid)
        if tr:
            return {"text": tr, "source": "youtube_transcript", "status": "completed", "error": ""}

    if not config.GEMINI_API_KEY:
        return {"text": "", "source": "manual", "status": "failed",
                "error": "자막 없음 + GEMINI_API_KEY 미설정"}

    # ② Gemini 영상 분석(YouTube URL 직접)
    if vid:
        g = _gemini([{"file_data": {"file_uri": YT.watch_url(vid)}}, {"text": PROMPT + _ctx(ad)}])
        if g:
            return {"text": g, "source": "gemini", "status": "completed", "error": ""}

    # ③ Gemini 추정(영상 접근 불가 — fbcdn/구글 등 → 카피 기반 추정)
    est = _gemini([{"text": PROMPT + "\n\n※ 영상 직접 확인 불가 → 아래 정보 기반 '추정' 스크립트."
                    + _ctx(ad)}])
    if est:
        return {"text": est, "source": "gemini_estimated", "status": "completed", "error": ""}
    return {"text": "", "source": "gemini", "status": "failed", "error": "Gemini 응답 없음/오류"}
