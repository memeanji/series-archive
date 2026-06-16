"""광고 ID 단건 즉시 수집 — Meta Ad Library ?id=<ID> 페이지를 크롤해 DB에 적재.
   ID 검색에서 '미수집'으로 나온 공유 광고를 바로 가져올 때 사용.
   사용:  python jobs/collect_by_id.py <id1> <id2> ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from collectors import meta_library_crawler  # noqa: E402


def main(ids: list) -> None:
    database.init_db()
    ids = [str(i).strip() for i in ids if str(i).strip()]
    print(f"=== ID 단건 수집: {len(ids)}개 ===", flush=True)
    total = 0
    for aid in ids:
        try:
            ads = meta_library_crawler.search_brand("", ad_id=aid, scrolls=2, retries=2)
            # 브랜드명이 비면 '(ID수집)'로 — 이후 재크롤/수동분류로 정정 가능
            for a in ads:
                a.setdefault("brand_name", a.get("advertiser_name") or "(ID수집)")
            saved = database.ingest_ad_library(ads)
            total += saved
            print(f"  {aid}: 발견 {len(ads)} 저장 {saved}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {aid}: 실패 {str(e)[:90]}", flush=True)
    if total:
        database.compute_matches()
        database.regrade()
        database.migrate_brands()
    print(f"=== 완료: {total}개 적재 ===", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python jobs/collect_by_id.py <id> [<id> ...]")
        sys.exit(1)
    main(sys.argv[1:])
