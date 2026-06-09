"""
3일 주기 자동 수집 파이프라인 (Windows 작업 스케줄러가 호출).
[모든 브랜드 메타+구글 크롤 → 매칭/재등급 → demo.db 갱신 → git 커밋·푸시(Cloud 반영)]
스크립트 결과는 영구저장(Supabase)에도 자동 백업됨.
사용:  python jobs/scheduled_update.py
"""
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database  # noqa: E402
from jobs.crawl_brand import crawl_one  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] {msg}", flush=True)


def main() -> None:
    database.init_db()
    conn = database.get_conn()
    brands = [r[0] for r in conn.execute(
        "SELECT display_name FROM brands WHERE COALESCE(is_active,1)=1 ORDER BY display_name").fetchall()]
    conn.close()
    _log(f"=== 3일 주기 수집 시작: {len(brands)}개 브랜드 ===")
    total = 0
    for i, b in enumerate(brands, 1):
        try:
            r = crawl_one(b)
            total += r["ad"]
            _log(f"[{i}/{len(brands)}] {b}: 광고 {r['ad']} · 소셜 {r['social']}")
        except Exception as e:  # noqa: BLE001
            _log(f"[{i}/{len(brands)}] {b}: 실패 {str(e)[:80]}")
    database.compute_matches()
    database.regrade()
    database.migrate_brands()
    _log(f"크롤 완료 · 누적 적재 {total}")

    # demo.db 갱신(계정 제거 + VACUUM)
    try:
        shutil.copy(ROOT / "data" / "series_archive.db", ROOT / "sample_data" / "demo.db")
        con = sqlite3.connect(ROOT / "sample_data" / "demo.db")
        con.isolation_level = None
        con.execute("DELETE FROM users")
        con.execute("VACUUM")
        con.close()
        _log("demo.db 갱신 완료")
    except Exception as e:  # noqa: BLE001
        _log(f"demo.db 갱신 실패: {e}")

    # git 커밋·푸시(Cloud 자동 반영)
    msg = f"auto: 3일 주기 수집 갱신 {datetime.now():%Y-%m-%d}"
    for cmd in (["git", "add", "sample_data/demo.db"],
                ["git", "commit", "-m", msg],
                ["git", "push", "origin", "main"]):
        try:
            subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        except Exception as e:  # noqa: BLE001
            _log(f"git 실패({cmd[1]}): {e}")
    _log("=== 완료(배포 푸시) ===")


if __name__ == "__main__":
    main()
