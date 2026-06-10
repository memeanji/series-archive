"""Series Archive UI 컴포넌트."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as stc

import database
import services.youtube as YT
import styles as S
from services.urls import is_valid_external_url, normalize_google_transparency_url

ROOT = Path(__file__).resolve().parent

PLATFORM_ICON = {"tiktok": "🎵", "meta": "📘", "google": "🔍", "naver": "🟢"}
PLAT_ICON = {"Facebook": "📘", "Instagram": "📸", "Messenger": "💬",
             "Audience Network": "📡", "Threads": "🧵"}
PLATFORM_LABEL = {"meta": "Meta", "tiktok": "TikTok", "google": "Google", "naver": "Naver"}
PAGE_SIZE = 12


def _fmt(n) -> str:
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "-"
    if n <= 0:
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _num(v, suffix="") -> str:
    if v in (None, "", 0):
        return "-"
    return f"{v}{suffix}"


def _full(n) -> str:
    """전체 숫자(개 단위, 천단위 콤마). 예: 1,234,567"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        return "-"
    return f"{n:,}" if n > 0 else "-"


def _g(ad: dict, key: str, default=""):
    v = ad.get(key)
    return default if v in (None, "") else v


def _reload() -> None:
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=86400, show_spinner=False)
def _yt_transcript(video_id: str) -> str:
    return YT.fetch_transcript(video_id)


@st.cache_data(ttl=3600, show_spinner=False)
def _file_data_uri(rel_path: str) -> str:
    """로컬 static 이미지 → data URI (렌더 순간 변환, 캐시). DB엔 저장 안 함."""
    p = Path(rel_path)
    if not p.is_absolute():
        p = ROOT / rel_path
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def get_display_thumbnail(ad: dict) -> dict:
    """카드/상세 공통 썸네일 결정. 우선순위: thumbnail_path>thumbnail_url>preview_url>image_url>media_url.
    로컬 static 경로는 data URI로 변환, http(s)는 그대로. 반환: {src, source, method, exists}."""
    for key in ("thumbnail_path", "thumbnail_url", "preview_url", "image_url", "media_url"):
        v = (ad.get(key) or "").strip()
        if not v:
            continue
        if v.startswith("http://") or v.startswith("https://"):
            return {"src": v, "source": key, "method": "url", "exists": True}
        if v.startswith("data:"):
            return {"src": v, "source": key, "method": "data_uri", "exists": True}
        rel = v[4:] if v.startswith("app/") else v   # 'app/static/..' → 'static/..'
        uri = _file_data_uri(rel)
        if uri:
            return {"src": uri, "source": key, "method": "local_data_uri", "exists": True}
        # 파일 없음 → 다음 후보
    return {"src": None, "source": None, "method": "none", "exists": False}


def _do_extract(social_id: str, video_id: str) -> None:
    """버튼 클릭 시에만 단건 추출. ① YouTube 자막 → ② 실패 시 Gemini 영상 전사."""
    database.update_script(social_id, "", "extracting")
    text = YT.fetch_transcript(video_id) if video_id else ""
    if not text and video_id:
        text = YT.gemini_transcript(video_id)   # 자막 없으면 Gemini 멀티모달
    database.update_script(social_id, text, "extracted" if text else "failed")
    _reload()


def render_script_section(social_id: str, video_id: str = "") -> None:
    """영상 하단 스크립트 — 자동추출 안 함. 저장된 값 표시 + 버튼으로만 추출/직접입력."""
    st.markdown(f"##### 📝 영상 스크립트 <span style='font-size:12px;color:{S.SUB}'>"
                f"· 버튼 클릭 시에만 추출</span>", unsafe_allow_html=True)
    if not social_id:
        st.caption("연결된 소셜 영상이 없습니다.")
        return
    sv = database.get_social(social_id) or {}
    status = sv.get("script_status") or "none"
    text = sv.get("script_text") or ""

    if text and status in ("extracted", "manual", "exists"):
        with st.expander("스크립트 보기", expanded=False):
            st.write(text)
        st.caption({"extracted": "YouTube 자막 자동 추출", "manual": "직접 입력",
                    "exists": "수집됨"}.get(status, ""))
        if st.button("🔁 재추출", key=f"re_{social_id}", disabled=not video_id):
            _do_extract(social_id, video_id)
        return
    if status == "extracting":
        st.info("추출 중입니다… 새로고침 후 확인하세요.")
        return

    st.caption("스크립트가 아직 없습니다." + (" (이전 추출 실패)" if status == "failed" else ""))
    c = st.columns(2)
    if c[0].button("🎬 스크립트 자동 추출", key=f"ex_{social_id}", disabled=not video_id,
                   help="① YouTube 자막 → ② 없으면 Gemini로 영상 전사 (영상 1건만 실행)"):
        _do_extract(social_id, video_id)
    with c[1].popover("✍️ 직접 입력"):
        man = st.text_area("스크립트", key=f"man_{social_id}", height=140,
                           label_visibility="collapsed", placeholder="스크립트를 직접 붙여넣기")
        if st.button("저장", key=f"mansave_{social_id}", type="primary"):
            database.update_script(social_id, man, "manual")
            _reload()
    if not video_id:
        st.caption("YouTube가 아닌 영상은 자동 추출 미지원 — 직접 입력만 가능(STT/Whisper 추후).")


# ════════════════════════════════════════════════════════════
def render_header(ads=None) -> dict:
    h = st.columns([5, 1.4])
    with h[0]:
        st.markdown(
            f"<div class='sa-header'><div><div class='sa-logo'>Series Archive</div>"
            f"<div class='sa-sub'>Ad Reference Library</div></div></div>",
            unsafe_allow_html=True)
    search = ""   # 통합 검색 제거(사이드바 브랜드 검색만 사용)
    with h[1]:
        cc = st.columns([1, 1, 2])
        if cc[0].button("🔄", help="새로고침", use_container_width=True):
            _reload()
        user = st.session_state.get("username", "guest")
        cc[2].markdown(f"<div style='text-align:right;font-size:12px;color:{S.SUB};margin-top:6px'>"
                       f"👤 <b>{user}</b></div>", unsafe_allow_html=True)

    tabs = ["전체", "Meta", "Google", "북마크"]
    tab = st.segmented_control("메뉴", tabs, default="전체",
                               label_visibility="collapsed") or "전체"
    return {"search": search, "tab": tab}


