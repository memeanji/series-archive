"""URL 정규화/검증 — Google 투명성센터 상대경로·localhost 오류 방지."""
from __future__ import annotations

from typing import Optional

GOOGLE_TC = "https://adstransparency.google.com"
_BAD = ("localhost", "127.0.0.1", "streamlit")


def is_valid_external_url(url: Optional[str]) -> bool:
    if not url:
        return False
    u = url.strip().lower()
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    return not any(b in u for b in _BAD)


def normalize_google_transparency_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    u = url.strip()
    low = u.lower()
    # 잘못 저장된 localhost/streamlit 경로 → 뒤의 /advertiser... 만 살려 도메인 교체
    if any(b in low for b in _BAD):
        idx = u.find("/advertiser/")
        if idx != -1:
            return GOOGLE_TC + u[idx:]
        return None
    if low.startswith("http://") or low.startswith("https://"):
        return u
    if u.startswith("/advertiser/"):
        return GOOGLE_TC + u
    if u.startswith("advertiser/"):
        return GOOGLE_TC + "/" + u
    return None
