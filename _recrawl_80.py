"""정확히 80개(과거 캡)인 브랜드만 재크롤 — 외국/중복 방지.
 - 중복: 수집한 creative_id가 이미 '다른 브랜드'로 DB에 있으면 skip(덮어쓰기·__꼬리표 방지)
 - 외국: 한글 브랜드명 + region=KR 로 한국 광고주 페이지 진입(영어 검색어 회피)
 - scrolls=5 (이 환경에서 background로 안 죽는 안정선)"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import database  # noqa: E402
from collectors import google_library_crawler as G  # noqa: E402

con = sqlite3.connect(str(ROOT / "data" / "series_archive.db"))
con.row_factory = sqlite3.Row
brands = [r[0] for r in con.execute(
    "SELECT brand_name FROM ad_library_ads WHERE platform='google' AND COALESCE(is_excluded,0)=0 "
    "GROUP BY brand_name HAVING count(*)=80 ORDER BY brand_name").fetchall()]
print(f"재크롤 대상(정확히 80개) {len(brands)}개 브랜드", flush=True)

for i, brand in enumerate(brands):
    try:
        gads, glog = G.search_brand(brand, region="KR", limit=400, scrolls=5, headless=True)
        # 중복 제거: 같은 creative_id가 '다른 브랜드'로 이미 있으면 제외(이 브랜드 것/신규만 통과)
        filt, dup = [], 0
        for a in gads:
            cid = a.get("platform_ad_id") or a.get("id")
            ex = con.execute("SELECT brand_name FROM ad_library_ads WHERE id=?", (cid,)).fetchone()
            if ex and ex["brand_name"] != brand:
                dup += 1
                continue
            filt.append({**a, "brand_name": brand})
        saved = database.ingest_ad_library(filt)
        after = con.execute(
            "SELECT count(*) FROM ad_library_ads WHERE platform='google' AND brand_name=? "
            "AND COALESCE(is_excluded,0)=0", (brand,)).fetchone()[0]
        print(f"[{i+1}/{len(brands)}] {brand}: 발견{glog.get('found')} 중복{dup}제외 저장{saved} → {after}개",
              flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i+1}/{len(brands)}] {brand}: ERR {str(e)[:50]}", flush=True)

con.close()
print("=== 80캡 재크롤 완료 ===", flush=True)
