# -*- coding: utf-8 -*-
"""참고 Google 광고(reference_picker_google_ads)를 **조회 순간에만** 기존 Google 광고 목록에 합쳐 보이게 한다.

원칙
  · DB(ad_library_ads / reference_picker_google_ads / brands)는 읽기만 — INSERT/UPDATE 없음.
  · 합치는 방법: 조회용 SQLite 커넥션 안에서만 사는 TEMP VIEW `ad_library_ads`
      = main.ad_library_ads  UNION ALL  메모리 테이블(참고 광고를 같은 컬럼 형태로 변환)
    → 기존 정렬·페이지·중복묶기 SQL 을 그대로 재사용. 커넥션을 닫으면 사라진다.
  · 대상: brand_id 가 연결된 행만, 선택한 브랜드 1개 기준으로만 조회(전체 브랜드 화면엔 넣지 않음).
  · 같은 video_id 가 우리 ad_library_ads 에 있으면 참고 광고는 숨김(우리 데이터 우선).
  · brands.is_active(자동수집 여부)와 무관하게 표시.
  · 화면에 출처 문구를 넣지 않는다. 내부 구분은 id 접두사 'pk_' 와 _source='picker'.
Supabase 미설정/오류면 조용히 아무것도 안 함(기존 화면 그대로).
"""
from __future__ import annotations

import time

import requests

PREFIX = "pk_"
TABLE = "reference_picker_google_ads"
_TTL = 600
_cache: dict = {}
_LIST_COLS = ("source_ad_id,brand_id,brand_name,title,video_url,video_id,youtube_channel_name,"
              "destination_url,upload_date,picker_created_at,is_active,views,like_count")


def is_picker_id(ad_id) -> bool:
    return str(ad_id or "").startswith(PREFIX)


def _sb():
    import services.supabase_read as sr
    if not sr.enabled():
        return None
    return sr


def _cached(key, fn, ttl=_TTL):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _fetch_all(sr, table: str, params: dict) -> list[dict]:
    """고정 정렬키(id) + Range 페이지 + 총건수 대조(1,000행 잘림·중복 방지)."""
    rows, step = [], 1000
    while True:
        for attempt in range(2):                    # Supabase 일시 5xx 대비 1회 재시도
            r = requests.get(f"{sr._base()}/rest/v1/{table}", timeout=30,
                             params={**params, "order": "id.asc"},
                             headers={**sr._headers(), "Range": f"{len(rows)}-{len(rows)+step-1}",
                                      "Prefer": "count=exact"})
            if r.status_code < 500:
                break
            time.sleep(1.5)
        r.raise_for_status()
        total = int(r.headers.get("content-range", "*/0").split("/")[-1])
        chunk = r.json()
        rows += chunk
        if len(chunk) < step or len(rows) >= total:
            break
    if len(rows) != total:
        raise RuntimeError(f"{table} 페이지 검증 실패 {len(rows)}/{total}")
    return rows


def _brand_ids() -> dict:
    """display_name → brands.id (Supabase brands, 로컬과 id 동일)."""
    sr = _sb()
    if not sr:
        return {}
    return _cached("brands", lambda: {b["display_name"]: b["id"] for b in
                                      _fetch_all(sr, "brands", {"select": "id,display_name"})
                                      if b.get("display_name")})


def _our_video_ids() -> set:
    """우리 ad_library_ads(google) 의 video_id 전체 — 중복이면 우리 쪽 우선."""
    sr = _sb()
    if not sr:
        return set()

    def load():
        from services.youtube import extract_video_id
        rows = _fetch_all(sr, "ad_library_ads", {"select": "id,video_url", "platform": "eq.google",
                                                  "video_url": "neq."})
        return {v for v in (extract_video_id(r["video_url"] or "") for r in rows) if v}
    return _cached("our_vids", load, ttl=1800)


def _rows_for_brand_id(bid: int) -> list[dict]:
    sr = _sb()
    if not sr:
        return []
    return _cached(f"rows:{bid}", lambda: _fetch_all(
        sr, TABLE, {"select": "id," + _LIST_COLS, "brand_id": f"eq.{int(bid)}"}))


def brand_counts_extra() -> dict:
    """사이드바용 {display_name: 표시될 참고 광고 수}(우리와 video_id 중복 제외). 실패 시 {}."""
    try:
        sr = _sb()
        if not sr:
            return {}

        def load():
            names = {v: k for k, v in _brand_ids().items()}
            ours = _our_video_ids()
            out: dict = {}
            for r in _fetch_all(sr, TABLE, {"select": "id,brand_id,video_id", "brand_id": "not.is.null"}):
                if r.get("video_id") in ours:
                    continue
                nm = names.get(r["brand_id"])
                if nm:
                    out[nm] = out.get(nm, 0) + 1
            return out
        return _cached("counts", load, ttl=1800)
    except Exception as e:  # noqa: BLE001
        print(f"  [참고광고] 브랜드 집계 실패(무시): {type(e).__name__}: {e}")
        return {}


