"""ID로 구글/메타 광고를 직접 수집(자동완성 검색이 안 되는 브랜드용).

사용:
  python _crawl_by_id.py google <advertiser_id> <브랜드명>
  python _crawl_by_id.py meta   <page_id>       <브랜드명>

ID 찾는 법:
  - 구글: 투명성센터에서 광고주 클릭 → 주소창 .../advertiser/<여기 ID>
  - 메타: 광고 라이브러리에서 페이지 → URL view_all_page_id=<여기 ID>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import database  # noqa: E402

plat = sys.argv[1] if len(sys.argv) > 1 else ""
the_id = sys.argv[2] if len(sys.argv) > 2 else ""
brand = sys.argv[3] if len(sys.argv) > 3 else "(ID수집)"

if plat == "google" and the_id:
    from collectors import google_library_crawler as G
    gads, glog = G.search_brand(brand, region="KR", advertiser_id=the_id,
                                scrolls=20, limit=800, headless=True)
    gads = [{**a, "brand_name": brand} for a in gads]
    saved = database.ingest_ad_library(gads)
    print(f"[구글 advertiser {the_id}] {brand}: 발견 {glog.get('found')} 저장 {saved}", flush=True)

elif plat == "meta" and the_id:
    from collectors import meta_library_crawler as M
    ads = M.search_brand(brand, country="KR", page_id=the_id, scrolls=20, headless=True)
    ads = [{**a, "brand_name": brand, "platform": "meta"} for a in ads]
    saved = database.ingest_ad_library(ads)
    print(f"[메타 page {the_id}] {brand}: 수집 {len(ads)} 저장 {saved}", flush=True)

else:
    print("사용: python _crawl_by_id.py google|meta <ID> <브랜드명>", flush=True)

print("=== 완료 ===", flush=True)
