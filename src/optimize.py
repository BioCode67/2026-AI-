# -*- coding: utf-8 -*-
"""
생활SOC 투자 우선순위 최적화 (추천 엔진)
  MCLP(Maximal Covering Location Problem)의 탐욕 근사(greedy).
  · 탐욕해는 (1-1/e)≈63% 이상의 최적성 보장 (submodular 최대화)
  · 목적: '한 곳을 새로 지었을 때 늘어나는 취약수요 커버리지'가 최대인 지점 선택
  · 후보지: 빈집률·노후도 높고 커버리지 낮은 격자 = 도시재생 유휴부지 대리변수
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import TAB, RANDOM_SEED
import ingest as I
from features import haversine

GRID_DEG = 0.006        # ≈ 600m
SERVICE_R = 1.0         # 서비스 반경 1.0 km (도보 15분)


def demand_grid(zone: pd.DataFrame) -> pd.DataFrame:
    """천안시 범위에 격자를 깔고, 생활권별 인구·취약도로 수요를 배분."""
    lats = [c[0] for c in I.CENTROID.values()]; lons = [c[1] for c in I.CENTROID.values()]
    la = np.arange(min(lats) - .03, max(lats) + .03, GRID_DEG)
    lo = np.arange(min(lons) - .03, max(lons) + .03, GRID_DEG)
    G = pd.DataFrame([(a, b) for a in la for b in lo], columns=["lat", "lon"])

    zc = pd.DataFrame([(z, *c) for z, c in I.CENTROID.items()],
                      columns=["zone", "zlat", "zlon"])
    d = np.stack([haversine(G.lat.values, G.lon.values, r.zlat, r.zlon)
                  for r in zc.itertuples()])
    idx = d.argmin(0)
    G["zone"] = zc.zone.values[idx]
    G["d_center"] = d.min(0)
    # 생활권 면적에서 유도한 등가반경 안쪽 격자만 유효 거주지로 인정
    # (도심 소면적 생활권에 농촌 공지가 잘못 배분되는 것을 방지)
    eqr = {z: (I.AREA_KM2[z] / np.pi) ** 0.5 * 1.25 for z in I.CENTROID}
    G = G[G.d_center <= G.zone.map(eqr)]

    zi = zone.set_index("zone")
    # 격자 수요 = (생활권 인구 / 격자수) × 취약가중(고령·저CBI)
    cnt = G.groupby("zone").size()
    G["pop_cell"] = G.zone.map(zi["pop"] / cnt)
    vul = 1 + 0.9 * (zi["aging_ratio"] / zi["aging_ratio"].max()) \
            + 0.9 * (1 - zi["CBI"] / 100)
    G["vul"] = G.zone.map(vul)
    G["demand"] = G["pop_cell"] * G["vul"]
    G["demand"] *= np.exp(-G["d_center"] / np.maximum(G.zone.map(
        lambda z: (I.AREA_KM2[z] / np.pi) ** 0.5), 0.8))   # 중심에서 멀수록 실거주 희박
    return G.reset_index(drop=True)


def coverage(G: pd.DataFrame, pts: pd.DataFrame, soc: str, r=SERVICE_R) -> np.ndarray:
    """격자별 해당 SOC 커버 여부(0/1)."""
    s = pts[pts.soc == soc]
    if not len(s):
        return np.zeros(len(G), bool)
    cov = np.zeros(len(G), bool)
    B = 4000
    for i in range(0, len(s), B):
        c = s.iloc[i:i + B]
        d = np.stack([haversine(G.lat.values, G.lon.values, la, lo)
                      for la, lo in zip(c.lat.values, c.lon.values)])
        cov |= (d.min(0) <= r)
    return cov


class InsufficientData(RuntimeError):
    """입지 최적화에 필요한 최소 데이터가 없을 때 — 이 단계만 건너뛴다."""


SITE_BASIS: list[str] = []     # 후보지 점수에 실제로 쓰인 지표(자료 상황에 따라 달라짐)


def greedy_sites(zone: pd.DataFrame, pts: pd.DataFrame, n_sites=12,
                 max_per_zone=2) -> pd.DataFrame:
    """max_per_zone: 예산 형평성 제약 — 한 생활권 집중 배정을 막는다."""
    if pts is None or not len(pts) or "lat" not in pts.columns:
        raise InsufficientData(
            "기존 생활SOC 위치 자료가 없어 커버리지를 계산할 수 없습니다. "
            "상가정보 또는 생활SOC 표준데이터(facility_*.csv)를 넣으면 실행됩니다.")
    G = demand_grid(zone)
    zi = zone.set_index("zone")
    total_demand = G["demand"].sum()

    # SOC 유형별 미충족 수요
    uncovered = {}
    for soc in I.SOC_TYPES:
        uncovered[soc] = ~coverage(G, pts, soc)

    # 후보지: 빈집률·노후도 상위 생활권의 격자 (도시재생 유휴부지 대리변수)
    parts, used = [], []
    for c, lab in (("vacancy_rate", "빈집률"), ("old_building", "노후도")):
        if c in zi.columns and pd.to_numeric(zi[c], errors="coerce").notna().any():
            parts.append(pd.to_numeric(zi[c], errors="coerce").rank(pct=True))
            used.append(lab)
    if not parts:      # 주거 자료 미확보 시 — 확보된 지표로 재생 필요도를 근사
        parts = [(1 - zi["CBI"].rank(pct=True)), zi["aging_ratio"].rank(pct=True)]
        used = ["CBI 열위", "고령비율"]
    renew = sum(parts) / len(parts)
    SITE_BASIS[:] = used            # 기획서·대시보드가 같은 문구를 쓰도록
    print(f"    · 후보지 점수 기준: {', '.join(used)}")
    G["renew_score"] = G.zone.map(renew)
    cand = G[G.renew_score > 0.35].index.to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    if len(cand) > 1200:
        cand = rng.choice(cand, 1200, replace=False)

    # 후보지×격자 거리행렬을 1회만 계산 (탐욕 반복은 행렬 연산으로 처리)
    D = np.stack([haversine(G.lat.values[c], G.lon.values[c],
                            G.lat.values, G.lon.values) for c in cand])   # (C, N)
    WITHIN = D <= SERVICE_R
    dem = G["demand"].values
    popc = G["pop_cell"].values

    chosen, remaining = [], {s_: u.copy() for s_, u in uncovered.items()}
    used = np.zeros(len(cand), bool)
    cand_zone = G.zone.values[cand]
    from collections import Counter
    zcount = Counter()
    for step in range(n_sites):
        best = None
        for soc, w in I.SOC_TYPES.items():
            need = remaining[soc]
            if not need.any():
                continue
            gains = (WITHIN * (dem * need)).sum(axis=1) * w      # (C,)
            gains[used] = -1
            blocked = np.array([zcount[z_] >= max_per_zone for z_ in cand_zone])
            gains[blocked] = -1
            j = int(gains.argmax())
            if best is None or gains[j] > best[0]:
                best = (float(gains[j]), soc, j)
        if best is None or best[0] <= 0:
            break
        gain, soc, j = best
        hit = WITHIN[j]
        newly = remaining[soc] & hit
        pop_served = popc[newly].sum()
        remaining[soc] &= ~hit
        used[j] = True
        ci = cand[j]
        zcount[G.zone.values[ci]] += 1
        chosen.append(dict(
            순위=step + 1, 생활권=G.zone.values[ci], 시설유형=soc,
            위도=round(float(G.lat.values[ci]), 5), 경도=round(float(G.lon.values[ci]), 5),
            신규수혜인구=int(pop_served),
            취약가중수요=round(gain, 1),
            커버리지개선률=round(gain / total_demand * 100, 2),
            빈집률=round(float(zi.loc[G.zone.values[ci], "vacancy_rate"]), 1),
            CBI=round(float(zi.loc[G.zone.values[ci], "CBI"]), 1),
        ))

    R = pd.DataFrame(chosen)
    if len(R):
        R["누적커버리지개선률"] = R["커버리지개선률"].cumsum().round(2)
        R.to_csv(TAB / "08_생활SOC_투자우선순위.csv", index=False, encoding="utf-8-sig")
        print(f"\n▶ 입지 최적화 완료 — {len(R)}개소 선정, "
              f"누적 취약수요 커버리지 +{R['커버리지개선률'].sum():.1f}%p, "
              f"신규 수혜인구 {R['신규수혜인구'].sum():,}명")
    return R
