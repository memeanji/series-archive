"""
Series Archive 저장 계층 (SQLite) — 광고 라이브러리 ↔ 소셜 영상 분리 설계.

테이블
  ad_library_ads   : 메타/구글 광고 라이브러리 (게재 정보 — 성과지표 없음)
  social_videos    : TikTok/IG/YouTube 원본 (조회수/좋아요/댓글/공유 — 소셜 반응)
  ad_social_matches: 두 데이터 연결(브랜드/카피·캡션/URL/미디어 유사도 → match_score)
  users            : 로그인 계정

⚠️ 조회수/좋아요/댓글/공유는 '광고 성과'가 아니라 '매칭된 소셜 원본 영상의 반응'이다.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC_THUMBS = ROOT / "static" / "thumbnails"
THUMB_URL_PREFIX = "app/static/thumbnails"
DB_PATH = DATA / "series_archive.db"
LOCAL_DB = DATA / "local_db.json"
USER_STATE = DATA / "user_state.json"

AD_COLS = [
    "id", "brand_name", "ad_title", "ad_copy", "platform", "media_type", "ad_format",
    "thumbnail_url", "video_url", "landing_url", "original_ad_url", "transparency_url",
    "media_url", "preview_url", "status",
    "started_at", "collected_at", "score", "category", "tags",
    "is_bookmarked", "memo", "created_at", "updated_at",
    "scrape_status", "error_message", "platforms", "local_thumbnail_path",
    "script_text", "script_source", "script_status", "script_error_message",
    "script_created_at", "script_updated_at", "cta", "ad_variant_count",
]
SOCIAL_COLS = [
    "id", "brand_name", "platform", "video_id", "embed_url", "title", "channel_title",
    "video_url", "thumbnail_url", "caption",
    "views", "likes", "comments", "shares", "posted_at", "source_url",
    "collected_at", "created_at", "updated_at",
    "brand_match_score", "brand_match_reason", "review_status",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(str(pw).encode("utf-8")).hexdigest()


def get_conn() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(seed_users: Optional[dict] = None) -> None:
    # DB가 없는 환경(예: Streamlit Cloud 첫 실행)이면 번들된 데모 DB로 시드
    if not DB_PATH.exists():
        seed = ROOT / "sample_data" / "demo.db"
        if seed.exists():
            import shutil
            DATA.mkdir(parents=True, exist_ok=True)
            shutil.copy(seed, DB_PATH)
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ad_library_ads (
        id TEXT PRIMARY KEY, brand_name TEXT, ad_title TEXT, ad_copy TEXT,
        platform TEXT, media_type TEXT, ad_format TEXT DEFAULT 'unknown',
        thumbnail_url TEXT, video_url TEXT,
        landing_url TEXT, original_ad_url TEXT, transparency_url TEXT,
        media_url TEXT, preview_url TEXT, status TEXT, started_at TEXT,
        collected_at TEXT, score INTEGER DEFAULT 0, category TEXT, tags TEXT,
        is_bookmarked INTEGER DEFAULT 0, memo TEXT DEFAULT '',
        created_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS social_videos (
        id TEXT PRIMARY KEY, brand_name TEXT, platform TEXT,
        video_id TEXT, embed_url TEXT, title TEXT, channel_title TEXT,
        video_url TEXT, thumbnail_url TEXT, caption TEXT,
        views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, posted_at TEXT,
        source_url TEXT, collected_at TEXT, created_at TEXT, updated_at TEXT,
        absolute_grade TEXT, internal_grade TEXT, final_grade TEXT,
        engagement_rate REAL, engagement_level TEXT, engagement_score REAL,
        internal_percentile REAL, grading_basis TEXT, graded_at TEXT,
        script_text TEXT, script_status TEXT DEFAULT 'none',
        brand_match_score REAL, brand_match_reason TEXT,
        review_status TEXT DEFAULT 'needs_review'
    );
    CREATE TABLE IF NOT EXISTS social_video_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, social_video_id TEXT, snapshot_date TEXT,
        views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, created_at TEXT,
        UNIQUE(social_video_id, snapshot_date)
    );
    CREATE TABLE IF NOT EXISTS ad_social_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_id TEXT, social_id TEXT,
        match_score REAL, brand_match INTEGER, copy_sim REAL, url_sim REAL,
        media_sim REAL, created_at TEXT,
        UNIQUE(ad_id, social_id)
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
        password_hash TEXT, role TEXT DEFAULT 'member', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT UNIQUE,
        search_keywords TEXT, official_domain TEXT, meta_page_name TEXT,
        google_advertiser_name TEXT, youtube_channel_name TEXT, tiktok_handle TEXT,
        instagram_handle TEXT, category TEXT, is_active INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS brand_collection_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, brand_id INTEGER, platform TEXT,
        keyword TEXT, status TEXT, found_count INTEGER DEFAULT 0,
        saved_count INTEGER DEFAULT 0, skipped_count INTEGER DEFAULT 0,
        error_message TEXT, started_at TEXT, finished_at TEXT
    );
    """)
    # 안전한 컬럼 마이그레이션(이미 있으면 건너뜀)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ad_library_ads)").fetchall()]
    for c, t in (("ad_format", "TEXT DEFAULT 'unknown'"), ("transparency_url", "TEXT"),
                 ("media_url", "TEXT"), ("preview_url", "TEXT"), ("brand_id", "INTEGER"),
                 ("scrape_status", "TEXT DEFAULT 'ok'"), ("error_message", "TEXT"),
                 ("platforms", "TEXT"), ("local_thumbnail_path", "TEXT"),
                 ("script_text", "TEXT"), ("script_source", "TEXT"),
                 ("script_status", "TEXT DEFAULT 'pending'"), ("script_error_message", "TEXT"),
                 ("script_created_at", "TEXT"), ("script_updated_at", "TEXT"),
                 ("cta", "TEXT"), ("ad_variant_count", "INTEGER DEFAULT 1")):
        if c not in cols:
            conn.execute(f"ALTER TABLE ad_library_ads ADD COLUMN {c} {t}")
    scols = [r[1] for r in conn.execute("PRAGMA table_info(social_videos)").fetchall()]
    for c, t in (("video_id", "TEXT"), ("embed_url", "TEXT"), ("title", "TEXT"),
                 ("channel_title", "TEXT"),
                 ("absolute_grade", "TEXT"), ("internal_grade", "TEXT"), ("final_grade", "TEXT"),
                 ("engagement_rate", "REAL"), ("engagement_level", "TEXT"),
                 ("engagement_score", "REAL"), ("internal_percentile", "REAL"),
                 ("grading_basis", "TEXT"), ("graded_at", "TEXT"),
                 ("script_text", "TEXT"), ("script_status", "TEXT DEFAULT 'none'"),
                 ("brand_match_score", "REAL"), ("brand_match_reason", "TEXT"),
                 ("review_status", "TEXT DEFAULT 'needs_review'")):
        if c not in scols:
            conn.execute(f"ALTER TABLE social_videos ADD COLUMN {c} {t}")
    conn.commit()

    # 계정 동기화(secrets.toml 단일 소스)
    if seed_users is not None:
        for uname, pw in seed_users.items():
            if conn.execute("SELECT 1 FROM users WHERE username=?", (uname,)).fetchone():
                conn.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_pw(pw), uname))
            else:
                conn.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                             (uname, hash_pw(pw), "admin" if uname == "admin" else "member", _now()))
        if seed_users:
            qs = ",".join("?" * len(seed_users))
            conn.execute(f"DELETE FROM users WHERE username NOT IN ({qs})", tuple(seed_users.keys()))
        conn.commit()

    _fix_google_urls(conn)
    # 구버전 ads 테이블 → ad_library_ads 이관(최초 1회)
    if conn.execute("SELECT COUNT(*) FROM ad_library_ads").fetchone()[0] == 0:
        _migrate_legacy(conn)
    conn.commit()
    conn.close()
    migrate_base64_thumbnails()
    migrate_brands()


