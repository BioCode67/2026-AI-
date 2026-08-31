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


def usable_indicators(df: pd.DataFrame) -> list[str]:
    """
    데이터가 없어 산출 불가한 지표는 CBI에서 제외한다.
    (예: 상가정보만 있고 인허가 시계열이 없으면 상권순증감·폐업률이 빠짐)
    빠진 지표의 몫은 엔트로피 가중이 남은 지표에 자동 재배분하므로 지수는 계속 유효하다.
    """
    ok = []
    for k in INDICATORS:
        if k not in df.columns:
            continue
        v = pd.to_numeric(df[k], errors="coerce")
        if v.notna().sum() >= max(3, int(len(v) * 0.5)) and v.std(skipna=True) > 0:
            ok.append(k)
    dropped = [INDICATORS[k][1] for k in INDICATORS if k not in ok]
    if dropped:
        print(f"    · 데이터 부재로 제외된 지표 {len(dropped)}개: {', '.join(dropped)}")
    return ok


WINSOR = (0.05, 0.95)


def normalize(df: pd.DataFrame, keys=None) -> pd.DataFrame:
    """
    방향 보정 정규화 → 0~1 (1이 항상 '좋음')

    [왜 그냥 min-max 를 쓰지 않는가]
    단순 min-max 는 극단값 하나에 지수 전체가 휘둘린다. 실제로 천안 데이터에서
    풍세면의 5년 인구증감률이 +158%(신축 입주 유입)로 나오자, 나머지 23개 생활권이
    0.02~0.2 구간에 뭉쳐 변별력을 잃는 현상이 관측됐다.
    → 5~95 백분위로 윈저화(winsorize)한 뒤 min-max 를 적용한다.
      극단값은 경계값으로 눌리되 순위는 보존되므로, 지수가 특정 동네의
      예외적 사건 하나에 좌우되지 않는다.
    """
    Z = pd.DataFrame(index=df.index)
    for k, (_, _, direction, _) in ((k, INDICATORS[k]) for k in (keys or INDICATORS)):
        v = pd.to_numeric(df[k], errors="coerce")
        v = v.fillna(v.median())
        lo, hi = v.quantile(WINSOR[0]), v.quantile(WINSOR[1])
        v = v.clip(lo, hi)
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
    X = df.set_index("zone")
    keys = usable_indicators(X)
    Z = normalize(X, keys)
    w = entropy_weights(Z)

    out = df.set_index("zone").copy()
    for dom in DOMAINS:
        ks = [k for k in keys if INDICATORS[k][0] == dom]
        if not ks:
            out[f"D_{dom}"] = np.nan
            continue
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
    out.attrs["indicators_used"] = keys

    out.attrs["domains_used"] = [d for d in DOMAINS if f"D_{d}" in out.columns
                                and out[f"D_{d}"].notna().any()]
    out = out.sort_values("CBI", ascending=False)
    out.reset_index().to_csv(TAB / "02_CBI_균형발전지수.csv", index=False, encoding="utf-8-sig")
    wt = w.rename("weight").to_frame()
    wt["도메인"] = [INDICATORS[i][0] for i in wt.index]
    wt["지표명"] = [INDICATORS[i][1] for i in wt.index]
    wt.sort_values("weight", ascending=False).to_csv(
        TAB / "03_엔트로피_가중치.csv", encoding="utf-8-sig")
    print(f"\n▶ CBI 산출 완료 — 군집 k={k}, 실루엣={sil:.3f}")
    return out, w


def index_label(cbi: pd.DataFrame) -> tuple[str, str]:
    """
    확보한 도메인 수에 따라 지수 이름을 정직하게 바꾼다.

    인구 축만 있는 상태에서 '균형발전지수'라고 부르면 이름과 내용이 어긋난다
    (실제로 인구 축만 남기자 신축 입주로 인구가 는 두 곳이 1·2위가 되었다).
    3개 도메인 이상을 확보했을 때만 '균형발전지수'로 부른다.
    """
    doms = [d for d in DOMAINS if f"D_{d}" in cbi.columns
            and pd.to_numeric(cbi[f"D_{d}"], errors="coerce").notna().any()]
    n = len(doms)
    if n >= 3:
        return "CBI 균형발전지수", f"{n}개 도메인 · {len(cbi.attrs.get('indicators_used', []))}개 지표"
    if n == 2:
        return "생활여건지수(잠정)", f"{'·'.join(doms)} 2개 도메인만 확보 — 확장 예정"
    return f"{doms[0] if doms else '단일'}지수(잠정)", \
           f"{doms[0] if doms else '?'} 도메인만 확보 — 균형발전지수로 부르기에는 이릅니다"


def gap_stats(cbi: pd.DataFrame) -> dict:
    """
    격차 요약 통계.
    '신도심 대 원도심'을 미리 정해 두지 않는다 — 실데이터에서 가장 큰 격차는
    도심 내부가 아니라 도농 간에서 나타났고(신도심 57.7 ↔ 농촌면 11.1),
    가설이 아니라 데이터가 헤드라인을 정해야 하기 때문이다.
    """
    g = cbi.groupby("ztype")["CBI"].mean().sort_values(ascending=False)
    hi_t, lo_t = g.index[0], g.index[-1]
    hi, lo = float(g.iloc[0]), float(g.iloc[-1])
    new, old = g.get("신도심", np.nan), g.get("원도심", np.nan)
    return dict(
        최대격차_상위유형=hi_t, 최대격차_하위유형=lo_t,
        최대격차_상위값=hi, 최대격차_하위값=lo,
        최대배율=hi / lo if lo else np.nan,
        신도심평균=new, 원도심평균=old, 격차=new - old, 배율=new / old if old else np.nan,
        최고=cbi["CBI"].max(), 최저=cbi["CBI"].min(),
        최고동=cbi["CBI"].idxmax(), 최저동=cbi["CBI"].idxmin(),
        지니=_gini(cbi["CBI"].values),
        변동계수=cbi["CBI"].std() / cbi["CBI"].mean() * 100,
        권역평균=g.round(1).to_dict(),
    )


def _gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))
