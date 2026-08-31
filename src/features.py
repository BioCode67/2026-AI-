# -*- coding: utf-8 -*-
"""지표 산출 — 12개 지표 조립 + 중력모형 기반 생활SOC 접근성"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INDICATORS, ZONE_NAMES, TAB
import ingest as I


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def soc_accessibility(points: pd.DataFrame, decay_km: float = 1.5) -> pd.Series:
    """
    중력모형(거리감쇠) 기반 생활SOC 접근성.
      A_z = Σ_t w_t · ln(1 + Σ_i exp(-d(z,i)/d0))
    · 단순 '우리 동 시설 개수'와 달리 **행정경계를 넘는 이용(spillover)** 을 반영한다.
      (예: 중앙동 주민이 걸어서 가는 문성동 병원도 접근성에 잡힌다)
    · d0=1.5km ≈ 도보 15~20분. '15분 도시' 개념과 정합.
    """
    out = {}
    for z in ZONE_NAMES:
        la, lo = I.CENTROID[z]
        tot = 0.0
        for soc, w in I.SOC_TYPES.items():
            sub = points[points.soc == soc]
            if not len(sub):
                continue
            d = haversine(la, lo, sub.lat.values, sub.lon.values)
            tot += w * np.log1p(np.exp(-d / decay_km).sum())
        out[z] = tot
    s = pd.Series(out)
    return (s - s.min()) / (s.max() - s.min() + 1e-9) * 100      # 0~100 정규화


def build_zone_table() -> tuple[pd.DataFrame, dict]:
    print("\n▶ 데이터 적재")
    pop, pop_panel = I.load_population()
    biz, biz_panel = I.load_business()
    fac, points    = I.load_facilities()
    hou            = I.load_housing(pop)
    tra            = I.load_transit()

    df = pop.merge(biz.drop(columns=["gu", "ztype"]), on="zone") \
            .merge(hou.drop(columns=["gu", "ztype"]), on="zone") \
            .merge(tra.drop(columns=["gu", "ztype"]), on="zone")

    soc_cols = [c for c in fac.columns if c in I.SOC_TYPES]
    df = df.merge(fac[["zone"] + soc_cols], on="zone")
    df["soc_total"]      = df[soc_cols].sum(axis=1)
    df["soc_per_capita"] = df["soc_total"] / df["pop"] * 1000
    df["soc_access"]     = df["zone"].map(soc_accessibility(points))
    df["biz_density"]    = df["active_biz"] / df["pop"] * 1000
    df["area_km2"]       = df["zone"].map(I.AREA_KM2)
    df["pop_density"]    = df["pop"] / df["area_km2"]

    for k in INDICATORS:                       # 누락 지표는 NaN 컬럼으로 두고 CBI에서 자동 제외
        if k not in df.columns:
            df[k] = np.nan

    panels = dict(pop=pop_panel, biz=biz_panel, points=points, soc_cols=soc_cols)
    df.to_csv(TAB / "01_생활권_지표원표.csv", index=False, encoding="utf-8-sig")
    return df, panels


def provenance_table() -> pd.DataFrame:
    rows = [dict(지표군=k, 상태=v["status"], 출처=v["source"], 비고=v["detail"], 행수=v["rows"])
            for k, v in I.PROVENANCE.items()]
    t = pd.DataFrame(rows)
    t.to_csv(TAB / "00_데이터_출처.csv", index=False, encoding="utf-8-sig")
    return t


def is_all_real() -> bool:
    return all(v["status"] in ("REAL", "PARTIAL") for v in I.PROVENANCE.values())


def has_synthetic() -> bool:
    """예시(illustrative) 값이 하나라도 섞였는가 — 제출 전 경고 판단용."""
    return any(v["status"] == "ILLUSTRATIVE" for v in I.PROVENANCE.values())
