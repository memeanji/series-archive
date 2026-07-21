# -*- coding: utf-8 -*-
"""보관정책 정리 — 월 1회 실행. 기본 DRY-RUN(집계만, 삭제 없음).

설계(확정):
  · 광고 만료 기준 = last_seen_at < (오늘-60일)  AND  아래 보존조건에 모두 해당 안 됨
      보존: is_bookmarked / memo / script_text / tags / is_preserved
  · 삭제 순서(참조 무결성): 자식(ad_view_snapshots, ad_social_matches) → 부모(ad_library_ads)
  · 스냅샷 압축: 60일 이내 일별 전량 / 61~180일 (ad,ISO주)당 1건 / 180일↑ (ad,연월)당 1건
  · first_seen_at 은 분석용 표시값이며 삭제 기준에 쓰지 않는다(삭제 기준은 last_seen_at).

안전장치:
  · --apply 경로는 의도적으로 비활성(백업·무결성검증 게이트를 붙인 뒤 별도 승인에서 개방).
  · dry-run 은 SELECT 만 수행(운영 DB 무변경).
  · --measure 는 임시 사본에 실제 삭제+VACUUM 후 파일크기 차이만 측정(원본 불변).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import database  # noqa: E402

# 만료 대상 광고 WHERE (보존 예외 제외). :d60 바인딩 필요.
EXPIRE_WHERE = """
      last_seen_at IS NOT NULL AND last_seen_at != '' AND last_seen_at < :d60
  AND COALESCE(is_bookmarked, 0) = 0
  AND COALESCE(TRIM(memo), '') = ''
  AND COALESCE(TRIM(script_text), '') = ''
  AND COALESCE(TRIM(tags), '[]') IN ('', '[]')
  AND COALESCE(is_preserved, 0) = 0
