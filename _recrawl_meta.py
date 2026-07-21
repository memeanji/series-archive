"""신규/누락 브랜드 메타(광고 라이브러리) 재서칭 — 브랜드명 키워드 + 중복 skip."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import database  # noqa: E402
from collectors import meta_library_crawler as M  # noqa: E402

MAP = [
    ("미라클시드니", "미라클 시드니"),
    ("소나담", "소나담"),
    ("소다랩", "소다랩"),
    ("겟비너스", "겟비너스"),
    ("노크톤", "노크톤"),
    ("닥터랩젯", "닥터랩젯"),
    ("데이베리어", "데이베리어"),
    ("아치핀", "아치핀"),
    ("이어셀", "이어셀"),
    ("테카라", "테카라"),
    ("퓨드리", "퓨드리"),
    ("하우스윗", "하우스윗"),
    ("라라스윗", "라라스윗"),
]

con = sqlite3.connect(str(ROOT / "data" / "series_archive.db"))
con.row_factory = sqlite3.Row
print(f"메타 재서칭 {len(MAP)}개 브랜드", flush=True)
for i, (brand, kw) in enumerate(MAP):
    try:
        ads = M.search_brand(kw, country="KR", scrolls=5, headless=True)
        filt, dup = [], 0
        for a in ads:
            cid = a.get("platform_ad_id") or a.get("id")
            ex = con.execute("SELECT brand_name FROM ad_library_ads WHERE id=?", (cid,)).fetchone()
            if ex and ex["brand_name"] != brand:
                dup += 1
                continue
            filt.append({**a, "brand_name": brand})
        saved = database.ingest_ad_library(filt)
        print(f"[{i+1}/{len(MAP)}] {brand}({kw}): 수집{len(ads)} 중복{dup}제외 저장{saved}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i+1}/{len(MAP)}] {brand}: ERR {str(e)[:50]}", flush=True)
con.close()
print("=== 메타 재서칭 완료 ===", flush=True)
