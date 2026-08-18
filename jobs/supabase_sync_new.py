# -*- coding: utf-8 -*-
"""크롤 직후 **신규분만** Supabase로 올린다(멱등).

무엇을 올리나
  · 신규 광고      : 로컬에는 있는데 Supabase에 없는 광고(오염 차단 규칙·제외 표시분은 뺀다)
  · 신규 브랜드    : brands 테이블에 새로 생긴 행
  · 신규 썸네일    : 그 광고들이 참조하는 파일 중 **Storage에 아직 없는 것만**
  · 딸린 데이터    : 그 광고의 영상 매칭 + 조회수 스냅샷

  · 기존 광고 갱신 : 재크롤로 **값이 바뀐 기존 광고**의 타임스탬프·상태를 PATCH(아래 참조)

무엇을 안 하나
  · 전체 재업로드(이미 올라간 광고·썸네일은 건너뛴다)
  · git 커밋/푸시(이 잡은 git을 전혀 건드리지 않는다)
  · 기존 행의 INSERT/DELETE — 갱신은 **PATCH(UPDATE) 전용**이라 행 수·id 고유성이 변하지 않는다

★ 기존 광고 갱신이 왜 필요한가(2026-08-18 추가)
  이 잡은 원래 "Supabase 에 없는 광고"만 올렸다. 그런데 `database.ingest_ad_library` 는 재크롤 때마다
  기존 행의 `collected_at` / `last_crawled_at` 을 현재 시각으로 갱신한다(INSERT OR REPLACE).
  그 갱신분이 Supabase 로 가지 않아 **클라우드 앱의 '수집일'이 최초 업로드 시점에 얼어붙는** 문제가 있었다
  (실측: 로컬 08-17 인 광고가 앱에서는 08-10 으로 보임 · 대상 8,172건).
  `last_seen_at` 은 `jobs/sync_views_to_supabase.py` 가 이미 동기화하고 있었으나 나머지는 누락이었다.

  값 역행 방지: 로컬 `collected_at` 이 Supabase 보다 **오래된** 행은 건드리지 않는다.

업서트는 `jobs/supabase_migrate.py` 의 기존 로직을 그대로 재사용하므로 몇 번 돌려도 중복이 안 생긴다.

사용:
  python jobs/supabase_sync_new.py             # DRY-RUN(집계만)
  python jobs/supabase_sync_new.py --apply     # 실제 반영(신규 업로드 + 기존 갱신)
  옵션: --days N (최근 N일 신규분만) · --workers 8
        --refresh-days N  기존 갱신 대상을 최근 N일 재크롤분으로 제한(기본 3 · 0=전체 백필)
        --refresh-only    신규 업로드는 건너뛰고 기존 갱신만
        --no-refresh      기존 갱신을 끈다(예전 동작)
        --platform google 기존 갱신 대상 플랫폼 제한 · --limit N 샘플 검증용
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import urllib.parse as _urlparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import database  # noqa: E402
import services.supabase_read as sr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "series_archive.db"

# 장기보존 브랜드(= is_preserved=1 로 올려 60일 retention에서 빼는 대상)
_PRESERVED: set = set()
for _p in sorted((ROOT / "data").glob("supabase_migration_plan*.json")):
    if _p.name == "supabase_migration_plan_rest66.json":
        continue                      # 66개는 retention 대상이라 보존 표시 안 함
    import json as _json
    _PRESERVED |= set(_json.loads(_p.read_text(encoding="utf-8"))["brands"])


def _migrate_mod():
    """supabase_migrate 의 업서트/업로드 로직을 그대로 재사용(중복 구현 금지)."""
    spec = importlib.util.spec_from_file_location("sm", ROOT / "jobs" / "supabase_migrate.py")
    mod = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["supabase_migrate"]      # 모듈 최상단이 argv를 보지 않게
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def _storage_objects(sm) -> set:
    """Storage 에 이미 있는 썸네일 파일명 집합(있는 건 다시 안 올린다)."""
    import requests
    out, off = set(), 0
    while True:
        r = requests.post(f"{sm._base()}/storage/v1/object/list/{sm.BUCKET}",
                          headers=sm._h({"Content-Type": "application/json"}),
                          json={"prefix": sm.PREFIX, "limit": 1000, "offset": off}, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"Storage 목록 {r.status_code}: {r.text[:120]}")
        items = r.json()
        out |= {x["name"] for x in items}
        if len(items) < 1000:
            return out
        off += 1000


# ════════════════════════════════════════════════════════════════════════
# 기존 광고 갱신 — PATCH(UPDATE) 전용
# ════════════════════════════════════════════════════════════════════════
# 재크롤이 바꾸는 값들. 신규 업로드 경로는 이 목록과 무관하게 예전 그대로 전 컬럼을 올린다.
REFRESH_COLS = ("collected_at", "last_seen_at", "last_crawled_at",
                "status", "video_status", "video_url")

# 한 요청에 넣는 id 개수(현재값 조회용). URL 길이 한계를 넉넉히 밑돌게 잡는다.
SB_ID_CHUNK = 120


def _norm(v) -> str:
    """비교용 정규화 — 같은 값의 표기 차이(마이크로초·타임존·None/'')를 흡수한다.

    SQLite 는 '2026-08-17T11:34:26.790902+00:00', PostgREST 는 같은 값을 다른 자릿수로
    돌려줄 수 있다. 초 단위까지만 보고 판단해야 **의미 없는 PATCH 수천 건**을 안 만든다.
    """
    if v is None:
        return ""
    s = str(v).strip()
    # ISO 타임스탬프면 초까지만(YYYY-MM-DDTHH:MM:SS)
    if len(s) >= 19 and s[4:5] == "-" and s[7:8] == "-":
        return s[:19]
    return s


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _sb_current(ids: list, platform: str = "") -> dict:
    """Supabase 의 현재값(REFRESH_COLS) 조회. 대상이 적으면 id=in.() 로, 많으면 전량 페이지네이션."""
    sel = "select=id," + ",".join(REFRESH_COLS)
    if ids and len(ids) <= 3000:
        out: dict = {}
        for ch in _chunks(ids, SB_ID_CHUNK):
            for r in sr._fetch("ad_library_ads", f"{sel}&id=in.{sr._in_list(ch)}", verify=False):
                out[r["id"]] = r
        return out
    q = sel + (f"&platform=eq.{_urlparse.quote(platform)}" if platform else "")
    return {r["id"]: r for r in sr._fetch("ad_library_ads", q)}


def _local_rows(days: int = 0, platform: str = "") -> dict:
    """로컬 DB 의 현재값. days>0 이면 '최근 N일 안에 재크롤된' 광고로 좁힌다."""
    con = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    where, args = ["COALESCE(is_excluded,0)=0"], []
    if platform:
        where.append("platform = ?")
        args.append(platform)
    if days > 0:
        # last_crawled_at 이 비어 있는 옛 행은 collected_at 으로 대신 판단
        where.append("substr(COALESCE(last_crawled_at, collected_at),1,10) >= date('now',?)")
        args.append(f"-{days} day")
    sql = (f"SELECT id, brand_name, platform, {','.join(REFRESH_COLS)} "
           f"FROM ad_library_ads WHERE {' AND '.join(where)}")
    try:
        return {r["id"]: dict(r) for r in con.execute(sql, args)}
    finally:
        con.close()


def _plan_refresh(local: dict, sb: dict) -> tuple:
    """PATCH 대상 계산. 반환 (작업목록, 통계).

    작업 1건 = (ad_id, {바뀐 컬럼만}). **바뀐 컬럼만** 보내 쓰기 범위를 최소화한다.
    """
    jobs, stat = [], {"common": 0, "same": 0, "older": 0, "changed": 0,
                      "col": {c: 0 for c in REFRESH_COLS}}
    for aid, l in local.items():
        s = sb.get(aid)
        if s is None:
            continue                                   # Supabase 에 없음 → 신규 업로드 경로 담당
        stat["common"] += 1
        diff = {c: l[c] for c in REFRESH_COLS if _norm(l[c]) != _norm(s.get(c))}
        if not diff:
            stat["same"] += 1
            continue
        # 값 역행 방지 — 로컬이 Supabase 보다 과거면 건드리지 않는다
        if _norm(l["collected_at"]) < _norm(s.get("collected_at")):
            stat["older"] += 1
            continue
        stat["changed"] += 1
        for c in diff:
            stat["col"][c] += 1
        jobs.append((aid, diff))
    return jobs, stat


def _patch_session(workers: int):
    import requests
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    ad = HTTPAdapter(pool_connections=workers, pool_maxsize=workers, max_retries=2)
    s.mount("https://", ad)
    s.mount("http://", ad)
    return s


def _patch_one(sess, aid: str, payload: dict) -> tuple:
    """단일 행 UPDATE. PATCH ?id=eq.<id> 라 INSERT 도 DELETE 도 절대 일어나지 않는다."""
    url = f"{sr._base()}/rest/v1/ad_library_ads?id=eq.{_urlparse.quote(str(aid), safe='')}"
    r = sess.patch(url,
                   headers={**sr._headers(), "Content-Type": "application/json",
                            "Prefer": "return=minimal"},
                   data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                   timeout=60)
    if r.status_code in (200, 204):
        return True, ""
    return False, f"{r.status_code}: {r.text[:160]}"


def refresh_existing(apply: bool = False, days: int = 3, workers: int = 8,
                     platform: str = "", limit: int = 0, verbose: bool = True) -> dict:
    """재크롤로 값이 바뀐 **기존** 광고를 Supabase 에 PATCH.

    · 행 추가/삭제 없음 — `?id=eq.<id>` 단건 UPDATE 만 수행.
    · 멱등: 두 번 돌리면 두 번째는 '변경 없음'으로 0건.
    · days=0 이면 전체 백필, >0 이면 최근 N일 재크롤분만(일일 체인용).
    """
    local = _local_rows(days=days, platform=platform)
    if not local:
        if verbose:
            print("[기존 갱신] 대상 없음")
        return {"changed": 0, "sent": 0, "failed": 0, "applied": apply}
    scope_ids = list(local.keys()) if days > 0 else []
    sb = _sb_current(scope_ids, platform=platform)
    jobs, stat = _plan_refresh(local, sb)
    if limit:
        jobs = jobs[:limit]
    if verbose:
        cols = " · ".join(f"{c} {n:,}" for c, n in stat["col"].items() if n)
        print(f"[기존 갱신] 공통 {stat['common']:,} · 변경 {stat['changed']:,} "
              f"(동일 {stat['same']:,} · 로컬이 과거라 건너뜀 {stat['older']:,})"
              + (f" · 컬럼별 {cols}" if cols else ""))
    if not apply:
        print(f"  [dry-run] PATCH 예정 {len(jobs):,}건 — 실제 반영은 --apply")
        return {"changed": stat["changed"], "sent": 0, "failed": 0, "applied": False,
                "stat": stat, "planned": len(jobs)}
    if not jobs:
        return {"changed": 0, "sent": 0, "failed": 0, "applied": True, "stat": stat}

    sess = _patch_session(workers)
    sent = failed = 0
    errs: list = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (ok, err) in enumerate(ex.map(lambda j: _patch_one(sess, j[0], j[1]), jobs), 1):
            if ok:
                sent += 1
            else:
                failed += 1
                if len(errs) < 5:
                    errs.append(err)
            if verbose and i % 1000 == 0:
                print(f"  [PATCH] {i:,}/{len(jobs):,}", flush=True)
    for e in errs:
        print(f"  [PATCH 실패] {e}")
    if verbose:
        print(f"  기존 갱신 완료 — UPDATE {sent:,} · 실패 {failed:,}")
    return {"changed": stat["changed"], "sent": sent, "failed": failed,
            "applied": True, "stat": stat}


def verify_refresh(days: int = 0, platform: str = "") -> dict:
    """백필 검증 — 남은 불일치 · 행 수 · id 고유성을 Supabase 에서 다시 읽어 확인."""
    local = _local_rows(days=days, platform=platform)
    sb = _sb_current([], platform=platform)
    _, stat = _plan_refresh(local, sb)
    ids = list(sb.keys())
    out = {"sb_rows": len(ids), "sb_unique_ids": len(set(ids)),
           "local_rows": len(local), "common": stat["common"],
           "still_different": stat["changed"], "local_older_skipped": stat["older"]}
    print(f"[검증] Supabase 행 {out['sb_rows']:,} · 고유 id {out['sb_unique_ids']:,} · "
          f"공통 {out['common']:,} · 남은 불일치 {out['still_different']:,} "
          f"(로컬이 과거라 제외 {out['local_older_skipped']:,})")
    return out


def run(apply: bool = False, days: int = 0, workers: int = 8,
        refresh_days: int = 3, refresh: bool = True, refresh_only: bool = False,
        platform: str = "") -> dict:
    sm = _migrate_mod()
    if not sm._base() or not sm._key():
        print("Supabase 설정 없음 — 동기화 생략")
        return {}

    # 기존 광고 갱신만 돌리는 모드(백필·재검증용) — 신규 업로드 경로는 건드리지 않는다
    if refresh_only:
        return {"refresh": refresh_existing(apply=apply, days=refresh_days, workers=workers,
                                            platform=platform), "applied": apply}

    # ── ① Supabase 현황(검증된 페이지네이션 사용) ─────────────────────────
    sb_ids = {x["id"] for x in sr._fetch("ad_library_ads", "select=id")}
    sb_brands = {x["display_name"] for x in sr._fetch("brands", "select=display_name")}

    # ── ② 로컬에서 '아직 안 올라간' 광고 추리기 ───────────────────────────
    con = sqlite3.connect(str(LIVE))
    con.row_factory = sqlite3.Row
    bl = database.load_ingest_blocklist(con)
    where = "COALESCE(is_excluded,0)=0"
    args: list = []
    if days > 0:
        where += " AND substr(COALESCE(first_seen_at,collected_at),1,10) >= date('now',?)"
        args.append(f"-{days} day")
    new_ads, blocked = [], 0
    for r in con.execute(f"SELECT * FROM ad_library_ads WHERE {where}", args):
        d = dict(r)
        if d["id"] in sb_ids:
            continue                                  # 이미 올라감 → 건너뜀(멱등)
        if database._blocked_reason(d, bl):
            blocked += 1
            continue                                  # 오염 차단 규칙
        new_ads.append(d)
    new_ids = {a["id"] for a in new_ads}

    new_brands = [dict(r) for r in con.execute("SELECT * FROM brands")
                  if r["display_name"] not in sb_brands]
    matches = [dict(r) for r in con.execute("SELECT * FROM ad_social_matches")
               if r["ad_id"] in new_ids]
    snaps = [dict(r) for r in con.execute("SELECT * FROM ad_view_snapshots")
             if r["ad_id"] in new_ids]
    cols = {t: [x[1] for x in con.execute(f"PRAGMA table_info({t})")]
            for t in ("ad_library_ads", "ad_social_matches", "ad_view_snapshots", "brands")}
    con.close()

    # ── ③ 썸네일: Storage에 없는 파일만 ───────────────────────────────────
    thumbs = sm.thumb_files(new_ads)                  # ad_id -> [로컬경로]
    have_obj = _storage_objects(sm)
    files, key_of = [], {}
    for aid, fs in thumbs.items():
        name = Path(fs[0]).name
        key_of[aid] = sm.PREFIX + name
        if name not in have_obj:
            files.append(fs[0])

    print(f"[신규 동기화] 광고 {len(new_ads):,} · 브랜드 {len(new_brands)} · 매칭 {len(matches):,} · "
          f"스냅샷 {len(snaps):,} · 썸네일 업로드 대상 {len(files):,}"
          f"{f' (이미 있음 {len(thumbs)-len(files):,})' if thumbs else ''}"
          f"{f' · 오염 차단 {blocked}' if blocked else ''}")
    if not apply:
        print("  [dry-run] 실제 반영은 --apply")
        rf = refresh_existing(apply=False, days=refresh_days, workers=workers,
                              platform=platform) if refresh else {}
        return {"ads": len(new_ads), "thumbs": len(files), "applied": False, "refresh": rf}
    if not new_ads and not new_brands:
        # 신규가 없어도 **기존 갱신은 돌아야 한다** — 재크롤로 값만 바뀐 날이 대부분이다
        rf = refresh_existing(apply=True, days=refresh_days, workers=workers,
                              platform=platform) if refresh else {}
        return {"ads": 0, "thumbs": 0, "applied": True, "refresh": rf}

    # ── ④ 업로드 & 업서트(기존 멱등 로직 재사용) ──────────────────────────
    up = sm.upload_thumbs(files, True, workers) if files else {"uploaded": 0, "failed": 0}
    rows = []
    for a in new_ads:
        key = key_of.get(a["id"], "")
        rows.append(sm._clean(a, cols["ad_library_ads"], {
            "storage_path": key,
            "thumbnail_url": sm.public_url(key) if key else (a.get("thumbnail_url") or ""),
            "orig_thumbnail_url": a.get("thumbnail_url") or "",
            "local_thumbnail_path": key,
            "is_preserved": 1 if a.get("brand_name") in _PRESERVED else (a.get("is_preserved") or 0),
        }))
    def _sent(r) -> int:            # sm.upsert 는 {"sent":n,"failed":n} 를 준다
        return int(r.get("sent", 0)) if isinstance(r, dict) else int(r or 0)

    res = {"ads": _sent(sm.upsert("ad_library_ads", rows, "id", True)),
           "brands": _sent(sm.upsert("brands", [sm._clean(b, cols["brands"]) for b in new_brands],
                                     "id", True)) if new_brands else 0,
           "matches": _sent(sm.upsert("ad_social_matches",
                                      [sm._clean(m, cols["ad_social_matches"]) for m in matches],
                                      "ad_id,social_id", True)) if matches else 0,
           "snapshots": _sent(sm.upsert("ad_view_snapshots",
                                        [sm._clean(s, cols["ad_view_snapshots"] + ["view_snapshot_source"],
                                                   {"view_snapshot_source": "live"}) for s in snaps],
                                        "ad_id,snapshot_date", True)) if snaps else 0,
           "thumbs": up.get("uploaded", 0), "thumb_failed": up.get("failed", 0), "applied": True}
    print(f"  반영 완료 — 광고 {res['ads']:,} · 브랜드 {res['brands']} · 매칭 {res['matches']:,} · "
          f"스냅샷 {res['snapshots']:,} · 썸네일 {res['thumbs']:,}(실패 {res['thumb_failed']})")

    # ── ⑤ 기존 광고 갱신(PATCH) — 방금 올린 신규분은 이미 최신이라 자동으로 대상에서 빠진다 ──
    if refresh:
        res["refresh"] = refresh_existing(apply=True, days=refresh_days, workers=workers,
                                          platform=platform)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=0, help="최근 N일 신규분만(0=Supabase에 없는 것 전부)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh-days", type=int, default=3,
                    help="기존 광고 갱신 대상 = 최근 N일 재크롤분(0=전체 백필)")
    ap.add_argument("--refresh-only", action="store_true", help="신규 업로드 없이 기존 갱신만")
    ap.add_argument("--no-refresh", action="store_true", help="기존 갱신을 끈다(예전 동작)")
    ap.add_argument("--platform", default="", help="기존 갱신 대상 플랫폼(google/meta 등)")
    ap.add_argument("--verify", action="store_true", help="갱신 없이 검증만 출력")
    a = ap.parse_args()
    if a.verify:
        verify_refresh(days=a.refresh_days, platform=a.platform)
        return
    run(apply=a.apply, days=a.days, workers=a.workers, refresh_days=a.refresh_days,
        refresh=not a.no_refresh, refresh_only=a.refresh_only, platform=a.platform)


if __name__ == "__main__":
    main()
