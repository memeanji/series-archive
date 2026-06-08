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
    """버튼 클릭 시에만 단건 추출(YouTube 자막). 무거운 자동추출 금지."""
    database.update_script(social_id, "", "extracting")
    text = YT.fetch_transcript(video_id) if video_id else ""
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
                   help="YouTube 자막에서 추출(영상 1건만 실행)"):
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
    h = st.columns([2.4, 4, 1.4])
    with h[0]:
        st.markdown(
            f"<div class='sa-header'><div><div class='sa-logo'>📚 Series Archive</div>"
            f"<div class='sa-sub'>Ad Reference Library for Series Builder</div></div></div>",
            unsafe_allow_html=True)
    search = h[1].text_input("검색", placeholder="🔎 브랜드 · 광고명 · 카피 통합 검색",
                             label_visibility="collapsed").strip().lower()
    with h[2]:
        cc = st.columns([1, 1, 2])
        if cc[0].button("🔄", help="새로고침", use_container_width=True):
            _reload()
        user = st.session_state.get("username", "guest")
        cc[2].markdown(f"<div style='text-align:right;font-size:12px;color:{S.SUB};margin-top:6px'>"
                       f"👤 <b>{user}</b></div>", unsafe_allow_html=True)

    tabs = ["전체", "Meta", "Google", "🔥 TOP", "소셜 영상", "북마크", "인사이트"]
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


def render_add_brand() -> None:
    """브랜드 추가 위저드: 입력 → 후보 찾기 → 선택 → 저장 → 수집(버튼 클릭 시에만)."""
    with st.sidebar.expander("➕ 브랜드 추가", expanded=False):
        name = st.text_input("브랜드명", key="ab_name", placeholder="예: 리바엔").strip()
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
            elif database.brand_exists(name):
                st.warning("이미 등록된 브랜드명입니다.")
            else:
                st.session_state.ab_cands = database.find_brand_candidates(name, domain, keywords)
                st.session_state.ab_searched = True

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

            can_save = bool(name) and (bool(cands) or bool(keywords))
            if st.button("💾 브랜드 저장", key="ab_save", type="primary",
                         disabled=not can_save, use_container_width=True):
                kws = list(dict.fromkeys([name] + keywords + picked))
                database.add_brand(name, kws, domain, cat,
                                   extra={"google_advertiser_name": picked[0] if picked else ""})
                st.session_state.ab_saved = name
                st.session_state.sa_brand = name
                st.cache_data.clear()
                st.success(f"'{name}' 저장됨 (키워드 {len(kws)}개)")

        # Step 5: 수집 실행(버튼 클릭 시에만)
        saved = st.session_state.get("ab_saved")
        if saved:
            stt = database.latest_brand_status(saved)
            st.caption(f"상태: {stt['status'] if stt else '대기'}")
            if st.button(f"📥 '{saved}' 지금 수집", key="ab_collect", use_container_width=True):
                _run_collect(saved)
                for k in ("ab_saved", "ab_searched", "ab_cands"):
                    st.session_state.pop(k, None)
                st.cache_data.clear()
                st.rerun()


