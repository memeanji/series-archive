"""더스크랙 우선 재크롤 — 여러 법인명 표기를 순서대로 시도해 광고가 잡히는 표기를 채택."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from collectors import google_library_crawler as G  # noqa: E402

TERMS = ["더스크랙"]   # '더스크랙' 검색 → 자동완성 '주식회사 더스크랙' 광고주 진입

best = None
for term in TERMS:
    try:
        gads, glog = G.search_brand(term, limit=800, scrolls=40, headless=True)
        found = glog.get("found", 0) if isinstance(glog, dict) else 0
        print(f"[term] {term!r} → 발견 {found}", flush=True)
        if found > 0:
            best = (term, gads, glog)
            break
    except Exception as e:  # noqa: BLE001
        print(f"[term] {term!r} ERR {str(e)[:60]}", flush=True)

if best:
    term, gads, glog = best
    gads = [{**a, "brand_name": "더스크랙"} for a in gads]
    saved = database.ingest_ad_library(gads)
    con = sqlite3.connect(str(ROOT / "data" / "series_archive.db"))
    after = con.execute(
        "SELECT count(*) FROM ad_library_ads WHERE platform='google' AND brand_name LIKE '%더스크랙%'"
    ).fetchone()[0]
    con.close()
    print(f"[더스크랙] 채택 term={term!r} 발견 {glog.get('found')} 저장 {saved} → 최종 {after}개", flush=True)
else:
    print("[더스크랙] 모든 표기 0건 — GTC에서 해당 법인명 광고를 못 찾음", flush=True)
print("=== 더스크랙 완료 ===", flush=True)
