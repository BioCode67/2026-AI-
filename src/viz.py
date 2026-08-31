# -*- coding: utf-8 -*-
"""시각화 — 제출용 그림 8종 (한글 폰트 적용)"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FIG, DOMAINS, TYPE_ORDER, TYPE_COLOR, INDICATORS
import ingest as I

for f in Path.home().glob(".fonts/Nanum*.ttf"):
    fm.fontManager.addfont(str(f))
plt.rcParams.update({
    "font.family": "NanumGothic", "axes.unicode_minus": False,
    "figure.dpi": 130, "savefig.dpi": 190, "savefig.bbox": "tight",
    "axes.edgecolor": "#C9CED6", "axes.linewidth": .9,
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.labelsize": 11,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
    "axes.grid": True, "grid.color": "#EBEEF2", "grid.linewidth": .9,
    "figure.facecolor": "white", "axes.facecolor": "white",
})
INK, MUTE, ACCENT = "#1B2430", "#6B7684", "#D64545"
BADGE = {"txt": "", "on": False}


def stamp(fig):
    if BADGE["on"]:
        fig.text(.995, .005, BADGE["txt"], ha="right", va="bottom",
                 fontsize=8, color="#B04A4A", alpha=.9)


def save(fig, name):
    stamp(fig); fig.savefig(FIG / name); plt.close(fig)
    print(f"    · {name}")


def _leg(types):
    return [Patch(facecolor=TYPE_COLOR[t], label=t) for t in TYPE_ORDER if t in types]


# ── 1. CBI 랭킹 ──────────────────────────────────────────────
def fig_cbi_rank(cbi):
    d = cbi.sort_values("CBI")
    fig, ax = plt.subplots(figsize=(9.4, 8.2))
    cols = [TYPE_COLOR[t] for t in d["ztype"]]
    ax.barh(d.index, d["CBI"], color=cols, height=.74,
            edgecolor="white", linewidth=.8)
    for y, (v, st) in enumerate(zip(d["CBI"], d["stage"])):
        ax.text(v + 1.2, y, f"{v:.0f}", va="center", fontsize=9.5, color=INK)
    mean = cbi["CBI"].mean()
    ax.axvline(mean, color=MUTE, ls="--", lw=1.2)
    ax.text(mean + .8, -1.1, f"시 평균 {mean:.0f}", color=MUTE, fontsize=9.5)
    ax.set_xlim(0, 108); ax.set_xlabel("CBI 균형발전지수 (0~100)")
    ax.set_title("천안시 25개 생활권 균형발전지수(CBI)\n"
                 "— 신도심 상위 3곳과 농촌·원도심 하위권의 구조적 이중격차", loc="left", pad=14)
    ax.legend(handles=_leg(set(d["ztype"])), loc="lower right", frameon=False, ncol=1)
    ax.grid(axis="y", visible=False)
    save(fig, "01_CBI_랭킹.png")


# ── 2. 권역유형 × 도메인 히트맵 ────────────────────────────────
def fig_domain_heat(cbi):
    m = cbi.groupby("ztype")[[f"D_{d}" for d in DOMAINS]].mean()
    m = m.reindex([t for t in TYPE_ORDER if t in m.index])
    m.columns = DOMAINS
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    im = ax.imshow(m.values, cmap="RdYlBu", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(len(DOMAINS)), DOMAINS)
    ax.set_yticks(range(len(m)), m.index)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=12,
                    color="white" if (v < 32 or v > 78) else INK, fontweight="bold")
    ax.set_title("권역유형별 5대 도메인 점수 — 쇠퇴의 '얼굴'이 다르다", loc="left", pad=12)
    fig.colorbar(im, ax=ax, shrink=.85, label="도메인 점수")
    ax.grid(False)
    fig.text(.01, -.07,
             "원도심: 생활SOC는 갖췄으나 경제활력·인구활력이 붕괴  ↔  농촌면: 생활SOC 자체가 부재\n"
             "→ 같은 '낙후'라도 처방이 정반대여야 함을 데이터가 보여준다.",
             fontsize=10, color=MUTE)
    save(fig, "02_도메인_히트맵.png")


# ── 3. 격차 추이 ─────────────────────────────────────────────
def fig_gap_trend(panels, cbi):
    pop, biz = panels["pop"], panels["biz"]
    t = cbi["ztype"]
    p = pop.assign(ztype=pop.zone.map(t)); b = biz.assign(ztype=biz.zone.map(t))
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    for ax, (d, col, ttl, ylab) in zip(axes, [
            (p, "pop", "인구 추이 (2018=100)", "지수"),
            (b, "active", "영업 중 사업체 추이 (2018=100)", "지수")]):
        for ty in TYPE_ORDER:
            s = d[d.ztype == ty].groupby("year")[col].sum()
            if len(s) < 2:
                continue
            base = s.loc[s.index.min()]
            ax.plot(s.index, s / base * 100, marker="o", ms=4.2, lw=2.3,
                    color=TYPE_COLOR[ty], label=ty)
        ax.axhline(100, color=MUTE, ls=":", lw=1)
        ax.set_title(ttl, loc="left"); ax.set_ylabel(ylab); ax.set_xlabel("연도")
    axes[0].legend(frameon=False, ncol=2, fontsize=9.5)
    fig.suptitle("격차는 좁혀지지 않고 '벌어지고' 있다 — 권역유형별 궤적 분기",
                 x=.012, ha="left", fontsize=15, fontweight="bold", y=1.03)
    save(fig, "03_격차추이.png")


# ── 4. 조기경보 ─────────────────────────────────────────────
def fig_earlywarn(res, cbi):
    d = res.merge(cbi.reset_index()[["zone", "ztype"]], on="zone")
    fig, ax = plt.subplots(figsize=(8.6, 6.6))
    for ty in TYPE_ORDER:
        s = d[d.ztype == ty]
        ax.scatter(s["risk"], s["risk_pred"], s=105, color=TYPE_COLOR[ty],
                   label=ty, edgecolor="white", linewidth=1.3, zorder=3)
    lim = (-4, 106)
    ax.plot(lim, lim, color=MUTE, ls="--", lw=1.2, zorder=1)
    ax.fill_between(lim, lim, 106, color=ACCENT, alpha=.06, zorder=0)
    ax.text(6, 96, "위험 상승 구간\n(3년 내 악화 예상)", color=ACCENT, fontsize=10.5,
            fontweight="bold", va="top")
    rise = d.nlargest(5, "risk_delta")
    for r in rise.itertuples():
        ax.annotate(f"{r.zone}  +{r.risk_delta:.0f}", (r.risk, r.risk_pred),
                    textcoords="offset points", xytext=(9, 7), fontsize=10,
                    fontweight="bold", color=ACCENT)
    ax.set_xlim(*lim); ax.set_ylim(*lim)
    ax.set_xlabel("현재 쇠퇴위험도 (백분위)"); ax.set_ylabel("3년 후 예측 쇠퇴위험도 (백분위)")
    ax.set_title("쇠퇴 조기경보 — '아직 안 나빠진 곳'을 미리 찾는다", loc="left", pad=12)
    ax.legend(frameon=False, loc="lower right", fontsize=9.5)
    save(fig, "04_조기경보.png")


# ── 5. SHAP ─────────────────────────────────────────────────
def fig_shap(glob, L, res):
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.6),
                             gridspec_kw={"width_ratios": [1, 1.35]})
    g = glob.head(10).sort_values()
    names = [INDICATORS.get(i, (None, i))[1] if i in INDICATORS else i for i in g.index]
    axes[0].barh(names, g.values, color="#2E7DD1", height=.7)
    axes[0].set_title("무엇이 쇠퇴를 예측하는가\n(SHAP 전역 중요도)", loc="left", fontsize=13)
    axes[0].set_xlabel("평균 |SHAP|"); axes[0].grid(axis="y", visible=False)

    top = res.nlargest(8, "risk_pred")["zone"].tolist()
    cols = glob.head(8).index.tolist()
    M = L.loc[[z for z in top if z in L.index], cols]
    M.columns = [INDICATORS.get(c, (None, c))[1] if c in INDICATORS else c for c in cols]
    v = np.abs(M.values).max()
    im = axes[1].imshow(M.values, cmap="RdBu_r", aspect="auto", vmin=-v, vmax=v)
    axes[1].set_xticks(range(M.shape[1]), M.columns, rotation=34, ha="right", fontsize=9.5)
    axes[1].set_yticks(range(M.shape[0]), M.index, fontsize=10.5)
    axes[1].set_title("위험 상위 생활권의 쇠퇴 기여요인 분해\n(붉을수록 위험을 밀어올린 요인)",
                      loc="left", fontsize=13)
    axes[1].grid(False)
    fig.colorbar(im, ax=axes[1], shrink=.8, label="SHAP 기여도")
    fig.text(.01, -.04, "→ 같은 '고위험'이라도 원인이 다르므로, 동별 맞춤 처방이 가능하다.",
             fontsize=10.5, color=MUTE)
    save(fig, "05_SHAP_요인분해.png")


# ── 6. 생활SOC 사각지대 ───────────────────────────────────────
def fig_soc_gap(cbi):
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    for ty in TYPE_ORDER:
        s = cbi[cbi.ztype == ty]
        ax.scatter(s["soc_access"], s["aging_ratio"], s=np.sqrt(s["pop"]) * 2.4,
                   color=TYPE_COLOR[ty], alpha=.85, edgecolor="white",
                   linewidth=1.3, label=ty, zorder=3)
    xm, ym = cbi["soc_access"].median(), cbi["aging_ratio"].median()
    ax.axvline(xm, color=MUTE, ls="--", lw=1); ax.axhline(ym, color=MUTE, ls="--", lw=1)
    risk = cbi[(cbi.soc_access < xm) & (cbi.aging_ratio > ym)]
    ax.fill_betweenx([ym, cbi.aging_ratio.max() * 1.06], -3, xm,
                     color=ACCENT, alpha=.07, zorder=0)
    for r in risk.itertuples():
        ax.annotate(r.Index, (r.soc_access, r.aging_ratio), fontsize=9.8,
                    textcoords="offset points", xytext=(8, 5), color=ACCENT,
                    fontweight="bold")
    ax.text(2, cbi.aging_ratio.max() * 1.02,
            f"⚠ 정책 최우선 사각지대 — 고령↑ · 생활SOC↓  ({len(risk)}개 생활권)",
            color=ACCENT, fontsize=11, fontweight="bold", va="top")
    ax.set_xlabel("생활SOC 접근성 점수 (중력모형, 0~100)")
    ax.set_ylabel("고령(65세+) 인구 비율 (%)")
    ax.set_title("생활SOC 사각지대 — 원의 크기는 인구 규모", loc="left", pad=12)
    ax.legend(frameon=False, loc="upper right", fontsize=9.5)
    ax.set_xlim(-3, 106)
    save(fig, "06_SOC_사각지대.png")


# ── 7. 투자 우선순위 지도 ─────────────────────────────────────
def fig_site_map(R, points, cbi):
    fig, ax = plt.subplots(figsize=(8.8, 8.4))
    ax.scatter(points.lon, points.lat, s=5, color="#C7D2DE", alpha=.55,
               label="기존 생활SOC", zorder=1)
    for z, (la, lo) in I.CENTROID.items():
        ax.scatter(lo, la, s=np.sqrt(cbi.loc[z, "pop"]) * 1.5,
                   color=TYPE_COLOR[cbi.loc[z, "ztype"]], alpha=.35,
                   edgecolor="white", linewidth=.8, zorder=2)
        ax.annotate(z, (lo, la), fontsize=8.2, color=MUTE, ha="center",
                    textcoords="offset points", xytext=(0, -12))
    if len(R):
        ax.scatter(R.경도, R.위도, s=190, marker="*", color=ACCENT,
                   edgecolor="white", linewidth=1.2, zorder=4, label="AI 추천 신규 입지")
        for r in R.itertuples():
            ax.annotate(f"{r.순위}", (r.경도, r.위도), fontsize=9,
                        fontweight="bold", color="white", ha="center", va="center", zorder=5)
    ax.set_xlabel("경도"); ax.set_ylabel("위도")
    ax.set_title("생활SOC 투자 우선순위 입지 — MCLP 탐욕 최적화 결과", loc="left", pad=12)
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    ax.set_aspect(1 / np.cos(np.radians(36.8)))
    save(fig, "07_투자입지_지도.png")


# ── 8. 커버리지 개선 곡선 ────────────────────────────────────
def fig_coverage(R):
    if not len(R):
        return
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    x = R["순위"]
    ax.bar(x, R["커버리지개선률"], color="#4FA88B", width=.62, label="개소별 커버리지 개선")
    ax2 = ax.twinx()
    ax2.plot(x, R["누적커버리지개선률"], color=ACCENT, marker="o", ms=5.5, lw=2.4,
             label="누적 개선")
    ax2.grid(False)
    for i, (xi, yi) in enumerate(zip(x, R["누적커버리지개선률"])):
        if i in (0, len(x) // 2, len(x) - 1):
            ax2.annotate(f"+{yi:.1f}%p", (xi, yi), textcoords="offset points",
                         xytext=(0, 10), fontsize=10, color=ACCENT,
                         fontweight="bold", ha="center")
    ax.set_xlabel("투자 순위 (예산 투입 순서)")
    ax.set_ylabel("개소별 개선(%p)"); ax2.set_ylabel("누적 개선(%p)")
    ax.set_xticks(x)
    ax.set_title("한정된 예산을 어디부터 쓸 것인가 — 한계효용 체감 곡선", loc="left", pad=12)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="center right", fontsize=10)
    tot = R["신규수혜인구"].sum()
    fig.text(.01, -.06, f"상위 {len(R)}개소만 우선 투자해도 취약수요 커버리지 "
                        f"+{R['커버리지개선률'].sum():.1f}%p, 신규 수혜인구 약 {tot:,}명.",
             fontsize=10.5, color=MUTE)
    save(fig, "08_커버리지_곡선.png")
