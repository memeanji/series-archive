# -*- coding: utf-8 -*-
"""광고 ID 단건 즉시 수집 — Meta Ad Library ?id=<ID> 페이지를 크롤해 DB에 적재하고,
   배포 환경(Streamlit Cloud)에서는 **Supabase 까지 즉시 반영**한다.

앱이 어느 단계에서 실패했는지 화면에 그대로 띄울 수 있도록, 진행을 5단계로 쪼개
`RESULT_JSON:` 한 줄에 구조화해 출력한다.

  ① import    playwright 파이썬 패키지 + 크로미움 확보(시스템 크로미움 → 번들 설치)
  ② browser   크로미움 실제 기동(about:blank) — Meta 접속 전에 원인 분리
  ③ meta      Meta Ad Library 조회
  ④ db        로컬 DB 저장(재수집 차단 규칙 포함)
  ⑤ supabase  Supabase 반영(썸네일 Storage + ad_library_ads upsert + 되읽기 확인)

사용:  python jobs/collect_by_id.py <id1> <id2> ...
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from services import browser as B  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_STAGES: list = []


def _stage(name: str, label: str, ok: bool, detail: str = "", skipped: bool = False) -> dict:
    d = {"name": name, "label": label, "ok": bool(ok), "detail": detail, "skipped": skipped}
    _STAGES.append(d)
    return d


# ?id= 단건 페이지는 카드 첫 줄이 광고주명이 아니라 안내문일 때가 많다.
# 이런 문자열이 브랜드명으로 저장되면 사이드바에 쓰레기 브랜드가 생긴다(실측: 2026-08-21).
_NOISE = ("크리에이티브", "문구를 사용", "요약 세부 사항", "라이브러리 ID", "Library ID",
          "Sponsored", "게재 시작", "이 광고", "Open Dropdown", "결과 약")


def _domain(url: str) -> str:
    from urllib.parse import urlparse
    try:
        d = (urlparse(url or "").hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return d[4:] if d.startswith("www.") else d


def _clean_name(s: str) -> str:
    s = (s or "").strip()
    if not s or len(s) > 40 or any(k in s for k in _NOISE):
        return ""
    return s


def resolve_brand(a: dict) -> tuple:
    """단건 수집 광고의 브랜드를 정한다. (브랜드명, 판단근거)

    카드 첫 줄(headline)을 그대로 쓰면 '광고 2개에서 이 크리에이티브 및 문구를 사용합니다'
    같은 안내문이 브랜드가 돼버린다. 실제 소속을 알 수 있는 단서부터 순서대로 본다."""
    pid = str(a.get("page_id") or "").strip()
    dom = _domain(a.get("landing_url") or "")
    conn = database.get_conn()
    try:
        if pid:
            r = conn.execute("SELECT display_name FROM brands WHERE meta_page_id=? LIMIT 1",
                             (pid,)).fetchone()
            if r:
                return r[0], f"브랜드 등록 page_id({pid})"
        if dom:
            r = conn.execute("SELECT display_name FROM brands WHERE official_domain<>'' AND "
                             "(lower(official_domain)=? OR ? LIKE '%.'||lower(official_domain)) LIMIT 1",
                             (dom, dom)).fetchone()
            if r:
                return r[0], f"브랜드 공식도메인({dom})"
            r = conn.execute(
                "SELECT brand_name, COUNT(*) n FROM ad_library_ads "
                "WHERE landing_url LIKE ? AND COALESCE(brand_name,'')<>'' "
                "GROUP BY brand_name ORDER BY n DESC LIMIT 1", (f"%{dom}%",)).fetchone()
            if r:
                return r[0], f"기존 광고 랜딩도메인({dom}) · {r[1]}건"
        if pid:
            r = conn.execute(
                "SELECT brand_name, COUNT(*) n FROM ad_library_ads "
                "WHERE page_id=? AND COALESCE(brand_name,'')<>'' "
                "GROUP BY brand_name ORDER BY n DESC LIMIT 1", (pid,)).fetchone()
            if r:
                return r[0], f"기존 광고 page_id({pid}) · {r[1]}건"
    finally:
        conn.close()
    nm = _clean_name(a.get("headline")) or _clean_name(a.get("advertiser_name"))
    if nm:
        return nm, "광고 카드 표기 광고주명"
    return "(ID수집)", "단서 없음 — 수동 지정 필요"


def _on_mirror() -> bool:
    """배포본(SUPABASE_READ_ALL=true)이라 DB 쓰기가 Supabase 미러로 가는 상태인가."""
    try:
        import services.supabase_read as sr
        return bool(sr.read_all())
    except Exception:  # noqa: BLE001
        return False


def _emit(results: list, supabase: dict = None) -> None:
    print("RESULT_JSON:" + json.dumps(
        {"stages": _STAGES, "results": results, "supabase": supabase or {}},
        ensure_ascii=False), flush=True)


# ── Supabase 즉시 반영 ────────────────────────────────────────────────────
def _migrate_mod():
    """supabase_migrate 의 업로드/업서트 로직 재사용(중복 구현 금지)."""
    spec = importlib.util.spec_from_file_location("sm_byid", ROOT / "jobs" / "supabase_migrate.py")
    mod = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["supabase_migrate"]   # 모듈 최상단이 argv를 보지 않게
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def push_supabase(ids: list) -> dict:
    """방금 수집한 광고 **그 ID들만** Supabase 로 올린다(전체 동기화 아님).

    전체 동기화(jobs/supabase_sync_new.py)를 여기서 부르면 안 된다 —
    배포 컨테이너의 로컬 DB 는 demo 스냅샷이라 '로컬에만 있는 광고' 판정이 어긋나
    수천 건을 되올릴 수 있다."""
    if not ids:
        return {"ok": True, "skipped": True, "detail": "신규 없음 — 올릴 것 없음"}
    if not (config.secret("SUPABASE_URL") and
            (config.secret("SUPABASE_SERVICE_KEY") or config.secret("SUPABASE_KEY"))):
        return {"ok": True, "skipped": True,
                "detail": "SUPABASE_URL/SERVICE_KEY 미설정 — 로컬 SQLite 에만 저장"}
    try:
        import requests
        sm = _migrate_mod()
        # ⚠️ ingest_ad_library 가 쓴 곳과 **같은 커넥션**이어야 한다.
        #    배포본(SUPABASE_READ_ALL=true)에서는 get_conn() 이 Supabase 미러를 돌려주고
        #    저장도 거기로 들어가므로, local=True 로 열면 방금 넣은 행을 못 찾는다.
        conn = database.get_conn()
        cols = [d[1] for d in conn.execute("PRAGMA table_info(ad_library_ads)")]
        qs = ",".join("?" * len(ids))
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM ad_library_ads WHERE id IN (%s)" % qs, ids)]
        conn.close()
        if not rows:
            return {"ok": False, "detail": "로컬 DB 에서 방금 저장한 행을 못 찾음"}

        thumbs = sm.thumb_files(rows)
        files = [f for fs in thumbs.values() for f in fs]
        up = {"uploaded": 0, "failed": 0}
        if files:
            sm.ensure_bucket(True)
            up = sm.upload_thumbs(files, True, 4)

        payload = []
        for a in rows:
            fs = thumbs.get(a["id"]) or []
            key = sm.PREFIX + Path(fs[0]).name if fs else ""
            payload.append(sm._clean(a, cols, {
                "storage_path": key,
                # Storage 사본이 없으면 원격 URL을 지우지 말고 유지 — 지우면 카드가 빈다
                "thumbnail_url": sm.public_url(key) if key else (a.get("thumbnail_url") or ""),
                "orig_thumbnail_url": a.get("thumbnail_url") or "",
                "local_thumbnail_path": key,      # 로컬 경로 대신 Storage 경로만 저장
                "is_preserved": a.get("is_preserved") or 0,
            }))
        res = sm.upsert("ad_library_ads", payload, "id", True)

        # 실제로 올라갔는지 되읽어 확인(앱 검색결과 노출 = Supabase 에 있어야 함)
        inlist = ",".join('"%s"' % i for i in ids)
        r = requests.get("%s/rest/v1/ad_library_ads?id=in.(%s)&select=id" % (sm._base(), inlist),
                         headers=sm._h(), timeout=60)
        seen = [x["id"] for x in r.json()] if r.status_code == 200 else []
        ok = res.get("failed", 0) == 0 and len(seen) == len(ids)
        return {"ok": ok, "sent": res.get("sent", 0), "failed": res.get("failed", 0),
                "thumbs": up, "verified": seen,
                "detail": "upsert %d건 · 썸네일 %d장 · 되읽기 확인 %d/%d건" % (
                    res.get("sent", 0), up.get("uploaded", 0), len(seen), len(ids))}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": "%s: %s" % (type(e).__name__, str(e)[:200])}


# ── 메인 ────────────────────────────────────────────────────────────────
def main(ids: list) -> None:
    ids = [str(i).strip() for i in ids if str(i).strip()]

    # ① playwright 패키지 + 브라우저 확보
    ok, detail = B.ensure_browser()
    _stage("import", "① 크롤러 준비(playwright)", ok, detail)
    if not ok:
        _emit([{"id": i, "ok": False, "is_new": False, "stage": "import",
                "reason": detail, "advertiser": "", "page_id": ""} for i in ids])
        return

    # ② 브라우저 실제 기동
    ok, detail = B.smoke_test()
    _stage("browser", "② 크로미움 기동", ok, detail)
    if not ok:
        _emit([{"id": i, "ok": False, "is_new": False, "stage": "browser",
                "reason": detail, "advertiser": "", "page_id": ""} for i in ids])
        return

    from collectors import meta_library_crawler   # 브라우저 확보 뒤에 import
    lo = B.launch_opts()

    database.init_db()
    before = database.existing_ad_ids(ids)
    results: list = []
    new_ids: list = []
    meta_ok = meta_fail = 0

    for aid in ids:
        if aid in before:
            results.append({"id": aid, "ok": True, "reason": "기존 보유", "is_new": False,
                            "stage": "db", "advertiser": "", "page_id": ""})
            continue
        # ③ Meta 조회
        try:
            ads = meta_library_crawler.search_brand("", ad_id=aid, retries=2, launch_opts=lo)
        except Exception as e:  # noqa: BLE001
            meta_fail += 1
            results.append({"id": aid, "ok": False, "stage": "meta",
                            "reason": "Meta 조회 오류: %s: %s" % (type(e).__name__, str(e)[:80]),
                            "is_new": False, "advertiser": "", "page_id": ""})
            continue
        if not ads:
            meta_fail += 1
            results.append({"id": aid, "ok": False, "stage": "meta",
                            "reason": "원본 접근 불가(만료·비공개·삭제 또는 권한 필요)",
                            "is_new": False, "advertiser": "", "page_id": ""})
            continue
        # ?id= 페이지는 추천/연관 광고도 같이 반환 → 입력 ID와 정확히 일치하는 광고만 저장(오염 방지)
        target = [a for a in ads if str(a.get("platform_ad_id")) == aid]
        if not target:
            meta_fail += 1
            results.append({"id": aid, "ok": False, "stage": "meta",
                            "reason": "해당 ID 광고 미확인(만료/비공개 가능) — 같은 페이지 광고 %d건은 저장 안 함" % len(ads),
                            "is_new": False, "advertiser": "",
                            "page_id": ads[0].get("page_id") or ""})
            continue
        meta_ok += 1

        # ④ DB 저장
        a = target[0]
        adv, why = resolve_brand(a)
        a["brand_name"] = a.get("brand_name") or adv
        if not _clean_name(a.get("headline")):    # 안내문이 광고 제목으로 굳지 않게
            a["headline"] = ""
        database.ingest_ad_library([a])           # 입력 ID 1건만 적재
        if aid not in database.existing_ad_ids([aid]):
            why = database._blocked_reason(a, database.load_ingest_blocklist()) or "알 수 없음"
            results.append({"id": aid, "ok": False, "stage": "db",
                            "reason": "재수집 차단 규칙으로 저장 안 함(%s)" % why,
                            "is_new": False, "advertiser": adv,
                            "page_id": a.get("page_id") or ""})
            continue
        new_ids.append(aid)
        results.append({"id": aid, "ok": True, "is_new": True, "reason": "신규 수집",
                        "stage": "db", "advertiser": adv, "brand_source": why,
                        "page_id": a.get("page_id") or "",
                        "media": a.get("media_type") or ""})

    _stage("meta", "③ Meta Ad Library 조회", meta_fail == 0,
           "성공 %d건 · 실패 %d건 · 기존보유 %d건" % (meta_ok, meta_fail, len(before)))
    _stage("db", "④ DB 저장", len(new_ids) == meta_ok,
           "신규 저장 %d건%s · 저장위치 %s" % (
               len(new_ids),
               " · 차단 %d건" % (meta_ok - len(new_ids)) if meta_ok != len(new_ids) else "",
               "Supabase 미러(배포본)" if _on_mirror() else "로컬 SQLite"))

    if new_ids and not _on_mirror():
        # 전체 재계산은 로컬(진짜 SQLite)에서만. 배포본에서는 대상이 Supabase 미러라
        # 수만 건을 재계산해봐야 미러 갱신 때 사라지고, 응답만 느려진다.
        database.compute_matches()
        database.regrade()
        database.migrate_brands()

    # ⑤ Supabase 반영
    sb = push_supabase(new_ids)
    _stage("supabase", "⑤ Supabase 반영", sb.get("ok", False), sb.get("detail", ""),
           skipped=bool(sb.get("skipped")))
    if not sb.get("ok"):
        for r in results:
            if r.get("is_new"):
                r["ok"] = False
                r["stage"] = "supabase"
                r["reason"] = "DB 저장은 됐으나 Supabase 반영 실패 — %s" % sb.get("detail", "")
    _emit(results, sb)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python jobs/collect_by_id.py <id> [<id> ...]")
        sys.exit(1)
    main(sys.argv[1:])
