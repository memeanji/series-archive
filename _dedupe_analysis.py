# -*- coding: utf-8 -*-
"""dedupe_key 보수적 로직 검증 — series_archive.db '복사본'에만 적용. 원본/demo.db 불변.
실행: (프로젝트 루트에서) python _dedupe_analysis.py
출력: _dedupe_report.txt"""
import hashlib
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "series_archive.db")
COPY = os.path.join(os.environ.get("TMP", "/tmp"), "_dedupe_test.db")

out = []
def p(*a): out.append(" ".join(str(x) for x in a))

# ── 0) 복사본 생성(백업 API=WAL 안전) — 원본은 읽기만 ──
if os.path.exists(COPY):
    os.remove(COPY)
_s = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
_d = sqlite3.connect(COPY)
_s.backup(_d)
_s.close(); _d.close()

conn = sqlite3.connect(COPY)
conn.row_factory = sqlite3.Row
p("SQLite 버전:", sqlite3.sqlite_version, "| 복사본:", COPY)

# ── 1) 복사본에 컬럼+인덱스 추가(마이그레이션 검증) ──
cols = [r[1] for r in conn.execute("PRAGMA table_info(ad_library_ads)").fetchall()]
for c, t in (("content_hash", "TEXT"), ("dedupe_key", "TEXT")):
    if c not in cols:
        conn.execute(f"ALTER TABLE ad_library_ads ADD COLUMN {c} {t}")
conn.execute("CREATE INDEX IF NOT EXISTS idx_ala_dedupe ON ad_library_ads(dedupe_key)")

# ── 헬퍼(제안 로직 그대로) ──
_YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})")
def yt_id(u): m = _YT_RE.search(u or ""); return m.group(1) if m else ""
def norm_copy(s): return re.sub(r"\s+", " ", (s or "")).strip().lower()

def thumb_file(row):
    """local_thumbnail_path>thumbnail_url>preview_url 중 '로컬 파일'을 프로젝트 루트 기준 안전 해석."""
    for k in ("local_thumbnail_path", "thumbnail_url", "preview_url"):
        v = (row[k] or "").strip() if k in row.keys() else ""
        if not v or v.startswith("http") or v.startswith("data:"):
            continue
        rel = v[4:] if v.startswith("app/") else v          # 'app/static/..' → 'static/..'
        full = os.path.join(ROOT, rel)                       # 루트 기준 절대경로
        if os.path.exists(full):
            return full
    return ""

_hcache = {}
def sha256_of(path):
    if not path: return ""
    if path in _hcache: return _hcache[path]
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
        v = h.hexdigest()
    except Exception:
        v = ""
    _hcache[path] = v
    return v

def dedupe_key(row, ch):
    vid = yt_id(row["video_url"] or "")
    if vid:
        return f"yt:{vid}"
    if (row["platform"] or "") == "meta":
        copy, land = norm_copy(row["ad_copy"]), (row["landing_url"] or "").strip().lower()
        if ch and copy and land:
            return f"meta:{row['brand_name']}|{copy}|{land}|{ch}"
    return ""

# ── 2) 백필(복사본만): content_hash + dedupe_key ──
rows = conn.execute("""SELECT id, platform, media_type, brand_name, ad_copy, landing_url, video_url,
                       local_thumbnail_path, thumbnail_url, preview_url, is_bookmarked, is_excluded,
                       memo, script_text, collected_at, status FROM ad_library_ads""").fetchall()
meta_no_thumb = 0
recs = []
for r in rows:
    pf = r["platform"] or ""
    ch = ""
    if pf == "meta":
        tf = thumb_file(r)
        ch = sha256_of(tf)
        if (r["media_type"] == "video" or (r["video_url"] or "")) and not ch:
            meta_no_thumb += 1
    key = dedupe_key(r, ch)
    conn.execute("UPDATE ad_library_ads SET content_hash=?, dedupe_key=? WHERE id=?", (ch, key, r["id"]))
    recs.append((dict(r), ch, key))
conn.commit()

# ── 3) 지표(보수적) ──
grp = defaultdict(list)
for r, ch, key in recs:
    if key:
        grp[key].append((r, ch))
yt_groups = {k: v for k, v in grp.items() if k.startswith("yt:") and len(v) > 1}
meta_groups = {k: v for k, v in grp.items() if k.startswith("meta:") and len(v) > 1}
yt_redund = sum(len(v) - 1 for v in yt_groups.values())
meta_redund = sum(len(v) - 1 for v in meta_groups.values())
total = len(recs)
user_groups = 0
for k, v in {**yt_groups, **meta_groups}.items():
    if any(rr[0]["is_bookmarked"] or (rr[0]["memo"] or "").strip() or (rr[0]["script_text"] or "").strip() for rr in v):
        user_groups += 1

p("\n===== 지표(보수적 기준) =====")
p(f"전체 광고행: {total:,}")
p(f"[YouTube video_id 확정] 중복그룹 {len(yt_groups):,} · 잉여행 {yt_redund:,}")
p(f"[Meta exact thumbnail SHA-256] '동일 소재 후보' 그룹 {len(meta_groups):,} · 잉여행 {meta_redund:,}")
p(f"중복 제거 후 예상 노출: {total:,} - ({yt_redund}+{meta_redund}) = {total - yt_redund - meta_redund:,}")
p(f"사용자데이터 포함 그룹: {user_groups}")
p(f"썸네일 없어 판정 못한 Meta 영상광고: {meta_no_thumb:,}")

