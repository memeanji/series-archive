"""Google Transparency Center 광고 → 실제 브랜드 매칭.
법인(advertiser/company)과 브랜드를 분리하고, 랜딩URL/문구/제품키워드/브랜드alias 우선순위로 매칭.
법인명만 일치하면 '브랜드 미확정(company_only)'으로 두고 리뷰 영역에서 수동 지정.
"""
from __future__ import annotations

import json


def _loads(v):
    try:
        x = json.loads(v) if v else []
        return x if isinstance(x, list) else []
    except Exception:  # noqa: BLE001
        return []


def build_registry(conn) -> dict:
    """brands → {brand: {aliases:[..lower], keywords:[..], domains:[..], company:str}}.
    company(법인) → [brands] 매핑도 포함(여러 브랜드가 한 법인 공유)."""
    rows = conn.execute(
        "SELECT display_name, search_keywords, official_domain, google_advertiser_name, "
        "brand_aliases, product_keywords, brand_domains FROM brands "
        "WHERE COALESCE(is_active,1)=1").fetchall()
    reg, by_company = {}, {}
    for r in rows:
        b = r["display_name"]
        aliases = {b.lower()} | {a.lower() for a in _loads(r["brand_aliases"]) if a}
        kws = {k.lower() for k in (_loads(r["product_keywords"]) + _loads(r["search_keywords"])) if k}
        domains = set()
        for d in ([r["official_domain"]] + _loads(r["brand_domains"])):
            d = (d or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
            if d:
                domains.add(d)
        company = (r["google_advertiser_name"] or "").strip().lower()
        reg[b] = {"aliases": aliases, "keywords": kws, "domains": domains, "company": company}
        if company:
            by_company.setdefault(company, []).append(b)
    return {"brands": reg, "by_company": by_company}


def load_rules(conn) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT pattern_type, pattern, brand_name FROM brand_match_rules").fetchall()]


def match_ad(ad: dict, registry: dict, rules: list) -> dict:
    """반환 {brand, method, confidence, status}.
    status: confirmed / estimated / company_only / unmatched."""
    landing = " ".join(str(ad.get(k) or "") for k in ("landing_url", "final_url", "media_url")).lower()
    text = " ".join(str(ad.get(k) or "") for k in
                    ("ad_title", "ad_copy", "transparency_url", "original_ad_url")).lower()
    blob = landing + " " + text
    adv = (ad.get("advertiser_name") or "").strip().lower()
    brands = registry["brands"]

    # 0) 학습 규칙(수동 매칭으로 등록된 도메인/키워드) — 최우선 자동매칭
    for rule in rules:
        pat = (rule["pattern"] or "").lower()
        if not pat:
            continue
        hay = landing if rule["pattern_type"] == "domain" else blob
        if pat in hay and rule["brand_name"] in brands:
            return {"brand": rule["brand_name"], "method": "manual", "confidence": "high",
                    "status": "confirmed"}
    # 1) 랜딩/최종 URL 에 브랜드 도메인
    for b, info in brands.items():
        if any(d and d in landing for d in info["domains"]):
            return {"brand": b, "method": "domain", "confidence": "high", "status": "confirmed"}
    # 2) 문구/소재 텍스트에 브랜드명·alias
    for b, info in brands.items():
        if any(a and a in text for a in info["aliases"]):
            return {"brand": b, "method": "brand_text", "confidence": "high", "status": "confirmed"}
    # 3) 제품/라인/키워드
    for b, info in brands.items():
        if any(k and k in blob for k in info["keywords"]):
            return {"brand": b, "method": "product_keyword", "confidence": "medium",
                    "status": "estimated"}
    # 4) 법인(광고주)만 일치 → 브랜드 미확정
    if adv:
        cands = registry["by_company"].get(adv, [])
        if len(cands) == 1:
            # 법인 아래 브랜드가 하나뿐이면 그 브랜드로 확정해도 안전
            return {"brand": cands[0], "method": "company_only", "confidence": "low",
                    "status": "confirmed"}
        if len(cands) >= 2:
            return {"brand": None, "method": "company_only", "confidence": "low",
                    "status": "company_only"}
    return {"brand": None, "method": "unmatched", "confidence": "none", "status": "unmatched"}
