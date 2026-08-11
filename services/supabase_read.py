# -*- coding: utf-8 -*-
"""앱 읽기 경로의 Supabase 전환 — **브랜드 화이트리스트 방식**(2026-08-11).

`SUPABASE_READ_BRANDS=테키라,세라블랑` 에 적힌 브랜드만 Supabase에서 읽고, 나머지는 기존 SQLite 그대로.
값을 비우면 100% 원래대로 돌아간다(코드 롤백 불필요).

동작 방식 — **Supabase에서 그 브랜드 행을 받아 로컬 미러 SQLite에 넣고, 기존 SQL을 그대로 실행**한다.
  · database.py 의 조회 SQL(윈도우 함수·중복묶기·소셜 조인)은 상당히 복잡하다. 이걸 PostgREST 문법으로
    다시 쓰면 미세하게 결과가 달라질 위험이 크다 → 쿼리는 손대지 않고 **데이터 출처만** 바꾼다.
  · 미러는 브랜드별 파일(.cache/supabase_<브랜드>.db)이며 MIRROR_TTL(기본 300초) 지나면 다시 받는다.
  · 어떤 단계든 실패하면 None 을 돌려주고, 호출측(database.py)은 즉시 SQLite로 폴백한다.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
MIRROR_TTL = int(config.secret("SUPABASE_MIRROR_TTL") or 300)
PAGE = 1000
TABLES = ("ad_library_ads", "ad_view_snapshots", "ad_social_matches",
          "social_videos", "social_video_snapshots", "brands", "video_view_state")

_last_error = ""
_stats: dict = {}          # 진단용: 브랜드별 마지막 하이드레이션 정보


# ── 설정 ────────────────────────────────────────────────────────────────
def brands() -> list[str]:
    raw = config.secret("SUPABASE_READ_BRANDS") or ""
    return [b.strip() for b in raw.split(",") if b.strip()]


def enabled() -> bool:
    return bool(brands() and config.secret("SUPABASE_URL")
                and (config.secret("SUPABASE_SERVICE_KEY") or config.secret("SUPABASE_KEY")))


def handles(brand: str | None) -> bool:
    return bool(brand) and enabled() and brand in brands()


def last_error() -> str:
    return _last_error


def stats() -> dict:
    return dict(_stats)


# ── Supabase 조회 ───────────────────────────────────────────────────────
def _base() -> str:
    return (config.secret("SUPABASE_URL") or "").rstrip("/")


def _headers() -> dict:
    k = config.secret("SUPABASE_SERVICE_KEY") or config.secret("SUPABASE_KEY")
    return {"apikey": k, "Authorization": f"Bearer {k}"}


def _fetch(table: str, query: str) -> list[dict]:
    """PostgREST 페이지네이션 조회."""
    import requests  # lazy
    out, start = [], 0
    while True:
        r = requests.get(f"{_base()}/rest/v1/{table}?{query}",
                         headers={**_headers(), "Range": f"{start}-{start + PAGE - 1}"}, timeout=60)
        if r.status_code not in (200, 206):
            raise RuntimeError(f"{table} {r.status_code}: {r.text[:120]}")
        rows = r.json()
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        start += PAGE


def _in_list(vals: list[str]) -> str:
    return "(" + ",".join('"' + str(v).replace('"', '') + '"' for v in vals) + ")"


# ── 로컬 미러 ───────────────────────────────────────────────────────────
def _mirror_path(brand: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(brand.encode("utf-8")).hexdigest()[:10]
    return CACHE / f"supabase_{h}.db"


def _schema_sql() -> list[str]:
    """로컬 LIVE DB에서 테이블 DDL을 그대로 복사 — 미러가 같은 스키마여야 같은 SQL이 돈다."""
    import database
    con = sqlite3.connect(str(database.DB_PATH))
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name IN (%s)"
            % ",".join("?" * len(TABLES)), TABLES).fetchall()
        return [r[0] for r in rows if r[0]]
    finally:
        con.close()


# 한 요청에 넣는 ad_id 개수. 200 → 400 으로 올려 왕복 횟수를 절반으로(매칭 85행에 3.7초 걸리던 원인).
ID_CHUNK = int(config.secret("SUPABASE_ID_CHUNK") or 400)


def _build_mirror(brand: str, path: Path) -> dict:
    """Supabase → 미러 SQLite. **목록 화면에 필요한 것만** 담는다.

    ★2026-08-11 최적화: 예전엔 조회수 스냅샷까지 전부 받아 테키라 기준 14.1초가 걸렸다
      (스냅샷 13,952행 = 8.7초, 전체의 63%). 스냅샷은 **상세 모달의 추이 그래프에서만** 쓰이므로
      미러에서 빼고, 상세 진입 시 그 광고 것만 직접 조회한다(`fetch_snapshots`).
    """
    t0 = time.time()
    ads = _fetch("ad_library_ads", f"select=*&brand_name=eq.{brand}")
    ids = [a["id"] for a in ads]
    snaps, matches, soc_snaps = [], [], []
    for i in range(0, len(ids), ID_CHUNK):
        matches += _fetch("ad_social_matches", f"select=*&ad_id=in.{_in_list(ids[i:i + ID_CHUNK])}")
    socials = _fetch("social_videos", f"select=*&brand_name=eq.{brand}")
    brand_rows = _fetch("brands", f"select=*&display_name=eq.{brand}")
    fetched = time.time() - t0

    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(str(tmp))
    for ddl in _schema_sql():
        con.execute(ddl)

    def _put(table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        use = [c for c in cols if c in rows[0]]
        ph = ",".join("?" * len(use))
        con.executemany(f"INSERT OR REPLACE INTO {table}({','.join(use)}) VALUES({ph})",
                        [tuple(r.get(c) for c in use) for r in rows])
        return len(rows)

    n = {"ad_library_ads": _put("ad_library_ads", ads),
         "ad_view_snapshots": _put("ad_view_snapshots", snaps),
         "ad_social_matches": _put("ad_social_matches", matches),
         "social_videos": _put("social_videos", socials),
         "social_video_snapshots": _put("social_video_snapshots", soc_snaps),
         "brands": _put("brands", brand_rows)}
    con.commit()
    con.close()
    tmp.replace(path)                           # 원자적 교체 — 조회 중 깨진 미러를 읽지 않게
    n["_fetch_sec"] = round(fetched, 2)
    n["_total_sec"] = round(time.time() - t0, 2)
    n["_built_at"] = time.time()
    return n


def conn(brand: str):
    """화이트리스트 브랜드의 Supabase 미러 커넥션. 실패하면 None(→ 호출측이 SQLite 폴백)."""
    global _last_error
    if not handles(brand):
        return None
    try:
        p = _mirror_path(brand)
        fresh = p.exists() and (time.time() - p.stat().st_mtime) < MIRROR_TTL
        if not fresh:
            _stats[brand] = _build_mirror(brand, p)
        c = sqlite3.connect(str(p), timeout=15)
        c.row_factory = sqlite3.Row
        return c
    except Exception as e:  # noqa: BLE001
        _last_error = f"{type(e).__name__}: {e}"
        print(f"  [supabase_read] {brand} 미러 실패 → SQLite 폴백: {_last_error}")
        return None


def ad_brand(ad_id: str) -> str:
    """이 광고가 화이트리스트 브랜드 소속이면 브랜드명, 아니면 ''(=SQLite로)."""
    if not (ad_id and enabled()):
        return ""
    for b in brands():
        p = _mirror_path(b)
        if not p.exists():
            continue
        try:
            c = sqlite3.connect(str(p), timeout=5)
            hit = c.execute("SELECT 1 FROM ad_library_ads WHERE id=? LIMIT 1", (ad_id,)).fetchone()
            c.close()
            if hit:
                return b
        except Exception:  # noqa: BLE001
            continue
    return ""


def fetch_snapshots(ad_id: str, days: int = 120) -> list[dict]:
    """상세 모달용 — 그 광고의 조회수 추이만 Supabase에서 직접(요청 1회). 미러에는 담지 않는다."""
    if not (ad_id and enabled()):
        return []
    rows = _fetch("ad_view_snapshots",
                  f"select=snapshot_date,views,likes,comments&ad_id=eq.{ad_id}"
                  f"&order=snapshot_date.desc&limit={int(days)}")
    return list(reversed(rows))


def storage_url(path: str) -> str:
    """Storage 키('thumbnails/x.jpg') → 공개 URL. SUPABASE_URL 없으면 ''."""
    base = _base()
    if not base or not path:
        return ""
    return f"{base}/storage/v1/object/public/series-archive/{path.lstrip('/')}"


def refresh(brand: str) -> dict:
    """미러 강제 갱신(진단/검증용)."""
    return _build_mirror(brand, _mirror_path(brand))
