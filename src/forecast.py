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


class InsufficientData(RuntimeError):
    """학습에 필요한 최소 데이터가 없을 때 — 파이프라인을 멈추지 않고 예측 단계만 건너뛴다."""


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


# 구조지표만으로 돌리는 횡단면 모드용 피처 (시계열 불필요)
XSEC_FEATURES = ["aging_ratio", "youth_ratio", "soc_access", "soc_per_capita",
                 "vacancy_rate", "old_building", "transit_density", "pop_density",
                 "biz_density", "biz_diversity"]

XSEC_PARAMS = dict(objective="regression", n_estimators=180, learning_rate=0.05,
                   num_leaves=3, min_child_samples=3, subsample=0.8, subsample_freq=1,
                   colsample_bytree=0.65, reg_lambda=5.0, random_state=RANDOM_SEED,
                   verbose=-1)


def fit_evaluate_xsec(zone_static: pd.DataFrame):
    """
    횡단면 모드 — 개·폐업 시계열(LOCALDATA)이 없을 때.
      X: 구조 지표(고령화·생활SOC·빈집·노후도·상권밀도 …)
      y: 실제 관측된 5년 인구증감률을 뒤집은 '인구유출 압력'(백분위)
    y가 X에 포함되지 않으므로 순환참조가 아니며, Leave-One-Zone-Out CV로
    한 번도 보지 않은 생활권에 대해 일반화되는지 검증한다.
    표본이 25개로 작아 규제를 강하게 걸고, 평균예측 베이스라인과 함께 보고한다.
    """
    d = zone_static.copy()
    # 정답변수가 상수면(예: 인구 데이터가 한 시점뿐) 학습 자체가 성립하지 않는다.
    gy = pd.to_numeric(d.get("pop_growth_5y"), errors="coerce")
    if gy is None or gy.std(skipna=True) < 1e-9 or gy.notna().sum() < 10:
        raise InsufficientData(
            "인구증감률(정답변수)이 단일 시점이라 변동이 없습니다. "
            "다른 연도의 주민등록 인구 파일을 data/raw/pop_jumin_2.csv 로 추가하면 "
            "조기경보 모델이 활성화됩니다.")
    feats = [f for f in XSEC_FEATURES
             if f in d.columns and pd.to_numeric(d[f], errors="coerce").notna().sum() >= 20]
    d = d.dropna(subset=feats + ["pop_growth_5y"])
    y = (-pd.to_numeric(d["pop_growth_5y"])).rank(pct=True) * 100
    X = d[feats].astype(float)

    preds = np.full(len(d), np.nan)
    for i in range(len(d)):
        tr = np.ones(len(d), bool); tr[i] = False
        m = lgb.LGBMRegressor(**XSEC_PARAMS).fit(X[tr], y[tr])
        preds[i] = m.predict(X.iloc[[i]])[0]
    base = np.full(len(d), y.mean())
    metrics = dict(mode="cross-section", n=len(d), n_features=len(feats),
                   R2=float(r2_score(y, preds)), MAE=float(mean_absolute_error(y, preds)),
                   baseline_R2=float(r2_score(y, base)),
                   baseline_MAE=float(mean_absolute_error(y, base)))
    metrics["MAE_개선율"] = (1 - metrics["MAE"] / metrics["baseline_MAE"]) * 100

    final = lgb.LGBMRegressor(**XSEC_PARAMS).fit(X, y)
    latest = d.copy()
    latest["risk"] = y.values
    latest["risk_pred"] = final.predict(X)
    latest["risk_delta"] = latest["risk_pred"] - latest["risk"]
    res = latest[["zone", "risk", "risk_pred", "risk_delta"]].sort_values(
        "risk_pred", ascending=False).reset_index(drop=True)
    res.to_csv(TAB / "04_쇠퇴조기경보_예측.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([metrics]).to_csv(TAB / "05_모델성능.csv", index=False, encoding="utf-8-sig")
    print(f"\n▶ 조기경보 모델 [횡단면 모드 · 구조지표→인구유출압력]"
          f"  LOZO-CV R²={metrics['R2']:.3f}  MAE={metrics['MAE']:.2f}"
          f"  (평균예측 베이스라인 MAE={metrics['baseline_MAE']:.2f}"
          f" → {metrics['MAE_개선율']:.1f}% 개선)")
    print( "    · 개·폐업 시계열(LOCALDATA) 투입 시 t→t+3 패널 예측 모드로 자동 전환됩니다.")
    latest = latest.rename(columns={f: f for f in feats})
    globals()["ACTIVE_FEATURES"] = feats
    return final, res, metrics, X, latest


def fit_evaluate(p: pd.DataFrame, zone_static: pd.DataFrame | None = None):
    d = p.dropna(subset=["target"] + FEATURES).copy()
    if len(d) < 60 and zone_static is not None:      # 패널이 얇으면 횡단면 모드
        return fit_evaluate_xsec(zone_static)
    if len(d) < 30:
        raise InsufficientData("시계열 패널과 구조지표가 모두 부족해 예측 모델을 학습할 수 없습니다.")
    globals()["ACTIVE_FEATURES"] = FEATURES
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

    feats = globals().get("ACTIVE_FEATURES", FEATURES)
    sv = ex.shap_values(latest[feats])
    L = pd.DataFrame(sv, columns=feats, index=latest["zone"].values)
    L.to_csv(TAB / "07_SHAP_생활권별요인.csv", encoding="utf-8-sig")
    return glob, L
