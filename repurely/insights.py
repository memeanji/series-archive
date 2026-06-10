"""repurely 내부 소재 분석 — 3개 시트 통합 + 위닝/OFF/피로도 분류 + 상태 요약.

⚠️ 시트는 캠페인/소재별 '현재 누적 합계'(날짜 컬럼 없음)라, '최근 3일 vs 7일' 같은
   일별 추세 기준은 일별 스냅샷이 쌓여야 가능 → 현재는 누적 지표 기반으로 분류.
"""
from __future__ import annotations


def load_all() -> list[dict]:
    """GFA + Meta + TikTok 통합(공통 스키마). 소스 하나 실패해도 나머지는 반환."""
    import repurely.gfa_sheet as gfa
    import repurely.meta_sheet as meta
    import repurely.tiktok_sheet as tiktok
    rows: list[dict] = []
    for mod in (gfa, meta, tiktok):
        try:
            rows += mod.load()
        except Exception:  # noqa: BLE001
            pass
    return rows


def averages(rows: list[dict]) -> dict:
    def avg(key):
        xs = [r[key] for r in rows if r.get(key, 0) > 0]
        return sum(xs) / len(xs) if xs else 0.0
    return {"roas": avg("roas"), "ctr": avg("ctr"), "cpc": avg("cpc"), "cpm": avg("cpm")}


def winning_score(r: dict, av: dict) -> int:
    s = 0
    if r.get("conversions", 0) >= 1:
        s += 2
    if av["roas"] and r.get("roas", 0) >= av["roas"]:
        s += 3
    if av["ctr"] and r.get("ctr", 0) >= av["ctr"]:
        s += 1
    if av["cpc"] and 0 < r.get("cpc", 0) <= av["cpc"]:
        s += 1
    if r.get("spend", 0) >= 50000 and (r.get("conversions", 0) > 0 or r.get("revenue", 0) > 0):
        s += 1
    # +1: 최근 3일 ROAS ≥ 최근 7일 평균 → 일별 스냅샷 필요(현재 데이터 없음, 생략)
    return s


def winning_label(score: int) -> str:
    return ("위닝 소재" if score >= 7 else "위닝 후보" if score >= 5
            else "모니터링" if score >= 3 else "일반 소재")


def off_reasons(r: dict) -> list[str]:
    out = []
    if r.get("spend", 0) >= 50000 and r.get("conversions", 0) == 0:
        out.append("광고비 5만원 이상 사용했지만 구매 0건")
    if r.get("spend", 0) > 0 and r.get("roas", 0) == 0:
        out.append("ROAS 0")
    # 일별 기준(최근 3일 구매 0 / CTR·CPC·CPM·ROAS 추세)은 스냅샷 누적 후 적용
    return out


def is_new_test(r: dict) -> bool:
    return r.get("spend", 0) < 50000 and r.get("conversions", 0) == 0 and r.get("roas", 0) == 0


def is_fatigue(r: dict, av: dict) -> bool:
    # 일별 데이터 없음 → 프록시: 광고비 충분 + 구매 있는데 ROAS가 평균의 70% 미만
    return (r.get("spend", 0) >= 50000 and r.get("conversions", 0) > 0
            and av["roas"] and r.get("roas", 0) < av["roas"] * 0.7)


def status_summary(r: dict, av: dict) -> str:
    if r.get("is_off"):
        if r.get("conversions", 0) == 0:
            return f"광고비 {int(r.get('spend',0)):,}원 사용했지만 구매가 없어 OFF 후보입니다."
        return "성과 지표가 낮아 OFF 후보로 분류됩니다."
    if r.get("winning_label") in ("위닝 소재", "위닝 후보"):
        return f"구매수와 ROAS가 양호해 {r['winning_label']}로 분류됩니다."
    if r.get("is_fatigue"):
        return "ROAS가 repurely 평균 대비 낮아 피로도가 의심됩니다."
    if r.get("is_new_test"):
        return "아직 데이터가 적은 신규 테스트 소재입니다."
    return "안정적으로 운영 중인 소재입니다."


def enrich(rows: list[dict]) -> tuple[list[dict], dict]:
    """각 행에 분석 필드 부여 + repurely 평균 반환."""
    av = averages(rows)
    for r in rows:
        sc = winning_score(r, av)
        r["winning_score"] = sc
        r["winning_label"] = winning_label(sc)
        r["off_reasons"] = off_reasons(r)
        r["is_off"] = bool(r["off_reasons"])
        r["is_new_test"] = is_new_test(r)
        r["is_fatigue"] = is_fatigue(r, av)
        r["status_text"] = status_summary(r, av)
    return rows, av


def summary(rows: list[dict]) -> dict:
    tot_spend = sum(r.get("spend", 0) for r in rows)
    tot_rev = sum(r.get("revenue", 0) for r in rows)
    tot_conv = sum(r.get("conversions", 0) for r in rows)
    av = averages(rows)
    return {
        "spend": tot_spend, "revenue": tot_rev, "conversions": tot_conv,
        "roas": (tot_rev / tot_spend * 100) if tot_spend else 0.0,
        "cpc": av["cpc"], "cpm": av["cpm"], "ctr": av["ctr"],
        "n": len(rows),
        "off": sum(1 for r in rows if r.get("is_off")),
        "winning": sum(1 for r in rows if r.get("winning_label") in ("위닝 소재", "위닝 후보")),
    }


def by_platform(rows: list[dict]) -> list[dict]:
    """매체별 성과 비교."""
    agg: dict = {}
    for r in rows:
        p = r.get("platform", "?")
        a = agg.setdefault(p, {"platform": p, "spend": 0.0, "revenue": 0.0,
                               "conversions": 0.0, "n": 0})
        a["spend"] += r.get("spend", 0)
        a["revenue"] += r.get("revenue", 0)
        a["conversions"] += r.get("conversions", 0)
        a["n"] += 1
    for a in agg.values():
        a["roas"] = (a["revenue"] / a["spend"] * 100) if a["spend"] else 0.0
    return sorted(agg.values(), key=lambda x: -x["spend"])
