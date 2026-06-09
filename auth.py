"""
내부 공유용 간단 로그인.
계정은 .streamlit/secrets.toml [auth.users] 에서 읽고, users 테이블(해시)로 검증한다.
로그인 상태는 st.session_state.authenticated 로 유지.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache
from pathlib import Path

import streamlit as st

import database

_ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=1)
def _login_bg_uri() -> str:
    """전체 장면(정원/하늘/잔디+캐릭터) 이미지를 base64 data URI 로 — 화면 전체 배경용."""
    for name in ("login_bg.png", "login_left.png"):
        try:
            fp = _ASSETS / name
            if fp.exists():
                return "data:image/png;base64," + base64.b64encode(fp.read_bytes()).decode()
        except Exception:  # noqa: BLE001
            pass
    return ""


def _secret(key: str) -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(key, "")


def _flat_login() -> tuple[str, str, str]:
    """LOGIN_USERNAME / LOGIN_PASSWORD / LOGIN_PASSWORD_HASH (secrets→env)."""
    return _secret("LOGIN_USERNAME"), _secret("LOGIN_PASSWORD"), _secret("LOGIN_PASSWORD_HASH")


def get_secret_users() -> dict:
    """{username: plaintext_password}. [auth.users] + 평면 LOGIN_USERNAME/PASSWORD 병합."""
    users: dict = {}
    try:
        users.update({k: str(v) for k, v in dict(st.secrets["auth"]["users"]).items()})
    except Exception:  # noqa: BLE001
        pass
    u, pw, _h = _flat_login()
    if u and pw:
        users[u] = pw
    return users


def check_password(username: str, password: str) -> bool:
    if database.verify_user(username, password):   # DB(users, 해시) — init_db가 시드
        return True
    if get_secret_users().get(username) == password:   # 평문 폴백
        return True
    lu, _pw, lh = _flat_login()                    # LOGIN_PASSWORD_HASH 폴백
    return bool(lh) and username == lu and database.hash_pw(password) == lh


def login() -> None:
    """로그인 화면 — 왼쪽은 캐릭터 비주얼(이미지의 그려진 로그인 박스는 크롭 제거),
    오른쪽은 실제 입력 가능한 카드 1개. (로직은 그대로)"""
    bg = _login_bg_uri()
    # 전체 장면을 화면 전체 배경(cover)으로 → 좌우가 한 장처럼 자연스럽게 이어짐
    bg_css = (f"url('{bg}') center center / cover no-repeat" if bg else
              "linear-gradient(180deg,#BCE8FF 0%,#CFEFD8 52%,#A7E3C0 100%)")
    st.markdown(f"""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
      html, body, [class*="css"], .stApp, input, button {{ font-family:'Pretendard',-apple-system,sans-serif; }}
      header[data-testid="stHeader"] {{ background:transparent; }}
      /* 한 장의 랜딩: 전체 장면을 화면 전체 cover 배경으로(폴백색 포함) */
      .stApp {{ background:#BFE9D2 {bg_css}; background-attachment:fixed; }}
      .block-container {{ padding-top:0 !important; padding-right:2.5rem !important; max-width:1280px; }}
      /* 오른쪽 카드: 배경 위에 자연스럽게 올라간 느낌(살짝 반투명+블러) */
      div[data-testid="stForm"] {{
        background:rgba(255,255,255,0.90); border:1px solid rgba(255,255,255,.6) !important;
        border-radius:34px; padding:38px 30px 28px;
        box-shadow:0 24px 60px rgba(16,24,40,.22);
        width:100%; max-width:430px; margin:0 auto; box-sizing:border-box;
        backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
      }}
      div[data-testid="stForm"] label {{ font-weight:700; color:#334155; font-size:13px; }}
      .stTextInput input {{ border-radius:20px !important; height:50px; border:1px solid #D1FAE5;
        background:rgba(246,255,250,0.95); font-size:14px; }}
      .stTextInput input:focus {{ border-color:#03C75A !important;
        box-shadow:0 0 0 3px rgba(3,199,90,.16) !important; }}
      div[data-testid="stForm"] button {{
        background:linear-gradient(135deg,#34D399 0%,#03C75A 100%) !important;
        color:#fff !important; border:none !important; border-radius:18px !important;
        height:50px; font-weight:800 !important; font-size:15.5px;
        box-shadow:0 12px 26px rgba(3,199,90,.40) !important; }}
      div[data-testid="stForm"] button:hover {{ filter:brightness(1.05); }}
      a, .stMarkdown a {{ color:#03C75A !important; }}
      @media (max-width:768px) {{
        div[data-testid="stForm"] {{ margin:0 auto; background:rgba(255,255,255,0.95); }}
      }}
    </style>
    """, unsafe_allow_html=True)

    # 카드는 오른쪽·세로 중앙(배경 장면의 우측 영역에 자연스럽게 안착)
    _, right = st.columns([1.15, 0.95])
    with right:
        st.markdown("<div style='height:17vh'></div>", unsafe_allow_html=True)
        with st.form("login", border=True):
            st.markdown(
                "<div style='font-size:34px;font-weight:900;color:#03C75A;"
                "letter-spacing:-1px;line-height:1.1'>Repurely</div>"
                "<div style='color:#64748B;font-size:13px;margin:6px 0 18px'>"
                "깨끗한 일상, 리퓨어리와 함께 💚</div>", unsafe_allow_html=True)
            u = st.text_input("아이디", placeholder="아이디")
            p = st.text_input("비밀번호", type="password", placeholder="비밀번호")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_password(u.strip(), p):
                    st.session_state.authenticated = True
                    st.session_state.username = u.strip()
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
            st.markdown("<div style='text-align:center;color:#94A3B8;font-size:12px;margin-top:12px'>"
                        "내부 공유용 · 계정 문의는 관리자에게</div>", unsafe_allow_html=True)


def logout() -> None:
    for k in ("authenticated", "username"):
        st.session_state.pop(k, None)
    st.rerun()


def require_login() -> bool:
    return bool(st.session_state.get("authenticated"))