def render_sidebar(counts: list, total: int) -> str:
    """counts: [(brand, n, live_flag), ...] (캐시). 상위 20개 + 검색."""
    sb = st.sidebar
    sb.markdown(f"<div style='font-weight:800;color:{S.TEXT};font-size:15px;margin-bottom:.3rem'>"
                f"🏷️ 브랜드</div>", unsafe_allow_html=True)
    render_add_brand()
    q = sb.text_input("브랜드 검색", placeholder="브랜드 찾기", label_visibility="collapsed").strip().lower()

    sel = st.session_state.get("sa_brand", "전체")
    if sb.button(f"📁 전체 브랜드  ·  {total}", key="b_all"):
        st.session_state.sa_brand = "전체"
        st.session_state.sa_page = 1
        st.rerun()
    sb.markdown(f"<hr style='margin:.3rem 0;border-color:{S.BORDER}'>", unsafe_allow_html=True)

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
    cats = opts.get("categories", [])
    has_social = social_count > 0
    c = st.columns([1.1, 1, 1, 1.4, 1.5, 0.9, 0.7])

    grade = c[0].selectbox("등급(소셜 원본 기준)", ["전체", "S급", "A급 이상", "B급 이상", "C급 이상"],
                           index=0, disabled=not has_social, key="f_grade",
                           help="매칭된 소셜 원본 영상이 있는 광고에만 적용됩니다.")
    media = c[1].multiselect("매체(소재)", ["video", "image"],
                             default=st.session_state.get("f_media", []),
                             format_func=lambda x: {"video": "🎬 영상", "image": "🖼 이미지"}.get(x, x),
                             key="f_media")
    status = c[2].selectbox("상태", ["전체", "라이브", "종료", "OFF"], key="f_status")
    categories = c[3].multiselect("카테고리", cats, key="f_cat")
    sort = c[4].selectbox("정렬",
                          ["🔥 터진순(추천)", "조회수 높은순(소셜)", "최근 수집순", "저장 많은순"],
                          index=(0 if has_social else 2), key="f_sort")
    period = c[5].selectbox("기간", ["전체", "7일", "30일", "90일"], key="f_period")
    if c[6].button("초기화", use_container_width=True):
        for k in ("f_grade", "f_media", "f_status", "f_cat", "f_sort", "f_period"):
            st.session_state.pop(k, None)
        st.rerun()
    if not has_social:
        st.caption("ℹ️ 등급 필터는 소셜 영상 데이터가 있어야 활성화됩니다 "
                   "(.env에 APIFY_TOKEN 설정 후 수집 시 S/A/B/C 자동 부여).")
    show_hidden = st.checkbox("🔧 개발자: 검색광고·미디어 없는 광고도 보기", value=False, key="f_devhidden")

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
    chips += list(categories)
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
        "categories": categories,
        "sort": sort,
        "grade": grade,
        "period_days": {"7일": 7, "30일": 30, "90일": 90}.get(period),
        "only_bookmark": only_bm,
        "show_hidden": show_hidden,
    }


# ════════════════════════════════════════════════════════════
def render_ad_card(ad: dict, idx: int) -> None:
    aid = ad.get("id")
    score = int(ad.get("score") or 0)
    plat = ad.get("platform", "")
    is_video = ad.get("media_type") == "video"
    th = get_display_thumbnail(ad)
    thumb = th["src"]

    if thumb:
        inner = f"<img src='{thumb}'/>"
    else:
        inner = f"<div class='sa-ph'>{'🎬' if is_video else '🖼'}</div>"
    play = "<div class='sa-play'>▶</div>" if is_video and thumb else ""
    media_badge = f"<div class='sa-media'>{'▶ 영상' if is_video else '🖼 이미지'}</div>"
    dot = S.status_color(ad.get("status"))

    status_txt = "🟢 라이브" if ad.get("status") == "live" else "⚫ " + str(ad.get("status") or "-")
    grade = ad.get("social_final_grade")
    if grade and ad.get("match_score"):
        eng = (f"<span title='매칭된 소셜 원본 영상 반응'>👁 {_fmt(ad.get('social_views'))} "
               f"❤ {_fmt(ad.get('social_likes'))} "
               f"<span style='color:{S.MINT};font-weight:700'>· 소셜 원본</span></span>")
        badge = (f"<div class='sa-badge' style='background:{S.grade_color(grade)};font-size:14px'>"
                 f"{grade}급</div>")
    else:
        eng = f"<span style='color:{S.SUB}'>게재 {str(_g(ad,'started_at','-'))[:10] or '-'}</span>"
        badge = f"<div class='sa-badge' style='background:{S.score_color(score)}'>{score}</div>"
    with st.container(border=True):
        st.markdown(
            f"<div class='sa-thumb'>{inner}{badge}"
            f"<div class='sa-dot' style='background:{dot}'></div>{play}{media_badge}</div>"
            f"<div class='sa-brand'>{PLATFORM_ICON.get(plat,'')} {_g(ad,'brand_name','-')}</div>"
            f"<div class='sa-title'>{_g(ad,'ad_title') or _g(ad,'ad_copy_short','(제목 없음)')[:40]}</div>"
            f"<div class='sa-copy'>{_g(ad,'ad_copy_short','')[:60]}</div>"
            f"<div class='sa-meta'><span>{eng}</span>"
            f"<span class='sa-pbadge'>{PLATFORM_LABEL.get(plat, plat or '-')}</span></div>"
            f"<div class='sa-meta'><span>📅 수집 {str(_g(ad,'collected_at','-'))[:10]}</span>"
            f"<span>{status_txt}</span></div>",
            unsafe_allow_html=True)
        b = st.columns([3, 1])
        if b[0].button("상세 보기", key=f"open_{aid}_{idx}", use_container_width=True):
            full = database.get_ad_full(aid)   # 상세 클릭 시에만 1건 전체 로드
            if full:
                render_ad_detail(full)
        marked = bool(ad.get("is_bookmarked"))
        if b[1].button("🔖" if marked else "🏷️", key=f"bm_{aid}_{idx}",
                       use_container_width=True, help="북마크"):
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