def _migrate_legacy(conn: sqlite3.Connection) -> int:
    has_old = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ads'").fetchone()
    if not has_old:
        return 0
    n = 0
    for r in conn.execute("SELECT * FROM ads").fetchall():
        a = dict(r)
        aid = a["id"]
        plat = a.get("platform")
        orig = (f"https://www.facebook.com/ads/library/?id={aid}" if plat == "meta" else "")
        row = {
            "id": aid, "brand_name": a.get("brand_name"), "ad_title": a.get("ad_title"),
            "ad_copy": a.get("ad_copy"), "platform": plat, "media_type": a.get("media_type"),
            "ad_format": a.get("media_type") or "unknown",
            "thumbnail_url": a.get("thumbnail_url"), "video_url": a.get("video_url"),
            "landing_url": a.get("landing_url"), "original_ad_url": orig,
            "transparency_url": "", "media_url": "", "preview_url": a.get("thumbnail_url") or "",
            "status": a.get("status"), "started_at": "",
            "collected_at": a.get("collected_at"), "score": a.get("score") or 0,
            "category": a.get("category"), "tags": a.get("tags") or "[]",
            "is_bookmarked": a.get("is_bookmarked") or 0, "memo": a.get("memo") or "",
            "created_at": a.get("created_at") or _now(), "updated_at": _now(),
            "scrape_status": "ok", "error_message": "", "platforms": "",
            "local_thumbnail_path": a.get("thumbnail_url") or "",
            "script_text": "", "script_source": "", "script_status": "pending",
            "script_error_message": "", "script_created_at": "", "script_updated_at": "", "cta": "",
            "ad_variant_count": 1,
        }
        conn.execute(f"INSERT OR REPLACE INTO ad_library_ads({','.join(AD_COLS)}) "
                     f"VALUES({','.join(['?']*len(AD_COLS))})", tuple(row[c] for c in AD_COLS))
        n += 1
    conn.commit()
    return n


def migrate_base64_thumbnails() -> int:
    """DB에 박힌 base64 썸네일 → static 파일로 빼고 URL만 남김(렌더 성능)."""
    import base64
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, thumbnail_url FROM ad_library_ads WHERE thumbnail_url LIKE 'data:image%'"
    ).fetchall()
    if not rows:
        conn.close()
        return 0
    STATIC_THUMBS.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        try:
            data = base64.b64decode(r["thumbnail_url"].split(",", 1)[-1])
        except Exception:  # noqa: BLE001
            continue
        safe = "".join(ch for ch in r["id"] if ch.isalnum() or ch in "_-")
        (STATIC_THUMBS / f"{safe}.png").write_bytes(data)
        conn.execute("UPDATE ad_library_ads SET thumbnail_url=?, preview_url=? WHERE id=?",
                     (f"{THUMB_URL_PREFIX}/{safe}.png", f"{THUMB_URL_PREFIX}/{safe}.png", r["id"]))
        n += 1
    conn.commit()
    conn.close()
    return n


# ── 탭별 페이지 조회(요약 컬럼만, SQL LIMIT/OFFSET) ──────
_SUMMARY_COLS = (
    "a.id, a.brand_name, a.ad_title, substr(a.ad_copy,1,90) AS ad_copy_short, "
    "a.platform, a.status, a.thumbnail_url, a.preview_url, a.video_url, a.score, "
    "a.media_type, a.ad_format, a.collected_at, a.started_at, a.is_bookmarked, "
    "a.scrape_status, a.error_message, a.platforms, "
    "(CASE WHEN length(a.memo)>0 THEN 1 ELSE 0 END) AS has_memo, "
    "m.match_score AS match_score, s.final_grade AS social_final_grade, "
    "s.views AS social_views, s.likes AS social_likes, "
    "s.engagement_score AS social_engagement_score, s.platform AS social_platform, "
    "COUNT(*) AS dup_rows, MAX(a.ad_variant_count) AS variant_count"
)
_JOIN = (" FROM ad_library_ads a "
         "LEFT JOIN (SELECT ad_id, social_id, match_score, "
         "ROW_NUMBER() OVER (PARTITION BY ad_id ORDER BY match_score DESC, social_id) rn "
         "FROM ad_social_matches) m ON m.ad_id=a.id AND m.rn=1 "
         "LEFT JOIN social_videos s ON s.id=m.social_id")

_GRADE_SET = {"S급": "('S')", "A급 이상": "('S','A')", "B급 이상": "('S','A','B')",
              "C급 이상": "('S','A','B','C')"}