# ════════════════════════════════════════════════════════════
def _add_to_watchlist(brand: str) -> None:
    wl_path = ROOT / "data" / "watchlist.json"
    try:
        wl = json.loads(wl_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        wl = {"brands": []}
    if brand not in wl.get("brands", []):
        wl.setdefault("brands", []).append(brand)
        wl_path.write_text(json.dumps(wl, ensure_ascii=False, indent=2), encoding="utf-8")


def _domain_ok(d: str) -> bool:
    d = (d or "").strip()
    if not d:
        return True
    d = d.replace("https://", "").replace("http://", "").split("/")[0]
    return bool(re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", d))


def _run_collect(display: str) -> None:
    with st.spinner(f"'{display}' 수집 중… (메타+구글+YouTube, 1~2분)"):
        try:
            r = subprocess.run([sys.executable, str(ROOT / "jobs" / "crawl_brand.py"), display],
                               capture_output=True, text=True, timeout=600, cwd=str(ROOT))
            tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or ["완료"]
            st.success(f"'{display}' 수집 완료 — {tail[0]}")
        except subprocess.TimeoutExpired:
            st.error("시간 초과")
        except Exception as e:  # noqa: BLE001
            st.error(f"수집 실패: {e}")


def _suggest_advertisers(brand: str) -> list:
    """구글 투명성센터 자동완성에서 법인명 후보를 subprocess 로 가져온다."""
    import json as _json
    try:
        r = subprocess.run([sys.executable, str(ROOT / "jobs" / "google_advertisers.py"), brand],
                           capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("ADVJSON:"):
                return _json.loads(ln[len("ADVJSON:"):])
    except Exception:  # noqa: BLE001
        pass
    return []


def render_add_brand() -> None:
    """브랜드 추가 위저드: 입력 → 후보 찾기 → 선택 → 저장 → 수집(버튼 클릭 시에만)."""
    with st.sidebar.expander("➕ 브랜드 추가", expanded=False):
        # 자동완성으로 받은 법인명 제안을 위젯 생성 전에 반영(위젯 생성 후 수정 불가)
        if "ab_gadv_pending" in st.session_state:
            st.session_state["ab_gadv"] = st.session_state.pop("ab_gadv_pending")

        name = st.text_input("브랜드명", key="ab_name", placeholder="예: 리바엔").strip()
        gadv = st.text_input("구글 광고주명(법인명)", key="ab_gadv",
                             placeholder="브랜드명만 넣고 '후보 찾기'를 누르면 자동으로 채워집니다",
                             help="구글 투명성센터는 '주식회사 OOO' 법인명으로 검색해야 잘 잡힙니다. "
                                  "비워두면 후보 찾기가 자동완성에서 법인명을 가져와 채웁니다.").strip()
        domain = st.text_input("공식몰 도메인(선택)", key="ab_domain", placeholder="rivan.co.kr").strip()
        kw_raw = st.text_input("검색 키워드(쉼표 구분)", key="ab_kw", placeholder="리바엔, RIVAN, 리바엔 공식몰")
        cat = st.text_input("카테고리(선택)", key="ab_cat").strip()
        keywords = [k.strip() for k in (kw_raw or "").split(",") if k.strip()]

        # Step 2: 후보 찾기
        if st.button("🔎 후보 찾기", key="ab_find", use_container_width=True):
            if not name:
                st.warning("브랜드명을 입력하세요.")
            elif not _domain_ok(domain):
                st.warning("도메인 형식이 올바르지 않습니다.")
            else:
                if database.brand_exists(name):
                    st.info("이미 등록된 브랜드 — 저장 시 법인명/도메인/키워드가 갱신됩니다.")
                st.session_state.ab_cands = database.find_brand_candidates(name, domain, keywords)
                st.session_state.ab_searched = True
                # 법인명이 비어 있으면 구글 자동완성에서 후보를 가져와 채운다
                if not gadv:
                    with st.spinner("구글 투명성센터에서 법인명 자동 검색 중… (~20초)"):
                        advs = _suggest_advertisers(name)
                    st.session_state.ab_adv_cands = advs
                    if advs:
                        st.session_state.ab_gadv_pending = advs[0]
                st.rerun()

        # Step 3: 후보 확인 + Step 4: 저장
        if st.session_state.get("ab_searched"):
            cands = st.session_state.get("ab_cands", [])
            picked = []
            if cands:
                st.caption(f"후보 {len(cands)}개 — 맞는 것 선택")
                for i, c in enumerate(cands[:10]):
                    if st.checkbox(f"**{c['name']}** · {'/'.join(c['sources'])} · "
                                   f"{c['ad_count']}건 · {','.join(c['reasons'])}", key=f"ab_c_{i}"):
                        picked.append(c["name"])
                    if c["thumbs"]:
                        tc = st.columns(3)
                        for col, th in zip(tc, c["thumbs"][:3]):
                            t = get_display_thumbnail({"thumbnail_url": th})
                            if t["src"]:
                                col.markdown(f"<img src='{t['src']}' style='width:100%;border-radius:4px'/>",
                                             unsafe_allow_html=True)
            else:
                st.info("후보 없음. 그래도 수동 추가하시겠습니까?")
                if not keywords:
                    st.caption("⚠️ 수동 추가는 검색 키워드 최소 1개 필요")

            # 구글 자동완성 법인명 후보 — 클릭하면 위 '구글 광고주명' 칸에 적용
            advs = st.session_state.get("ab_adv_cands", [])
            if advs:
                cur_g = st.session_state.get("ab_gadv", "")
                st.caption("🏢 구글 법인명 후보(자동완성) — 클릭해 적용")
                for j, a in enumerate(advs[:6]):
                    mark = "✓ " if a == cur_g else ""
                    if st.button(f"{mark}{a}", key=f"ab_adv_{j}", use_container_width=True):
                        st.session_state.ab_gadv_pending = a
                        st.rerun()
            elif st.session_state.get("ab_searched") and not gadv:
                st.caption("자동완성에 법인명이 없어요 — 직접 입력하거나 메타만 수집됩니다.")

            can_save = bool(name) and (bool(cands) or bool(keywords))
            if st.button("💾 브랜드 저장", key="ab_save", type="primary",
                         disabled=not can_save, use_container_width=True):
                kws = list(dict.fromkeys([name] + keywords + picked))
                database.add_brand(name, kws, domain, cat,
                                   extra={"google_advertiser_name": gadv or (picked[0] if picked else "")})
                st.session_state.ab_saved = name
                st.session_state.sa_brand = name
                st.cache_data.clear()   # 캐시 비워서 사이드바에 즉시 반영
                st.rerun()

        # Step 5: 수집 실행(버튼 클릭 시에만)
        saved = st.session_state.get("ab_saved")
        if saved:
            stt = database.latest_brand_status(saved)
            st.caption(f"상태: {stt['status'] if stt else '대기'}")
            if st.button(f"📥 '{saved}' 지금 수집", key="ab_collect", use_container_width=True):
                _run_collect(saved)
                for k in ("ab_saved", "ab_searched", "ab_cands", "ab_adv_cands"):
                    st.session_state.pop(k, None)
                st.cache_data.clear()
                st.rerun()


def render_sidebar(counts: list, total: int) -> str:
    """counts: [(brand, n, live_flag), ...] (캐시). 상위 20개 + 검색."""
    sb = st.sidebar
    sb.markdown(f"<div style='font-weight:800;color:{S.TEXT};font-size:15px;"
                f"margin:.2rem 0 .8rem'>🏷️ 브랜드</div>", unsafe_allow_html=True)
    render_add_brand()
    sb.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
    q = sb.text_input("브랜드 검색", placeholder="브랜드 찾기", label_visibility="collapsed").strip().lower()

    sel = st.session_state.get("sa_brand", "전체")
    if sb.button(f"📁 전체 브랜드  ·  {total}", key="b_all"):
        st.session_state.sa_brand = "전체"
        st.session_state.sa_page = 1
        st.rerun()
    sb.markdown(f"<hr style='margin:.55rem 0 .7rem;border-color:{S.BORDER}'>", unsafe_allow_html=True)

    shown = [r for r in counts if not q or q in (r["name"] or "").lower()]
    if not q:
        shown = shown[:20]   # 검색 없을 땐 상위 20개만 렌더(성능)
    for r in shown:
        b = r["name"]
        mark = "▸ " if b == sel else ""
        extra = f"  ·  📺{r['approved']}" if r["approved"] else ""
        tip = f"승인 {r['approved']} · 검토필요 {r['needs']} · 제외 {r['rejected']}"
        if sb.button(f"{mark}{'🟢' if r['live'] else '⚪'} {b}  ·  {r['ad']}{extra}",
                     key=f"b_{b}", help=tip):
            st.session_state.sa_brand = b
            st.session_state.sa_page = 1
            st.rerun()
    if not q and len(counts) > 20:
        sb.caption(f"… 외 {len(counts) - 20}개. 검색으로 찾기")
    return sel


# ════════════════════════════════════════════════════════════
def render_filters(opts: dict, header: dict, social_count: int = 0) -> dict:
    has_social = social_count > 0
    grade = "전체"   # 등급 기능 제거
    c = st.columns([1, 1, 1.6, 1, 0.8])

    media = c[0].multiselect("매체(소재)", ["video", "image"],
                             default=st.session_state.get("f_media", []),
                             format_func=lambda x: {"video": "🎬 영상", "image": "🖼 이미지"}.get(x, x),
                             key="f_media")
    status = c[1].selectbox("상태", ["전체", "라이브", "종료", "OFF"], key="f_status")
    sort = c[2].selectbox("정렬",
                          ["최근 수집순", "오래된순", "조회수 높은순", "게재기간 긴순",
                           "게재기간 짧은순", "저장 많은순"],
                          index=0, key="f_sort")
    period = c[3].selectbox("기간(게재 시작 기준)", ["전체", "7일", "30일", "90일"], key="f_period")
    c[4].markdown("<div style='height:2.05rem'></div>", unsafe_allow_html=True)
    if c[4].button("초기화", use_container_width=True, help="필터 초기화"):
        for k in ("f_media", "f_status", "f_sort", "f_period"):
            st.session_state.pop(k, None)
        st.rerun()
    hc = st.columns([1, 1])
    show_hidden = hc[0].checkbox("🔧 (개발용) 검색형·미디어 없는 광고도 표시", value=False, key="f_devhidden",
                                 help="구글의 텍스트/검색광고나 썸네일·영상이 없는 광고는 품질 위해 기본 숨김.")
    only_unavail = hc[1].checkbox("⚠️ 상세 확인 불가 광고만 보기", value=False, key="f_unavail",
                                  help="카드엔 보여도 상세에서 '광고 라이브러리에 없습니다'가 뜨는 광고. "
                                       "기본 목록에선 자동 제외되며, 여기서만 따로 확인.")

    # 탭 → 매체/북마크 매핑
    tab = header["tab"]
    platforms = {"Meta": ["meta"], "Google": ["google"]}.get(tab)
    only_bm = tab == "북마크"

    # 활성 필터 칩
    chips = []
    if st.session_state.get("sa_brand", "전체") != "전체":
        chips.append("🏷️ " + st.session_state["sa_brand"])
    chips += [f"🎬 {m}" if m == "video" else f"🖼 {m}" for m in media]
    if status != "전체":
        chips.append("● " + status)
    if period != "전체":
        chips.append("📅 " + period)
    if chips:
        st.markdown(" ".join(f"<span class='sa-chip'>{c}</span>" for c in chips),
                    unsafe_allow_html=True)

    return {
        "search": header["search"],
        "brand": st.session_state.get("sa_brand", "전체"),
        "platforms": platforms,
        "media": media,
        "status": status,
        "sort": sort,
        "grade": grade,
        "period_days": {"7일": 7, "30일": 30, "90일": 90}.get(period),
        "only_bookmark": only_bm,
        "show_hidden": show_hidden,
        "only_unavailable": only_unavail,
    }


# ════════════════════════════════════════════════════════════
def render_ad_card(ad: dict, idx: int) -> None:
    aid = ad.get("id")
    score = int(ad.get("score") or 0)
    plat = ad.get("platform", "")
    is_video = ad.get("media_type") == "video"
    th = get_display_thumbnail(ad)
    thumb = th["src"]

    if ad.get("detail_status") == "unavailable":
        inner = ("<div class='sa-ph'><span class='i'>⚠️</span>상세 확인 불가"
                 "<div style='font-size:10px;opacity:.7'>광고 라이브러리에 없음</div></div>")
        thumb_cls = "sa-thumb sa-thumb-empty"
    elif thumb:
        inner = f"<img src='{thumb}'/>"
        thumb_cls = "sa-thumb"
    elif ad.get("scrape_status") == "failed":
        why = (ad.get("error_message") or "수집 실패")[:24]
        inner = (f"<div class='sa-ph'><span class='i'>⚠️</span>수집 실패"
                 f"<div style='font-size:10px;opacity:.7'>{why}</div></div>")
        thumb_cls = "sa-thumb sa-thumb-empty"
    else:
        inner = (f"<div class='sa-ph'><span class='i'>{'🎬' if is_video else '🖼'}</span>"
                 f"미리보기 없음</div>")
        thumb_cls = "sa-thumb sa-thumb-empty"
    nab = max(int(ad.get("variant_count") or 1), int(ad.get("dup_rows") or 1))
    ab_chip = (f"<span style='background:#F59E0B;color:#fff;font-size:10px;font-weight:700;"
               f"padding:1px 6px;border-radius:5px;margin-left:5px' "
               f"title='이 크리에이티브·문구를 사용하는 광고 {nab}개 (A/B 테스트)'>A/B {nab}</span>"
               if plat == "meta" and nab >= 2 else "")
    plats = [p.strip() for p in (ad.get("platforms") or "").split(",") if p.strip()]
    plat_chip = (" ".join(PLAT_ICON.get(p, "") for p in plats) + " ") if plats else ""
    play = "<div class='sa-play'>▶</div>" if is_video and thumb else ""
    if plat == "google":
        media_badge = "<div class='sa-media'>🔍 Google Preview</div>"
    else:
        media_badge = f"<div class='sa-media'>{'▶ 영상' if is_video else '🖼 이미지'}</div>"
    dot = S.status_color(ad.get("status"))

    status_txt = "🟢 라이브" if ad.get("status") == "live" else "⚫ " + str(ad.get("status") or "-")
    badge = ""   # 등급/점수 뱃지 제거
    if int(ad.get("yt_views") or 0) or int(ad.get("yt_likes") or 0):
        eng = (f"<span title='연결된 유튜브 원본 영상의 공개 지표 · 광고 성과 아님'>"
               f"👁 {_full(ad.get('yt_views'))}회 ❤ {_full(ad.get('yt_likes'))}</span>")
    else:
        eng = f"<span style='color:{S.SUB}'>게재 {str(_g(ad,'started_at','-'))[:10] or '-'}</span>"
    _title = (_g(ad, "ad_title", "") or "")[:40]            # 실제 제목만(없으면 공백 div 생략)
    _copy = (_g(ad, "ad_copy_short", "") or "")[:60]
    with st.container(border=True):
        st.markdown(
            f"<div class='{thumb_cls}'>{inner}{badge}"
            f"<div class='sa-dot' style='background:{dot}'></div>{play}{media_badge}</div>"
            f"<div class='sa-brand'>{_g(ad,'brand_name','-')}{ab_chip}</div>"
            + (f"<div class='sa-title'>{_title}</div>" if _title else "")
            + (f"<div class='sa-copy'>{_copy}</div>" if _copy else "")
            +
            f"<div class='sa-meta'><span>{eng}</span>"
            f"<span title='게재 플랫폼: {', '.join(plats) if plats else '-'}'>{plat_chip}"
            f"<span class='sa-pbadge'>{PLATFORM_LABEL.get(plat, plat or '-')}</span></span></div>"
            f"<div class='sa-meta' style='margin-bottom:10px'><span>📅 수집 {str(_g(ad,'collected_at','-'))[:10]}</span>"
            f"<span>{status_txt}</span></div>",
            unsafe_allow_html=True)
        b = st.columns([2, 1])
        if b[0].button("상세 보기", key=f"open_{aid}_{idx}", use_container_width=True):
            full = database.get_ad_full(aid)   # 상세 클릭 시에만 1건 전체 로드
            if full:
                render_ad_detail(full)
        marked = bool(ad.get("is_bookmarked"))
        if b[1].button("북마크됨" if marked else "북마크", key=f"bm_{aid}_{idx}",
                       use_container_width=True, type=("primary" if marked else "secondary"),
                       help="북마크"):
            database.update_bookmark(aid, not marked)
            _reload()
        if st.session_state.get("f_devhidden"):
            st.caption(f"🔧 id={aid} · {plat} · src={th['source']} · "
                       f"{th['method']} · exists={th['exists']}")


# ════════════════════════════════════════════════════════════
def _render_source_buttons(ad: dict) -> None:
    """원본/투명성센터/랜딩 버튼 — 유효한 외부 절대 URL일 때만 노출."""
    if ad.get("platform") == "google":
        turl = normalize_google_transparency_url(ad.get("transparency_url") or ad.get("original_ad_url"))
        if is_valid_external_url(turl):
            st.link_button("🔎 Google 투명성센터에서 보기 ↗", turl, use_container_width=True)
        else:
            st.caption("투명성센터 URL 없음")
        if is_valid_external_url(ad.get("landing_url")):
            st.link_button("🛒 랜딩 열기 ↗", ad["landing_url"], use_container_width=True)
        else:
            st.caption("랜딩 URL 추출 안 됨")
    else:
        if is_valid_external_url(ad.get("original_ad_url")):
            st.link_button("🔗 원본 광고 열기 ↗", ad["original_ad_url"], use_container_width=True)
        if is_valid_external_url(ad.get("landing_url")):
            st.link_button("🛒 랜딩 열기 ↗", ad["landing_url"], use_container_width=True)


def _greybox(text: str) -> str:
    import html as _h
    return (f"<div style='background:{S.BG};border:1px solid {S.BORDER};border-radius:10px;"
            f"padding:10px 12px;white-space:pre-wrap;font-size:13px;color:{S.TEXT};"
            f"line-height:1.5;max-height:340px;overflow:auto'>{_h.escape(text)}</div>")


_TS_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–~]?\s*"
                    r"(\d{1,2}:\d{2}(?::\d{2})?)?\s*(.*)$")


def _render_script_segments(text: str):
    """Gemini 구간 JSON([{start,end,script,visual_summary,on_screen_text}])이면 리치 타임라인으로,
    아니면 None(일반 텍스트 렌더로 폴백)."""
    import html as _h
    import json as _json
    t = (text or "").strip()
    if not (t.startswith("[") and t.endswith("]")):
        return None
    try:
        segs = _json.loads(t)
        if not isinstance(segs, list) or not segs or not isinstance(segs[0], dict):
            return None
    except Exception:  # noqa: BLE001
        return None
    rows = []
    for s in segs:
        chip = f"{s.get('start','')}–{s.get('end','')}".strip("–")
        script = _h.escape(s.get("script") or "")
        vis = _h.escape(s.get("visual_summary") or "")
        ost = _h.escape(s.get("on_screen_text") or "")
        ost_badge = (f"<span style='background:{S.MINT}1A;color:#0F766E;font-size:10.5px;"
                     f"padding:1px 6px;border-radius:5px;margin-left:6px'>화면: {ost}</span>"
                     if ost else "")
        rows.append(
            f"<div style='display:flex;gap:9px;align-items:flex-start;padding:7px 0;"
            f"border-bottom:1px solid {S.BORDER}'>"
            f"<span style='flex:0 0 auto;background:{S.MINT}1A;color:#0F766E;font-weight:700;"
            f"font-size:11px;padding:2px 7px;border-radius:6px;font-variant-numeric:tabular-nums;"
            f"white-space:nowrap'>{_h.escape(chip)}</span>"
            f"<span style='flex:1'>"
            f"<span style='font-size:13px;color:{S.TEXT};line-height:1.5;font-weight:600'>"
            f"{script or '<span style=\"color:#94A3B8\">(대사 없음)</span>'}</span>{ost_badge}"
            + (f"<div style='font-size:11.5px;color:{S.SUB};margin-top:2px'>🎬 {vis}</div>" if vis else "")
            + "</span></div>")
    return (f"<div style='background:{S.BG};border:1px solid {S.BORDER};border-radius:10px;"
            f"padding:10px 12px;max-height:380px;overflow:auto'>{''.join(rows)}</div>")


def _render_thumb_analysis(text: str) -> str:
    """이미지 소재 썸네일 분석 JSON({thumbnail_text,visual_summary,main_subject,hook_type,ad_angle})을 카드로."""
    import html as _h
    import json as _json
    try:
        o = _json.loads(text or "{}")
    except Exception:  # noqa: BLE001
        return _greybox(text or "")
    rows = [("화면 문구", o.get("thumbnail_text")), ("장면 요약", o.get("visual_summary")),
            ("핵심 피사체", o.get("main_subject")), ("후킹 유형", o.get("hook_type")),
            ("소구 포인트", o.get("ad_angle"))]
    inner = "".join(
        f"<div style='display:flex;gap:8px;padding:5px 0;border-bottom:1px solid {S.BORDER}'>"
        f"<span style='flex:0 0 84px;color:{S.SUB};font-size:11.5px;font-weight:700'>{k}</span>"
        f"<span style='flex:1;color:{S.TEXT};font-size:13px'>{_h.escape(str(v or '-'))}</span></div>"
        for k, v in rows)
    return (f"<div style='background:{S.BG};border:1px solid {S.BORDER};border-radius:10px;"
            f"padding:10px 12px'>{inner}</div>")


def _render_script_body(text: str) -> str:
    """Gemini 구간 JSON이면 리치 타임라인, 아니면 'MM:SS–MM:SS 대사' 줄 타임라인."""
    rich = _render_script_segments(text)
    if rich is not None:
        return rich
    import html as _h
    rows = []
    for raw in (text or "").splitlines():
        ln = raw.rstrip()
        if not ln.strip():
            continue
        if ln.strip().startswith("[") and ln.strip().endswith("]"):
            rows.append(f"<div style='font-weight:800;color:{S.TEXT};font-size:12px;"
                        f"margin:10px 0 4px'>{_h.escape(ln.strip()[1:-1])}</div>")
            continue
        m = _TS_RE.match(ln)
        if m and m.group(1) and m.group(3) is not None and m.group(3) != "":
            t0, t1, body = m.group(1), m.group(2), m.group(3)
            chip = t0 + (f"–{t1}" if t1 else "")
            rows.append(
                f"<div style='display:flex;gap:8px;align-items:flex-start;padding:5px 0;"
                f"border-bottom:1px solid {S.BORDER}'>"
                f"<span style='flex:0 0 auto;background:{S.MINT}1A;color:#0F766E;"
                f"font-weight:700;font-size:11px;padding:2px 7px;border-radius:6px;"
                f"font-variant-numeric:tabular-nums;white-space:nowrap'>{_h.escape(chip)}</span>"
                f"<span style='font-size:13px;color:{S.TEXT};line-height:1.5'>{_h.escape(body)}</span>"
                f"</div>")
        else:
            rows.append(f"<div style='font-size:13px;color:{S.TEXT};line-height:1.5;"
                        f"padding:3px 0'>{_h.escape(ln)}</div>")
    return (f"<div style='background:{S.BG};border:1px solid {S.BORDER};border-radius:10px;"
            f"padding:10px 12px;max-height:360px;overflow:auto'>{''.join(rows)}</div>")


def _render_video_script(ad: dict) -> None:
    """모달을 닫지 않고(=튕김 없음) 세션 상태에 결과를 캐시해 즉시 갱신."""
    import services.script_gen as SG
    aid = ad.get("id")
    if ad.get("detail_status") == "unavailable":
        st.markdown("##### 영상 스크립트")
        st.caption("⚠️ 이 광고는 광고 라이브러리 상세에 표시되지 않아(노출 미발생 등) "
                   "영상/스크립트 수집 대상이 아닙니다.")
        return
    src_ko = {"youtube_transcript": "YouTube 자막", "gemini_video": "Gemini 영상분석",
              "gemini_estimated": "Gemini 추정(카피 기반)", "manual": "직접 입력"}
    ovr = st.session_state.setdefault("_script_result", {})

    def _gen(label: str):
        with st.spinner(label):
            r = SG.generate(ad)
        database.update_ad_script(aid, r["text"], r["source"], r["status"], r["error"])
        ovr[aid] = r   # 세션 캐시 → 리런 없이 바로 표시

    # 현재 상태(세션 캐시 우선)
    cur = ovr.get(aid) or {"text": ad.get("script_text") or "",
                           "status": ad.get("script_status") or "pending",
                           "source": ad.get("script_source") or "",
                           "error": ad.get("script_error_message") or ""}

    has_video = bool((ad.get("video_url") or ad.get("media_url") or "").startswith("http"))

    # 상세 진입 시 자동 생성 — 무료(YouTube 자막)만. Gemini 는 버튼 클릭 시에만(키 절약)
    if cur["status"] == "pending" and aid not in ovr:
        done = st.session_state.setdefault("_autogen_done", set())
        if aid not in done:
            done.add(aid)
            with st.spinner("자막 확인 중…"):
                r = SG.transcript_only(ad)
            if r:
                database.update_ad_script(aid, r["text"], r["source"], r["status"], r["error"])
                ovr[aid] = r
            elif has_video:
                ovr[aid] = {"text": "", "status": "needs_ai", "source": "", "error": ""}
            else:
                ovr[aid] = {"text": "", "status": "thumbnail_only", "source": "", "error": ""}
            cur = ovr[aid]

    status = cur["status"]
    head = st.columns([3, 1, 1])

    # ── 이미지 소재: 썸네일 분석(후킹/소구/화면문구) ──
    if not has_video:
        head[0].markdown("##### 소재 분석 (이미지)")
        thumb_done = bool(cur["text"]) and status == "thumbnail_only"
        run = head[1].button("재분석" if thumb_done else "썸네일 분석", key=f"thb_{aid}",
                             use_container_width=True,
                             help="Gemini Vision으로 썸네일의 후킹/소구/화면문구를 추출합니다.")
        if run:
            with st.spinner("Gemini가 썸네일을 분석 중…"):
                r = SG.analyze_thumbnail(ad)
            database.update_ad_script(aid, r["text"], r["source"], r["status"], r["error"])
            ovr[aid] = r
            cur = r
            thumb_done = bool(cur["text"]) and cur["status"] == "thumbnail_only"
        if thumb_done:
            st.caption("🖼 이미지 소재 · Gemini 분석 결과는 추정이며 실제와 다를 수 있습니다.")
            st.markdown(_render_thumb_analysis(cur["text"]), unsafe_allow_html=True)
        elif cur.get("error"):
            st.caption(f"⚠️ {cur['error']}")
        else:
            st.caption("이미지 소재입니다. **썸네일 분석**을 누르면 후킹·소구·화면문구를 추출합니다.")
        return

    # ── 영상 소재: 3초 구간 스크립트 ──
    head[0].markdown("##### 영상 스크립트")
    completed = bool(cur["text"]) and status == "completed"
    if completed:
        regen = head[1].button("재생성", key=f"rgen_{aid}", use_container_width=True)
        edit = head[2].toggle("편집", key=f"edit_{aid}")
    else:
        regen = head[1].button("AI 생성", key=f"rgen2_{aid}", use_container_width=True,
                               help="Gemini가 이 영상을 분석해 3초 구간별 대본(대사·화면문구·장면)을 만듭니다.")
        edit = False
    if regen:
        _gen("Gemini가 영상을 분석해 구간별 대본 작성 중… (최대 2분)")
        cur = ovr[aid]
        status = cur["status"]
        completed = bool(cur["text"]) and status == "completed"
        edit = False

    if completed and not edit:
        if cur["source"] == "gemini_video":
            st.caption("🤖 Gemini가 영상을 분석한 추정 대본 — 실제 대사와 다를 수 있습니다.")
        else:
            st.caption(f"출처: {src_ko.get(cur['source'], cur['source'] or '-')}")
        st.markdown(_render_script_body(cur["text"]), unsafe_allow_html=True)
    elif completed and edit:
        new = st.text_area("스크립트 편집", value=cur["text"], height=260, key=f"scredit_{aid}",
                           label_visibility="collapsed")
        if st.button("💾 스크립트 저장", key=f"scsave_{aid}", type="primary"):
            database.update_ad_script(aid, new, "manual", "completed", "")
            ovr[aid] = {"text": new, "status": "completed", "source": "manual", "error": ""}
    else:
        if status == "video_too_long":
            st.caption(f"⏱ {cur['error']}")
        elif cur.get("error"):
            st.caption(f"⚠️ {cur['error']}")
        else:
            st.caption("**AI 생성**을 누르면 Gemini가 이 영상을 3초 구간별 대본으로 분석합니다.")
        with st.popover("✍️ 직접 입력"):
            man = st.text_area("스크립트", key=f"scman_{aid}", height=160,
                               label_visibility="collapsed", placeholder="스크립트를 직접 붙여넣기")
            if st.button("저장", key=f"scmansave_{aid}", type="primary"):
                database.update_ad_script(aid, man, "manual", "completed", "")
                ovr[aid] = {"text": man, "status": "completed", "source": "manual", "error": ""}


@st.dialog("광고 상세", width="large")
def render_ad_detail(ad: dict) -> None:
    aid = ad.get("id")
    plat = ad.get("platform", "")
    st.markdown(f"### {_g(ad,'brand_name','-')}", unsafe_allow_html=True)

    left, right = st.columns([2, 3], gap="medium")
    # ── 좌: 영상/썸네일 + 버튼 ──
    with left:
        th = get_display_thumbnail(ad)
        vurl = ad.get("video_url") or ""
        yt_vid = YT.extract_video_id(vurl) if "youtu" in vurl else None
        if yt_vid:
            # 유튜브 영상(구글 투명성센터 영상광고 등)은 임베드로 직접 재생(크게)
            stc.html(f"<iframe width='100%' height='460' src='{YT.embed_url(yt_vid)}' "
                     f"frameborder='0' style='border-radius:10px' allowfullscreen "
                     f"allow='accelerometer;autoplay;clipboard-write;encrypted-media;"
                     f"gyroscope;picture-in-picture'></iframe>", height=470)
        elif vurl:
            st.video(vurl)
        elif th["src"]:
            # 구글 소재 스크린샷은 작을 수 있어 최대한 크게(업스케일) 표시
            st.markdown(f"<img src='{th['src']}' style='width:100%;min-height:240px;"
                        f"object-fit:contain;background:#0F172A;border-radius:10px'/>",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='sa-thumb sa-thumb-empty' style='aspect-ratio:1/1'>"
                        f"<div class='sa-ph'><span class='i'>🖼</span>미리보기 없음</div></div>",
                        unsafe_allow_html=True)
        _render_source_buttons(ad)

    # ── 우: 정보 → 소셜반응 → 카피 → 스크립트 → 메모 ──
    with right:
        if ad.get("ad_title"):
            st.markdown(f"#### {ad['ad_title']}")
        info = st.columns(3)
        info[0].metric("상태", "라이브" if ad.get("status") == "live" else (ad.get("status") or "-"))
        info[1].metric("게재 시작", str(_g(ad, "started_at", "-"))[:10] or "-")
        info[2].metric("플랫폼", PLATFORM_LABEL.get(plat, plat or "-"))

        # 대시보드형 지표(상태/게재/플랫폼 바로 아래) — 구글 영상=유튜브 공개 지표
        yv, yl, yc = (int(ad.get("yt_views") or 0), int(ad.get("yt_likes") or 0),
                      int(ad.get("yt_comments") or 0))
        if ad.get("video_url") and (yv or yl or yc):
            cards = [("👁", "조회수", _full(yv) + ("회" if yv else ""), "#03C75A"),
                     ("❤", "좋아요", _full(yl), "#EF4444"),
                     ("💬", "댓글", _full(yc), "#0EA5E9")]
            html = "<div style='display:flex;gap:10px;margin:10px 0 6px'>"
            for icon, lab, val, col in cards:
                html += (f"<div style='flex:1;background:#F8FFFB;border:1px solid {S.BORDER};"
                         f"border-radius:16px;padding:14px 8px;text-align:center'>"
                         f"<div style='font-size:12px;color:{S.SUB};font-weight:700'>{icon} {lab}</div>"
                         f"<div style='font-size:27px;font-weight:900;color:{col};"
                         f"line-height:1.25;font-variant-numeric:tabular-nums'>{val}</div></div>")
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)
            # 조회수 추이 그래프(일자별 스냅샷이 2개 이상 쌓이면 표시)
            snaps = database.get_ad_snapshots(aid, days=60)
            if len(snaps) >= 2:
                import pandas as _pd
                df = _pd.DataFrame(snaps)
                df = df.rename(columns={"snapshot_date": "날짜", "views": "조회수"})[["날짜", "조회수"]]
                df = df.set_index("날짜")
                st.markdown("<div style='font-size:12px;color:#64748B;margin:6px 0 2px'>"
                            "조회수 추이</div>", unsafe_allow_html=True)
                st.line_chart(df, height=160)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            # 출처/신뢰도 명확화: 메타 라이브러리 지표가 아니라 연결된 유튜브 원본 영상의 공개 지표
            st.caption("출처: 연결된 유튜브 원본 영상의 공개 지표(YouTube API) · 광고 성과 지표 아님(참고용)")
        elif plat == "meta":
            st.caption("ℹ️ 메타 광고 라이브러리는 조회수·좋아요·댓글 등 반응 지표를 제공하지 않습니다.")
        elif plat == "google":
            st.caption("ℹ️ 이 구글 광고는 유튜브 영상이 아니어서 조회수·좋아요 지표가 없습니다.")

        d_plats = [p.strip() for p in (ad.get("platforms") or "").split(",") if p.strip()]
        if d_plats:
            chips = " ".join(f"<span style='background:{S.BG};border:1px solid {S.BORDER};"
                             f"padding:1px 8px;border-radius:6px;font-size:12px;margin-right:3px'>"
                             f"{PLAT_ICON.get(p,'')} {p}</span>" for p in d_plats)
            st.markdown(f"**게재 위치** {chips}", unsafe_allow_html=True)
        if ad.get("cta"):
            st.markdown(f"**CTA 버튼** <span style='background:{S.SOFT_MINT};color:{S.DEEP};"
                        f"padding:1px 8px;border-radius:6px;font-size:12px;font-weight:700'>"
                        f"{ad['cta']}</span>", unsafe_allow_html=True)
        nab = int(ad.get("ad_variant_count") or 1)
        if plat == "meta" and nab >= 2:
            st.markdown(f"**A/B 테스트** <span style='background:#F59E0B;color:#fff;"
                        f"padding:1px 8px;border-radius:6px;font-size:12px;font-weight:700'>"
                        f"광고 {nab}개</span> "
                        f"<span style='font-size:11px;color:{S.SUB}'>· 같은 크리에이티브·문구를 "
                        f"여러 광고에서 사용</span>", unsafe_allow_html=True)
        if ad.get("landing_url"):
            st.markdown(f"**랜딩** <span style='font-size:12px'>"
                        f"[{ad['landing_url'][:54]}…]({ad['landing_url']})</span>",
                        unsafe_allow_html=True)
        st.caption(f"광고 ID {aid} · 수집일 {str(_g(ad,'collected_at','-'))[:10]}")

        st.divider()
        st.markdown("##### 광고 카피")
        if ad.get("ad_copy"):
            st.markdown(_greybox(ad["ad_copy"]), unsafe_allow_html=True)
        else:
            st.caption("광고 카피가 없습니다.")

        st.divider()
        _render_video_script(ad)

    # ── 분석 메모(스크립트와 분리) ──
    st.divider()
    st.markdown("##### 분석 메모")
    memo = st.text_area("메모", value=ad.get("memo") or "", label_visibility="collapsed",
                        key=f"memo_{aid}", placeholder="이 레퍼런스의 후킹/구조/인사이트 메모…")
    cc = st.columns([1, 1, 2])
    if cc[0].button("💾 메모 저장", use_container_width=True, type="primary", key=f"sm_{aid}"):
        database.update_memo(aid, memo)
        st.toast("메모 저장됨")
        _reload()
    marked = bool(ad.get("is_bookmarked"))
    if cc[1].button("🔖 북마크 해제" if marked else "🏷️ 북마크 추가",
                    use_container_width=True, key=f"bmm_{aid}"):
        database.update_bookmark(aid, not marked)
        _reload()
    with cc[2].popover("🔗 YouTube 원본 연결"):
        if not YT.is_enabled():
            st.caption("YOUTUBE_API_KEY 등록 시 사용 가능")
        else:
            yurl = st.text_input("YouTube URL", key=f"yt_{aid}", placeholder="watch?v=… / shorts/…")
            if st.button("연결", key=f"ytlink_{aid}", type="primary"):
                vid = YT.extract_video_id(yurl)
                data = YT.fetch_video(vid) if vid else None
                if not data:
                    st.error("유효한 URL/영상 아님")
                else:
                    data["brand_name"] = ad.get("brand_name")
                    database.ingest_social_videos([data])
                    database.add_snapshot(data["id"], data["views"], data["likes"],
                                          data["comments"], data["shares"])
                    database.link_ad_social(aid, data["id"], 100.0)
                    database.regrade()
                    st.success("연결 완료")
                    _reload()