# 카피·랜딩 같지만 썸네일 다른(=분리 유지) Meta 그룹
sig = defaultdict(list)
for r, ch, key in recs:
    if (r["platform"] or "") == "meta":
        c, l = norm_copy(r["ad_copy"]), (r["landing_url"] or "").strip().lower()
        if c and l:
            sig[(r["brand_name"], c[:120], l)].append((r, ch))
diff_thumb_groups = {k: v for k, v in sig.items()
                     if len({ch for _, ch in v if ch}) > 1 and len(v) > 1}
p(f"[카피·랜딩 같지만 썸네일 다름 → 분리 유지] 그룹 {len(diff_thumb_groups):,}")

# ── 4) 샘플 120 ──
def fmt(r, ch):
    tf = thumb_file(r)
    tf_disp = os.path.relpath(tf, ROOT) if tf else "(없음)"
    return (f"    id={r['id'][:20]} · {r['brand_name']} · '{(r['ad_copy'] or '')[:24].strip()}' · "
            f"land={(r['landing_url'] or '')[:28]} · thumb={tf_disp} · ch={ch[:12] or '-'} · {r['collected_at'][:10]}")

p("\n===== 샘플 A: YouTube 확정 동일영상 40 그룹 =====")
for k, v in list(sorted(yt_groups.items(), key=lambda kv: -len(kv[1])))[:40]:
    p(f"  [YT 확정] {len(v)}건 · key={k}")
    for r, ch in v[:2]:
        p(fmt(r, ch))

p("\n===== 샘플 B: Meta '동일 소재 후보'(썸네일·카피·랜딩 일치) 40 그룹 =====")
p("  ※ 영상ID/영상파일 해시가 없으므로 '동일영상 확정' 아님 — '동일 소재 후보'로 분류")
for k, v in list(sorted(meta_groups.items(), key=lambda kv: -len(kv[1])))[:40]:
    p(f"  [Meta 동일소재 후보] {len(v)}건 · ch={k.split('|')[-1][:12]}")
    for r, ch in v[:2]:
        p(fmt(r, ch))

p("\n===== 샘플 C: 카피·랜딩 같지만 썸네일 다름(분리 유지) 40 그룹 =====")
for k, v in list(sorted(diff_thumb_groups.items(), key=lambda kv: -len(kv[1])))[:40]:
    hashes = {ch[:8] for _, ch in v if ch}
    p(f"  [분리 유지] {len(v)}건 · 서로다른 썸네일해시 {len(hashes)}종 · {k[0]} · '{k[1][:24]}'")
    for r, ch in v[:2]:
        p(fmt(r, ch))

# ── 6) 기술 검증: ROW_NUMBER 쿼리 + 필터/정렬/페이지네이션 ──
p("\n===== 기술 검증 =====")
GRP = "COALESCE(NULLIF(a.dedupe_key,''), a.id)"
REP = ("(CASE WHEN a.is_bookmarked=1 OR length(COALESCE(a.memo,''))>0 "
       "OR length(COALESCE(a.script_text,''))>0 THEN 1 ELSE 0 END) DESC, "
       "(CASE WHEN a.status='live' THEN 1 ELSE 0 END) DESC, a.collected_at DESC")
try:
    q = (f"SELECT * FROM (SELECT a.id, a.brand_name, a.platform, a.dedupe_key, "
         f"COUNT(*) OVER (PARTITION BY {GRP}) AS dup_rows, "
         f"ROW_NUMBER() OVER (PARTITION BY {GRP} ORDER BY {REP}) AS rn "
         f"FROM ad_library_ads a WHERE a.platform=? AND COALESCE(a.is_excluded,0)=0 "
         f"AND (a.ad_copy LIKE ? OR ?='')) t "
         f"WHERE t.rn=1 ORDER BY t.dup_rows DESC, t.brand_name LIMIT ? OFFSET ?")
    res = conn.execute(q, ("meta", "%%", "", 5, 0)).fetchall()
    p(f"  ROW_NUMBER+필터(platform,LIKE)+정렬+LIMIT/OFFSET 실행: ✅ OK, 반환 {len(res)}행")
    p(f"  예시 대표행: " + ", ".join(f"{dict(r)['brand_name']}(dup {dict(r)['dup_rows']})" for r in res[:3]))
    # 개별보기(그룹=id) 카운트 vs 묶기 카운트
    n_all = conn.execute(f"SELECT COUNT(DISTINCT a.id) FROM ad_library_ads a WHERE COALESCE(a.is_excluded,0)=0").fetchone()[0]
    n_grp = conn.execute(f"SELECT COUNT(DISTINCT {GRP}) FROM ad_library_ads a WHERE COALESCE(a.is_excluded,0)=0").fetchone()[0]
    p(f"  개별보기 {n_all:,}건 vs 묶기 {n_grp:,}건 (묶기시 {n_all-n_grp:,}건 숨김)")
except Exception as e:
    p(f"  🚨 쿼리 실행 실패: {e}")

# dedupe_key 저장 지속성(썸네일 없어도 유지) 검증: 컬럼값이 DB에 저장됨
stored = conn.execute("SELECT COUNT(*) FROM ad_library_ads WHERE dedupe_key IS NOT NULL AND dedupe_key<>''").fetchone()[0]
p(f"  dedupe_key 저장된 행: {stored:,} → DB 컬럼에 영속(배포본은 썸네일 없이 이 값 재사용, 재해싱 불필요)")

conn.close()
open(os.path.join(ROOT, "_dedupe_report.txt"), "w", encoding="utf-8").write("\n".join(out))
print("done ->", os.path.join(ROOT, "_dedupe_report.txt"))
print("원본 series_archive.db / demo.db 미변경 (복사본만 사용:", COPY, ")")