def _where(tab: str, f: dict) -> tuple[str, list]:
    w, p = ["1=1"], []
    if tab in ("meta", "google"):
        w.append("a.platform=?"); p.append(tab)
    if tab == "TOP":
        w.append("s.final_grade IN ('S','A','B')")
        w.append("(a.thumbnail_url<>'' OR a.video_url<>'')")  # placeholder 카드 제외
        w.append("a.ad_format NOT IN ('search_text','unknown')")
    if not f.get("show_hidden"):
        w.append("a.ad_format NOT IN ('search_text','unknown')")
        w.append("(a.thumbnail_url<>'' OR a.video_url<>'')")
    if f.get("brand") and f["brand"] != "전체":
        w.append("a.brand_name=?"); p.append(f["brand"])
    if f.get("platforms"):
        w.append("a.platform IN (%s)" % ",".join("?" * len(f["platforms"]))); p += f["platforms"]
    if f.get("media"):
        w.append("a.media_type IN (%s)" % ",".join("?" * len(f["media"]))); p += f["media"]
    st_ = f.get("status")
    if st_ == "라이브":
        w.append("a.status='live'")
    elif st_ == "종료":
        w.append("a.status IN ('ended','inactive')")
    elif st_ == "OFF":
        w.append("a.status<>'live'")
    if f.get("only_bookmark"):
        w.append("a.is_bookmarked=1")
    if f.get("grade") and f["grade"] in _GRADE_SET:
        w.append(f"s.final_grade IN {_GRADE_SET[f['grade']]}")
    if f.get("search"):
        w.append("(a.brand_name LIKE ? OR a.ad_title LIKE ? OR a.ad_copy LIKE ?)")
        p += [f"%{f['search']}%"] * 3
    return " AND ".join(w), p


def _order(tab: str, sort: str) -> str:
    rank = ("CASE s.final_grade WHEN 'S' THEN 4 WHEN 'A' THEN 3 WHEN 'B' THEN 2 "
            "WHEN 'C' THEN 1 ELSE 0 END")
    if tab == "TOP" or sort == "🔥 터진순(추천)":
        return (f"ORDER BY {rank} DESC, s.engagement_score DESC NULLS LAST, "
                "s.views DESC NULLS LAST, a.collected_at DESC")
    empty_last = "(a.started_at='' OR a.started_at IS NULL) ASC"
    return {
        "조회수 높은순(소셜)": "ORDER BY s.views DESC NULLS LAST",
        "최근 수집순": "ORDER BY a.collected_at DESC",
        "오래된순": "ORDER BY a.collected_at ASC",
        "게재기간 긴순": f"ORDER BY {empty_last}, a.started_at ASC",   # 오래 게재(시작 이른 순)
        "게재기간 짧은순": f"ORDER BY {empty_last}, a.started_at DESC",  # 최근 게재
        "저장 많은순": "ORDER BY a.is_bookmarked DESC, a.score DESC",
    }.get(sort, "ORDER BY a.collected_at DESC")


# 같은 크리에이티브+문구를 쓰는 A/B 변형을 1개로 묶는다(브랜드+매체+카피 시그니처).
# 카피가 비면(구글 등) 영상URL>썸네일>id 로 폴백 → 과합치기 방지.
_DEDUP = ("a.brand_name || '|' || a.media_type || '|' || "
          "COALESCE(NULLIF(TRIM(a.ad_copy),''), NULLIF(a.video_url,''), "
          "NULLIF(a.thumbnail_url,''), a.id)")


def count_ads(tab: str, f: dict) -> int:
    where, p = _where(tab, f)
    conn = get_conn()
    n = conn.execute(f"SELECT COUNT(DISTINCT {_DEDUP}) {_JOIN} WHERE {where}", p).fetchone()[0]
    conn.close()
    return n


