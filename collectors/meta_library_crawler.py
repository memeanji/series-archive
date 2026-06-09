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
    card.setAttribute('data-sa-card', id);   // Python에서 screenshot 폴백용 위치표시
    const vids = Array.from(card.querySelectorAll('video'))
        .map(v => v.src || (v.querySelector('source')||{}).src).filter(Boolean);
    const posters = Array.from(card.querySelectorAll('video')).map(v => v.poster).filter(Boolean);
    const imgs = Array.from(card.querySelectorAll('img')).map(i => i.src)
        .filter(s => s && !s.startsWith('data:'));
    // background-image url 후보
    let bg = '';
    for (const e of card.querySelectorAll('*')) {
      const b = getComputedStyle(e).backgroundImage || '';
      const mm = b.match(/url\(["']?(https?:[^"')]+)["']?\)/);
      if (mm) { bg = mm[1]; break; }
    }
    const links = Array.from(card.querySelectorAll('a')).map(a => a.href).filter(Boolean);
    // 우선순위: img → poster → bg
    const thumb = imgs[0] || posters[0] || bg || '';
    const src = imgs[0] ? 'img' : (posters[0] ? 'poster' : (bg ? 'bg' : 'none'));
    out.push({ library_id: id, has_video: vids.length > 0,
               video_url: vids[0] || '', thumbnail_url: thumb, thumb_src: src,
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
    cta_set = ["지금 구매하기", "구매하기", "지금 주문하기", "주문하기", "자세히 알아보기",
               "더 알아보기", "자세히 보기", "지금 신청하기", "신청하기", "문의하기",
               "지금 예약하기", "예약하기", "다운로드", "가입하기", "무료 체험하기",
               "지금 이용해 보기", "쇼핑하기", "지금 쇼핑", "할인받기", "더보기"]
    full_text = r.get("text", "")
    cta = next((c for c in cta_set if c in full_text), "")
    # A/B 테스트: "이 크리에이티브 및 문구를 사용하는 광고 N개" / "광고 N개에서 …" → N 추출
    vm = (re.search(r"광고\s*(\d+)\s*개[^\n]{0,40}(?:크리에이티브|문구)", full_text)
          or re.search(r"(?:크리에이티브|문구)[^\n]{0,40}광고\s*(\d+)\s*개", full_text))
    variant_count = int(vm.group(1)) if vm else 1
    return {
        "started": started,
        "page_name": page_name,
        "ad_text": "\n".join(lines),
        "landing": _pick_landing(r.get("links", [])),
        "cta": cta,
        "variant_count": variant_count,
    }


def search_brand(brand: str, country: str = "KR", scrolls: int = 6,
                 headless: bool = True, shot: bool = False, retries: int = 1) -> list[dict]:
    """Playwright 렌더 → 다단계 썸네일 추출 → 실패 시 카드 screenshot 폴백.
    각 광고에 scrape_status(img/poster/bg/screenshot/failed)·local_thumbnail_path 기록."""
    from playwright.sync_api import sync_playwright

    url = (f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
           f"&country={country}&q={quote(brand)}&search_type=keyword_unordered&media_type=all")
    rows: list[dict] = []
    ads: list[dict] = []
    stats = {"img": 0, "poster": 0, "bg": 0, "screenshot": 0, "failed": 0}

    with sync_playwright() as p:
        br = p.chromium.launch(headless=headless)
        ctx = br.new_context(locale="ko-KR", user_agent=UA,
                             viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        try:
            ok = False
            for attempt in range(retries + 1):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.wait_for_selector("text=/라이브러리 ID|Library ID/", timeout=15000)
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        page.wait_for_load_state("networkidle", timeout=12000)
                    except Exception:  # noqa: BLE001
                        pass
                    ok = True
                    break
                except Exception:  # noqa: BLE001
                    page.wait_for_timeout(3000)
            if not ok:
                return []
            for _ in range(scrolls):
                page.mouse.wheel(0, 6000)
                page.wait_for_timeout(2200)
            rows = page.evaluate(_JS_EXTRACT)

            for r in rows:
                cid = r["library_id"]
                parsed = _parse_card(r, brand)
                status, err, thumb = "failed", "", ""
                # 1) img/poster/bg 후보 다운로드
                if r.get("thumbnail_url"):
                    saved = _save_thumb(r["thumbnail_url"], cid)
                    if saved.startswith("app/static"):
                        thumb, status = saved, r.get("thumb_src", "img")
                    else:
                        err = "이미지 다운로드 실패"
                # 2) 폴백: 카드 element screenshot
                if not thumb:
                    try:
                        el = page.query_selector(f'[data-sa-card="{cid}"]')
                        if el:
                            box = el.bounding_box()
                            if box and box["height"] <= 700:
                                el.scroll_into_view_if_needed(timeout=3000)
                                page.wait_for_timeout(200)
                                _STATIC.mkdir(parents=True, exist_ok=True)
                                el.screenshot(timeout=6000, path=str(_STATIC / f"m_{cid}.jpg"))
                                thumb, status, err = f"app/static/thumbnails/m_{cid}.jpg", "screenshot", ""
                    except Exception as e:  # noqa: BLE001
                        err = f"screenshot 실패: {str(e)[:80]}"
                stats[status] = stats.get(status, 0) + 1
                ads.append({
                    "platform": PLATFORM, "platform_ad_id": cid, "advertiser_name": brand,
                    "headline": parsed["page_name"], "ad_text": parsed["ad_text"], "transcript": "",
                    "media_type": "video" if r["has_video"] else "image",
                    "video_url": r["video_url"], "thumbnail_url": thumb,
                    "local_thumbnail_path": thumb if thumb.startswith("app/static") else "",
                    "landing_url": parsed["landing"],
                    "original_ad_url": f"https://www.facebook.com/ads/library/?id={cid}",
                    "status": "live", "first_seen": parsed["started"], "started_at": parsed["started"],
                    "cta": parsed.get("cta", ""),
                    "ad_variant_count": parsed.get("variant_count", 1),
                    "platforms": "", "scrape_status": status, "error_message": err,
                    "views": 0, "likes": 0, "comments": 0, "shares": 0, "raw_data": r,
                })
        finally:
            br.close()

    okc = len(ads) - stats["failed"]
    print(f"  [meta-thumb] '{brand}' 성공 {okc}/{len(ads)} "
          f"(img {stats['img']}, poster {stats['poster']}, bg {stats['bg']}, "
          f"shot {stats['screenshot']}, 실패 {stats['failed']})")
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
