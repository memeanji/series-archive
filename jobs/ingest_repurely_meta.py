"""repurely Meta 소재(Marketing API)를 브랜드 레퍼런스에 적재.
시트 성과와 매칭된 소재의 썸네일을 로컬 저장(만료 방지), 영상은 Facebook permalink를 원본링크로.
사용:  python jobs/ingest_repurely_meta.py
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from repurely import insights as I, meta_api as API  # noqa: E402
from collectors.meta_library_crawler import _save_thumb  # noqa: E402


def main() -> None:
    database.init_db()
    database.add_brand("repurely", ["올레놀샷", "repurely"], extra={"meta_page_name": "Video st"})
    rows = I.load_all()
    meta = [r for r in rows if r.get("platform") == "Meta"
            and (r.get("thumbnail_url") or "").startswith("http")]
    print(f"매칭된 repurely Meta 소재: {len(meta)}건 (영상 {sum(1 for r in meta if r.get('video_id'))})")

    conn = database.get_conn()
    conn.execute("DELETE FROM ad_library_ads WHERE brand_name='repurely' AND platform='meta'")
    conn.commit()
    conn.close()

    ads = []
    for r in meta:
        cname = r.get("creative_name") or ""
        aid = "rep_" + cname
        local = _save_thumb(r["thumbnail_url"], aid) or r["thumbnail_url"]  # 로컬 저장(실패 시 원본URL)
        vid = r.get("video_id") or ""
        perm = API.video_permalink(vid) if vid else ""
        ads.append({
            "platform_ad_id": aid, "brand_name": "repurely", "platform": "meta",
            "ad_title": cname, "ad_copy": r.get("campaign_name", ""),
            "thumbnail_url": local, "video_url": "",
            "original_ad_url": perm,   # 영상 원본(Facebook) — 클릭 시 보기
            "landing_url": r.get("landing", ""),
            "media_type": "video" if vid else "image",
            "status": "live" if r.get("status") == "live" else "ended",
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    saved = database.ingest_ad_library(ads)
    v = sum(1 for a in ads if a["media_type"] == "video")
    print(f"repurely Meta 레퍼런스 적재: {saved}건 (영상 {v} · 이미지 {len(ads)-v})")
    database.migrate_brands()


if __name__ == "__main__":
    main()