def load_ads_page(tab: str, f: dict, page: int = 1, page_size: int = 12) -> list[dict]:
    where, p = _where(tab, f)
    order = _order(tab, f.get("sort", ""))
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {_SUMMARY_COLS} {_JOIN} WHERE {where} "
        f"GROUP BY {_DEDUP} {order} LIMIT ? OFFSET ?",
        p + [page_size, max(0, (page - 1) * page_size)]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ad_full(ad_id: str) -> Optional[dict]:
    """상세 모달용 — 1건 전체 + 매칭 소셜 + 등급."""
    conn = get_conn()
    r = conn.execute(f"SELECT a.*, m.match_score AS match_score, s.id AS social_id, "
                     "s.views AS social_views, s.likes AS social_likes, "
                     "s.comments AS social_comments, s.shares AS social_shares, "
                     "s.source_url AS social_source_url, s.platform AS social_platform, "
                     "s.engagement_rate AS social_engagement_rate, "
                     "s.engagement_level AS social_engagement_level, "
                     "s.absolute_grade AS social_absolute_grade, "
                     "s.internal_grade AS social_internal_grade, "
                     "s.final_grade AS social_final_grade, "
                     "s.internal_percentile AS social_internal_percentile, "
                     "s.grading_basis AS social_grading_basis "
                     f"{_JOIN} WHERE a.id=?", (ad_id,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except Exception:  # noqa: BLE001
        d["tags"] = []
    return d


# ── 브랜드 ───────────────────────────────────────────────
def migrate_brands() -> int:
    """ad_library_ads + social_videos 의 brand_name 기준으로 brands 생성 + brand_id 채움."""
    conn = get_conn()
    # 잘못 저장된 URL brand_name 정리(소셜)
    conn.execute("UPDATE social_videos SET brand_name='(미상)' "
                 "WHERE brand_name LIKE 'http%' OR brand_name LIKE '%/%'")
    names = set()
    for tbl in ("ad_library_ads", "social_videos"):
        for r in conn.execute(f"SELECT DISTINCT brand_name FROM {tbl} WHERE brand_name<>''").fetchall():
            nm = (r[0] or "").strip()
            if nm and nm != "(미상)" and not nm.lower().startswith("http"):
                names.add(nm)
    n = 0
    for nm in names:
        if not conn.execute("SELECT 1 FROM brands WHERE display_name=?", (nm,)).fetchone():
            conn.execute("INSERT INTO brands(display_name, search_keywords, is_active, "
                         "created_at, updated_at) VALUES(?,?,?,?,?)",
                         (nm, json.dumps([nm], ensure_ascii=False), 1, _now(), _now()))
            n += 1
    conn.execute("UPDATE ad_library_ads SET brand_id=("
                 "SELECT id FROM brands WHERE brands.display_name=ad_library_ads.brand_name) "
                 "WHERE brand_id IS NULL")
    conn.commit()
    conn.close()
    return n


def brand_exists(display_name: str) -> bool:
    conn = get_conn()
    r = conn.execute("SELECT 1 FROM brands WHERE display_name=?", (display_name,)).fetchone()
    conn.close()
    return bool(r)


def add_brand(display_name: str, keywords: list, official_domain: str = "",
              category: str = "", extra: Optional[dict] = None) -> int:
    """있으면 갱신(upsert): 법인명/도메인/카테고리 채우고 키워드 병합."""
    extra = extra or {}
    conn = get_conn()
    exist = conn.execute("SELECT id, search_keywords FROM brands WHERE display_name=?",
                         (display_name,)).fetchone()
    kws = list(dict.fromkeys(keywords))
    gadv = extra.get("google_advertiser_name", "")
    if exist:
        try:
            kws = list(dict.fromkeys((json.loads(exist["search_keywords"] or "[]")) + kws))
        except Exception:  # noqa: BLE001
            pass
        sets, vals = ["search_keywords=?", "updated_at=?"], [json.dumps(kws, ensure_ascii=False), _now()]
        if official_domain:
            sets.append("official_domain=?"); vals.append(official_domain)
        if category:
            sets.append("category=?"); vals.append(category)
        if gadv:
            sets.append("google_advertiser_name=?"); vals.append(gadv)
        vals.append(display_name)
        conn.execute(f"UPDATE brands SET {','.join(sets)} WHERE display_name=?", vals)
        rid = exist["id"]
    else:
        conn.execute(
            "INSERT INTO brands(display_name, search_keywords, official_domain, "
            "meta_page_name, google_advertiser_name, youtube_channel_name, tiktok_handle, "
            "instagram_handle, category, is_active, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,1,?,?)",
            (display_name, json.dumps(kws, ensure_ascii=False),
             official_domain, extra.get("meta_page_name", ""), gadv,
             extra.get("youtube_channel_name", ""), extra.get("tiktok_handle", ""),
             extra.get("instagram_handle", ""), category, _now(), _now()))
        rid = conn.execute("SELECT id FROM brands WHERE display_name=?", (display_name,)).fetchone()[0]
    conn.commit()
    conn.close()
    return rid


def get_brand_keywords(display_name: str) -> list:
    conn = get_conn()
    r = conn.execute("SELECT search_keywords FROM brands WHERE display_name=?",
                     (display_name,)).fetchone()
    conn.close()
    if not r:
        return [display_name]
    try:
        return json.loads(r[0]) or [display_name]
    except Exception:  # noqa: BLE001
        return [display_name]


def find_brand_candidates(query: str, domain: str = "", keywords: Optional[list] = None) -> list[dict]:
    """이미 수집된 데이터(ad_library_ads/social_videos)에서 후보 검색. 크롤 안 함."""
    terms = [t.strip() for t in ([query] + (keywords or [])) if t and t.strip()]
    if not terms and not domain:
        return []
    conn = get_conn()
    cand: dict = {}

    def add(name, source, reason, count, thumb):
        if not name:
            return
        c = cand.setdefault(name, {"name": name, "sources": set(), "reasons": set(),
                                   "ad_count": 0, "thumbs": []})
        c["sources"].add(source)
        c["reasons"].add(reason)
        c["ad_count"] = max(c["ad_count"], count)
        if thumb and len(c["thumbs"]) < 3:
            c["thumbs"].append(thumb)

    like = " OR ".join(["brand_name LIKE ?"] * len(terms)) or "0"
    params = [f"%{t}%" for t in terms]
    if terms:
        for r in conn.execute(
                f"SELECT brand_name, platform, COUNT(*) n, "
                "MAX(thumbnail_url) th FROM ad_library_ads "
                f"WHERE {like} GROUP BY brand_name, platform", params).fetchall():
            add(r["brand_name"], r["platform"] or "DB", "브랜드명 유사", r["n"], r["th"])
        for r in conn.execute(
                f"SELECT brand_name, platform, COUNT(*) n, MAX(thumbnail_url) th "
                f"FROM social_videos WHERE {like} GROUP BY brand_name, platform", params).fetchall():
            add(r["brand_name"], r["platform"] or "social", "브랜드명 유사", r["n"], r["th"])
    if domain:
        d = domain.replace("https://", "").replace("http://", "").split("/")[0]
        for r in conn.execute(
                "SELECT brand_name, platform, COUNT(*) n, MAX(thumbnail_url) th "
                "FROM ad_library_ads WHERE landing_url LIKE ? GROUP BY brand_name, platform",
                (f"%{d}%",)).fetchall():
            add(r["brand_name"], r["platform"] or "DB", f"도메인 일치({d})", r["n"], r["th"])
    conn.close()
    out = [{**c, "sources": sorted(c["sources"]), "reasons": sorted(c["reasons"])}
           for c in cand.values()]
    return sorted(out, key=lambda x: -x["ad_count"])


def log_brand_collection(brand_id: int, platform: str, keyword: str, status: str,
                         found: int = 0, saved: int = 0, skipped: int = 0,
                         error: str = "", started: str = "", finished: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO brand_collection_logs(brand_id, platform, keyword, status, found_count, "
        "saved_count, skipped_count, error_message, started_at, finished_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (brand_id, platform, keyword, status, found, saved, skipped, error,
         started or _now(), finished or _now()))
    conn.commit()
    conn.close()


def latest_brand_status(display_name: str) -> Optional[dict]:
    conn = get_conn()
    r = conn.execute(
        "SELECT l.status, l.finished_at FROM brand_collection_logs l "
        "JOIN brands b ON b.id=l.brand_id WHERE b.display_name=? "
        "ORDER BY l.id DESC LIMIT 1", (display_name,)).fetchone()
    conn.close()
    return dict(r) if r else None


def filter_options() -> dict:
    conn = get_conn()
    plats = [r[0] for r in conn.execute(
        "SELECT DISTINCT platform FROM ad_library_ads WHERE platform<>''").fetchall()]
    media = [r[0] for r in conn.execute(
        "SELECT DISTINCT media_type FROM ad_library_ads WHERE media_type<>''").fetchall()]
    cats: set = set()
    for r in conn.execute("SELECT tags FROM ad_library_ads WHERE tags NOT IN ('','[]') "
                          "AND tags IS NOT NULL").fetchall():
        try:
            cats.update(json.loads(r[0]))
        except Exception:  # noqa: BLE001
            pass
    conn.close()
    return {"platforms": sorted(plats), "media": sorted(media), "categories": sorted(cats)}


def brand_counts() -> list[dict]:
    """등록 브랜드 전체. 📺소셜수는 approved 기준 + needs/rejected 별도(툴팁용)."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.display_name,
          (SELECT COUNT(*) FROM ad_library_ads a WHERE a.brand_name=b.display_name) ad_n,
          (SELECT COALESCE(MAX(CASE WHEN a.status='live' THEN 1 ELSE 0 END),0)
             FROM ad_library_ads a WHERE a.brand_name=b.display_name) live,
          (SELECT COUNT(*) FROM social_videos s WHERE s.brand_name=b.display_name
             AND s.review_status='approved') soc_ok,
          (SELECT COUNT(*) FROM social_videos s WHERE s.brand_name=b.display_name
             AND s.review_status='needs_review') soc_rev,
          (SELECT COUNT(*) FROM social_videos s WHERE s.brand_name=b.display_name
             AND s.review_status='rejected') soc_rej
        FROM brands b WHERE b.is_active=1
        ORDER BY (ad_n + soc_ok + soc_rev) DESC, b.display_name
    """).fetchall()
    conn.close()
    return [{"name": r["display_name"], "ad": r["ad_n"], "live": r["live"],
             "approved": r["soc_ok"], "needs": r["soc_rev"], "rejected": r["soc_rej"]}
            for r in rows]


def brand_diagnostics() -> list[dict]:
    """브랜드별 수집/매칭 상태 진단(읽기 전용). 0건 원인 분류 포함."""
    conn = get_conn()
    out = []
    for b in conn.execute("SELECT * FROM brands WHERE is_active=1").fetchall():
        bn, bid = b["display_name"], b["id"]
        ad = conn.execute("SELECT COUNT(*) FROM ad_library_ads WHERE brand_name=?", (bn,)).fetchone()[0]
        sc = conn.execute(
            "SELECT review_status, COUNT(*) n FROM social_videos WHERE brand_name=? "
            "GROUP BY review_status", (bn,)).fetchall()
        scd = {r["review_status"]: r["n"] for r in sc}
        ap, rv, rj = scd.get("approved", 0), scd.get("needs_review", 0), scd.get("rejected", 0)
        logs = conn.execute(
            "SELECT platform, SUM(found_count) f, SUM(saved_count) s, COUNT(*) tries "
            "FROM brand_collection_logs WHERE brand_id=? GROUP BY platform", (bid,)).fetchall()
        plat = {r["platform"]: {"found": r["f"] or 0, "saved": r["s"] or 0, "tries": r["tries"]}
                for r in logs}
        has_kw = len((b["search_keywords"] or "[]")) > 4
        has_official = any(b[k] for k in ("official_domain", "youtube_channel_name",
                                          "tiktok_handle", "instagram_handle", "meta_page_name"))
        total = ap + rv + rj
        if (ap + ad) > 0:
            cause = "ok"                       # 광고 있거나 소셜 승인 있으면 정상
        elif not logs and total == 0:
            cause = "not_collected"
        elif total == 0:
            cause = "no_result"
        elif rv > 0:
            cause = "needs_review_only"
        elif rj > 0:
            cause = "rejected_only"
        else:
            cause = "unknown"
        action = {
            "not_collected": "수집 미실행 → '소량 재수집' 또는 jobs/crawl_brand.py 실행",
            "no_result": "검색어/핸들 부족 가능 → search_keywords 확장",
            "needs_review_only": "데이터 있음(승인 전) → 소셜탭 '검토 필요 포함' 후 '이 브랜드 맞음' 승인 / 공식핸들 등록 시 자동승인",
            "rejected_only": "영상이 브랜드와 무관 판정 → 공식 채널/도메인 등록 또는 키워드 정확화",
            "ok": "정상", "unknown": "확인 필요",
        }[cause]
        out.append({
            "브랜드": bn, "광고": ad, "소셜승인": ap, "검토필요": rv, "제외": rj,
            "Meta": f"{plat.get('meta',{}).get('saved',0)}/{plat.get('meta',{}).get('found',0)}" if 'meta' in plat else "-",
            "Google": f"{plat.get('google',{}).get('saved',0)}/{plat.get('google',{}).get('found',0)}" if 'google' in plat else "-",
            "YouTube": f"{plat.get('youtube',{}).get('saved',0)}/{plat.get('youtube',{}).get('found',0)}" if 'youtube' in plat else "-",
            "키워드": "O" if has_kw else "부족", "공식정보": "O" if has_official else "없음",
            "원인": cause, "조치": action,
        })
    conn.close()
    out.sort(key=lambda x: (x["원인"] != "ok", -(x["광고"] + x["소셜승인"])))
    return out


def insight_summary() -> dict:
    conn = get_conn()
    r = conn.execute(
        "SELECT COUNT(*) total, "
        "SUM(CASE WHEN media_type='video' THEN 1 ELSE 0 END) videos, "
        "SUM(CASE WHEN status='live' THEN 1 ELSE 0 END) live, "
        "SUM(is_bookmarked) bm FROM ad_library_ads").fetchone()
    conn.close()
    return {"total": r["total"] or 0, "videos": r["videos"] or 0,
            "live": r["live"] or 0, "bm": r["bm"] or 0}


def _fix_google_urls(conn: sqlite3.Connection) -> int:
    """기존 google 행의 상대경로/localhost transparency URL 을 절대 URL 로 교정."""
    from services.urls import normalize_google_transparency_url as N
    rows = conn.execute(
        "SELECT id, original_ad_url, transparency_url FROM ad_library_ads "
        "WHERE platform='google'").fetchall()
    fixed = 0
    for r in rows:
        cur = (r["transparency_url"] or "") or (r["original_ad_url"] or "")
        good = N(cur)
        if good and good != (r["transparency_url"] or ""):
            conn.execute("UPDATE ad_library_ads SET transparency_url=?, original_ad_url=? WHERE id=?",
                         (good, good, r["id"]))
            fixed += 1
    if fixed:
        conn.commit()
    return fixed


# ── 적재 ─────────────────────────────────────────────────
def _quick_score(ad: dict) -> int:
    s = 40
    if ad.get("media_type") == "video":
        s += 25
    if ad.get("status") == "live":
        s += 20
    if ad.get("thumbnail_url"):
        s += 10
    if len((ad.get("ad_copy") or ad.get("ad_text") or "")) > 40:
        s += 10
    return max(0, min(100, s))


def ingest_ad_library(ads: list[dict]) -> int:
    conn = get_conn()
    n = 0
    for a in ads:
        aid = a.get("id") or a.get("platform_ad_id")
        if not aid:
            continue
        tags = a.get("tags") or (a.get("hook_tags") or []) + (a.get("format_tags") or [])
        prev = conn.execute("SELECT * FROM ad_library_ads WHERE id=?", (aid,)).fetchone()
        prev = dict(prev) if prev else None
        row = {
            "id": aid, "brand_name": a.get("brand_name") or a.get("advertiser_name") or "(미상)",
            "ad_title": a.get("ad_title") or a.get("headline") or "",
            "ad_copy": a.get("ad_copy") or a.get("ad_text") or "",
            "platform": a.get("platform") or "", "media_type": a.get("media_type") or "unknown",
            "ad_format": a.get("ad_format") or a.get("media_type") or "unknown",
            "thumbnail_url": a.get("thumbnail_url") or "", "video_url": a.get("video_url") or "",
            "landing_url": a.get("landing_url") or "", "original_ad_url": a.get("original_ad_url") or "",
            "transparency_url": a.get("transparency_url") or "", "media_url": a.get("media_url") or "",
            "preview_url": a.get("preview_url") or "",
            "status": a.get("status") or "live", "started_at": a.get("started_at") or a.get("first_seen") or "",
            "collected_at": str(a.get("collected_at") or _now())[:19],
            "score": (prev["score"] if prev and prev["score"] else _quick_score(a)),
            "category": (a.get("format_tags") or ["기타"])[0] if a.get("format_tags") else "기타",
            "tags": json.dumps(tags, ensure_ascii=False),
            "is_bookmarked": prev["is_bookmarked"] if prev else 0,
            "memo": prev["memo"] if prev else "",
            "created_at": a.get("created_at") or _now(), "updated_at": _now(),
            "scrape_status": a.get("scrape_status") or "ok",
            "error_message": a.get("error_message") or "",
            "platforms": a.get("platforms") or "",
            "local_thumbnail_path": a.get("local_thumbnail_path") or "",
            # 재수집 시 생성된 스크립트는 보존
            "script_text": (prev or {}).get("script_text") or "",
            "script_source": (prev or {}).get("script_source") or "",
            "script_status": (prev or {}).get("script_status") or "pending",
            "script_error_message": (prev or {}).get("script_error_message") or "",
            "script_created_at": (prev or {}).get("script_created_at") or "",
            "script_updated_at": (prev or {}).get("script_updated_at") or "",
            "cta": a.get("cta") or (prev or {}).get("cta") or "",
            "ad_variant_count": max(int(a.get("ad_variant_count") or 1),
                                    int((prev or {}).get("ad_variant_count") or 1)),
        }
        conn.execute(f"INSERT OR REPLACE INTO ad_library_ads({','.join(AD_COLS)}) "
                     f"VALUES({','.join(['?']*len(AD_COLS))})", tuple(row[c] for c in AD_COLS))
        n += 1
    conn.commit()
    conn.close()
    return n


def get_brand(display_name: str) -> Optional[dict]:
    conn = get_conn()
    r = conn.execute("SELECT * FROM brands WHERE display_name=?", (display_name,)).fetchone()
    conn.close()
    return dict(r) if r else None


def ingest_social_videos(vids: list[dict], from_keyword_search: bool = True) -> int:
    """저장 전 브랜드 검증 점수 계산. 브랜드명/키워드가 전혀 없으면 저장 제외."""
    import services.brand_match as BM
    conn = get_conn()
    brand_cache: dict = {}
    n = 0
    for v in vids:
        vid = v.get("id") or v.get("video_id")
        if not vid:
            continue
        bn = v.get("brand_name") or "(미상)"
        if bn not in brand_cache:
            br = conn.execute("SELECT * FROM brands WHERE display_name=?", (bn,)).fetchone()
            brand_cache[bn] = dict(br) if br else {"display_name": bn,
                                                   "search_keywords": json.dumps([bn])}
        m = BM.score(v, brand_cache[bn], from_keyword_search=from_keyword_search)
        if not m["keep"]:
            continue   # 브랜드명/키워드/공식일치 전혀 없음 → 저장 안 함
        row = {
            "id": str(vid), "brand_name": bn,
            "platform": v.get("platform") or "tiktok",
            "video_id": v.get("video_id") or "", "embed_url": v.get("embed_url") or "",
            "title": v.get("title") or "", "channel_title": v.get("channel_title") or "",
            "video_url": v.get("video_url") or "",
            "thumbnail_url": v.get("thumbnail_url") or "", "caption": v.get("caption") or "",
            "views": int(v.get("views") or 0), "likes": int(v.get("likes") or 0),
            "comments": int(v.get("comments") or 0), "shares": int(v.get("shares") or 0),
            "posted_at": v.get("posted_at") or "", "source_url": v.get("source_url") or "",
            "collected_at": str(v.get("collected_at") or _now())[:19],
            "created_at": _now(), "updated_at": _now(),
            "brand_match_score": m["score"], "brand_match_reason": m["reason"],
            "review_status": m["status"],
        }
        conn.execute(f"INSERT OR REPLACE INTO social_videos({','.join(SOCIAL_COLS)}) "
                     f"VALUES({','.join(['?']*len(SOCIAL_COLS))})", tuple(row[c] for c in SOCIAL_COLS))
        n += 1
    conn.commit()
    conn.close()
    return n


def recompute_brand_match() -> dict:
    """기존 social_videos 전체 brand_match 재계산 + review_status 갱신."""
    import services.brand_match as BM
    conn = get_conn()
    socials = [dict(r) for r in conn.execute("SELECT * FROM social_videos").fetchall()]
    brands = {r["display_name"]: dict(r) for r in conn.execute("SELECT * FROM brands").fetchall()}
    stat = {"approved": 0, "needs_review": 0, "rejected": 0}
    for v in socials:
        br = brands.get(v.get("brand_name")) or {"display_name": v.get("brand_name"),
                                                 "search_keywords": json.dumps([v.get("brand_name")])}
        m = BM.score(v, br, from_keyword_search=True)
        conn.execute("UPDATE social_videos SET brand_match_score=?, brand_match_reason=?, "
                     "review_status=?, updated_at=? WHERE id=?",
                     (m["score"], m["reason"], m["status"], _now(), v["id"]))
        stat[m["status"]] = stat.get(m["status"], 0) + 1
    conn.commit()
    conn.close()
    return stat


def update_review_status(social_id: str, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE social_videos SET review_status=?, updated_at=? WHERE id=?",
                 (status, _now(), social_id))
    conn.commit()
    conn.close()


def move_social_brand(social_id: str, new_brand: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE social_videos SET brand_name=?, updated_at=? WHERE id=?",
                 (new_brand, _now(), social_id))
    conn.commit()
    conn.close()


# ── 매칭 ─────────────────────────────────────────────────
def compute_matches(threshold: float = 30.0) -> int:
    """광고↔소셜 영상 매칭. 브랜드명만 같은 건 '같은 광고'가 아니므로 제외하고,
    카피/랜딩 토큰이 영상 캡션과 실제로 일치(창작물 수준 확인)될 때만 연결한다.
    → 확인 안 되는 '원본 영상 보기' 링크가 붙지 않는다."""
    import services.matching as M
    conn = get_conn()
    ads = [dict(r) for r in conn.execute("SELECT * FROM ad_library_ads").fetchall()]
    socials = [dict(r) for r in conn.execute("SELECT * FROM social_videos").fetchall()]
    conn.execute("DELETE FROM ad_social_matches")
    n = 0
    by_brand: dict = {}
    for s in socials:
        by_brand.setdefault(s.get("brand_name"), []).append(s)
    for ad in ads:
        # 구글 투명성센터 광고는 카피·랜딩이 없어 영상 단위 확인 불가 → 유튜브 매칭 안 함(트렌드만).
        if (ad.get("platform") or "") == "google":
            continue
        for s in by_brand.get(ad.get("brand_name"), []):
            r = M.match(ad, s)
            # 창작물 수준 확인: 랜딩 상품토큰이 캡션에 있거나(url_sim≈1) 카피가 상당히 유사할 때만.
            # 브랜드명만 일치(copy/url 0)하는 매칭은 버린다 → 엉뚱한 유튜브 연결 방지.
            confirmed = r["brand_match"] and (r["url_sim"] >= 0.6
                                              or r["copy_sim"] >= 0.5
                                              or r["media_sim"] >= 0.5)
            if confirmed and r["match_score"] >= threshold:
                conn.execute(
                    "INSERT OR REPLACE INTO ad_social_matches"
                    "(ad_id,social_id,match_score,brand_match,copy_sim,url_sim,media_sim,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (ad["id"], s["id"], r["match_score"], r["brand_match"],
                     r["copy_sim"], r["url_sim"], r["media_sim"], _now()))
                n += 1
    conn.commit()
    conn.close()
    return n


