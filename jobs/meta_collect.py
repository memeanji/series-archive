"""Meta 수집 오케스트레이션 — page_id 우선, 없으면 키워드+page_id 후보 추출.
   사용:  python jobs/meta_collect.py "세라블랑"          (해당 브랜드 수집)
          python jobs/meta_collect.py "세라블랑" --keyword (page_id 있어도 키워드로)
"""
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from collectors import meta_library_crawler  # noqa: E402


def collect_meta(display: str, force_keyword: bool = False) -> dict:
    """단일 브랜드 Meta 수집. 반환: {method,found,new,updated,page_id,status}."""
    run_start = datetime.now(timezone.utc).isoformat()
    b = database.get_brand(display) or {}
    bid = b.get("id") or 0
    pid = (b.get("meta_page_id") or "").strip()
    use_pid = bool(pid) and not force_keyword
    method = "page_id" if use_pid else "keyword"

    ads: list = []
    if use_pid:
        ads = meta_library_crawler.search_brand("", page_id=pid)
    else:
        for kw in (database.get_brand_keywords(display) or [display]):
            try:
                ads += meta_library_crawler.search_brand(kw)
            except Exception as e:  # noqa: BLE001
                print(f"  [meta] '{kw}' 실패: {str(e)[:90]}", flush=True)
        # page_id 후보 추출(카드에서 가장 흔한 값) → 저장(candidate)
        cands = Counter(a.get("page_id") for a in ads if (a.get("page_id") or "").strip())
        if cands and not pid:
            cand = cands.most_common(1)[0][0]
            database.set_brand_page_id(display, cand, "candidate")
            print(f"  [meta] page_id 후보 추출: {cand} (다음부터 page_id 수집 가능)", flush=True)

    for a in ads:
        a["brand_name"] = display
    ids = list(dict.fromkeys(a.get("platform_ad_id") for a in ads if a.get("platform_ad_id")))
    before = database.existing_ad_ids(ids)
    database.ingest_ad_library(ads)
    new = sum(1 for i in ids if i not in before)
    updated = len(ids) - new

    database.log_brand_collection(bid, "meta", method, "success", len(ids), new, updated, started=run_start)
    database.compute_matches()
    database.regrade()
    database.migrate_brands()
    database.finalize_meta_video_status(run_start, brands=[display])
    st = database.brand_collection_status(display)
    res = {"brand": display, "method": method, "found": len(ids),
           "new": new, "updated": updated, "page_id": st["page_id"], "status": st["status"]}
    print(f"  [meta] {display}: {method} · 발견 {len(ids)} · 신규 {new} · 갱신 {updated} · 상태 {st['status']}",
          flush=True)
    return res


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_kw = "--keyword" in sys.argv
    if not args:
        print("usage: python jobs/meta_collect.py <브랜드> [--keyword]")
        sys.exit(1)
    database.init_db()
    collect_meta(args[0], force_keyword=force_kw)


if __name__ == "__main__":
    main()
