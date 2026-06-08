"""
브랜드 1건 수집 → SQLite.  (UI '수집 실행'이 subprocess 로 호출)
사용:  python jobs/crawl_brand.py "디스플레이명"
brands.search_keywords 를 순회해 메타/구글(+YouTube) 수집, brand_name 은 디스플레이명으로 통일,
brand_collection_logs 기록, ingest 가 id 기준 dedupe.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from collectors import google_library_crawler, meta_library_crawler  # noqa: E402

GOOGLE_LIMIT = 30


def _now():
    return datetime.now(timezone.utc).isoformat()


def _brand_id(display: str) -> int:
    conn = database.get_conn()
    r = conn.execute("SELECT id FROM brands WHERE display_name=?", (display,)).fetchone()
    conn.close()
    return r[0] if r else 0


def crawl_one(display: str) -> dict:
    res = {"ad": 0, "social": 0}
    bid = _brand_id(display)
    keywords = database.get_brand_keywords(display) if database.brand_exists(display) else [display]

    # 구글 광고주명(법인명) — 있으면 구글은 이걸로 검색
    brand = database.get_brand(display) or {}
    google_term = (brand.get("google_advertiser_name") or "").strip() or display

    # 메타: 키워드(브랜드명)로 검색 — 브랜드명이 잘 잡힘
    for kw in keywords:
        t0 = _now()
        try:
            ads = [{**a, "brand_name": display} for a in meta_library_crawler.search_brand(kw)]
            saved = database.ingest_ad_library(ads)
            database.log_brand_collection(bid, "meta", kw, "success", len(ads), saved,
                                          len(ads) - saved, started=t0)
            res["ad"] += saved
            print(f"  [meta]   '{kw}' 발견 {len(ads)} 저장 {saved}")
        except Exception as e:  # noqa: BLE001
            database.log_brand_collection(bid, "meta", kw, "error", error=str(e)[:200], started=t0)
            print(f"  [meta]   '{kw}' 실패: {e}")

    # 구글: 법인명(google_advertiser_name)으로 1회 검색
    t0 = _now()
    try:
        gads, glog = google_library_crawler.search_brand(google_term, limit=GOOGLE_LIMIT)
        gads = [{**a, "brand_name": display} for a in gads]
        saved = database.ingest_ad_library(gads)
        database.log_brand_collection(bid, "google", google_term, "success", glog["found"], saved,
                                      glog["found"] - saved, started=t0)
        res["ad"] += saved
        print(f"  [google] '{google_term}' 발견 {glog['found']} 저장 {saved}")
    except Exception as e:  # noqa: BLE001
        database.log_brand_collection(bid, "google", google_term, "error", error=str(e)[:200], started=t0)
        print(f"  [google] '{google_term}' 실패: {e}")

    # YouTube (디스플레이명 1회, quota 절약)
    try:
        import services.youtube as YT
        if YT.is_enabled():
            t0 = _now()
            ids = YT.search_video_ids(display, max_results=5)
            vids = [{**v, "brand_name": display} for v in YT.fetch_videos(ids)]
            saved = database.ingest_social_videos(vids)
            for v in vids:
                database.add_snapshot(v["id"], v["views"], v["likes"], v["comments"], v["shares"])
            database.log_brand_collection(bid, "youtube", display, "success", len(vids), saved,
                                          0, started=t0)
            res["social"] += saved
            print(f"  [youtube] '{display}' 저장 {saved}")
    except Exception as e:  # noqa: BLE001
        print(f"  [youtube] 실패: {e}")

    return res


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python jobs/crawl_brand.py <디스플레이명>")
        sys.exit(1)
    display = sys.argv[1]
    database.init_db()
    print(f"=== '{display}' 수집 시작 ===")
    r = crawl_one(display)
    m = database.compute_matches()
    g = database.regrade()
    database.migrate_brands()  # 새 brand_name → brand_id 연결
    print(f"=== 완료: 광고 {r['ad']} · 소셜 {r['social']} · 매칭 {m} · 재등급 {g} ===")