# ── 조회 ─────────────────────────────────────────────────
def add_snapshot(social_video_id: str, views, likes, comments, shares) -> None:
    """일자별 지표 스냅샷(같은 날짜면 갱신)."""
    from datetime import date
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO social_video_snapshots"
        "(social_video_id,snapshot_date,views,likes,comments,shares,created_at) VALUES(?,?,?,?,?,?,?)",
        (social_video_id, date.today().isoformat(), int(views or 0), int(likes or 0),
         int(comments or 0), int(shares or 0), _now()))
    conn.commit()
    conn.close()


def get_snapshots(social_video_id: str, days: int = 7) -> list[dict]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM social_video_snapshots WHERE social_video_id=? "
        "ORDER BY snapshot_date DESC LIMIT ?", (social_video_id, days)).fetchall()]
    conn.close()
    return list(reversed(rows))


def link_ad_social(ad_id: str, social_id: str, score: float = 100.0) -> None:
    """수동으로 광고↔소셜 영상 연결."""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ad_social_matches"
        "(ad_id,social_id,match_score,brand_match,copy_sim,url_sim,media_sim,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (ad_id, social_id, score, 1, 0.0, 0.0, 0.0, _now()))
    conn.commit()
    conn.close()


def update_script(social_id: str, text: str, status: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE social_videos SET script_text=?, script_status=?, updated_at=? WHERE id=?",
                 (text, status, _now(), social_id))
    conn.commit()
    conn.close()


