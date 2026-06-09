"""Series Archive custom CSS — 그린/민트 SaaS 룩."""
import streamlit as st

# 팔레트
PRIMARY = "#03C75A"      # Naver green
DEEP = "#10B981"
MINT = "#2DD4BF"
SOFT_MINT = "#ECFDF5"
BG = "#F8FAFC"
CARD = "#FFFFFF"
TEXT = "#1E293B"
SUB = "#64748B"
BORDER = "#E2E8F0"
END_RED = "#EF4444"
OFF_GRAY = "#94A3B8"


def status_color(status: str) -> str:
    return {"live": PRIMARY, "ended": END_RED, "inactive": OFF_GRAY}.get(status, OFF_GRAY)


def score_color(s: int) -> str:
    return DEEP if s >= 80 else PRIMARY if s >= 60 else OFF_GRAY


def grade_color(g: str) -> str:
    return {"S": "#0F766E", "A": "#10B981", "B": "#0EA5A4", "C": "#94A3B8"}.get(g, "#CBD5E1")


def inject_css() -> None:
    st.markdown(f"""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
      html, body, [class*="css"], .stApp, button, input, select, textarea {{
          font-family: Pretendard, -apple-system, BlinkMacSystemFont, system-ui, "Segoe UI",
                       "Malgun Gothic", sans-serif !important; }}
      /* 메인 폭 제한 + 여백(밀도 ↑) */
      .block-container {{padding: 0.4rem 1.8rem 2rem !important; max-width: 1480px;}}
      [data-testid="stHorizontalBlock"] {{gap: 0.7rem;}}
      [data-testid="stVerticalBlock"] {{gap: 0.45rem;}}
      ::-webkit-scrollbar {{width: 7px; height: 7px;}}
      ::-webkit-scrollbar-thumb {{background: #CBD5E1; border-radius: 8px;}}
      ::-webkit-scrollbar-track {{background: transparent;}}

      /* 헤더 통합검색 input(낮게) */
      .stTextInput input {{height: 38px; border-radius: 10px !important; border:1px solid {BORDER};
          background:#fff; font-size:13.5px;}}
      .stTextInput input:focus {{border-color:{PRIMARY}; box-shadow:0 0 0 3px {SOFT_MINT};}}

      /* selectbox / multiselect — 낮고 컴팩트하게 */
      div[data-baseweb="select"] > div {{border-radius:10px !important; border-color:{BORDER} !important;
          min-height:38px; background:#fff; font-size:13px;}}
      .stSelectbox label, .stMultiSelect label {{font-size:12px !important; color:{SUB};
          font-weight:600; margin-bottom:1px !important;}}
      div[data-testid="stCheckbox"] label {{font-size:11.5px; color:{OFF_GRAY};}}

      /* segmented control(탭/필터) → 작은 pill */
      div[data-testid="stSegmentedControl"] button {{border-radius:9px !important;
          font-size:12.5px; font-weight:600; border:1px solid {BORDER}; padding:3px 12px;}}
      div[data-testid="stSegmentedControl"] button[aria-checked="true"],
      div[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"] {{
          background:{SOFT_MINT} !important; color:{DEEP} !important; border-color:{PRIMARY} !important;}}
      #MainMenu, footer {{visibility:hidden;}}
      /* header(상단 툴바)는 숨기지 않음 — 사이드바 펼치는 '>' 버튼이 여기 들어있다.
         배경만 투명 처리해 깔끔하게, 펼침/접기 컨트롤은 항상 보이도록 강제. */
      header[data-testid="stHeader"] {{background:transparent;}}
      [data-testid="stSidebarCollapseButton"],
      [data-testid="stSidebarCollapsedControl"],
      [data-testid="collapsedControl"] {{
          visibility:visible !important; display:flex !important; opacity:1 !important;}}
      .stApp {{background:{BG};}}
      .block-container {{padding-top:1rem; padding-bottom:2.5rem; max-width:1560px;}}

      /* ── 헤더 ── */
      .sa-header {{display:flex; align-items:center; gap:12px;}}
      .sa-logo {{font-size:18px; font-weight:800; color:{PRIMARY}; line-height:1.1; white-space:nowrap;}}
      .sa-sub {{font-size:11px; color:{SUB}; margin-top:1px;}}
      .sa-info {{color:{SUB}; font-size:12.5px; margin:.2rem 0 .6rem;}}
      .sa-info b {{color:{TEXT};}}

      /* ── 칩 ── */
      .sa-chip {{display:inline-block; background:{SOFT_MINT}; color:{DEEP}; border:1px solid #A7F3D0;
                 font-size:12px; padding:2px 10px; border-radius:999px; margin:0 6px 6px 0;}}

      /* ── 카드 ── */
      div[data-testid="stVerticalBlockBorderWrapper"] {{
          background:{CARD}; border:1px solid {BORDER} !important; border-radius:16px;
          box-shadow:0 1px 2px rgba(16,24,40,.04); transition:transform .15s, box-shadow .15s;}}
      div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
          transform:translateY(-3px); box-shadow:0 8px 22px rgba(16,24,40,.10);}}
      .sa-thumb {{position:relative; aspect-ratio:16/10; border-radius:12px; overflow:hidden;
                  background:#0F172A;}}
      .sa-thumb img {{width:100%; height:100%; object-fit:cover;}}
      .sa-badge {{position:absolute; top:8px; left:8px; color:#fff; font-weight:800; font-size:12px;
                  padding:3px 9px; border-radius:999px; box-shadow:0 1px 4px rgba(0,0,0,.2);}}
      .sa-dot {{position:absolute; top:10px; right:10px; width:11px; height:11px; border-radius:50%;
                box-shadow:0 0 0 2px #fff;}}
      .sa-media {{position:absolute; bottom:8px; right:8px; background:rgba(15,23,42,.78); color:#fff;
                  font-size:11px; font-weight:700; padding:2px 8px; border-radius:6px;}}
      .sa-play {{position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); font-size:38px;
                 color:#fff; opacity:.95; text-shadow:0 2px 10px rgba(0,0,0,.55);}}
      .sa-thumb-empty {{background:{BG} !important; border:1px dashed {BORDER};}}
      .sa-ph {{position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
               text-align:center; color:{OFF_GRAY}; font-size:13px; font-weight:600;}}
      .sa-ph .i {{display:block; font-size:30px; margin-bottom:2px; opacity:.7;}}
      .sa-brand {{font-weight:800; font-size:15.5px; color:{PRIMARY}; margin-top:7px;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
      .sa-title {{font-size:14.5px; color:{TEXT}; font-weight:700; margin-top:1px; line-height:1.25;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
      .sa-copy {{font-size:12px; color:{SUB}; line-height:1.3; margin-top:2px; min-height:30px;
                 display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}}
      .sa-meta {{font-size:13px; color:{SUB}; margin-top:5px; display:flex; justify-content:space-between;}}
      .sa-pbadge {{font-size:11.5px; font-weight:700; color:{SUB}; background:{BG};
                   border:1px solid {BORDER}; padding:1px 7px; border-radius:6px;}}

      /* ── 버튼 ── */
      div[data-testid="stButton"] button {{border-radius:9px; font-size:12px; border:1px solid {BORDER};
          color:{TEXT}; background:{CARD};}}
      div[data-testid="stButton"] button:hover {{border-color:{PRIMARY}; color:{PRIMARY};}}
      div[data-testid="stButton"] button[kind="primary"] {{background:{PRIMARY}; border-color:{PRIMARY}; color:#fff;}}

      /* ── 사이드바(흰 카드) ── */
      section[data-testid="stSidebar"] {{background:{CARD}; border-right:1px solid {BORDER};
          width:320px !important; min-width:320px !important;}}
      section[data-testid="stSidebar"] > div {{width:320px !important;}}
      section[data-testid="stSidebar"] .block-container {{padding:1rem 18px 1rem !important;}}
      section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{gap:.4rem;}}
      /* 브랜드 row: 이름 왼쪽 · 개수 오른쪽(양끝 정렬) */
      section[data-testid="stSidebar"] div[data-testid="stButton"] button {{
          width:100%; background:transparent; border:none; color:{TEXT};
          font-size:13px; padding:9px 10px; min-height:0; line-height:1.3; border-radius:8px;}}
      section[data-testid="stSidebar"] div[data-testid="stButton"] button p {{
          display:flex; justify-content:space-between; align-items:center; width:100%; margin:0;}}
      section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
          background:{SOFT_MINT}; color:{DEEP};}}
      section[data-testid="stSidebar"] .stTextInput input {{height:38px;}}
      section[data-testid="stSidebar"] hr {{margin:.45rem 0 !important;}}
      section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{margin:0 !important;}}
      section[data-testid="stSidebar"] [data-testid="stExpander"] {{margin:.15rem 0;}}
      section[data-testid="stSidebar"] [data-testid="stExpander"] summary {{padding:.3rem .6rem;}}
      section[data-testid="stSidebar"] [data-testid="stElementContainer"] {{margin-bottom:0 !important;}}

      /* 탭(segmented) 라운드 */
      div[data-testid="stSegmentedControl"] button {{border-radius:9px;}}
    </style>
    """, unsafe_allow_html=True)
