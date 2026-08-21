# -*- coding: utf-8 -*-
"""Chromium 실행 환경 준비 — 배포(Streamlit Community Cloud) 에서 Playwright 가
   브라우저를 못 찾아 '미수집 광고 바로 수집하기' 가 실패하던 문제 대응.

⚠️ **정기 크롤(daily_group_update / google_group_update) 은 이 모듈을 쓰지 않는다.**
   로컬(Windows)에서 `launch_opts()` 는 항상 `{}` 를 돌려주므로, 이 모듈을 거치더라도
   `p.chromium.launch(headless=True)` 와 완전히 동일하게 동작한다.

배포 환경에서 브라우저를 얻는 순서
  ① `packages.txt` 로 apt 설치된 시스템 크로미움(`/usr/bin/chromium`) — 다운로드 0, 즉시 실행
  ② 없으면 `playwright install chromium` 을 런타임에 1회 실행(컨테이너 수명 동안 캐시)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# apt(packages.txt) 로 깔리는 크로미움 후보. 앞에서부터 처음 존재하는 것을 쓴다.
_CANDIDATES = (
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium",
)

# 컨테이너(비특권 사용자)에서 크로미움 샌드박스가 뜨지 않는 문제 회피용 인자
_CONTAINER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]


def is_posix() -> bool:
    return os.name != "nt"


def import_error() -> str:
    """playwright 파이썬 패키지 import 가능 여부. 정상이면 '' , 아니면 사유 문자열."""
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
    return ""


def playwright_version() -> str:
    try:
        from importlib.metadata import version
        return version("playwright")
    except Exception:  # noqa: BLE001
        return "?"


def system_chromium() -> str:
    """apt 로 설치된 크로미움 실행 파일 경로(없으면 '')."""
    env = (os.getenv("PLAYWRIGHT_CHROMIUM_PATH") or "").strip()
    if env and Path(env).exists():
        return env
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    return ""


def bundled_browser_path() -> str:
    """`playwright install` 로 받은 번들 크로미움 디렉터리(없으면 '')."""
    base = Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    if not base.exists():
        return ""
    hits = sorted(base.glob("chromium*"))
    return str(hits[0]) if hits else ""


def install_bundled(timeout: int = 600) -> tuple[bool, str]:
    """`playwright install chromium` 을 런타임에 실행. (성공여부, 메시지)"""
    try:
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"playwright install 시간 초과({timeout}s)"
    except Exception as e:  # noqa: BLE001
        return False, f"playwright install 실행 실패: {type(e).__name__}: {e}"
    if r.returncode != 0:
        tail = ((r.stderr or r.stdout) or "").strip().splitlines()[-3:]
        return False, "playwright install 실패: " + " / ".join(tail)[:300]
    return True, "번들 크로미움 설치 완료"


# 시스템 크로미움이 너무 낡아 Playwright 가 못 붙는 경우, 번들 크로미움으로 한 번 갈아탄다.
_FORCE_BUNDLED = False


def launch_opts() -> dict:
    """`p.chromium.launch(**opts)` 에 얹을 인자.
       로컬(Windows)에서는 **빈 dict** — 기존 동작과 100% 동일하다."""
    if not is_posix():
        return {}
    opts: dict = {"args": list(_CONTAINER_ARGS)}
    exe = "" if _FORCE_BUNDLED else system_chromium()
    if exe:
        opts["executable_path"] = exe
    return opts


def ensure_browser() -> tuple[bool, str]:
    """수집 직전에 부르는 준비 함수. (사용가능여부, 사람이 읽는 설명)

    로컬 Windows  → 항상 (True, '로컬 …') : 아무것도 건드리지 않는다.
    배포(리눅스)  → 시스템 크로미움 우선, 없으면 번들 설치까지 시도.
    """
    err = import_error()
    if err:
        return False, f"playwright 패키지 없음 — {err}"
    if not is_posix():
        return True, f"로컬 Windows · playwright {playwright_version()} (번들 크로미움)"
    exe = system_chromium()
    if exe:
        return True, f"시스템 크로미움 {exe} · playwright {playwright_version()}"
    if bundled_browser_path():
        return True, f"번들 크로미움 {bundled_browser_path()} · playwright {playwright_version()}"
    ok, msg = install_bundled()
    if ok:
        return True, f"{msg} · playwright {playwright_version()}"
    return False, msg


def _try_launch() -> tuple[bool, str]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True, **launch_opts())
        try:
            pg = br.new_page()
            pg.goto("about:blank", timeout=15000)
            ver = br.version
        finally:
            br.close()
    return True, ver


def smoke_test() -> tuple[bool, str]:
    """브라우저가 실제로 뜨는지 about:blank 로 확인(Meta 접속 전에 원인 분리용).

    apt 크로미움이 너무 낡아 Playwright 가 못 붙는 경우가 있어, 실패하면
    **번들 크로미움으로 한 번 갈아타서** 재시도한다."""
    global _FORCE_BUNDLED
    exe = "" if _FORCE_BUNDLED else system_chromium()
    try:
        ok, ver = _try_launch()
        return ok, f"크로미움 기동 OK ({ver}){' · ' + exe if exe else ''}"
    except Exception as e:  # noqa: BLE001
        first = f"{type(e).__name__}: {str(e)[:200]}"
    if not (is_posix() and exe):          # 이미 번들이면 더 갈아탈 곳이 없다
        return False, first
    ok, msg = install_bundled()
    if not ok:
        return False, f"시스템 크로미움({exe}) 실패 → {first} · 번들 설치도 실패: {msg}"
    _FORCE_BUNDLED = True
    try:
        ok, ver = _try_launch()
        return ok, f"시스템 크로미움 실패 → 번들 크로미움으로 기동 OK ({ver})"
    except Exception as e:  # noqa: BLE001
        return False, (f"시스템 크로미움({exe}) 실패: {first} / "
                       f"번들 크로미움도 실패: {type(e).__name__}: {str(e)[:200]}")