def get_social(social_id: str) -> Optional[dict]:
    conn = get_conn()
    r = conn.execute("SELECT * FROM social_videos WHERE id=?", (social_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def social_count() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM social_videos").fetchone()[0]
    conn.close()
    return n


def brand_youtube_summary(brand_name: str) -> dict:
    """브랜드 단위 유튜브 존재 여부 — '이 브랜드가 유튜브에도 광고/영상을 돌리는지'.
    (특정 광고↔영상 1:1 매칭이 아니라 브랜드 차원의 참고용)"""
    out = {"count": 0, "max_views": 0, "top": None, "videos": []}
    if not brand_name:
        return out
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, title, source_url, views, likes, thumbnail_url, final_grade, posted_at "
        "FROM social_videos WHERE brand_name=? AND platform='youtube' "
        "ORDER BY views DESC", (brand_name,)).fetchall()]
    conn.close()
    out["count"] = len(rows)
    out["videos"] = rows[:6]
    if rows:
        out["max_views"] = int(rows[0].get("views") or 0)
        out["top"] = rows[0]
    return out


def regrade() -> int:
    """social_videos 전체 재등급(절대→내부분위수). ingest 후 호출."""
    import services.grading as G
    conn = get_conn()
    socials = [dict(r) for r in conn.execute("SELECT * FROM social_videos").fetchall()]
    if not socials:
        conn.close()
        return 0
    G.grade_all(socials, now_iso=_now())
    for v in socials:
        conn.execute(
            "UPDATE social_videos SET absolute_grade=?, internal_grade=?, final_grade=?, "
            "engagement_rate=?, engagement_level=?, engagement_score=?, internal_percentile=?, "
            "grading_basis=?, graded_at=? WHERE id=?",
            (v.get("absolute_grade"), v.get("internal_grade"), v.get("final_grade"),
             v.get("engagement_rate"), v.get("engagement_level"), v.get("engagement_score"),
             v.get("internal_percentile"), v.get("grading_basis"), v.get("graded_at"), v["id"]))
    conn.commit()
    conn.close()
    return len(socials)