# ════════════════════════════════════════════════════════════
def render_empty_state(msg: str = "표시할 광고가 없습니다") -> None:
    st.markdown(f"""
    <div style='text-align:center; padding:5rem 1rem; color:{S.SUB}'>
      <div style='font-size:54px'>🗂️</div>
      <div style='font-size:17px; font-weight:700; color:{S.TEXT}; margin-top:.6rem'>{msg}</div>
      <div style='font-size:13px; margin-top:.3rem'>필터를 바꾸거나 새 브랜드를 수집해 보세요.</div>
    </div>
    """, unsafe_allow_html=True)


def render_ad_grid(rows: list[dict], total: int, page: int, page_size: int) -> None:
    """rows 는 이미 잘린 현재 페이지(SQL LIMIT/OFFSET)."""
    if not rows:
        render_empty_state("조건에 맞는 광고가 없습니다")
        return
    total_pages = max(1, (total + page_size - 1) // page_size)
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for col, ad in zip(cols, rows[i:i + 4]):
            with col:
                render_ad_card(ad, i)
    nav = st.columns([1, 1, 6, 1])
    if nav[0].button("◀ 이전", disabled=page <= 1, use_container_width=True):
        st.session_state.sa_page = page - 1
        st.rerun()
    nav[2].markdown(f"<div style='text-align:center;color:{S.SUB};font-size:13px;margin-top:6px'>"
                    f"페이지 {page} / {total_pages}</div>", unsafe_allow_html=True)
    if nav[1].button("다음 ▶", disabled=page >= total_pages, use_container_width=True):
        st.session_state.sa_page = page + 1
        st.rerun()


def render_add_youtube() -> None:
    """YouTube 영상 URL 수동 등록."""
    with st.expander("➕ YouTube 영상 등록"):
        if not YT.is_enabled():
            st.info("YOUTUBE_API_KEY를 등록하면 YouTube 조회수/좋아요/댓글 수집이 가능합니다.")
            return
        url = st.text_input("YouTube URL", key="yt_add_url",
                            placeholder="watch?v=... / shorts/... / youtu.be/...")
        brand = st.text_input("브랜드명(선택)", key="yt_add_brand", placeholder="예: 더스크랙")
        if st.button("등록", type="primary", key="yt_add_btn"):
            vid = YT.extract_video_id(url)
            if not vid:
                st.error("유효한 YouTube URL이 아닙니다.")
                return
            data = YT.fetch_video(vid)
            if not data:
                st.error("영상 정보를 가져오지 못했습니다.")
                return
            if brand.strip():
                data["brand_name"] = brand.strip()
            database.ingest_social_videos([data])          # 중복(video_id)이면 갱신
            database.add_snapshot(data["id"], data["views"], data["likes"],
                                  data["comments"], data["shares"])
            database.regrade()
            st.success(f"등록/갱신: {data['title'][:40]} ({_fmt(data['views'])}회)")
            _reload()


def _social_card(v: dict) -> None:
    plat = v.get("platform")
    thumb = v.get("thumbnail_url")
    grade = v.get("final_grade")
    inner = f"<img src='{thumb}'/>" if thumb else "<div class='sa-ph'>🎬</div>"
    badge = (f"<div class='sa-badge' style='background:{S.grade_color(grade)}'>{grade}급</div>"
             if grade and grade != "미분류" else "")
    rs = v.get("review_status") or "needs_review"
    rs_label = {"approved": "✅ 승인", "needs_review": "🔍 검토필요", "rejected": "🚫 제외"}.get(rs, rs)
    with st.container(border=True):
        st.markdown(
            f"<div class='sa-thumb'>{inner}{badge}<div class='sa-play'>▶</div>"
            f"<div class='sa-media'>{PLATFORM_LABEL.get(plat,'소셜')}</div></div>"
            f"<div class='sa-brand'>{v.get('brand_name','-')} "
            f"<span style='font-size:10px;color:{S.SUB}'>{rs_label}</span></div>"
            f"<div class='sa-title'>{(v.get('title') or v.get('caption') or '')[:42]}</div>"
            f"<div class='sa-copy'>{(v.get('channel_title') or '')[:40]}</div>"
            f"<div class='sa-meta'><span>👁 {_fmt(v.get('views'))} ❤ {_fmt(v.get('likes'))} "
            f"💬 {_fmt(v.get('comments'))}</span><span class='sa-pbadge'>소셜 원본</span></div>"
            f"<div class='sa-meta'><span>📅 {str(v.get('posted_at') or '-')[:10]}</span>"
            f"<span class='sa-pbadge'>{'📝 스크립트' if (v.get('script_status') in ('extracted','manual','exists')) else '스크립트 없음'}</span></div>",
            unsafe_allow_html=True)
        if st.button("상세 보기", key=f"sv_{v.get('id')}", use_container_width=True):
            render_social_detail(v)


def render_social_grid(vids: list[dict]) -> None:
    """소셜 원본 영상 그리드 — 조회수/좋아요/댓글은 원본 반응 지표(광고 성과 아님)."""
    st.markdown(f"**🎬 소셜 원본 영상** <span style='font-size:12px;color:{S.SUB}'>"
                f"· 조회수·좋아요·댓글은 원본 영상 반응 기준 (광고 성과 아님)</span>",
                unsafe_allow_html=True)
    render_add_youtube()

    fc = st.columns([2, 1.4])
    plats = ["전체", "TikTok", "Instagram", "YouTube"]
    pick = fc[0].segmented_control("플랫폼", plats, default="전체",
                                   label_visibility="collapsed", key="sv_plat") or "전체"
    incl_review = fc[1].toggle("검토 필요 포함", value=False, key="sv_review",
                               help="기본은 승인(approved)만. 켜면 검토필요도 표시. 제외(rejected)는 항상 숨김")
    pmap = {"TikTok": "tiktok", "Instagram": "instagram", "YouTube": "youtube"}

    def keep(v):
        if pick != "전체" and v.get("platform") != pmap.get(pick):
            return False
        rs = v.get("review_status") or "needs_review"
        if rs == "rejected":
            return False
        if rs == "needs_review" and not incl_review:
            return False
        return True

    rows = [v for v in vids if keep(v)]
    n_app = sum(1 for v in vids if (v.get("review_status") == "approved"))
    n_rev = sum(1 for v in vids if (v.get("review_status") == "needs_review"))
    st.caption(f"승인 {n_app} · 검토 필요 {n_rev} · 제외 {sum(1 for v in vids if v.get('review_status')=='rejected')}"
               f"  (브랜드 공식 계정/도메인/키워드 기반 매칭 점수로 분류)")

    if not rows:
        render_empty_state("표시할 소셜 영상이 없습니다")
        if n_rev and not incl_review:
            st.info(f"승인된 영상이 없습니다. '검토 필요 포함'을 켜면 {n_rev}건을 검토할 수 있습니다.")
        elif not YT.is_enabled():
            st.info("YouTube는 **YOUTUBE_API_KEY**, TikTok/IG는 **APIFY_TOKEN**을 등록하면 수집됩니다.")
        return
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for col, v in zip(cols, rows[i:i + 4]):
            with col:
                _social_card(v)


YT_CLS = {
    "youtube_ad_matched": ("광고 확정", S.PRIMARY),
    "youtube_ad_candidate": ("광고 후보", "#F59E0B"),
    "not_matched": ("미매칭", S.SUB),
    "youtube_social_or_ppl": ("미매칭", S.SUB),   # 구버전 호환
}
YT_CONF = {"high": "확신 높음", "medium": "검토 필요", "low": "약함", "none": "근거 부족"}


def _run_yt_match(brand: str) -> None:
    """인라인 실행 — subprocess는 Streamlit secrets(YOUTUBE_API_KEY)를 못 읽으므로 직접 호출."""
    if not YT.is_enabled():
        st.error("YOUTUBE_API_KEY가 설정되지 않아 매칭할 수 없습니다. (배포 시 secrets에 등록 필요)")
        return
    import jobs.match_youtube_ads as MJ
    target = brand if brand and brand != "전체" else ""
    if target:
        brands = [target]
    else:
        conn = database.get_conn()
        brands = [r[0] for r in conn.execute(
            "SELECT DISTINCT brand_name FROM ad_library_ads WHERE brand_name<>''").fetchall()]
        conn.close()
    if not brands:
        st.warning("구글 광고를 가진 브랜드가 없습니다. 먼저 구글 투명성센터 광고를 수집하세요.")
        return
    before = sum(database.youtube_candidate_counts().values())
    tot = {"matched": 0, "candidate": 0, "ppl": 0}
    with st.spinner(f"{len(brands)}개 브랜드 YouTube 광고 매칭 중… (검색→유사도→분류)"):
        for b in brands:
            try:
                r = MJ.match_brand(b)
                for k in tot:
                    tot[k] += r.get(k, 0)
            except Exception as e:  # noqa: BLE001
                st.warning(f"{b}: {type(e).__name__} {e}")
    after = sum(database.youtube_candidate_counts().values())
    added = after - before
    st.success(f"매칭 완료 — 대상 {len(brands)}개 브랜드 · 광고확정 {tot['matched']} · "
               f"후보 {tot['candidate']} · 미매칭 {tot['ppl']} (신규 {max(added,0)}건)")
    if tot["matched"] + tot["candidate"] + tot["ppl"] == 0:
        st.info("후보 영상이 0건입니다. YouTube 검색 결과가 없거나 API 키/쿼터 문제일 수 있습니다.")


def _yt_match_card(c: dict) -> None:
    import json as _json
    status = c.get("match_status") or c.get("classification")
    label, color = YT_CLS.get(status, ("?", S.SUB))
    conf = YT_CONF.get(c.get("matching_confidence") or "", "")
    th = c.get("thumbnail_url") or ""
    dur = int(c.get("duration_sec") or 0)
    durtxt = f"{dur//60}:{dur%60:02d}" if dur else "-"
    cap = "· 자막" if c.get("has_caption") else ""
    try:
        why = _json.loads(c.get("matched_by") or "[]")
    except Exception:  # noqa: BLE001
        why = []
    try:
        sg = _json.loads(c.get("signals") or "{}")
    except Exception:  # noqa: BLE001
        sg = {}
    chan = c.get("source_account_name") or c.get("channel_title") or "-"
    legal = c.get("advertiser_legal_name") or "-"
    with st.container(border=True):
        if th:
            st.markdown(f"<div class='sa-thumb'><img src='{th}'/>"
                        f"<div class='sa-badge' style='background:{color}'>{int(c.get('matching_score') or 0)}</div>"
                        f"<div class='sa-media'>{durtxt}</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:700;font-size:12px;color:{color};margin-top:6px'>{label}"
                    f"<span style='color:{S.SUB};font-weight:500'> · 신뢰도 {conf}</span></div>"
                    f"<div class='sa-title'>{(c.get('title') or '(제목 없음)')[:46]}</div>"
                    f"<div class='sa-copy'>채널 {chan[:22]} · {str(c.get('published_at') or '')[:10]} {cap}</div>",
                    unsafe_allow_html=True)
        if why:
            st.caption("근거: " + " · ".join(why))
        # 왜 이 분류인지 — 5개 신호 상세(특히 후보 검토용)
        def _mk(ok):
            return ("✓" if ok else "·")
        cs = int((sg.get("copy_sim") or 0) * 100)
        ts = sg.get("thumb_sim")
        tstxt = f"{int(ts*100)}%" if ts is not None else "—"
        with st.expander("근거 상세", expanded=(status == "youtube_ad_candidate")):
            st.markdown(
                f"<div style='font-size:11.5px;line-height:1.7;color:{S.TEXT}'>"
                f"법인명: <b>{legal}</b> · 채널: <b>{chan}</b><br>"
                f"랜딩 URL 일치 <b>{_mk(sg.get('landing_hit'))}</b> · "
                f"브랜드/상품명 일치 <b>{_mk(sg.get('product_in_body'))}</b> · "
                f"채널명 일치 <b>{_mk(sg.get('channel_hit'))}</b><br>"
                f"문구 유사도 <b>{cs}%</b> · 썸네일 유사도 <b>{tstxt}</b> · "
                f"해시태그만 {_mk(sg.get('hashtag_only'))}</div>",
                unsafe_allow_html=True)
        if is_valid_external_url(c.get("source_url")):
            st.link_button("YouTube에서 보기", c["source_url"], use_container_width=True)


def render_youtube_ad_matches(brand: str, candidates: list, counts: dict) -> None:
    """YouTube '광고' 매칭 뷰 — 광고 데이터 기반 후보를 3분류해 표시(전체 수집과 분리)."""
    st.markdown(f"**YouTube 광고 매칭** <span style='font-size:12px;color:{S.SUB}'>"
                f"· 광고주·문구·썸네일·랜딩 기준으로 광고 영상만 가려냅니다 (제품명·해시태그만 일치는 광고로 보지 않음)</span>",
                unsafe_allow_html=True)
    run = st.columns([1.4, 3])
    btxt = brand if brand and brand != "전체" else "구글 광고 보유 브랜드 전체"
    if run[0].button(f"'{btxt}' 매칭 실행", use_container_width=True, type="primary"):
        _run_yt_match(brand)
        st.cache_data.clear()
        st.rerun()
    key_ok = YT.is_enabled()   # 키 '값'이 아니라 로딩 여부만 확인
    run[1].caption(f"YouTube API 키: {'로딩됨 ✓' if key_ok else '미설정 ✗ (Cloud Secrets에 YOUTUBE_API_KEY 등록 필요)'}"
                   "  ·  사이드바에서 브랜드를 고르면 그 브랜드만, '전체'면 구글 광고 보유 브랜드 전부 매칭")

    nm = counts.get("youtube_ad_matched", 0)
    nc = counts.get("youtube_ad_candidate", 0)
    npp = counts.get("not_matched", 0) + counts.get("youtube_social_or_ppl", 0)
    pick = st.segmented_control(
        "상태", [f"광고 확정 {nm}", f"광고 후보 {nc}", f"미매칭 {npp}", "전체"],
        default=f"광고 확정 {nm}", label_visibility="collapsed", key="ytm_cls")
    cmap = {f"광고 확정 {nm}": "youtube_ad_matched", f"광고 후보 {nc}": "youtube_ad_candidate",
            f"미매칭 {npp}": "not_matched"}
    want = cmap.get(pick or "")

    def _st(c):
        return c.get("match_status") or c.get("classification")
    if want == "not_matched":
        rows = [c for c in candidates if _st(c) in ("not_matched", "youtube_social_or_ppl")]
    elif want:
        rows = [c for c in candidates if _st(c) == want]
    else:
        rows = candidates

    if not rows:
        if not candidates:
            render_empty_state("아직 매칭 결과가 없습니다 — 위 '매칭 실행'을 눌러주세요")
            if not YT.is_enabled():
                st.info("YouTube 광고 매칭은 **YOUTUBE_API_KEY**가 필요합니다.")
        else:
            render_empty_state("이 분류에 해당하는 영상이 없습니다")
        return
    for i in range(0, len(rows), 4):
        cols = st.columns(4)
        for col, c in zip(cols, rows[i:i + 4]):
            with col:
                _yt_match_card(c)


@st.dialog("소셜 원본 영상", width="large")
def render_social_detail(v: dict) -> None:
    st.info("아래 지표는 **광고 성과가 아니라 원본 소셜 영상(YouTube/TikTok/IG) 반응 기준**입니다.")
    plat = v.get("platform")
    st.markdown(f"### {PLATFORM_LABEL.get(plat,'소셜')} · {v.get('brand_name','-')}")
    if v.get("title"):
        st.markdown(f"**{v['title']}**")
    if v.get("channel_title"):
        st.caption(f"채널: {v['channel_title']} · 게시일 {str(v.get('posted_at') or '-')[:10]}")

    # 브랜드 매칭 검증 + 수동 수정
    rs = v.get("review_status") or "needs_review"
    rs_label = {"approved": "✅ 승인", "needs_review": "🔍 검토필요", "rejected": "🚫 제외"}.get(rs, rs)
    sid = v.get("id")
    st.caption(f"**브랜드 매칭**: {rs_label} · 점수 {int(v.get('brand_match_score') or 0)} · "
               f"사유: {v.get('brand_match_reason') or '-'}")
    rc = st.columns(3)
    if rc[0].button("✅ 이 브랜드 맞음", key=f"appr_{sid}", use_container_width=True):
        database.update_review_status(sid, "approved")
        _reload()
    if rc[1].button("🚫 이 브랜드 아님", key=f"rej_{sid}", use_container_width=True):
        database.update_review_status(sid, "rejected")
        _reload()
    with rc[2].popover("↔ 다른 브랜드"):
        names = [r["name"] for r in database.brand_counts()]
        if names:
            nb = st.selectbox("브랜드 선택", names, key=f"mv_{sid}")
            if st.button("이동", key=f"mvb_{sid}", type="primary"):
                database.move_social_brand(sid, nb)
                _reload()
    st.divider()

    # 영상 재생: YouTube 는 embed iframe, 그 외는 video_url/source
    if plat == "youtube" and v.get("embed_url"):
        stc.html(
            f"<iframe width='100%' height='460' src='{v['embed_url']}' frameborder='0' "
            f"allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; "
            f"picture-in-picture' allowfullscreen style='border-radius:10px'></iframe>", height=470)
    elif v.get("video_url"):
        st.video(v["video_url"])
    elif v.get("thumbnail_url"):
        st.image(v["thumbnail_url"], use_container_width=True)
    if is_valid_external_url(v.get("source_url")):
        st.link_button("▶ YouTube에서 보기 ↗" if plat == "youtube" else "▶ 원본 보기 ↗",
                       v["source_url"], use_container_width=True)

    # 영상 밑 스크립트(자막)
    render_script_section(v.get("id") or "", v.get("video_id") or "")

    m = st.columns(4)
    m[0].metric("조회수", _fmt(v.get("views")))
    m[1].metric("좋아요", _fmt(v.get("likes")))
    m[2].metric("댓글", _fmt(v.get("comments")))
    er = v.get("engagement_rate")
    m[3].metric("참여율", f"{er*100:.1f}%" if er else "-")
    fg, ag = v.get("final_grade"), v.get("absolute_grade")
    st.caption(f"등급: 최종 {fg or '-'}급 · 절대 {ag or '-'}급 · 참여 {v.get('engagement_level') or '-'} "
               f"· YouTube/소셜 원본 기준")

    # 최근 7일 추이
    st.markdown("##### 📈 최근 7일 추이")
    snaps = database.get_snapshots(v.get("id"), days=7)
    if len(snaps) < 2:
        st.caption("추이 데이터가 아직 부족합니다. 며칠 더 수집되면 그래프가 표시됩니다.")
    else:
        import pandas as pd
        df = pd.DataFrame(snaps).set_index("snapshot_date")[["views", "likes", "comments"]]
        st.line_chart(df)


def render_top(ads: list[dict]) -> None:
    """A급 이상 '터진' 소재 모아보기 (소셜 원본 기준)."""
    import services.grading as G
    st.markdown(f"**🔥 TOP — A급 이상 터진 소재** <span style='font-size:12px;color:{S.SUB}'>"
                f"· 소셜 원본 영상 반응 기준 (광고 성과 아님)</span>", unsafe_allow_html=True)
    top = [a for a in ads if G.GRADE_RANK.get(a.get("social_final_grade"), 0) >= G.GRADE_RANK["A"]]
    top.sort(key=lambda a: (G.GRADE_RANK.get(a.get("social_final_grade"), 0),
                            a.get("social_engagement_score") or 0,
                            int(a.get("social_views") or 0)), reverse=True)
    if not top:
        render_empty_state("아직 A급 이상 소재가 없습니다")
        st.info("소셜 원본 영상(TikTok/YouTube 등)이 매칭·등급화되면 여기에 모입니다. "
                "현재는 소셜 데이터가 없어 비어 있습니다.")
        return
    for i in range(0, len(top), 4):
        cols = st.columns(4)
        for col, ad in zip(cols, top[i:i + 4]):
            with col:
                render_ad_card(ad, i)


def render_insights() -> None:
    st.markdown("#### 📊 인사이트")
    s = database.insight_summary()
    if not s["total"]:
        render_empty_state("데이터가 없습니다")
        return
    c = st.columns(4)
    c[0].metric("총 광고", s["total"])
    c[1].metric("영상", s["videos"])
    c[2].metric("라이브", s["live"])
    c[3].metric("북마크", s["bm"])
    st.divider()
    counts = database.brand_counts()[:15]
    st.markdown("**브랜드별 광고 수 (상위 15)**")
    st.bar_chart({b: n for (b, n, _lv) in counts})
    st.markdown("**🔥 터진순 상위 10 (소셜 원본 기준)**")
    for a in database.load_ads_page("TOP", {}, 1, 10):
        g = a.get("social_final_grade") or "-"
        st.write(f"- `{g}급` **{a.get('brand_name')}** · "
                 f"{a.get('ad_title') or (a.get('ad_copy_short') or '')[:40]}")

    st.divider()
    st.markdown("#### 🩺 브랜드 진단 — 0건 브랜드 원인 분류")
    st.caption("사이드바 숫자는 **광고 + 소셜 승인(approved)** 기준. 데이터가 있어도 검토 필요(needs_review)면 0으로 보입니다.")
    diag = database.brand_diagnostics()
    import pandas as pd
    st.dataframe(pd.DataFrame(diag), use_container_width=True, hide_index=True,
                 column_config={"조치": st.column_config.TextColumn(width="large")})
    cause_ko = {"not_collected": "수집 미실행", "no_result": "결과 없음(검색어 부족)",
                "needs_review_only": "검토 필요만 있음(승인 전)", "rejected_only": "전부 무관 판정",
                "ok": "정상", "unknown": "확인 필요"}
    import collections as _c
    dist = _c.Counter(d["원인"] for d in diag)
    st.caption("원인 분포: " + " · ".join(f"{cause_ko.get(k,k)} {v}" for k, v in dist.most_common()))
