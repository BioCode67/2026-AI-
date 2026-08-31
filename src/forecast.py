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
    """
    쇠퇴위험도 R_t 를 만들 때 **실데이터로 확보된 축만** 사용한다.
    예시(illustrative) 값이 섞인 축을 정답변수에 넣으면 모델이 잡음을 학습하게 되고,
    그 결과 성능이 베이스라인과 구분되지 않는다(실제로 그런 현상을 관측해 이렇게 바꿨다).
    """
    import ingest as _I
    pop, biz = panels["pop"], panels["biz"]
    # 상권 자료가 '시계열'인지 '한 시점'인지 구분한다.
    # 상가정보는 한 분기 스냅샷이라 연도가 1개뿐인데, 이걸 inner join 하면
    # 애써 모은 인구 11개년 패널이 그 한 해로 잘려 예측 모드가 후퇴한다.
    biz_years = int(biz["year"].nunique()) if biz is not None and len(biz) else 0
    biz_series = biz_years >= 5
    p = (pop.merge(biz, on=["zone", "year"], how="inner" if biz_series else "left")
            .sort_values(["zone", "year"]))
    if not biz_series and biz_years:
        print(f"    · 상권 자료가 {biz_years}개 연도뿐이라 시계열 피처에서 제외하고, "
              "인구 패널을 그대로 유지합니다")
    g = p.groupby("zone")

    p["pop_yoy"]      = g["pop"].pct_change() * 100
    p["pop_3y"]       = g["pop"].pct_change(3) * 100
    p["biz_yoy"]      = g["active"].pct_change() * 100
    p["biz_3y"]       = g["active"].pct_change(3) * 100
    p["net_entry"]    = (p["opened"] - p["closed"]) / p["active"].replace(0, np.nan) * 100
    p["closure_rate"] = p["closed"] / p["active"].replace(0, np.nan) * 100
    p["open_rate"]    = p["opened"] / p["active"].replace(0, np.nan) * 100
    p["biz_per_1k"]   = p["active"] / p["pop"] * 1000

    if "aging_ratio_y" in p.columns:
        p["aging_trend"] = g["aging_ratio_y"].diff(3) if False else \
            p.groupby("zone")["aging_ratio_y"].diff(3)
    keep = ["zone", "soc_access", "soc_per_capita", "vacancy_rate",
            "old_building", "transit_density", "pop_density", "biz_per_km2",
            "biz_diversity"]
    st = zone_static[[c for c in keep if c in zone_static.columns]]
    p = p.merge(st, on="zone", how="left")

    # ── 연도별 쇠퇴위험도 R_t (0~100, 클수록 위험) ──────────────
    #   R = 표준화(-인구증감, -상권증감, +폐업률, -사업체밀도) 평균
    def z(s, inv=False):
        v = (s - s.mean()) / (s.std() + 1e-9)
        return -v if inv else v

    # 인구 축(실데이터)
    comps = [z(p["pop_3y"], inv=True)]
    used = ["3년 인구증감률"]
    if "aging_ratio_y" in p.columns and p["aging_ratio_y"].notna().any():
        comps.append(z(p["aging_ratio_y"]));            used.append("고령비율")
    if "youth_ratio_y" in p.columns and p["youth_ratio_y"].notna().any():
        comps.append(z(p["youth_ratio_y"], inv=True));  used.append("청년비율")
    # 상권 축(실데이터일 때만)
    if biz_series:
        comps += [z(p["biz_3y"], inv=True), z(p["closure_rate"]),
                  z(p["biz_per_1k"], inv=True)]
        used += ["3년 상권증감", "폐업률", "사업체밀도"]
    p["risk"] = (sum(comps) / len(comps)).rank(pct=True) * 100
    p.attrs["risk_components"] = used
    p.attrs["biz_series"] = biz_series
    print(f"    · 쇠퇴위험도 정의에 사용한 축({len(used)}): {', '.join(used)}")

    # 목표는 위험도 '수준'이 아니라 '변화량'.
    #  · 수준은 자기상관이 강해 '작년과 같다'는 지속성 예측이 이미 거의 정답이 된다
    #    (실제로 수준을 목표로 두면 모델이 베이스라인을 이기지 못했다).
    #  · 조기경보가 알고 싶은 것은 "어느 동이 앞으로 나빠질 것인가" = 변화량이므로,
    #    Δrisk = risk(t+3) − risk(t) 를 직접 예측한다. 지속성 베이스라인은 Δ=0 예측에 해당한다.
    p["risk_future"] = p.groupby("zone")["risk"].shift(-HORIZON)
    p["target"] = p["risk_future"] - p["risk"]
    p["ztype"]  = p["zone"].map(ZONE_TYPE).astype("category")
    return p


POP_FEATURES = ["pop", "pop_yoy", "pop_3y", "risk", "aging_ratio_y", "youth_ratio_y",
                "aging_trend", "pop_density"]
BIZ_FEATURES = ["active", "biz_yoy", "biz_3y", "net_entry", "closure_rate",
                "open_rate", "biz_per_1k"]
STATIC_BIZ = ["biz_per_km2", "biz_diversity"]
STATIC_FEATURES = ["soc_access", "soc_per_capita", "vacancy_rate",
                   "old_building", "transit_density"] + STATIC_BIZ
FEATURES = POP_FEATURES + BIZ_FEATURES + STATIC_FEATURES