def load_ad_library() -> list[dict]:
    """각 광고에 최고 매칭 소셜 영상의 반응지표·등급을 social_* 로 붙여 반환."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, m.match_score AS match_score,
               s.views AS social_views, s.likes AS social_likes,
               s.comments AS social_comments, s.shares AS social_shares,
               s.video_url AS social_video_url, s.source_url AS social_source_url,
               s.platform AS social_platform, s.engagement_rate AS social_engagement_rate,
               s.engagement_level AS social_engagement_level,
               s.absolute_grade AS social_absolute_grade, s.internal_grade AS social_internal_grade,
               s.final_grade AS social_final_grade, s.engagement_score AS social_engagement_score,
               s.internal_percentile AS social_internal_percentile,
               s.grading_basis AS social_grading_basis
        FROM ad_library_ads a
        LEFT JOIN ad_social_matches m ON m.ad_id=a.id AND m.match_score=(
            SELECT MAX(match_score) FROM ad_social_matches WHERE ad_id=a.id)
        LEFT JOIN social_videos s ON s.id=m.social_id
    """).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except Exception:  # noqa: BLE001
            d["tags"] = []
        out.append(d)
    return out


def load_social_videos() -> list[dict]:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM social_videos ORDER BY views DESC").fetchall()]
    conn.close()
    return rows


