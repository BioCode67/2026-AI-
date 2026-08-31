# -*- coding: utf-8 -*-
"""
쇠퇴 조기경보 모델 (Early-Warning)
  t년 시점 정보만으로 t+3년 쇠퇴위험도를 예측 → 쇠퇴가 '완료'되기 전에 개입
  · LightGBM 회귀 + Leave-One-Zone-Out CV (공간 누수 차단)
  · 지속성(persistence) 베이스라인 대비 개선폭으로 실효성 검증
  · SHAP으로 생활권별 쇠퇴 기여요인 분해 → 정책 처방과 직결
"""
from __future__ import annotations
import sys, warnings, numpy as np, pandas as pd
from pathlib import Path
import lightgbm as lgb
from sklearn.metrics import r2_score, mean_absolute_error
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import TAB, RANDOM_SEED, ZONE_TYPE
warnings.filterwarnings("ignore")

HORIZON = 3          # 3년 앞


def build_panel(panels: dict, zone_static: pd.DataFrame) -> pd.DataFrame:
    pop, biz = panels["pop"], panels["biz"]
    p = pop.merge(biz, on=["zone", "year"], how="inner").sort_values(["zone", "year"])
    g = p.groupby("zone")

    p["pop_yoy"]      = g["pop"].pct_change() * 100
    p["pop_3y"]       = g["pop"].pct_change(3) * 100
    p["biz_yoy"]      = g["active"].pct_change() * 100
    p["biz_3y"]       = g["active"].pct_change(3) * 100
    p["net_entry"]    = (p["opened"] - p["closed"]) / p["active"].replace(0, np.nan) * 100
    p["closure_rate"] = p["closed"] / p["active"].replace(0, np.nan) * 100
    p["open_rate"]    = p["opened"] / p["active"].replace(0, np.nan) * 100
    p["biz_per_1k"]   = p["active"] / p["pop"] * 1000

    st = zone_static[["zone", "aging_ratio", "youth_ratio", "soc_access",
                      "soc_per_capita", "vacancy_rate", "old_building",
                      "transit_density", "pop_density"]]
    p = p.merge(st, on="zone", how="left")

    # ── 연도별 쇠퇴위험도 R_t (0~100, 클수록 위험) ──────────────
    #   R = 표준화(-인구증감, -상권증감, +폐업률, -사업체밀도) 평균
    def z(s, inv=False):
        v = (s - s.mean()) / (s.std() + 1e-9)
        return -v if inv else v
    p["risk"] = (z(p["pop_3y"], inv=True) + z(p["biz_3y"], inv=True) +
                 z(p["closure_rate"]) + z(p["biz_per_1k"], inv=True)) / 4
    p["risk"] = (p["risk"].rank(pct=True) * 100)

    p["target"] = p.groupby("zone")["risk"].shift(-HORIZON)
    p["ztype"]  = p["zone"].map(ZONE_TYPE).astype("category")
    return p


FEATURES = ["pop", "pop_yoy", "pop_3y", "active", "biz_yoy", "biz_3y",
            "net_entry", "closure_rate", "open_rate", "biz_per_1k", "risk",
            "aging_ratio", "youth_ratio", "soc_access", "soc_per_capita",
            "vacancy_rate", "old_building", "transit_density", "pop_density"]

PARAMS = dict(objective="regression", n_estimators=400, learning_rate=0.045,
              num_leaves=6, min_child_samples=8, subsample=0.85, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=3.0, random_state=RANDOM_SEED, verbose=-1)


def fit_evaluate(p: pd.DataFrame):
    d = p.dropna(subset=["target"] + FEATURES).copy()
    X, y, zones = d[FEATURES], d["target"], d["zone"]

    # Leave-One-Zone-Out CV — 같은 생활권이 학습/검증에 동시에 들어가지 않게 함
    preds = np.full(len(d), np.nan)
    for z_ in zones.unique():
        tr, te = zones != z_, zones == z_
        if tr.sum() < 30 or te.sum() == 0:
            continue
        m = lgb.LGBMRegressor(**PARAMS).fit(X[tr], y[tr])
        preds[te.values] = m.predict(X[te])
    ok = ~np.isnan(preds)
    metrics = dict(
        n=int(ok.sum()),
        R2=float(r2_score(y[ok], preds[ok])),
        MAE=float(mean_absolute_error(y[ok], preds[ok])),
        baseline_R2=float(r2_score(y[ok], d["risk"][ok])),          # 지속성 베이스라인
        baseline_MAE=float(mean_absolute_error(y[ok], d["risk"][ok])),
    )
    metrics["MAE_개선율"] = (1 - metrics["MAE"] / metrics["baseline_MAE"]) * 100

    final = lgb.LGBMRegressor(**PARAMS).fit(X, y)

    # 최신연도 시점에서 3년 앞 예측
    latest = p[p.year == p.year.max()].dropna(subset=FEATURES).copy()
    latest["risk_pred"] = final.predict(latest[FEATURES])
    latest["risk_delta"] = latest["risk_pred"] - latest["risk"]
    res = latest[["zone", "risk", "risk_pred", "risk_delta"]].sort_values(
        "risk_pred", ascending=False).reset_index(drop=True)
    res.to_csv(TAB / "04_쇠퇴조기경보_예측.csv", index=False, encoding="utf-8-sig")

    cv = pd.DataFrame([metrics]); cv.to_csv(TAB / "05_모델성능.csv", index=False,
                                            encoding="utf-8-sig")
    print(f"\n▶ 조기경보 모델  LOZO-CV  R²={metrics['R2']:.3f}  MAE={metrics['MAE']:.2f}"
          f"  (지속성 베이스라인 MAE={metrics['baseline_MAE']:.2f}"
          f" → {metrics['MAE_개선율']:.1f}% 개선)")
    return final, res, metrics, X, latest


def explain(model, X: pd.DataFrame, latest: pd.DataFrame):
    """SHAP — 전역 중요도 + 생활권별 쇠퇴요인 분해"""
    import shap
    ex = shap.TreeExplainer(model)
    sv_all = ex.shap_values(X)
    glob = pd.Series(np.abs(sv_all).mean(0), index=X.columns).sort_values(ascending=False)
    glob.rename("mean_abs_shap").to_frame().to_csv(
        TAB / "06_SHAP_전역중요도.csv", encoding="utf-8-sig")

    sv = ex.shap_values(latest[FEATURES])
    L = pd.DataFrame(sv, columns=FEATURES, index=latest["zone"].values)
    L.to_csv(TAB / "07_SHAP_생활권별요인.csv", encoding="utf-8-sig")
    return glob, L
