"""
메타로 '브랜드명 → 남의 광고' 수집이 되는지 점검 — 읽기 전용 probe.
meta-cafe24-dashboard 의 토큰으로 Ad Library(ads_archive) 를 호출해 결과를 그대로 출력.
사용: python probe_meta_ref.py "브랜드명"
"""
import json
import sys

import requests

import config  # noqa: E402
TOKEN = config.META_ACCESS_TOKEN   # .env / secrets 에서 로드(하드코딩 금지)
VER = "v21.0"
BRAND = sys.argv[1] if len(sys.argv) > 1 else "글로우"


def call(label, params):
    params["access_token"] = TOKEN
    r = requests.get(f"https://graph.facebook.com/{VER}/ads_archive", params=params, timeout=60)
    try:
        j = r.json()
    except Exception:
        print(f"\n### {label}\n  HTTP {r.status_code} (JSON아님) {r.text[:200]}")
        return
    if "error" in j:
        e = j["error"]
        print(f"\n### {label}\n  HTTP {r.status_code}  ERROR code={e.get('code')} "
              f"msg={e.get('message')}")
        return
    data = j.get("data", [])
    print(f"\n### {label}\n  HTTP {r.status_code}  결과 {len(data)}건")
    for ad in data[:3]:
        print("   -", str(ad.get("ad_creative_bodies") or ad.get("page_name") or ad)[:120])


print("=" * 64)
print(f"브랜드='{BRAND}'  token=...{TOKEN[-6:]}")
print("=" * 64)

FIELDS = "id,page_name,ad_creative_bodies,ad_delivery_start_time,ad_snapshot_url"

# A) 한국 + 전체 광고(ALL) — 상업 광고 검색 시도
call("A) country=KR, ad_type=ALL", {
    "search_terms": BRAND, "ad_reached_countries": '["KR"]',
    "ad_type": "ALL", "fields": FIELDS, "limit": 5,
})

# B) 한국 + 정치/이슈 광고만(비EU 기본 허용 범위)
call("B) country=KR, ad_type=POLITICAL_AND_ISSUE_ADS", {
    "search_terms": BRAND, "ad_reached_countries": '["KR"]',
    "ad_type": "POLITICAL_AND_ISSUE_ADS", "fields": FIELDS, "limit": 5,
})

# C) EU(독일) + 전체 — DSA로 상업광고도 열려있는 지역(가능성 확인용)
call("C) country=DE, ad_type=ALL", {
    "search_terms": BRAND, "ad_reached_countries": '["DE"]',
    "ad_type": "ALL", "fields": FIELDS, "limit": 5,
})

print("\n" + "=" * 64)
print("판정: A) 결과>0 → 한국 상업광고 브랜드검색 가능(최상). "
      "A) 오류/0 & C) 결과>0 → API는 되나 한국 상업광고는 비공개(EU만).")
print("=" * 64)
