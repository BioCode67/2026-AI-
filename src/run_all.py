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

    panel = forecast.build_panel(panels, cbi.reset_index())
    model, res, metrics, X, latest = forecast.fit_evaluate(panel)
    shap_glob, shap_local = forecast.explain(model, X, latest)

    sites = optimize.greedy_sites(cbi.reset_index(), panels["points"],
                                  n_sites=n_sites)

    prov = features.provenance_table()
    all_real = features.is_all_real()
    n_real = int((prov["상태"] == "REAL").sum())
    viz.BADGE.update(on=not all_real,
                     txt="※ 일부 지표는 예시(illustrative) 데이터 — 실데이터 투입 시 자동 갱신")

    print("\n▶ 시각화 생성")
    viz.fig_cbi_rank(cbi)
    viz.fig_domain_heat(cbi)
    viz.fig_gap_trend(panels, cbi)
    viz.fig_earlywarn(res, cbi)
    viz.fig_shap(shap_glob, shap_local, res)
    viz.fig_soc_gap(cbi)
    viz.fig_site_map(sites, panels["points"], cbi)
    viz.fig_coverage(sites)

    summary = dict(
        생활권수=len(cbi), 지표수=len(weights),
        신도심_CBI=round(gaps["신도심평균"], 1), 원도심_CBI=round(gaps["원도심평균"], 1),
        격차배율=round(gaps["배율"], 2), 지니계수=round(gaps["지니"], 3),
        변동계수=round(gaps["변동계수"], 1),
        최고=f'{gaps["최고동"]} {gaps["최고"]:.0f}', 최저=f'{gaps["최저동"]} {gaps["최저"]:.0f}',
        군집수=int(cbi.attrs["k"]), 실루엣=round(float(cbi.attrs["silhouette"]), 3),
        모델_R2=round(metrics["R2"], 3), 모델_MAE=round(metrics["MAE"], 2),
        베이스라인_MAE=round(metrics["baseline_MAE"], 2),
        MAE_개선율=round(metrics["MAE_개선율"], 1),
        위험급등_생활권=res.nlargest(3, "risk_delta")["zone"].tolist(),
        추천입지수=len(sites),
        신규수혜인구=int(sites["신규수혜인구"].sum()) if len(sites) else 0,
        커버리지개선=round(float(sites["커버리지개선률"].sum()), 1) if len(sites) else 0,
        실데이터지표=f"{n_real}/{len(prov)}", 전체실데이터=all_real,
    )
    (TAB / "09_요약지표.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n▶ 대시보드 생성")
    dashboard.build(cbi, weights, res, shap_glob, sites, prov, summary, gaps, panels)

    print("\n" + BAR)
    print(f"  완료 ({time.time() - t0:.1f}s)   실데이터 지표: {n_real}/{len(prov)}")
    if not all_real:
        need = prov[prov["상태"] != "REAL"]["지표군"].tolist()
        print(f"  ⚠ 예시 데이터 사용 중: {', '.join(need)}")
        print("    → docs/01_데이터_수집_가이드.md 대로 CSV를 넣고 다시 실행하면 전부 실데이터로 갱신됩니다.")
    else:
        print("  ✅ 전 지표 실데이터 — 그대로 제출 가능")
    print(f"  산출물: outputs/figures/(8장)  outputs/tables/(9종)  deliverables/dashboard.html")
    print(BAR)
    return summary


if __name__ == "__main__":
    main()