def _kst_day(ts) -> str:
    """'2026-03-30T15:00:00+00:00'(=KST 자정) → '2026-03-31'. 비면 ''."""
    if not ts:
        return ""
    from datetime import datetime, timedelta, timezone
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d.astimezone(timezone(timedelta(hours=9))).date().isoformat()
    except Exception:  # noqa: BLE001
        return str(ts)[:10]


def to_ad(r: dict, display_name: str) -> dict:
    """참고 광고 1행 → ad_library_ads 형태(없는 필드는 비움/기본값, 추정 금지)."""
    vid = r.get("video_id") or ""
    return {
        "id": PREFIX + str(r["source_ad_id"]),
        "brand_name": display_name,                  # 우리 브랜드 표기(brand_id 로 연결된 값)
        "brand_id": r.get("brand_id"),
        "platform": "google",
        "ad_title": r.get("title") or "",
        "ad_copy": "",
        "video_url": r.get("video_url") or "",
        "media_type": "video",
        "ad_format": "video",
        # YouTube 고정 썸네일 경로(video_id 로 결정되는 값 — 기존 YT.thumb_url 과 동일 규칙)
        "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "",
        "landing_url": r.get("destination_url") or "",
        "status": "live" if r.get("is_active") else "ended",
        "started_at": _kst_day(r.get("upload_date")),
        "collected_at": _kst_day(r.get("picker_created_at")),
        "yt_views": r.get("views"),
        "yt_likes": r.get("like_count"),
        "brand_status": "confirmed",                 # brand_id 로 확정 연결된 것만 들어옴
        "dedupe_key": f"yt:{vid}" if vid else "",    # 기존 영상 중복묶기 규칙과 동일
        "is_excluded": 0, "is_bookmarked": 0, "detail_status": "",
        "youtube_channel_name": r.get("youtube_channel_name") or "",
        "_source": "picker",
    }


def install(conn, brand) -> int:
    """이 커넥션에서만 ad_library_ads 를 (우리 + 참고 광고) 로 보이게 한다. 반환=합친 참고 광고 수."""
    try:
        if not brand or brand == "전체" or _sb() is None:
            return 0
        bid = _brand_ids().get(brand)
        if bid is None:
            return 0
        rows = _rows_for_brand_id(bid)
        if not rows:
            return 0
        from services.youtube import extract_video_id
        ours = set(_our_video_ids())
        ours |= {v for v in (extract_video_id(x[0] or "") for x in conn.execute(
            "SELECT video_url FROM main.ad_library_ads WHERE platform='google' AND video_url<>''")) if v}
        ads = [to_ad(r, brand) for r in rows if r.get("video_id") not in ours]
        if not ads:
            return 0
        cols = [c[1] for c in conn.execute("PRAGMA main.table_info(ad_library_ads)")]
        conn.execute("ATTACH DATABASE ':memory:' AS pk")
        conn.execute("CREATE TABLE pk.ad_library_ads AS SELECT * FROM main.ad_library_ads WHERE 0")
        use = [c for c in cols if c in ads[0]]
        conn.executemany(f"INSERT INTO pk.ad_library_ads ({','.join(use)}) VALUES ({','.join('?' * len(use))})",
                         [[a.get(c) for c in use] for a in ads])
        conn.execute("CREATE TEMP VIEW ad_library_ads AS "
                     "SELECT * FROM main.ad_library_ads UNION ALL SELECT * FROM pk.ad_library_ads")
        return len(ads)
    except Exception as e:  # noqa: BLE001  (어떤 실패든 기존 화면 그대로)
        print(f"  [참고광고] 합치기 생략: {type(e).__name__}: {e}")
        return 0


def get_full(ad_id: str) -> dict | None:
    """상세 모달용 1건(대본 포함). id 는 'pk_<source_ad_id>'."""
    try:
        sr = _sb()
        if not sr or not is_picker_id(ad_id):
            return None
        r = requests.get(f"{sr._base()}/rest/v1/{TABLE}", headers=sr._headers(), timeout=15,
                         params={"select": _LIST_COLS + ",transcript",
                                 "source_ad_id": f"eq.{ad_id[len(PREFIX):]}",
                                 "brand_id": "not.is.null", "limit": "1"})
        r.raise_for_status()
        js = r.json()
        if not js:
            return None
        names = {v: k for k, v in _brand_ids().items()}
        ad = to_ad(js[0], names.get(js[0]["brand_id"]) or js[0].get("brand_name") or "")
        ad["transcript"] = js[0].get("transcript") or ""
        return ad
    except Exception as e:  # noqa: BLE001
        print(f"  [참고광고] 상세 조회 실패: {type(e).__name__}: {e}")
        return None