# 피처 → 출처 지표군. 해당 지표군이 실데이터가 아니면 학습에서 제외한다
# (예시 값을 피처로 넣으면 모델이 잡음을 학습해 일반화가 무너진다).
FEATURE_SOURCE = ({f: "인구" for f in POP_FEATURES} |
                  {f: "상권" for f in BIZ_FEATURES} |
                  {f: "상권" for f in STATIC_BIZ} |
                  {"soc_access": "생활SOC", "soc_per_capita": "생활SOC",
                   "vacancy_rate": "주거", "old_building": "주거",
                   "transit_density": "이동성"})


def real_features(candidates):
    import ingest as _I
    out, dropped = [], []
    for f in candidates:
        src = FEATURE_SOURCE.get(f, "인구")
        if _I.PROVENANCE.get(src, {}).get("status") in ("REAL", "PARTIAL"):
            out.append(f)
        else:
            dropped.append(f)
    if dropped:
        print(f"    · 예시 데이터라 학습에서 제외한 피처 {len(dropped)}개: {', '.join(dropped)}")
    return out

PARAMS = dict(objective="regression", n_estimators=300, learning_rate=0.04,
              num_leaves=5, min_child_samples=10, subsample=0.85, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=6.0, random_state=RANDOM_SEED, verbose=-1)


# 구조지표만으로 돌리는 횡단면 모드용 피처 (시계열 불필요)
XSEC_FEATURES = ["aging_ratio", "youth_ratio", "soc_access", "soc_per_capita",
                 "vacancy_rate", "old_building", "transit_density", "pop_density",
                 "biz_per_km2", "biz_diversity"]

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
    feats = real_features([f for f in XSEC_FEATURES
                           if f in d.columns
                           and pd.to_numeric(d[f], errors="coerce").notna().sum() >= 20])
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
    feats = real_features([f for f in FEATURES
                           if f in p.columns
                           and pd.to_numeric(p[f], errors="coerce").notna().sum() > 0])
    if not p.attrs.get("biz_series", True):
        feats = [f for f in feats if f not in BIZ_FEATURES]   # 한 시점짜리 상권 피처 제외
    globals()["ACTIVE_FEATURES"] = feats
    d = p.dropna(subset=["target"] + feats).copy()
    if len(d) < 60 and zone_static is not None:      # 패널이 얇으면 횡단면 모드
        return fit_evaluate_xsec(zone_static)
    if len(d) < 30:
        raise InsufficientData("시계열 패널과 구조지표가 모두 부족해 예측 모델을 학습할 수 없습니다.")
    X, y, zones = d[feats], d["target"], d["zone"]

    # Leave-One-Zone-Out CV — 같은 생활권이 학습/검증에 동시에 들어가지 않게 함
    preds = np.full(len(d), np.nan)
    for z_ in zones.unique():
        tr, te = zones != z_, zones == z_
        if tr.sum() < 30 or te.sum() == 0:
            continue
        m = lgb.LGBMRegressor(**PARAMS).fit(X[tr], y[tr])
        preds[te.values] = m.predict(X[te])
    ok = ~np.isnan(preds)
    base = np.zeros(int(ok.sum()))                    # 지속성 = 변화 없음(Δ=0)
    metrics = dict(
        mode="panel", target="Δrisk (3년 후 위험도 변화량)",
        n=int(ok.sum()), n_features=len(feats),
        R2=float(r2_score(y[ok], preds[ok])),
        MAE=float(mean_absolute_error(y[ok], preds[ok])),
        baseline_R2=float(r2_score(y[ok], base)),
        baseline_MAE=float(mean_absolute_error(y[ok], base)),
    )
    metrics["MAE_개선율"] = (1 - metrics["MAE"] / metrics["baseline_MAE"]) * 100
    # 방향(악화/개선) 적중률 — 정책적으로 가장 중요한 지표
    m = np.abs(y[ok]) > 2
    metrics["방향적중률"] = float((np.sign(preds[ok][m]) == np.sign(y[ok][m])).mean() * 100) \
        if m.sum() else float("nan")

    final = lgb.LGBMRegressor(**PARAMS).fit(X, y)

    # 최신연도 시점에서 3년 앞 예측
    latest = p[p.year == p.year.max()].dropna(subset=feats).copy()
    latest["risk_delta"] = final.predict(latest[feats])
    latest["risk_pred"] = (latest["risk"] + latest["risk_delta"]).clip(0, 100)
    res = latest[["zone", "risk", "risk_pred", "risk_delta"]].sort_values(
        "risk_pred", ascending=False).reset_index(drop=True)
    res.to_csv(TAB / "04_쇠퇴조기경보_예측.csv", index=False, encoding="utf-8-sig")

    cv = pd.DataFrame([metrics]); cv.to_csv(TAB / "05_모델성능.csv", index=False,
                                            encoding="utf-8-sig")
    print(f"\n▶ 조기경보 모델 [패널 · 목표=Δrisk]  LOZO-CV  R²={metrics['R2']:.3f}"
          f"  MAE={metrics['MAE']:.2f}"
          f"  (지속성 베이스라인 Δ=0 의 MAE={metrics['baseline_MAE']:.2f}"
          f" → {metrics['MAE_개선율']:+.1f}%)"
          f"  방향적중률={metrics['방향적중률']:.0f}%")
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