""".strip()


def _cutoffs(today: dt.date) -> dict:
    return {
        "d60": (today - dt.timedelta(days=60)).isoformat(),
        "d180": (today - dt.timedelta(days=180)).isoformat(),
    }


def _compaction_counts(conn, where: str, fmt: str) -> tuple[int, int]:
    """구간 내 스냅샷 총수 / 압축 후 유지수(=(ad,버킷) 조합 수)."""
    total = conn.execute(f"SELECT COUNT(*) FROM ad_view_snapshots WHERE {where}").fetchone()[0]
    keep = conn.execute(
        f"SELECT COUNT(*) FROM (SELECT ad_id, strftime('{fmt}', snapshot_date) b "
        f"FROM ad_view_snapshots WHERE {where} GROUP BY ad_id, b)"
    ).fetchone()[0]
    return total, keep


def dry_run(measure: bool = False) -> None:
    conn = database.get_conn()
    today = dt.date.today()
    P = _cutoffs(today)
    d60, d180 = P["d60"], P["d180"]

    # ── 만료 광고 + 보존 예외 ──
    n_expire = conn.execute(f"SELECT COUNT(*) FROM ad_library_ads WHERE {EXPIRE_WHERE}", P).fetchone()[0]
    n_keep = conn.execute(
        f"SELECT COUNT(*) FROM ad_library_ads WHERE last_seen_at < :d60 AND NOT ({EXPIRE_WHERE})", P
    ).fetchone()[0]
    snap_child = conn.execute(
        f"SELECT COUNT(*) FROM ad_view_snapshots WHERE ad_id IN (SELECT id FROM ad_library_ads WHERE {EXPIRE_WHERE})", P
    ).fetchone()[0]
    match_child = conn.execute(
        f"SELECT COUNT(*) FROM ad_social_matches WHERE ad_id IN (SELECT id FROM ad_library_ads WHERE {EXPIRE_WHERE})", P
    ).fetchone()[0]

    # ── 스냅샷 압축(만료광고 삭제분과 별개, 남는 스냅샷 대상) ──
    mid_where = f"snapshot_date >= '{d180}' AND snapshot_date < '{d60}'"
    old_where = f"snapshot_date < '{d180}'"
    mid_tot, mid_keep = _compaction_counts(conn, mid_where, "%Y-%W")
    old_tot, old_keep = _compaction_counts(conn, old_where, "%Y-%m")

    print("=" * 60)
    print(f"[RETENTION DRY-RUN] 기준일 {today}  (60일<{d60} / 180일<{d180})")
    print("-" * 60)
    print(f"  만료 광고            : {n_expire:>8,}  (동반 스냅샷 {snap_child:,} · 매칭 {match_child:,})")
    print(f"  보존 예외(60일↑ 제외): {n_keep:>8,}  (북마크/메모/스크립트/태그/is_preserved)")
    print(f"  스냅샷 압축 61~180일 : {mid_tot:>8,} → 주1 유지 {mid_keep:,} (삭제 {mid_tot - mid_keep:,})")
    print(f"  스냅샷 압축 180일↑   : {old_tot:>8,} → 월1 유지 {old_keep:,} (삭제 {old_tot - old_keep:,})")
    conn.close()

    if measure:
        _measure_savings(P)
    print("-" * 60)
    print("  DRY-RUN: 아무것도 삭제하지 않았습니다.")
    print("  실제 삭제/압축(--apply)은 백업·무결성검증 게이트 통과 후에만 개방됩니다.")
    print("=" * 60)


def _measure_savings(P: dict) -> None:
    """임시 사본에 실제 삭제+VACUUM → 파일크기 절감만 측정(원본 불변)."""
    src = str(database.DB_PATH)
    d60, d180 = P["d60"], P["d180"]
    tmp = os.path.join(tempfile.gettempdir(), "retention_measure.db")
    shutil.copy(src, tmp)
    before = os.path.getsize(tmp)
    m = sqlite3.connect(tmp)
    m.execute(f"DELETE FROM ad_view_snapshots WHERE ad_id IN (SELECT id FROM ad_library_ads WHERE {EXPIRE_WHERE})", P)
    m.execute(f"DELETE FROM ad_social_matches WHERE ad_id IN (SELECT id FROM ad_library_ads WHERE {EXPIRE_WHERE})", P)
    m.execute(f"DELETE FROM ad_library_ads WHERE {EXPIRE_WHERE}", P)
    for where, fmt in ((f"snapshot_date >= '{d180}' AND snapshot_date < '{d60}'", "%Y-%W"),
                       (f"snapshot_date < '{d180}'", "%Y-%m")):
        m.execute(
            f"DELETE FROM ad_view_snapshots WHERE {where} AND rowid NOT IN ("
            f"  SELECT rowid FROM (SELECT rowid, ROW_NUMBER() OVER ("
            f"    PARTITION BY ad_id, strftime('{fmt}', snapshot_date) ORDER BY snapshot_date DESC) rn "
            f"  FROM ad_view_snapshots WHERE {where}) WHERE rn = 1)"
        )
    m.commit()
    m.execute("VACUUM")
    m.close()
    after = os.path.getsize(tmp)
    os.remove(tmp)
    print(f"  예상 DB 절감(사본 VACUUM 측정): {before/1024/1024:.1f}MB → {after/1024/1024:.1f}MB "
          f"(절감 {(before-after)/1024/1024:.1f}MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="보관정책 정리(기본 dry-run)")
    ap.add_argument("--apply", action="store_true", help="(미구현) 실제 삭제/압축 — 백업·검증 게이트 필요")
    ap.add_argument("--measure", action="store_true", help="임시 사본으로 예상 DB 절감량 측정(원본 불변)")
    args = ap.parse_args()
    if args.apply:
        raise SystemExit(
            "--apply 는 아직 비활성입니다. 백업 생성 → 무결성 검증(건수·역직렬화) → "
            "승인 절차를 붙인 뒤 개방합니다. 현재는 dry-run(+선택적 --measure)만 지원."
        )
    dry_run(measure=args.measure)


if __name__ == "__main__":
    main()
