"""신규/누락 브랜드 구글 재서칭 — 사용자 제공 검색어(법인명/브랜드명) 기준.
 중복 skip 내장(이미 다른 브랜드로 있는 creative_id 제외 → 공유법인·테키라 중복 자동 방지)."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import database  # noqa: E402
from collectors import google_library_crawler as G  # noqa: E402

MAP = [
    ("미라클시드니", "미라클 시드니"),
    ("소나담", "주식회사 베그리프"),
    ("소다랩", "주식회사 베그리프"),
    ("겟비너스", "겟비너스"),
    ("노크톤", "주식회사 베그리프"),
    ("닥터랩젯", "닥터랩젯"),
    ("데이베리어", "데이베리어"),
    ("아치핀", "주식회사 데이즈"),
    ("이어셀", "Baseglow Inc."),
    ("테카라", "ascentone"),
    ("퓨드리", "퓨드리"),
    ("하우스윗", "(주)이삼오구"),
    ("라라스윗", "(주)라라스윗"),
]

con = sqlite3.connect(str(ROOT / "data" / "series_archive.db"))
con.row_factory = sqlite3.Row
print(f"구글 재서칭 {len(MAP)}개 브랜드", flush=True)
for i, (brand, term) in enumerate(MAP):
    try:
        gads, glog = G.search_brand(term, region="KR", limit=400, scrolls=5, headless=True)
        filt, dup = [], 0
        for a in gads:
            cid = a.get("platform_ad_id") or a.get("id")
            ex = con.execute("SELECT brand_name FROM ad_library_ads WHERE id=?", (cid,)).fetchone()
            if ex and ex["brand_name"] != brand:
                dup += 1
                continue
            filt.append({**a, "brand_name": brand})
        saved = database.ingest_ad_library(filt)
        print(f"[{i+1}/{len(MAP)}] {brand}({term}): 발견{glog.get('found')} 중복{dup}제외 저장{saved}",
              flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i+1}/{len(MAP)}] {brand}: ERR {str(e)[:50]}", flush=True)
con.close()
print("=== 구글 재서칭 완료 ===", flush=True)
