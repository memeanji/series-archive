"""
틱톡으로 '브랜드명 → 남의 인기 광고 영상' 수집이 실제로 가능한지 점검 — 읽기 전용 probe.
현재 .env 의 Marketing API 토큰으로 후보 엔드포인트들을 호출해 code/message 를 그대로 출력한다.
아무것도 생성하지 않는다. 브랜드명은 인자로: python probe_tiktok_ref.py "브랜드명"
"""
import json
import sys

import requests

import config

BRAND = sys.argv[1] if len(sys.argv) > 1 else "글로우"
TOKEN = config.TIKTOK_ACCESS_TOKEN
ADV = config.TIKTOK_ADVERTISER_ID


def show(label, r):
    try:
        j = r.json()
    except Exception:
        print(f"\n### {label}\n  HTTP {r.status_code}  (JSON 아님) {r.text[:200]}")
        return None
    code = j.get("code", j.get("error", {}).get("code") if isinstance(j.get("error"), dict) else j.get("error"))
    msg = j.get("message") or (j.get("error", {}).get("message") if isinstance(j.get("error"), dict) else "")
    print(f"\n### {label}\n  HTTP {r.status_code}  code={code}  msg={msg}")
    s = json.dumps(j, ensure_ascii=False)
    print("  data:", s[:500] + (" …" if len(s) > 500 else ""))
    return j


print("=" * 64)
print(f"브랜드='{BRAND}'  token=...{TOKEN[-6:]}  advertiser={ADV}")
print("=" * 64)

# A) Commercial Content API (research/adlib) — '남의 공개광고' 정식 경로(승인/지역 제한)
try:
    r = requests.post(
        "https://open.tiktokapis.com/v2/research/adlib/ad/query/",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={"filters": {"ad_published_date_range": {"min": "20240101", "max": "20261231"},
                          "country_code": "KR", "search_term": BRAND}, "max_count": 10},
        timeout=60,
    )
    show("A) Commercial Content API /v2/research/adlib/ad/query/", r)
except Exception as e:
    print(f"\n### A) 호출예외: {e}")

# B) Marketing API — 내 계정 소재(남의 브랜드 아님, 권한 확인용 baseline)
try:
    r = requests.get(
        f"{config.TIKTOK_API_BASE}/file/ad/info/",
        headers={"Access-Token": TOKEN},
        params={"advertiser_id": ADV, "page": 1, "page_size": 5},
        timeout=60,
    )
    show("B) Marketing API /file/ad/info/ (내 계정 baseline)", r)
except Exception as e:
    print(f"\n### B) 호출예외: {e}")

# C) Creative Center 'Top Ads' 류 — 키워드로 인기광고(비공식, 별도 인증 필요할 수 있음)
try:
    r = requests.get(
        "https://business-api.tiktok.com/open_api/v1.3/creative/portfolio/list/",
        headers={"Access-Token": TOKEN},
        params={"advertiser_id": ADV, "page": 1, "page_size": 5},
        timeout=60,
    )
    show("C) Marketing API creative/portfolio (참고)", r)
except Exception as e:
    print(f"\n### C) 호출예외: {e}")

print("\n" + "=" * 64)
print("판정: A) code=0 이고 data에 ad 목록 → 브랜드 검색 수집 가능.")
print("      A) 권한/지역 오류 → 이 토큰으론 남의 광고 검색 불가 → Creative Center/Apify 경로 필요.")
print("=" * 64)
