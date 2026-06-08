"""
YouTube 유틸 — video_id 추출 + YouTube Data API(videos.list).
YOUTUBE_API_KEY 는 .env(config) 또는 .streamlit/secrets.toml 에서 읽는다.
키가 없으면 is_enabled()=False → 등록 기능 비활성.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

_ID = r"([A-Za-z0-9_-]{11})"
_PATTERNS = [rf"[?&]v={_ID}", rf"youtu\.be/{_ID}", rf"shorts/{_ID}", rf"embed/{_ID}", rf"live/{_ID}"]


def extract_video_id(url: str) -> str | None:
    url = (url or "").strip()
    for p in _PATTERNS:
        m = re.search(p, url)
        if m:
            return m.group(1)
    if re.fullmatch(_ID, url):
        return url
    return None


def embed_url(video_id: str) -> str:
    return f"https://www.youtube.com/embed/{video_id}"


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def get_api_key() -> str:
    if config.YOUTUBE_API_KEY:
        return config.YOUTUBE_API_KEY
    try:
        import streamlit as st
        return str(st.secrets.get("YOUTUBE_API_KEY", "")).strip()
    except Exception:  # noqa: BLE001
        return ""


def is_enabled() -> bool:
    return bool(get_api_key())


def fetch_transcript(video_id: str, languages=("ko", "en")) -> str:
    """YouTube 자막(스크립트) 추출. 자막 없으면 ''. API 키 불필요."""
    if not video_id:
        return ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=list(languages) + ["a.ko", "a.en"])
        return " ".join(s.text for s in fetched).strip()
    except Exception:  # noqa: BLE001  (TranscriptsDisabled/NoTranscript 등)
        return ""


def search_video_ids(query: str, max_results: int = 5, api_key: str = "") -> list[str]:
    """search.list 로 키워드(브랜드명) 관련 영상 id 목록. quota 100유닛/호출."""
    import requests
    key = api_key or get_api_key()
    if not key or not query:
        return []
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search",
                         params={"part": "snippet", "q": query, "type": "video",
                                 "maxResults": max_results, "regionCode": "KR",
                                 "relevanceLanguage": "ko", "key": key}, timeout=30)
        items = r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []
    return [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]


def fetch_videos(video_ids: list[str], api_key: str = "") -> list[dict]:
    """videos.list 배치 조회(최대 50개). 1유닛/호출."""
    key = api_key or get_api_key()
    ids = [v for v in video_ids if v][:50]
    if not key or not ids:
        return []
    import requests
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "snippet,statistics", "id": ",".join(ids), "key": key},
                         timeout=30)
        items = r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in items:
        d = _parse_item(it)
        if d:
            out.append(d)
    return out


def _parse_item(it: dict) -> dict | None:
    vid = it.get("id")
    if isinstance(vid, dict):
        vid = vid.get("videoId")
    if not vid:
        return None
    sn = it.get("snippet", {})
    stt = it.get("statistics", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {
        "id": f"yt_{vid}", "video_id": vid, "platform": "youtube",
        "video_url": watch_url(vid), "embed_url": embed_url(vid),
        "thumbnail_url": thumb, "title": sn.get("title", ""),
        "channel_title": sn.get("channelTitle", ""),
        "caption": sn.get("description", "")[:1000],
        "posted_at": (sn.get("publishedAt", "") or "")[:10], "source_url": watch_url(vid),
        "views": int(stt.get("viewCount") or 0), "likes": int(stt.get("likeCount") or 0),
        "comments": int(stt.get("commentCount") or 0), "shares": 0,
    }


def fetch_video(video_id: str, api_key: str = "") -> dict | None:
    """videos.list 로 단일 영상 메타+통계 조회. 실패시 None."""
    import requests
    key = api_key or get_api_key()
    if not key or not video_id:
        return None
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/videos",
                         params={"part": "snippet,statistics", "id": video_id, "key": key},
                         timeout=30)
        items = r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return None
    if not items:
        return None
    it = items[0]
    sn = it.get("snippet", {})
    stt = it.get("statistics", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {
        "id": f"yt_{video_id}", "video_id": video_id, "platform": "youtube",
        "video_url": watch_url(video_id), "embed_url": embed_url(video_id),
        "thumbnail_url": thumb, "title": sn.get("title", ""),
        "channel_title": sn.get("channelTitle", ""),
        "caption": sn.get("description", "")[:1000],
        "posted_at": (sn.get("publishedAt", "") or "")[:10],
        "source_url": watch_url(video_id),
        "views": int(stt.get("viewCount") or 0), "likes": int(stt.get("likeCount") or 0),
        "comments": int(stt.get("commentCount") or 0), "shares": 0,
    }
