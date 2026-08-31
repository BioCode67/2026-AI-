# -*- coding: utf-8 -*-
"""
전체 파이프라인 실행 진입점
  $ python3 src/run_all.py
data/raw/ 에 있는 실데이터만 골라 쓰고, 없는 부분은 예시 데이터로 채운 뒤
어떤 지표가 실데이터인지 명시적으로 표시한다.
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from config import TAB, FIG, DELIV
import ingest as I
import features, cbi as cbi_mod, forecast, optimize, viz, dashboard

BAR = "═" * 72


def main(n_sites: int = 12):
    t0 = time.time()
    print(BAR)
    print("  천안 균형발전 나침반(CBC) — 분석 파이프라인")
    print(BAR)

    zone_raw, panels = features.build_zone_table()
    cbi, weights = cbi_mod.compute(zone_raw)
    gaps = cbi_mod.gap_stats(cbi)
    idx_label, idx_scope = cbi_mod.index_label(cbi)
    print(f"    · 지수 명칭: {idx_label}  ({idx_scope})")

    panel = forecast.build_panel(panels, cbi.reset_index())
    forecast_ok, res, metrics, shap_glob, shap_local = True, None, {}, None, None
    try:
        model, res, metrics, X, latest = forecast.fit_evaluate(panel, cbi.reset_index())
        shap_glob, shap_local = forecast.explain(model, X, latest)
    except forecast.InsufficientData as e:
        forecast_ok = False
        print(f"\n▶ 조기경보 모델 \033[93m[건너뜀]\033[0m {e}")
        for f in ("04_쇠퇴조기경보_예측.csv", "05_모델성능.csv",
                  "06_SHAP_전역중요도.csv", "07_SHAP_생활권별요인.csv"):
            (TAB / f).unlink(missing_ok=True)
        for f in ("04_조기경보.png", "05_SHAP_요인분해.png"):
            (FIG / f).unlink(missing_ok=True)
        metrics = dict(status="unavailable", reason=str(e))

    try:
        sites = optimize.greedy_sites(cbi.reset_index(), panels["points"],
                                      n_sites=n_sites)
        sites_ok = True
    except optimize.InsufficientData as e:
        sites, sites_ok = pd.DataFrame(), False
        print(f"\n▶ 입지 최적화 \033[93m[건너뜀]\033[0m {e}")
        for f in ("08_생활SOC_투자우선순위.csv",):
            (TAB / f).unlink(missing_ok=True)
        for f in ("06_SOC_사각지대.png", "07_투자입지_지도.png", "08_커버리지_곡선.png"):
            (FIG / f).unlink(missing_ok=True)

    prov = features.provenance_table()
    all_real = features.is_all_real()
    n_real = int(prov["상태"].isin(["REAL", "PARTIAL"]).sum())
    # 예시 값이 섞였을 때만 경고를 찍는다. 엄격 모드에서는 미확보 지표를 아예 빼므로 경고가 없다.
    viz.BADGE.update(on=features.has_synthetic(),
                     txt="※ 일부 지표는 예시(illustrative) 데이터 — 실데이터 투입 시 자동 갱신")

    print("\n▶ 시각화 생성")
    viz.fig_cbi_rank(cbi)
    viz.fig_domain_heat(cbi)
    viz.fig_gap_trend(panels, cbi)
    if forecast_ok:
        viz.fig_earlywarn(res, cbi)
        viz.fig_shap(shap_glob, shap_local, res)
    if sites_ok:
        viz.fig_soc_gap(cbi)
        viz.fig_site_map(sites, panels["points"], cbi)
        viz.fig_coverage(sites)

    summary = dict(
        생활권수=len(cbi), 지표수=len(weights),
        지수명=idx_label, 지수범위=idx_scope,
        도메인수=len(cbi.attrs.get("domains_used", [])),
        신도심_CBI=round(gaps["신도심평균"], 1), 원도심_CBI=round(gaps["원도심평균"], 1),
        격차배율=round(gaps["배율"], 2), 지니계수=round(gaps["지니"], 3),
        변동계수=round(gaps["변동계수"], 1),
        최고=f'{gaps["최고동"]} {gaps["최고"]:.0f}', 최저=f'{gaps["최저동"]} {gaps["최저"]:.0f}',
        군집수=int(cbi.attrs["k"]), 실루엣=round(float(cbi.attrs["silhouette"]), 3),
        예측엔진=forecast_ok,
        예측미실행사유=metrics.get("reason", ""),
        모델_모드=metrics.get("mode", "panel"),
        모델_R2=round(metrics["R2"], 3) if forecast_ok else None,
        모델_MAE=round(metrics["MAE"], 2) if forecast_ok else None,
        베이스라인_MAE=round(metrics["baseline_MAE"], 2) if forecast_ok else None,
        MAE_개선율=round(metrics["MAE_개선율"], 1) if forecast_ok else None,
        방향적중률=round(metrics.get("방향적중률", float("nan")), 0) if forecast_ok else None,
        모델_목표=metrics.get("target", ""),
        위험급등_생활권=res.nlargest(3, "risk_delta")["zone"].tolist() if forecast_ok else [],
        처방엔진=sites_ok,
        추천입지수=len(sites),
        신규수혜인구=int(sites["신규수혜인구"].sum()) if len(sites) else 0,
        커버리지개선=round(float(sites["커버리지개선률"].sum()), 1) if len(sites) else 0,
        실데이터지표=f"{n_real}/{len(prov)}", 전체실데이터=all_real,
    )
    (TAB / "09_요약지표.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n▶ 대시보드 생성")
    dashboard.build(cbi, weights, res, shap_glob, sites, prov, summary, gaps, panels)

    print("\n▶ 기획서 생성")
    import make_deck
    make_deck.save()

    # PDF 는 LibreOffice 가 있을 때만 만든다(없어도 파이프라인은 정상 완료)
    import subprocess
    sh = ROOT_TOOLS = Path(__file__).resolve().parent.parent / "tools" / "make_pdf.sh"
    if sh.exists():
        try:
            out = subprocess.run(["bash", str(sh)], capture_output=True, text=True,
                                 timeout=420)
            print(out.stdout.rstrip() or "    · PDF 변환 건너뜀")
        except Exception as e:
            print(f"    · PDF 변환 건너뜀 ({e})")

    print("\n" + BAR)
    print(f"  완료 ({time.time() - t0:.1f}s)   실데이터 지표: {n_real}/{len(prov)}")
    if features.has_synthetic():
        need = prov[prov["상태"] == "ILLUSTRATIVE"]["지표군"].tolist()
        print(f"  ⚠ 예시 데이터 사용 중: {', '.join(need)}")
    elif not all_real:
        need = prov[prov["상태"] == "MISSING"]["지표군"].tolist()
        print(f"  미확보 지표군: {', '.join(need)} — 지수에서 제외하고 산출했습니다(예시 값 없음)")
        print("    → 파일을 넣고 다시 실행하면 해당 지표가 추가됩니다.")
    else:
        print("  ✅ 전 지표 실데이터 — 그대로 제출 가능")
    print("  산출물: outputs/figures/(8장) · outputs/tables/(9종) ·"
          " deliverables/{dashboard.html, 기획서_*.pptx, 기획서_*.pdf}")
    print(BAR)
    return summary


if __name__ == "__main__":
    main()
