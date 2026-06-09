"""
YouTube '광고' 매칭 로직 (전체 수집과 분리).
광고 데이터(광고주/법인명·문구·썸네일·랜딩·게재일)로 검색어를 만들고,
YouTube 후보 영상과의 유사도(matching_score)를 계산해 3분류한다.

분류:
  - youtube_ad_matched     : 광고 썸네일/문구/랜딩/브랜드와 '창작물 수준' 연결됨 → 광고로 확정
  - youtube_ad_candidate   : 브랜드는 맞지만 확신 부족(채널·부분유사) → 후보
  - youtube_social_or_ppl  : 제품명/해시태그만 일치(후기·PPL·일반) → 광고 아님

⚠️ 제품명/해시태그만 같다고 광고로 확정하지 않는다.
   광고 썸네일/문구/랜딩 URL/브랜드와 연결될 때만 youtube_ad_matched.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

# 법인 표기 — 브랜드명 후보를 만들 때 제거
_LEGAL = [
    "주식회사", "유한회사", "유한책임회사", "합자회사", "합명회사", "재단법인", "사단법인",
    "㈜", "(주)", "(유)", "주식 회사",
    "inc", "inc.", "co.", "co", "ltd", "ltd.", "corp", "corp.", "corporation",
    "llc", "company", "limited", "co.,ltd", "co., ltd", "co.,ltd.",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _ratio(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def strip_legal(name: str) -> str:
    """'주식회사 천경' → '천경', 'ABC Co., Ltd.' → 'ABC' 처럼 법인 표기 제거."""
    s = (name or "").strip()
    if not s:
        return ""
    # 괄호형 (주)/(유)/㈜ 제거
    s = s.replace("㈜", " ").replace("(주)", " ").replace("(유)", " ")
    low = s.lower()
    # 단어 단위로 법인 토큰 제거(앞/뒤 모두)
    tokens = re.split(r"[\s,]+", s)
    kept = []
    for t in tokens:
        tl = t.lower().strip(".,")
        if tl in _LEGAL or t.lower() in _LEGAL:
            continue
        kept.append(t)
    out = " ".join(kept).strip(" ,.")
    return out or s


def brand_candidates(advertiser: str, display_brand: str = "") -> list[str]:
    """광고주명/디스플레이명에서 브랜드명 후보 생성(법인 표기 제거 버전 우선)."""
    cands = []
    for raw in (display_brand, strip_legal(advertiser), advertiser):
        c = (raw or "").strip()
        if c and c not in cands:
            cands.append(c)
    return cands


# TLD/SLD·서브도메인 토큰(도메인 루트 추출 시 무시) — .co.kr, .com 등 복합 TLD 대응
_TLD_SLD = {"com", "net", "org", "co", "kr", "jp", "cn", "io", "shop", "store",
            "me", "biz", "info", "go", "or", "ne", "ac", "gov", "app", "kkr",
            "www", "m", "shopping", "smartstore"}


def domain_root(url: str) -> str:
    """도메인에서 브랜드 토큰 추출. 'raycelturn.co.kr' → 'raycelturn', 'brand.com' → 'brand'."""
    if not url:
        return ""
    host = (urlparse(url if "//" in url else "//" + url).netloc or "").split(":")[0]
    parts = [p for p in host.split(".") if p]
    meaningful = [p for p in parts if p.lower() not in _TLD_SLD]
    return meaningful[-1] if meaningful else (parts[0] if parts else "")


def build_queries(advertiser: str, display_brand: str = "",
                  ad_copies: list[str] | None = None,
                  landing_urls: list[str] | None = None,
                  max_q: int = 4) -> list[str]:
    """브랜드명 후보 + 상품/랜딩 도메인 + 문구 키워드로 YouTube 검색어 자동 생성."""
    brand = brand_candidates(advertiser, display_brand)[0]
    roots = []
    for u in (landing_urls or []):
        r = domain_root(u)
        if r and r.lower() != brand.lower() and r not in roots:
            roots.append(r)
    queries = [brand, f"{brand} 광고"]
    for r in roots[:1]:
        queries.append(f"{brand} {r}")
    # 광고 문구에서 의미있는 토큰 1개(브랜드와 다른 한글/영문 단어)
    for cp in (ad_copies or []):
        for w in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9]{1,}", cp or ""):
            if len(w) >= 2 and _norm(w) != _norm(brand) and w not in brand:
                queries.append(f"{brand} {w}")
                break
        if len(queries) >= max_q:
            break
    # 중복 제거 + 상한
    seen, out = set(), []
    for q in queries:
        k = _norm(q)
        if k and k not in seen:
            seen.add(k)
            out.append(q)
    return out[:max_q]


def _ahash_image(img) -> int:
    img = img.convert("L").resize((8, 8))
    px = list(img.getdata())
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= (1 << i)
    return bits


def ahash(src: str, root=None) -> int | None:
    """썸네일 average-hash(64bit). http URL·로컬 경로('app/static/...') 모두 지원.
    PIL 없거나 실패하면 None(썸네일 신호 생략)."""
    if not src:
        return None
    try:
        import io
        from pathlib import Path

        from PIL import Image
        if src.startswith("http"):
            import requests
            r = requests.get(src, timeout=15)
            if r.status_code != 200 or not r.content:
                return None
            img = Image.open(io.BytesIO(r.content))
        else:
            p = src[4:] if src.startswith("app/") else src   # 'app/static/..' → 'static/..'
            base = Path(root) if root else Path(".")
            fp = base / p
            if not fp.exists():
                return None
            img = Image.open(fp)
        return _ahash_image(img)
    except Exception:  # noqa: BLE001
        return None


def ahash_url(url: str) -> int | None:
    return ahash(url)


def hash_sim(h1: int | None, h2: int | None) -> float | None:
    """두 aHash의 유사도(0~1). 하나라도 없으면 None."""
    if h1 is None or h2 is None:
        return None
    dist = bin(h1 ^ h2).count("1")
    return 1.0 - dist / 64.0


def score(ctx: dict, video: dict) -> dict:
    """광고 컨텍스트(ctx) ↔ YouTube 후보(video) 유사도.
    ctx: {advertiser, display_brand, copies[], landing_urls[], thumb_hashes[], last_shown}
    video: {title, description, channel_title, thumb_hash, published_at, ...}
    """
    cands = [c for c in brand_candidates(ctx.get("advertiser", ""),
                                         ctx.get("display_brand", "")) if c]
    text = _norm(f"{video.get('title','')} {video.get('description','')}")
    chan = _norm(video.get("channel_title", ""))

    brand_hit = any(_norm(c) and _norm(c) in text for c in cands)
    channel_official = any(_norm(c) and _norm(c) in chan for c in cands)

    title_desc = f"{video.get('title','')} {video.get('description','')}"
    copy_sim = max([_ratio(cp, title_desc) for cp in (ctx.get("copies") or [])] or [0.0])

    desc = _norm(video.get("description", ""))
    roots = [domain_root(u) for u in (ctx.get("landing_urls") or [])]
    landing_hit = any(r and _norm(r) in desc for r in roots)

    sims = [hash_sim(h, video.get("thumb_hash")) for h in (ctx.get("thumb_hashes") or [])]
    sims = [s for s in sims if s is not None]
    thumb_sim = max(sims) if sims else None

    # 게재일 ↔ 업로드일 근접(±60일 내면 보너스)
    date_prox = 0.0
    try:
        from datetime import date
        ls = (ctx.get("last_shown") or "")[:10]
        pu = (video.get("published_at") or "")[:10]
        if ls and pu:
            dl = date.fromisoformat(ls)
            dp = date.fromisoformat(pu)
            if abs((dl - dp).days) <= 60:
                date_prox = 1.0
    except Exception:  # noqa: BLE001
        pass

    ms = (20 * brand_hit + 15 * channel_official + 30 * copy_sim
          + 20 * landing_hit + 15 * (thumb_sim or 0) + 5 * date_prox)
    signals = {
        "brand_hit": bool(brand_hit), "channel_official": bool(channel_official),
        "copy_sim": round(copy_sim, 3), "landing_hit": bool(landing_hit),
        "thumb_sim": round(thumb_sim, 3) if thumb_sim is not None else None,
        "date_prox": bool(date_prox),
    }
    return {"matching_score": round(min(ms, 100.0), 1),
            "classification": classify(signals), "signals": signals}


def classify(sg: dict) -> str:
    """3분류. 광고 확정은 '창작물 수준 연결'(썸네일/문구/랜딩)이 있을 때만."""
    strong = (sg.get("landing_hit")
              or (sg.get("copy_sim") or 0) >= 0.5
              or (sg.get("thumb_sim") is not None and sg["thumb_sim"] >= 0.85))
    medium = (sg.get("channel_official")
              or (sg.get("copy_sim") or 0) >= 0.3
              or (sg.get("thumb_sim") is not None and sg["thumb_sim"] >= 0.7))
    if sg.get("brand_hit") and strong:
        return "youtube_ad_matched"
    if sg.get("brand_hit") and medium:
        return "youtube_ad_candidate"
    return "youtube_social_or_ppl"
