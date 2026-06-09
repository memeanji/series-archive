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
    """전체 장면 이미지를 base64 data URI 로 — 가벼운 jpg 우선(메모리·로딩 절감)."""
    for name, mime in (("login_bg.jpg", "image/jpeg"), ("login_bg.png", "image/png"),
                       ("login_left.png", "image/png")):
        try:
            fp = _ASSETS / name
            if fp.exists():
                return f"data:{mime};base64," + base64.b64encode(fp.read_bytes()).decode()
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
    """로그인 화면 — 이미지 없이 깔끔한 배경 + 가운데 정렬 카드 1개. (로직은 그대로)"""
    st.markdown("""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
      html, body, [class*="css"], .stApp, input, button { font-family:'Pretendard',-apple-system,sans-serif; }
      header[data-testid="stHeader"] { background:transparent; }
      /* 깔끔한 연그린 그라데이션 배경(이미지 없음) */
      .stApp { background:linear-gradient(180deg,#F0FBF4 0%,#E3F6EC 55%,#D5F0E0 100%); }
      .block-container { padding-top:0 !important; max-width:1100px; }
      /* 가운데 로그인 카드 1개 */
      div[data-testid="stForm"] {
        background:#FFFFFF; border:1px solid #E7F3EC !important;
        border-radius:34px; padding:36px 40px;
        box-shadow:0 20px 50px rgba(16,24,40,.12);
        width:100%; max-width:440px; margin:0 auto; box-sizing:border-box;
      }
      div[data-testid="stForm"] label { font-weight:700; color:#334155; font-size:13px;
        margin-bottom:6px; }
      div[data-testid="stForm"] div[data-testid="stTextInput"] { margin-bottom:15px; }
      /* baseweb 기본 레이아웃(세로중앙·눈아이콘 내부배치)을 유지하고 '외형만' 입힘
         → 아이디=비밀번호 동일 크기, 텍스트 안 잘림, 눈 아이콘이 박스 크기 안 바꿈 */
      div[data-testid="stForm"] [data-baseweb="input"] {
        border-radius:22px !important; border:1px solid #D1FAE5 !important;
        background:#F6FFFA !important; box-sizing:border-box; }
      div[data-testid="stForm"] [data-baseweb="input"]:focus-within {
        border-color:#03C75A !important; box-shadow:0 0 0 3px rgba(3,199,90,.16) !important; }
      /* ★ 컨테이너 내부 모든 요소(눈 아이콘 enhancer/button 포함)의 배경·그림자·테두리 제거
         → 아이콘 뒤 연한 초록 박스 완전 제거. 컨테이너 자체 배경/테두리/포커스글로우는 위에서 유지 */
      div[data-testid="stForm"] [data-baseweb="input"] *,
      div[data-testid="stForm"] [data-baseweb="input"] *:hover,
      div[data-testid="stForm"] [data-baseweb="input"] *:focus,
      div[data-testid="stForm"] [data-baseweb="input"] *:active,
      div[data-testid="stForm"] [data-baseweb="input"] *:focus-visible {
        background:transparent !important; background-color:transparent !important;
        box-shadow:none !important; outline:none !important; border:none !important; }
      div[data-testid="stForm"] [data-baseweb="input"] input { font-size:14.5px !important; }
      div[data-testid="stForm"] [data-baseweb="input"] button {
        border-radius:0 !important; color:#64748B !important; }
      div[data-testid="stForm"] button {
        background:linear-gradient(135deg,#34D399 0%,#03C75A 100%) !important;
        color:#fff !important; border:none !important; border-radius:26px !important;
        height:54px; font-weight:800 !important; font-size:15.5px; margin-top:6px;
        box-shadow:0 12px 26px rgba(3,199,90,.40) !important; }
      div[data-testid="stForm"] button:hover { filter:brightness(1.05); }
      a, .stMarkdown a { color:#03C75A !important; }
    </style>
    """, unsafe_allow_html=True)

    # 화면 가운데 정렬
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown("<div style='height:23vh'></div>", unsafe_allow_html=True)
        with st.form("login", border=True):
            st.markdown(
                "<div style='text-align:center;font-size:38px;font-weight:900;color:#03C75A;"
                "letter-spacing:-1px;line-height:1.1;margin-bottom:24px'>Repurely</div>",
                unsafe_allow_html=True)
            u = st.text_input("아이디", placeholder="아이디")
            p = st.text_input("비밀번호", type="password", placeholder="비밀번호")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_password(u.strip(), p):
                    st.session_state.authenticated = True
                    st.session_state.username = u.strip()
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
            st.markdown("<div style='text-align:center;color:#94A3B8;font-size:12px;margin-top:14px'>"
                        "내부 공유용 · 계정 문의는 관리자에게</div>", unsafe_allow_html=True)


def logout() -> None:
    for k in ("authenticated", "username"):
        st.session_state.pop(k, None)
    st.rerun()


def require_login() -> bool:
    return bool(st.session_state.get("authenticated"))