@st.dialog("광고 상세", width="large")
def render_ad_detail(ad: dict) -> None:
    aid = ad.get("id")
    score = int(ad.get("score") or 0)
    plat = ad.get("platform", "")
    st.markdown(
        f"### {PLATFORM_ICON.get(plat,'')} {_g(ad,'brand_name','-')} "
        f"<span style='color:{S.score_color(score)};font-size:18px'>· {score}점</span>",
        unsafe_allow_html=True)
    st.caption(f"{PLATFORM_LABEL.get(plat, plat)} · "
               f"{'🟢 라이브' if ad.get('status')=='live' else '⚫ '+str(ad.get('status'))} · "
               f"{'🎬 영상' if ad.get('media_type')=='video' else '🖼 이미지'} · "
               f"수집일 {str(_g(ad,'collected_at','-'))[:10]}")

    left, right = st.columns([2, 3])
    with left:
        th = get_display_thumbnail(ad)
        if ad.get("video_url"):
            st.video(ad["video_url"])
        elif th["src"]:
            st.markdown(f"<img src='{th['src']}' style='width:100%;border-radius:10px'/>",
                        unsafe_allow_html=True)
        else:
            st.caption("소재 미리보기 없음")
        _render_source_buttons(ad)
    with right:
        if ad.get("ad_title"):
            st.markdown(f"#### {ad['ad_title']}")
        st.markdown(f"**📄 광고 게재 정보** <span style='font-size:12px;color:{S.SUB}'>"
                    f"· 광고 라이브러리</span>", unsafe_allow_html=True)
        g = st.columns(3)
        g[0].metric("게재 상태", "라이브" if ad.get("status") == "live" else (ad.get("status") or "-"))
        g[1].metric("게재 시작", str(_g(ad, "started_at", "-"))[:10] or "-")
        g[2].metric("플랫폼", PLATFORM_LABEL.get(plat, plat or "-"))
        tags = ad.get("tags") or []
        if tags:
            st.markdown("**태그** " + " ".join(f"`{t}`" for t in tags))
        if ad.get("landing_url"):
            st.markdown(f"**랜딩 URL** [{ad['landing_url'][:64]}]({ad['landing_url']})")

    st.divider()
    if ad.get("ad_copy"):
        st.markdown("##### 📝 광고 카피")
        st.write(ad["ad_copy"])

    # 소셜 원본 반응 — 광고 성과가 아니라 매칭된 원본 영상 지표(출처 명시)
    st.markdown(f"##### 📊 소셜 원본 반응 <span style='font-size:12px;color:{S.SUB}'>"
                f"· 매칭된 원본 영상 기준 (광고 성과 아님)</span>", unsafe_allow_html=True)
    if ad.get("match_score"):
        st.info("아래 수치는 **광고 성과가 아니라 매칭된 원본 소셜 영상(TikTok/IG/YT)의 반응 지표**입니다.")
        sc = st.columns(4)
        sc[0].metric("조회수", _fmt(ad.get("social_views")))
        sc[1].metric("좋아요", _fmt(ad.get("social_likes")))
        sc[2].metric("댓글", _fmt(ad.get("social_comments")))
        sc[3].metric("공유", _fmt(ad.get("social_shares")))
        er = ad.get("social_engagement_rate")
        gr = st.columns(4)
        gr[0].metric("참여율", f"{er*100:.1f}%" if er else "-")
        fg = ad.get("social_final_grade")
        gr[1].metric("최종 등급", f"{fg}급" if fg else "-")
        ag = ad.get("social_absolute_grade")
        gr[2].metric("절대 등급", f"{ag}급" if ag else "-")
        ig = ad.get("social_internal_grade")
        ip = ad.get("social_internal_percentile")
        gr[3].metric("내부 등급", f"{ig}급" if ig else "준비중")
        basis_ko = {"absolute_only": "절대 기준", "platform_category_percentile": "플랫폼·카테고리 분위수",
                    "platform_percentile": "플랫폼 분위수", "global_percentile": "전체 분위수"}
        bits = [f"출처: {(ad.get('social_platform') or '소셜').upper()} 원본 영상",
                f"참여율 {ad.get('social_engagement_level') or '-'}",
                f"기준: {basis_ko.get(ad.get('social_grading_basis'), '준비중')}"]
        if ig and ip is not None:
            bits.append(f"내부 상위 {round((1-ip)*100)}%")
        bits.append(f"매칭도 {ad.get('match_score')}점")
        st.caption(" · ".join(bits))
        if ad.get("social_source_url"):
            st.markdown(f"[▶ 원본 영상 보기 ↗]({ad['social_source_url']})")
        if ad.get("social_platform") == "youtube":
            render_script_section(ad.get("social_id") or "",
                                   YT.extract_video_id(ad.get("social_source_url") or "") or "")
    else:
        st.info("매칭된 소셜 원본 영상이 없습니다. `.env`에 APIFY_TOKEN을 넣고 수집하면 "
                "TikTok 원본의 조회수·좋아요·댓글·공유와 등급(S/A/B/C)이 여기에 표시됩니다.")

    # 소셜 원본 영상(YouTube) 수동 연결
    with st.expander("🔗 소셜 원본 영상(YouTube) 연결"):
        if not YT.is_enabled():
            st.info("YOUTUBE_API_KEY를 .env 또는 secrets.toml에 등록하면 YouTube 원본을 연결할 수 있습니다.")
        else:
            yurl = st.text_input("YouTube URL", key=f"yt_{aid}",
                                 placeholder="https://youtube.com/watch?v=... / shorts/... / youtu.be/...")
            if st.button("연결", key=f"ytlink_{aid}", type="primary"):
                vid = YT.extract_video_id(yurl)
                if not vid:
                    st.error("유효한 YouTube URL이 아닙니다.")
                else:
                    data = YT.fetch_video(vid)
                    if not data:
                        st.error("영상 정보를 가져오지 못했습니다(API 키/영상 확인).")
                    else:
                        data["brand_name"] = ad.get("brand_name")
                        database.ingest_social_videos([data])
                        database.add_snapshot(data["id"], data["views"], data["likes"],
                                              data["comments"], data["shares"])
                        database.link_ad_social(aid, data["id"], 100.0)
                        database.regrade()
                        st.success(f"연결 완료: {data['title'][:40]}")
                        _reload()

    st.markdown("##### 📒 분석 메모")
    memo = st.text_area("메모", value=ad.get("memo") or "", label_visibility="collapsed",
                        key=f"memo_{aid}", placeholder="이 레퍼런스의 후킹/구조/인사이트 메모…")
    cc = st.columns(2)
    if cc[0].button("💾 메모 저장", use_container_width=True, type="primary", key=f"sm_{aid}"):
        database.update_memo(aid, memo)
        st.toast("메모 저장됨")
        _reload()
    marked = bool(ad.get("is_bookmarked"))
    if cc[1].button("🔖 북마크 해제" if marked else "🏷️ 북마크 추가",
                    use_container_width=True, key=f"bmm_{aid}"):
        database.update_bookmark(aid, not marked)
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
