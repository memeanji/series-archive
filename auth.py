"""
내부 공유용 간단 로그인.
계정은 .streamlit/secrets.toml [auth.users] 에서 읽고, users 테이블(해시)로 검증한다.
로그인 상태는 st.session_state.authenticated 로 유지.
"""
from __future__ import annotations

import os

import streamlit as st

import database


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
    """로그인 화면. 성공 시 session_state 설정 후 rerun."""
    company = st.secrets.get("auth", {}).get("company", "Series Builder")
    st.markdown(f"""
    <div style='max-width:380px;margin:8vh auto 1.5rem;text-align:center'>
      <div style='font-size:30px;font-weight:800;color:#03C75A'>📚 Series Archive</div>
      <div style='color:#64748B;margin-top:6px'>Ad Reference Library · {company}</div>
    </div>
    """, unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        with st.form("login", border=True):
            u = st.text_input("아이디", placeholder="username")
            p = st.text_input("비밀번호", type="password", placeholder="password")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                if check_password(u.strip(), p):
                    st.session_state.authenticated = True
                    st.session_state.username = u.strip()
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
        st.caption("내부 공유용 · 계정 문의는 관리자에게")


def logout() -> None:
    for k in ("authenticated", "username"):
        st.session_state.pop(k, None)
    st.rerun()


def require_login() -> bool:
    return bool(st.session_state.get("authenticated"))