def verify_user(username: str, password: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return bool(row) and row["password_hash"] == hash_pw(password)


def update_bookmark(ad_id: str, value: bool) -> None:
    conn = get_conn()
    conn.execute("UPDATE ad_library_ads SET is_bookmarked=?, updated_at=? WHERE id=?",
                 (1 if value else 0, _now(), ad_id))
    conn.commit()
    conn.close()


def update_memo(ad_id: str, memo: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE ad_library_ads SET memo=?, updated_at=? WHERE id=?", (memo, _now(), ad_id))
    conn.commit()
    conn.close()


def update_ad_script(ad_id: str, text: str, source: str, status: str, error: str = "") -> None:
    conn = get_conn()
    row = conn.execute("SELECT script_created_at FROM ad_library_ads WHERE id=?", (ad_id,)).fetchone()
    created = (row["script_created_at"] if row and row["script_created_at"] else _now())
    conn.execute(
        "UPDATE ad_library_ads SET script_text=?, script_source=?, script_status=?, "
        "script_error_message=?, script_created_at=?, script_updated_at=? WHERE id=?",
        (text, source, status, error, created, _now(), ad_id))
    conn.commit()
    conn.close()


def filter_ads(ads: list[dict], f: dict) -> list[dict]:
    from datetime import date
    today = date.today()
    days = f.get("period_days")
    search = (f.get("search") or "").strip().lower()

    def keep(a: dict) -> bool:
        # 기본: 검색/텍스트·미상 포맷 및 미디어 없는(placeholder) 광고 숨김 (개발자모드 제외)
        if not f.get("show_hidden"):
            if a.get("ad_format") in ("search_text", "unknown"):
                return False
            if not (a.get("thumbnail_url") or a.get("video_url")):
                return False
        if f.get("brand") and f["brand"] != "전체" and a.get("brand_name") != f["brand"]:
            return False
        if f.get("platforms") and a.get("platform") not in f["platforms"]:
            return False
        if f.get("media") and a.get("media_type") not in f["media"]:
            return False
        st_ = f.get("status")
        if st_ == "라이브" and a.get("status") != "live":
            return False
        if st_ == "종료" and a.get("status") not in ("ended", "inactive"):
            return False
        if st_ == "OFF" and a.get("status") == "live":
            return False
        if f.get("categories") and not set(f["categories"]) & set(a.get("tags") or []):
            return False
        if f.get("only_bookmark") and not a.get("is_bookmarked"):
            return False
        if f.get("grade") and f["grade"] != "전체":
            import services.grading as G
            if not G.passes_grade_filter(a.get("social_final_grade"), f["grade"]):
                return False
        if search:
            hay = " ".join(str(a.get(k) or "") for k in ("brand_name", "ad_title", "ad_copy")).lower()
            if search not in hay:
                return False
        if days:
            d = str(a.get("collected_at") or "")[:10]
            try:
                if (today - datetime.strptime(d, "%Y-%m-%d").date()).days > days:
                    return False
            except ValueError:
                return False
        return True

    import services.grading as G

    def viral_key(a):
        """터진순: 등급 매칭된 광고 우선 → final_grade → engagement_score → social views → 수집일.
        소셜 없는 광고는 뒤로(0그룹) score/collected 순."""
        g = a.get("social_final_grade")
        if g:
            return (1, G.GRADE_RANK.get(g, 0), a.get("social_engagement_score") or 0,
                    int(a.get("social_views") or 0), str(a.get("collected_at") or ""))
        return (0, 0, 0, int(a.get("score") or 0) / 100.0, str(a.get("collected_at") or ""))

    keyf = {
        "🔥 터진순(추천)": viral_key,
        "조회수 높은순(소셜)": lambda a: int(a.get("social_views") or 0),
        "최근 수집순": lambda a: str(a.get("collected_at") or ""),
        "점수 높은순": lambda a: int(a.get("score") or 0),
        "저장 많은순": lambda a: (int(a.get("is_bookmarked") or 0), int(a.get("score") or 0)),
    }.get(f.get("sort"), lambda a: int(a.get("score") or 0))
    return sorted((a for a in ads if keep(a)), key=keyf, reverse=True)


def stats(ads: list[dict]) -> dict:
    return {"total": len(ads),
            "last_update": max((str(a.get("updated_at") or a.get("created_at") or "")
                                for a in ads), default="")[:16].replace("T", " ")}
