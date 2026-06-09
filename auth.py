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
    """왼쪽 캐릭터/배경만 크롭한 login_left.png(없으면 원본) base64 data URI."""
    for name in ("login_left.png", "login_bg.png"):
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
    # ★ 레이어 순서: 이미지가 '먼저'(위), 그라데이션은 '뒤'(폴백) — 안 그러면 그라데이션이 캐릭터를 덮음
    img_layer = (f"url('{bg}') left bottom / auto 100% no-repeat, " if bg else "")
    st.markdown(f"""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
      html, body, [class*="css"], .stApp, input, button {{ font-family:'Pretendard',-apple-system,sans-serif; }}
      header[data-testid="stHeader"] {{ background:transparent; }}
      /* 배경: 왼쪽 캐릭터 이미지(위) + 하늘→잔디 그라데이션(뒤 폴백) */
      .stApp {{ background:{img_layer}linear-gradient(180deg,#BCE8FF 0%,#CFEFD8 52%,#A7E3C0 100%);
                background-color:#A7E3C0; }}
      .block-container {{ padding-top:0 !important; max-width:1240px; }}
      /* 오른쪽 실제 로그인 카드 1개 (불투명 흰색 → 왼쪽 이미지와 겹쳐 보이지 않음) */
      div[data-testid="stForm"] {{
        background:rgba(255,255,255,0.97); border:none !important; border-radius:34px;
        padding:40px 34px 30px; box-shadow:0 26px 70px rgba(16,24,40,.30);
        max-width:470px; min-width:330px; margin:0 0 0 auto;
      }}
      div[data-testid="stForm"] label {{ font-weight:700; color:#334155; font-size:13px; }}
      .stTextInput input {{ border-radius:20px !important; height:50px; border:1px solid #D1FAE5;
        background:#F6FFFA; font-size:14px; }}
      .stTextInput input:focus {{ border-color:#03C75A !important;
        box-shadow:0 0 0 3px rgba(3,199,90,.16) !important; }}
      div[data-testid="stForm"] button {{
        background:linear-gradient(135deg,#34D399 0%,#03C75A 100%) !important;
        color:#fff !important; border:none !important; border-radius:18px !important;
        height:50px; font-weight:800 !important; font-size:15.5px;
        box-shadow:0 12px 26px rgba(3,199,90,.40) !important; }}
      div[data-testid="stForm"] button:hover {{ filter:brightness(1.05); }}
      a, .stMarkdown a {{ color:#03C75A !important; }}
      /* 모바일: 배경 캐릭터는 흐리게 깔고 카드 중앙 */
      @media (max-width:768px) {{
        .stApp {{ background:linear-gradient(180deg,#BCE8FF,#A7E3C0); }}
        div[data-testid="stForm"] {{ margin:0 auto; }}
      }}
    </style>
    """, unsafe_allow_html=True)

    # 왼쪽 55%(캐릭터) : 오른쪽 45%(카드) — 카드는 오른쪽 세로 중앙
    _, right = st.columns([1.25, 1])
    with right:
        st.markdown("<div style='height:14vh'></div>", unsafe_allow_html=True)
        with st.form("login", border=True):
            st.markdown(
                "<div style='font-size:34px;font-weight:900;color:#03C75A;"
                "letter-spacing:-1px;line-height:1.1'>Repurely</div>"
                "<div style='color:#64748B;font-size:13px;margin:6px 0 18px'>"
                "깨끗한 일상, 리퓨얼리와 함께 💚</div>", unsafe_allow_html=True)
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
