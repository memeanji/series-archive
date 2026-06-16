"""광고 ID 단건 즉시 수집 — Meta Ad Library ?id=<ID> 페이지를 크롤해 DB에 적재.
   ID별 성공/실패·사유·page_id 를 구조화해 'RESULT_JSON:' 로 출력(앱이 파싱).
   사용:  python jobs/collect_by_id.py <id1> <id2> ...
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from collectors import meta_library_crawler  # noqa: E402


def main(ids: list) -> None:
    database.init_db()
    ids = [str(i).strip() for i in ids if str(i).strip()]
    before = database.existing_ad_ids(ids)
    results = []
    for aid in ids:
        if aid in before:
            results.append({"id": aid, "ok": True, "reason": "기존 보유", "is_new": False,
                            "advertiser": "", "page_id": ""})
            continue
        try:
            ads = meta_library_crawler.search_brand("", ad_id=aid, retries=2)
        except Exception as e:  # noqa: BLE001
            results.append({"id": aid, "ok": False, "reason": f"네트워크/크롤 오류: {str(e)[:60]}",
                            "is_new": False, "advertiser": "", "page_id": ""})
            continue
        if not ads:
            results.append({"id": aid, "ok": False,
                            "reason": "원본 접근 불가(만료·비공개·삭제 또는 권한 필요)",
                            "is_new": False, "advertiser": "", "page_id": ""})
            continue
        adv = (ads[0].get("headline") or ads[0].get("advertiser_name") or "(ID수집)").strip() or "(ID수집)"
        for a in ads:   # ?id= 는 광고주의 광고 여러 건을 반환 → 모두 같은 광고주명으로
            a["brand_name"] = a.get("brand_name") or adv
        database.ingest_ad_library(ads)
        got = {str(a.get("platform_ad_id")) for a in ads}
        hit = aid in got
        results.append({"id": aid, "ok": hit, "is_new": hit,
                        "reason": "신규 수집" if hit else "광고주 광고는 받았으나 해당 ID 미확인(만료/비공개 가능)",
                        "advertiser": adv, "page_id": ads[0].get("page_id") or "",
                        "media": ads[0].get("media_type") or ""})
    if any(r["is_new"] for r in results):
        database.compute_matches()
        database.regrade()
        database.migrate_brands()
    print("RESULT_JSON:" + json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python jobs/collect_by_id.py <id> [<id> ...]")
        sys.exit(1)
    main(sys.argv[1:])
