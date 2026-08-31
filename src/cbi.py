# -*- coding: utf-8 -*-
"""
CBI(Cheonan Balance Index) — 천안 균형발전지수
  · 엔트로피 가중법으로 12개 지표를 객관 가중 (자의적 가중치 배제)
  · 5개 도메인 점수 + 종합 CBI(0~100)
  · K-means 군집 → 생활권 유형 4단계(활력/관찰/주의/쇠퇴) 자동 라벨링
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INDICATORS, DOMAINS, DECLINE_LABELS, TAB, RANDOM_SEED


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """방향 보정 min-max 정규화 → 0~1 (1이 항상 '좋음')"""
    Z = pd.DataFrame(index=df.index)
    for k, (_, _, direction, _) in INDICATORS.items():
        v = pd.to_numeric(df[k], errors="coerce")
        v = v.fillna(v.median())
        lo, hi = v.min(), v.max()
        n = (v - lo) / (hi - lo) if hi > lo else pd.Series(0.5, index=v.index)
        Z[k] = n if direction > 0 else 1 - n
    return Z


def entropy_weights(Z: pd.DataFrame) -> pd.Series:
    """
    엔트로피 가중법: 지표의 정보 엔트로피가 낮을수록(=생활권 간 변별력이 클수록) 가중치↑
      p_ij = z_ij / Σ_i z_ij ,  e_j = -k Σ p ln p ,  w_j ∝ (1 - e_j)
    → 연구자의 주관적 가중치 부여를 배제해 심사 재현성을 확보.
    """
    P = Z.clip(lower=1e-6)
    P = P / P.sum(axis=0)
    k = 1.0 / np.log(len(Z))
    e = -k * (P * np.log(P)).sum(axis=0)
    d = 1 - e
    return d / d.sum()


def compute(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    Z = normalize(df.set_index("zone"))
    w = entropy_weights(Z)

    out = df.set_index("zone").copy()
    for dom in DOMAINS:
        ks = [k for k, v in INDICATORS.items() if v[0] == dom]
        ww = w[ks] / w[ks].sum()
        out[f"D_{dom}"] = (Z[ks] * ww).sum(axis=1) * 100
    out["CBI"] = (Z * w).sum(axis=1) * 100

    # ── 군집: 실루엣으로 k 선택(3~6) 후 CBI 순으로 쇠퇴단계 라벨 부여 ──
    X = Z.values
    best = (None, -1, None)
    for k in range(3, 7):
        km = KMeans(n_clusters=k, n_init=25, random_state=RANDOM_SEED).fit(X)
        s = silhouette_score(X, km.labels_)
        if s > best[1]:
            best = (km, s, k)
    km, sil, k = best
    out["cluster"] = km.labels_
    order = out.groupby("cluster")["CBI"].mean().sort_values(ascending=False).index
    lab = {c: DECLINE_LABELS[min(i, len(DECLINE_LABELS) - 1)] for i, c in enumerate(order)}
    out["stage"] = out["cluster"].map(lab)
    out.attrs["silhouette"] = sil
    out.attrs["k"] = k

    out = out.sort_values("CBI", ascending=False)
    out.reset_index().to_csv(TAB / "02_CBI_균형발전지수.csv", index=False, encoding="utf-8-sig")
    wt = w.rename("weight").to_frame()
    wt["도메인"] = [INDICATORS[i][0] for i in wt.index]
    wt["지표명"] = [INDICATORS[i][1] for i in wt.index]
    wt.sort_values("weight", ascending=False).to_csv(
        TAB / "03_엔트로피_가중치.csv", encoding="utf-8-sig")
    print(f"\n▶ CBI 산출 완료 — 군집 k={k}, 실루엣={sil:.3f}")
    return out, w


def gap_stats(cbi: pd.DataFrame) -> dict:
    """격차 요약 통계 (기획서 핵심 수치)"""
    g = cbi.groupby("ztype")["CBI"].mean()
    new, old = g.get("신도심", np.nan), g.get("원도심", np.nan)
    return dict(
        신도심평균=new, 원도심평균=old, 격차=new - old, 배율=new / old if old else np.nan,
        최고=cbi["CBI"].max(), 최저=cbi["CBI"].min(),
        최고동=cbi["CBI"].idxmax(), 최저동=cbi["CBI"].idxmin(),
        지니=_gini(cbi["CBI"].values),
        변동계수=cbi["CBI"].std() / cbi["CBI"].mean() * 100,
    )


def _gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))
