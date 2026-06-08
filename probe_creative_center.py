"""
TikTok Creative Center(Top Ads) 비공식 API 로 '브랜드 키워드 → 한국 인기광고'가
토큰 없이 실제로 긁히는지 점검 — 읽기 전용 probe.
사용: python probe_creative_center.py "키워드"
"""
import json
import sys

import requests

KW = sys.argv[1] if len(sys.argv) > 1 else "글로우"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def call(label, url, params, headers):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=40)
    except Exception as e:
        print(f"\n### {label}\n  호출예외: {e}")
        return
    try:
        j = r.json()
    except Exception:
        print(f"\n### {label}\n  HTTP {r.status_code} (JSON아님) {r.text[:160]}")
        return
    code = j.get("code")
    msg = j.get("msg") or j.get("message")
    data = j.get("data") or {}
    items = data.get("materials") or data.get("list") or data.get("ads") or []
    print(f"\n### {label}\n  HTTP {r.status_code}  code={code}  msg={msg}  items={len(items)}")
    s = json.dumps(j, ensure_ascii=False)
    print("  raw:", s[:300] + (" …" if len(s) > 300 else ""))


print("=" * 64)
print(f"키워드='{KW}'  (TikTok Creative Center / 토큰 불필요 경로 시도)")
print("=" * 64)

# 1) anonymous token 발급 시도
tok = None
try:
    r = requests.get("https://ads.tiktok.com/creative_radar_api/v1/anchor/anonymous_token",
                     headers={"User-Agent": UA}, timeout=30)
    tok = (r.json().get("data") or {}).get("token")
    print(f"\n[anonymous_token] HTTP {r.status_code}  token={'있음' if tok else '없음'}")
except Exception as e:
    print(f"\n[anonymous_token] 예외: {e}")

H = {"User-Agent": UA, "Accept": "application/json"}
if tok:
    H["anonymous-user-id"] = tok

# 2) Top Ads 목록 (키워드 검색)
call("Top Ads list (keyword=KR)",
     "https://ads.tiktok.com/creative_radar_api/v1/top_ads/v2/list",
     {"period": 30, "page": 1, "limit": 10, "order_by": "ctr",
      "country_code": "KR", "keyword": KW}, H)

# 3) Top Ads 목록 (서명 없이 기본)
call("Top Ads list (no keyword)",
     "https://ads.tiktok.com/creative_radar_api/v1/top_ads/v2/list",
     {"period": 7, "page": 1, "limit": 5, "country_code": "KR"}, H)

print("\n" + "=" * 64)
print("판정: code=0 & items>0 → 토큰없이 실수집 가능(이 경로로 붙이면 됨).")
print("      code!=0(예: 40101/서명오류) → 서명/쿠키 필요 → Apify 등 우회 권장.")
print("=" * 64)
