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
      #MainMenu, footer, header {{visibility:hidden;}}
      .stApp {{background:{BG};}}
      .block-container {{padding-top:1rem; padding-bottom:2.5rem; max-width:1560px;}}

      /* ── 헤더 ── */
      .sa-header {{display:flex; align-items:center; gap:12px;}}
      .sa-logo {{font-size:21px; font-weight:800; color:{PRIMARY}; line-height:1; white-space:nowrap;}}
      .sa-sub {{font-size:12px; color:{SUB}; margin-top:2px;}}
      .sa-info {{color:{SUB}; font-size:13px; margin:.4rem 0 1rem;}}
      .sa-info b {{color:{TEXT};}}

      /* ── 칩 ── */
      .sa-chip {{display:inline-block; background:{SOFT_MINT}; color:{DEEP}; border:1px solid #A7F3D0;
                 font-size:12px; padding:2px 10px; border-radius:999px; margin:0 6px 6px 0;}}

      /* ── 카드 ── */
      div[data-testid="stVerticalBlockBorderWrapper"] {{
          background:{CARD}; border:1px solid {BORDER} !important; border-radius:16px;
          box-shadow:0 1px 2px rgba(16,24,40,.04); transition:transform .15s, box-shadow .15s;}}
      div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
          transform:translateY(-4px); box-shadow:0 10px 24px rgba(3,199,90,.12);}}
      .sa-thumb {{position:relative; aspect-ratio:4/3; border-radius:12px; overflow:hidden;
                  background:linear-gradient(160deg,{SOFT_MINT},#E0F2FE);}}
      .sa-thumb img {{width:100%; height:100%; object-fit:cover;}}
      .sa-badge {{position:absolute; top:8px; left:8px; color:#fff; font-weight:800; font-size:12px;
                  padding:3px 9px; border-radius:999px; box-shadow:0 1px 4px rgba(0,0,0,.2);}}
      .sa-dot {{position:absolute; top:10px; right:10px; width:11px; height:11px; border-radius:50%;
                box-shadow:0 0 0 2px #fff;}}
      .sa-media {{position:absolute; bottom:8px; right:8px; background:rgba(15,23,42,.78); color:#fff;
                  font-size:11px; font-weight:700; padding:2px 8px; border-radius:6px;}}
      .sa-play {{position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); font-size:38px;
                 color:#fff; opacity:.95; text-shadow:0 2px 10px rgba(0,0,0,.55);}}
      .sa-ph {{position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); font-size:40px; opacity:.6;}}
      .sa-brand {{font-weight:800; font-size:13px; color:{PRIMARY}; margin-top:9px;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
      .sa-title {{font-size:12.5px; color:{TEXT}; font-weight:600; margin-top:1px;
                  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
      .sa-copy {{font-size:11.5px; color:{SUB}; height:30px; overflow:hidden; line-height:1.28; margin-top:2px;}}
      .sa-meta {{font-size:11.5px; color:{SUB}; margin-top:6px; display:flex; justify-content:space-between;}}
      .sa-pbadge {{font-size:10.5px; font-weight:700; color:{SUB}; background:{BG};
                   border:1px solid {BORDER}; padding:1px 7px; border-radius:6px;}}

      /* ── 버튼 ── */
      div[data-testid="stButton"] button {{border-radius:9px; font-size:12px; border:1px solid {BORDER};
          color:{TEXT}; background:{CARD};}}
      div[data-testid="stButton"] button:hover {{border-color:{PRIMARY}; color:{PRIMARY};}}
      div[data-testid="stButton"] button[kind="primary"] {{background:{PRIMARY}; border-color:{PRIMARY}; color:#fff;}}

      /* ── 사이드바(흰 카드) ── */
      section[data-testid="stSidebar"] {{background:{CARD}; border-right:1px solid {BORDER};}}
      section[data-testid="stSidebar"] div[data-testid="stButton"] button {{
          width:100%; text-align:left; background:transparent; border:none; color:{TEXT}; font-size:13px;}}
      section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
          background:{SOFT_MINT}; color:{DEEP};}}

      /* 탭(segmented) 라운드 */
      div[data-testid="stSegmentedControl"] button {{border-radius:9px;}}
    </style>
    """, unsafe_allow_html=True)
