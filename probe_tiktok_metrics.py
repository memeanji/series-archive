"""TikTok Marketing API — 현재 토큰으로 어떤 광고 지표가 응답되는지 그룹별 확인(읽기 전용).
조회/완료율/시청시간/좋아요/댓글/공유 등 metric 가용성을 실측한다. 아무것도 생성하지 않음.
"""
import datetime
import json

import requests

import config

TOKEN = config.TIKTOK_ACCESS_TOKEN
ADV = config.TIKTOK_ADVERTISER_ID
BASE = config.TIKTOK_API_BASE
H = {"Access-Token": TOKEN}

print(f"token=...{TOKEN[-6:] if TOKEN else '(없음)'}  advertiser={ADV}  base={BASE}")
print("=" * 70)

# 0) 토큰/권한 — advertiser 정보 조회
try:
    r = requests.get(f"{BASE}/advertiser/info/", headers=H,
                     params={"advertiser_ids": json.dumps([ADV]),
                             "fields": json.dumps(["name", "status", "role"])}, timeout=30)
    j = r.json()
    print(f"[advertiser/info] code={j.get('code')} msg={str(j.get('message'))[:80]}")
    if j.get("code") == 0:
        for a in j.get("data", {}).get("list", []):
            print("   →", a.get("name"), "| role:", a.get("role"), "| status:", a.get("status"))
except Exception as e:
    print("[advertiser/info] ERR", str(e)[:120])
print("-" * 70)

END = datetime.date.today()
START = END - datetime.timedelta(days=30)


def report(metrics, label):
    params = {"advertiser_id": ADV, "report_type": "BASIC", "data_level": "AUCTION_AD",
              "dimensions": json.dumps(["ad_id"]), "metrics": json.dumps(metrics),
              "start_date": str(START), "end_date": str(END), "page": 1, "page_size": 5}
    try:
        r = requests.get(f"{BASE}/report/integrated/get/", headers=H, params=params, timeout=40)
        j = r.json()
        code = j.get("code")
        print(f"[{label}] code={code} msg={str(j.get('message'))[:90]}")
        if code == 0:
            rows = j.get("data", {}).get("list", [])
            if rows:
                m = rows[0].get("metrics", {})
                got = {k: v for k, v in m.items()}
                print(f"   ✓ 응답 metric({len(got)}개):")
                for k, v in got.items():
                    print(f"      {k} = {v}")
            else:
                print("   (해당 기간 광고 데이터 행 없음 — metric 자체는 허용됨)")
        return code == 0
    except Exception as e:
        print(f"[{label}] ERR", str(e)[:120])
        return False


# 1) 기본 성과
report(["spend", "impressions", "clicks", "ctr", "cpc", "cpm", "conversion"], "기본 성과")
print("-" * 70)
# 2) 영상 조회 지표
report(["video_play_actions", "video_watched_2s", "video_watched_6s",
        "average_video_play", "average_video_play_per_user",
        "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100"],
       "영상 조회/완료율/시청시간")
print("-" * 70)
# 3) 인게이지먼트
report(["likes", "comments", "shares", "follows", "profile_visits", "clicks_on_music_disc"],
       "인게이지먼트(좋아요/댓글/공유)")
print("-" * 70)
# 4) 소재(영상/썸네일) 매칭용 — ad 기본정보(ad_id, video_id, 소재 URL)
try:
    r = requests.get(f"{BASE}/ad/get/", headers=H,
                     params={"advertiser_id": ADV, "page": 1, "page_size": 3,
                             "fields": json.dumps(["ad_id", "ad_name", "campaign_id",
                                                   "adgroup_id", "video_id", "image_ids",
                                                   "creative_authorized"])}, timeout=40)
    j = r.json()
    print(f"[ad/get] code={j.get('code')} msg={str(j.get('message'))[:80]}")
    if j.get("code") == 0:
        for a in j.get("data", {}).get("list", [])[:3]:
            print("   ad:", {k: a.get(k) for k in ("ad_id", "ad_name", "video_id", "image_ids")})
except Exception as e:
    print("[ad/get] ERR", str(e)[:120])
print("-" * 70)
# 5) 영상 파일 정보(썸네일/재생URL) — file/video/ad/info/
try:
    r = requests.get(f"{BASE}/file/video/ad/info/", headers=H,
                     params={"advertiser_id": ADV, "page": 1, "page_size": 3}, timeout=40)
    j = r.json()
    print(f"[file/video/ad/info] code={j.get('code')} msg={str(j.get('message'))[:80]}")
    if j.get("code") == 0:
        for v in j.get("data", {}).get("list", [])[:2]:
            print("   video keys:", list(v.keys()))
            print("      poster_url:", v.get("poster_url", "")[:60], "| video_cover_url:",
                  v.get("video_cover_url", "")[:60])
except Exception as e:
    print("[file/video/ad/info] ERR", str(e)[:120])
