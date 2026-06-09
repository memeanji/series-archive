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
    """assets/login_bg.png 를 base64 data URI 로(없으면 '')."""
    try:
        fp = _ASSETS / "login_bg.png"
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
    """로그인 화면 — 커스텀 배경 이미지 + 오른쪽 카드에 실제 로그인 입력. (로직은 그대로)"""
    bg = _login_bg_uri()
    bg_layer = (f"background-image:url('{bg}');background-size:cover;background-position:center;"
                if bg else "")
    st.markdown(f"""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
      html, body, [class*="css"], .stApp, input, button {{ font-family:'Pretendard',-apple-system,sans-serif; }}
      header[data-testid="stHeader"] {{ background:transparent; }}
      /* 배경: 이미지(cover/center) + 실패 시 초록 폴백색 */
      .stApp {{ background-color:#A7E3C0; {bg_layer} }}
      .block-container {{ padding-top:0 !important; max-width:1180px; }}
      /* 오른쪽 로그인 카드(이미지의 카드 영역에 얹음) */
      div[data-testid="stForm"] {{
        background:rgba(255,255,255,0.93); border:none !important; border-radius:34px;
        padding:30px 28px 26px; box-shadow:0 24px 60px rgba(16,24,40,.28);
        backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
      }}
      div[data-testid="stForm"] label {{ font-weight:700; color:#334155; font-size:13px; }}
      .stTextInput input {{ border-radius:13px !important; height:46px; border:1px solid #D1FAE5;
        background:#F8FFFB; }}
      .stTextInput input:focus {{ border-color:#03C75A !important; box-shadow:0 0 0 2px rgba(3,199,90,.18) !important; }}
      /* 버튼: 초록 그라데이션 + 그림자 (파란 포인트 → 초록) */
      div[data-testid="stForm"] button {{
        background:linear-gradient(135deg,#34D399 0%,#03C75A 100%) !important;
        color:#fff !important; border:none !important; border-radius:14px !important;
        height:48px; font-weight:800 !important; font-size:15px;
        box-shadow:0 10px 22px rgba(3,199,90,.38) !important; }}
      div[data-testid="stForm"] button:hover {{ filter:brightness(1.04); }}
      a, .stMarkdown a {{ color:#03C75A !important; }}
    </style>
    """, unsafe_allow_html=True)

    company = st.secrets.get("auth", {}).get("company", "Series Builder")
    # 왼쪽 캐릭터 여백 : 오른쪽 카드 = 이미지 카드 위치에 맞춤
    _, right = st.columns([1.45, 1])
    with right:
        st.markdown("<div style='height:13vh'></div>", unsafe_allow_html=True)
        with st.form("login", border=True):
            st.markdown("<div style='font-size:30px;font-weight:900;color:#03C75A;"
                        "letter-spacing:-.5px'>📚 Series Archive</div>"
                        f"<div style='color:#64748B;font-size:13px;margin:4px 0 16px'>"
                        f"Ad Reference Library · {company} 💚</div>", unsafe_allow_html=True)
            u = st.text_input("아이디", placeholder="아이디")
            p = st.text_input("비밀번호", type="password", placeholder="비밀번호")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_password(u.strip(), p):
                    st.session_state.authenticated = True
                    st.session_state.username = u.strip()
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
            st.markdown("<div style='text-align:center;color:#94A3B8;font-size:12px;margin-top:10px'>"
                        "내부 공유용 · 계정 문의는 관리자에게</div>", unsafe_allow_html=True)


def logout() -> None:
    for k in ("authenticated", "username"):
        st.session_state.pop(k, None)
    st.rerun()


def require_login() -> bool:
    return bool(st.session_state.get("authenticated"))
