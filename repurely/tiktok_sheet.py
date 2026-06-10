"""틱톡 대시보드 시트 로더 → 공통 스키마(platform='TikTok'). 구조는 Meta 시트와 동일."""
from repurely import google_sheets_client as G

SHEET_ID = "1wLQcxziZZKoBrEPmrV8Ckb9VU-32eYn5LAPSMJ2YiHQ"
GID = "1153373295"
PLATFORM = "TikTok"

MAP = {
    "creative_name": ["틱톡_조인소스", "조인소스", "소재명"],
    "campaign_name": ["캠페인"],
    "utm_value": ["UTM", "utm"],
    "spend": ["광고비"],
    "revenue": ["매출액", "매출"],
    "cpc": ["CPC(전체)", "CPC"],
    "cpm": ["CPM"],
    "ctr": ["CTR"],
    "conversions": ["구매건수", "구매수"],
    "roas": ["ROAS"],
}


def load() -> list[dict]:
    out = []
    for r in G.fetch_rows(SHEET_ID, GID):
        n = G.normalize(r, MAP, PLATFORM, SHEET_ID, GID)
        if n:
            out.append(n)
    return out
