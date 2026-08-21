"""브랜드 1개만 즉시 수집 — 요일 스케줄을 기다리지 않고 지금 돌릴 때 사용.
   메타(daily_group_update)와 구글(google_group_update)의 브랜드 1건 수집 로직을 그대로 재사용하고,
   상태확정 → 매칭/재등급 → Supabase 동기화(배포본 반영) → demo.db 까지 같은 순서로 수행한다.
   사용:  python jobs/collect_one_brand.py 디라셀            (메타+구글)
          python jobs/collect_one_brand.py 디라셀 --meta-only
          python jobs/collect_one_brand.py 디라셀 --google-only
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from jobs.daily_group_update import _collect_one as _meta_one  # noqa: E402
from jobs.google_group_update import _collect_one as _google_one  # noqa: E402


def _log(m: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)


def main(brand: str, do_meta: bool = True, do_google: bool = True) -> None:
    database.init_db()
    run_start = datetime.now(timezone.utc).isoformat()
    if not database.get_brand(brand):
        _log(f"브랜드 '{brand}' 가 brands 테이블에 없습니다 — 중단")
        return
    _log(f"=== 단일 브랜드 수집 시작: {brand} ===")

    tot_new = tot_upd = 0
    if do_meta:
        try:
            r = _meta_one(brand, run_start)
            tot_new += r["new"]; tot_upd += r["updated"]
            _log(f"[메타] {r['method']} 발견 {r['found']} 신규 {r['new']} 갱신 {r['updated']}")
        except Exception as e:  # noqa: BLE001
            _log(f"[메타] 실패 {type(e).__name__}: {str(e)[:120]}")
    if do_google:
        try:
            r = _google_one(brand, run_start)
            tot_new += r["new"]; tot_upd += r["updated"]
            _log(f"[구글] '{r['term']}' 발견 {r['found']} 신규 {r['new']} 갱신 {r['updated']}")
        except Exception as e:  # noqa: BLE001
            _log(f"[구글] 실패 {type(e).__name__}: {str(e)[:120]}")

    vs = {}
    if do_meta:
        try:
            vs = database.finalize_meta_video_status(run_start, brands=[brand])
        except Exception as e:  # noqa: BLE001
            _log(f"상태확정 실패: {e}")
    database.compute_matches()
    database.regrade()
    database.migrate_brands()

    try:
        import jobs.supabase_sync_new as SN
        SN.run(apply=True)
    except Exception as e:  # noqa: BLE001
        _log(f"Supabase 동기화 실패: {type(e).__name__}: {e}")

    try:
        database.regenerate_demo_db()
    except Exception as e:  # noqa: BLE001
        _log(f"demo.db 실패: {e}")

    gone = (vs.get("private_or_deleted", 0) + vs.get("expired_url", 0))
    _log(f"=== 완료: {brand} · 신규 {tot_new} · 갱신 {tot_upd} · 만료/비공개 {gone} ===")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("사용: python jobs/collect_one_brand.py <브랜드명> [--meta-only|--google-only]")
        sys.exit(1)
    main(args[0],
         do_meta="--google-only" not in sys.argv,
         do_google="--meta-only" not in sys.argv)
