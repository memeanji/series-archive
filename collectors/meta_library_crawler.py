"""
메타 Ad Library 웹페이지 직접 크롤러 (Playwright).
API 가 아니라 사람이 보는 공개 라이브러리 페이지를 렌더링해 광고를 추출한다.
  - Ad Library API(ads_archive) 는 앱 승인(에러10)·지역제한이 있어 한국 상업광고를 못 줌.
  - 웹페이지는 그 제한 없이 보이므로 브랜드 검색 결과를 그대로 긁는다.

단독 테스트:  python collectors/meta_library_crawler.py 더스크랙
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402  (stdout utf-8 재설정 포함)

PLATFORM = "meta"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_STATIC = Path(__file__).resolve().parent.parent / "static" / "thumbnails"


def _save_thumb(url: str, ad_id: str) -> str:
    """fbcdn 서명 썸네일은 만료되므로 크롤 시점에 static 파일로 내려받아 영구 보존."""
    if not url or not url.startswith("http"):
        return url
    try:
        import requests
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.content:
            _STATIC.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch for ch in str(ad_id) if ch.isalnum() or ch in "_-")
            (_STATIC / f"m_{safe}.jpg").write_bytes(r.content)
            return f"app/static/thumbnails/m_{safe}.jpg"
    except Exception:  # noqa: BLE001
        pass
    return url  # 실패 시 원본 URL 폴백

_NAV = {
    "Meta 광고 라이브러리", "광고 라이브러리", "광고 라이브러리 보고서", "광고 라이브러리 API",
    "브랜디드 콘텐츠", "대한민국", "모든 광고", "키워드 또는 광고주로 검색", "로그인",
    "시스템 상태", "이메일 업데이트 구독", "FAQ", "광고 및 데이터 사용 정보",
    "개인 정보 보호", "이용 약관", "쿠키", "필터", "정렬", "정렬 기준",
    "광고", "플랫폼", "드롭다운 열기", "활성", "비활성", "광고 상세 정보 보기",
}

# 카드 추출 JS — 'Library ID/라이브러리 ID' 텍스트를 가진 최소 블록을 카드로 본다.
_JS_EXTRACT = r"""
() => {
  const out = [], seen = new Set();
  for (const el of Array.from(document.querySelectorAll('div'))) {
    const t = el.innerText || '';
    const m = t.match(/(?:Library ID|라이브러리 ID)[:\s]*([0-9]{6,})/);
    if (!m) continue;
    let card = el;
    for (let i = 0; i < 6 && card.parentElement; i++) {
      if ((card.innerText || '').length > 80) break;
      card = card.parentElement;
    }
    const id = m[1];
    if (seen.has(id)) continue;
    seen.add(id);
    const vids = Array.from(card.querySelectorAll('video')).map(v => v.src || (v.querySelector('source')||{}).src).filter(Boolean);
    const imgs = Array.from(card.querySelectorAll('img')).map(i => i.src).filter(s => s && !s.startsWith('data:'));
    const links = Array.from(card.querySelectorAll('a')).map(a => a.href).filter(Boolean);
    out.push({ library_id: id, has_video: vids.length > 0,
               video_url: vids[0] || '', thumbnail_url: imgs[0] || '',
               links: links.slice(0, 8), text: (card.innerText || '').trim().slice(0, 1200) });
  }
  return out;
}
"""


def _pick_landing(links: list[str]) -> str:
    """l.facebook.com 리다이렉트(u=)를 풀어 실제 랜딩 URL을 고른다."""
    for href in links:
        if "l.facebook.com" in href and "u=" in href:
            u = parse_qs(urlparse(href).query).get("u", [""])[0]
            if u:
                return unquote(u)
    for href in links:
        host = urlparse(href).netloc
        if host and "facebook.com" not in host and "fbcdn" not in host:
            return href
    return ""


def _parse_card(r: dict, brand: str) -> dict:
    text = r.get("text", "")
    # 카드가 다음 광고까지 먹었으면 두 번째 '라이브러리 ID' 앞에서 자른다
    ids = [m.start() for m in re.finditer(r"라이브러리 ID", text)]
    if len(ids) > 1:
        text = text[:ids[1]]
    dm = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.", text)
    started = (f"{int(dm.group(1)):04d}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
               if dm else None)
    body = text.split("광고 상세 정보 보기", 1)[1] if "광고 상세 정보 보기" in text else text
    lines = []
    for ln in body.split("\n"):
        ln = ln.replace("​", "").strip()
        if not ln or ln in _NAV or ln.startswith("결과 ") or ln.startswith("이 결과") \
                or "라이브러리 ID" in ln or "게재 시작" in ln or re.match(r"^\d+:\d+\s*/", ln):
            continue
        lines.append(ln)
    page_name = lines[0] if lines else brand
    page_name = re.sub(r"\s*페이지는.*함께합니다$", "", page_name)
    return {
        "started": started,
        "page_name": page_name,
        "ad_text": "\n".join(lines),
        "landing": _pick_landing(r.get("links", [])),
    }


def search_brand(brand: str, country: str = "KR", scrolls: int = 6,
                 headless: bool = True, shot: bool = False) -> list[dict]:
    from playwright.sync_api import sync_playwright

    url = (f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
           f"&country={country}&q={quote(brand)}&search_type=keyword_unordered&media_type=all")
    rows: list[dict] = []
    with sync_playwright() as p:
        br = p.chromium.launch(headless=headless)
        ctx = br.new_context(locale="ko-KR", user_agent=UA,
                             viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            for _ in range(scrolls):
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(2500)
            rows = page.evaluate(_JS_EXTRACT)
            if shot:
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path=f"data/_meta_{brand}.png")
        finally:
            br.close()

    ads = []
    for r in rows:
        p = _parse_card(r, brand)
        ads.append({
            "platform": PLATFORM,
            "platform_ad_id": r["library_id"],
            "advertiser_name": brand,
            "headline": p["page_name"],
            "ad_text": p["ad_text"],
            "transcript": "",
            "media_type": "video" if r["has_video"] else "image",
            "video_url": r["video_url"],
            "thumbnail_url": _save_thumb(r["thumbnail_url"], r["library_id"]),
            "landing_url": p["landing"],
            "original_ad_url": f"https://www.facebook.com/ads/library/?id={r['library_id']}",
            "status": "live",
            "first_seen": p["started"],
            "started_at": p["started"],
            "views": 0, "likes": 0, "comments": 0, "shares": 0,
            "raw_data": r,
        })
    return ads


def collect() -> list[dict]:
    """watchlist.json 의 모든 브랜드를 검색해 합친다."""
    wl = json.loads((config.DATA_DIR / "watchlist.json").read_text(encoding="utf-8"))
    out = []
    for b in wl.get("brands", []):
        try:
            ads = search_brand(b)
            print(f"  [meta-lib] '{b}' {len(ads)}건")
            out.extend(ads)
        except Exception as e:  # noqa: BLE001
            print(f"  [meta-lib] '{b}' 실패: {e}")
    return out


if __name__ == "__main__":
    term = sys.argv[1] if len(sys.argv) > 1 else "더스크랙"
    res = search_brand(term, headless=True, shot=True)
    print(f"\n'{term}' 추출 {len(res)}건")
    for a in res[:6]:
        print(f"  - id={a['platform_ad_id']} {a['first_seen']} video={'O' if a['video_url'] else 'X'} "
              f"| {a['headline'][:20]} | {a['ad_text'][:40].replace(chr(10), ' ')}")
