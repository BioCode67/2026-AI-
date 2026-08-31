# -*- coding: utf-8 -*-
"""
시각화 — 제출용 그림 8종

설계 기준
 · 색은 눈으로 고르지 않고 검증 스크립트를 통과한 조합만 쓴다(config.TYPE_COLOR 주석 참조)
 · 마크는 얇게, 데이터 끝은 둥글게, 채움 사이에는 표면색 간격을 둔다
 · 격자·축은 뒤로 물리고, 라벨은 필요한 곳에만 직접 붙인다
 · 값 라벨을 항상 함께 두어 색 대비가 낮은 계열도 색만으로 읽히지 않게 한다
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Patch, FancyBboxPatch
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from matplotlib.colors import LinearSegmentedColormap
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (FIG, DOMAINS, TYPE_ORDER, TYPE_COLOR, INDICATORS,
                    SURFACE, INK, INK_2, INK_MUTE, GRID, AXIS,
                    SEQ_BLUE, DIV_LOW, DIV_MID, DIV_HIGH,
                    ST_WARN, ST_CRITICAL)
import ingest as I

for f in Path.home().glob(".fonts/Nanum*.ttf"):
    fm.fontManager.addfont(str(f))

# 타이포 스케일 (pt) — 한 단계씩만 차이 나게 해 위계를 분명히
T_TITLE, T_SUB, T_AXIS, T_TICK, T_LABEL, T_NOTE = 16, 11.5, 11, 10.5, 10, 10

plt.rcParams.update({
    "font.family": "NanumGothic", "axes.unicode_minus": False,
    "figure.dpi": 130, "savefig.dpi": 200, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.28,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
    "axes.labelcolor": INK_2, "axes.labelsize": T_AXIS, "axes.labelpad": 9,
    "axes.titlesize": T_TITLE, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "xtick.labelsize": T_TICK, "ytick.labelsize": T_TICK,
    "xtick.color": INK_2, "ytick.color": INK_2,
    "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 7,
    "legend.fontsize": T_LABEL, "legend.frameon": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.9,
    "axes.axisbelow": True,
})

SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
DIV_CMAP = LinearSegmentedColormap.from_list("div_br", [DIV_LOW, DIV_MID, DIV_HIGH])
BADGE = {"txt": "", "on": False}


# ── 공통 헬퍼 ────────────────────────────────────────────────
def _spines(ax, keep=()):
    for k, sp in ax.spines.items():
        sp.set_visible(k in keep)


def title(ax, main, sub=None, pad=16):
    ax.set_title(main, loc="left", pad=pad + (14 if sub else 0))
    if sub:
        ax.text(0, 1.012, sub, transform=ax.transAxes, fontsize=T_SUB,
                color=INK_MUTE, va="bottom", ha="left")


def note(fig, text, y=-0.055):
    fig.text(0.008, y, text, fontsize=T_NOTE, color=INK_MUTE, va="top", linespacing=1.55)


def legend(ax, types, **kw):
    kw.setdefault("loc", "lower right")
    handles = [Patch(facecolor=TYPE_COLOR[t], label=t, edgecolor=SURFACE, linewidth=1.4)
               for t in TYPE_ORDER if t in types]
    lg = ax.legend(handles=handles, handlelength=.95, handleheight=.95,
                   borderpad=.6, labelspacing=.62, **kw)
    for t in lg.get_texts():
        t.set_color(INK_2)
    return lg


def hbar(ax, y, width, color, h=0.62, r_frac=0.5, x0=0.0):
    """데이터 끝만 둥근 가로 막대 (기준선 쪽은 각지게)."""
    if width <= 0:
        return
    r = min(h * r_frac / 2, width)
    y0, y1 = y - h / 2, y + h / 2
    x1 = x0 + width
    v = [(x0, y0), (x1 - r, y0), (x1, y0), (x1, y0 + r), (x1, y1 - r), (x1, y1),
         (x1 - r, y1), (x0, y1), (x0, y0)]
    c = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3,
         MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(v, c), facecolor=color, edgecolor=SURFACE,
                           linewidth=1.6, zorder=3))


def vbar(ax, x, height, color, w=0.62, r_frac=0.5, y0=0.0):
    """데이터 끝(위)만 둥근 세로 막대."""
    if height <= 0:
        return
    ylim = ax.get_ylim(); span = (ylim[1] - ylim[0]) or 1
    r = min(w * r_frac / 2 * (span / max(ax.get_xlim()[1] - ax.get_xlim()[0], 1e-9)) * 0,
            0)  # 좌표계 비율 왜곡을 피하려 반지름은 데이터 단위로 직접 계산
    r = min(span * 0.012, height)
    x0, x1 = x - w / 2, x + w / 2
    y1 = y0 + height
    v = [(x0, y0), (x0, y1 - r), (x0, y1), (x0 + r, y1), (x1 - r, y1), (x1, y1),
         (x1, y1 - r), (x1, y0), (x0, y0)]
    c = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3,
         MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(v, c), facecolor=color, edgecolor=SURFACE,
                           linewidth=1.6, zorder=3))


def colorbar(fig, im, ax, label, shrink=.84):
    """라벨을 세로로 눕히지 않고 컬러바 위에 가로로 얹는다."""
    cb = fig.colorbar(im, ax=ax, shrink=shrink, pad=.022)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=T_TICK, colors=INK_2, length=0)
    cb.ax.set_title(label, fontsize=T_NOTE, color=INK_MUTE, pad=8, loc="left")
    return cb


def spread(ys, min_gap):
    """가까이 몰린 라벨 y좌표를 최소 간격만큼 벌린다(순서 보존)."""
    idx = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for k in range(1, len(idx)):
        a, b = idx[k - 1], idx[k]
        if out[b] - out[a] < min_gap:
            out[b] = out[a] + min_gap
    return out


class LabelPlacer:
    """
    화면(픽셀) 좌표에서 라벨 상자 겹침을 검사해, 자리가 없으면 건너뛴다.
    후보 위치를 여러 방향으로 시도하고 모두 막히면 라벨을 포기한다
    (겹쳐 찍어 읽을 수 없게 만드는 것보다 낫다).
    """
    # 가까운 자리부터 시도하고, 막히면 점점 멀리 — 멀어지면 지시선을 함께 그린다
    NEAR = [(9, 0), (-9, 0), (0, 11), (0, -11), (9, 9), (-9, 9), (9, -9), (-9, -9)]
    FAR = [(d * cx, d * cy) for d in (22, 34, 48)
           for cx, cy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                          (.72, .72), (-.72, .72), (.72, -.72), (-.72, -.72))]
    LEAD_FROM = len(NEAR)

    @property
    def OFFSETS(self):
        return self.NEAR + (self.FAR if self.allow_lead else [])

    def __init__(self, ax, pad=2.0, allow_lead=False):
        self.ax, self.pad, self.boxes = ax, pad, []
        self.allow_lead = allow_lead

    def _extent(self, text, size):
        wide = sum(1 for c in text if ord(c) > 0x2E80)
        narrow = len(text) - wide
        dpi = self.ax.figure.dpi / 72
        return (wide * size + narrow * size * .56) * dpi * 1.10, size * 1.40 * dpi

    def reserve(self, x0, y0, x1, y1):
        self.boxes.append((x0, y0, x1, y1))

    def reserve_point(self, xd, yd, r_px=9):
        px, py = self.ax.transData.transform((xd, yd))
        self.reserve(px - r_px, py - r_px, px + r_px, py + r_px)

    def _free(self, b):
        # 축 영역을 벗어나면 잘리므로 배치하지 않는다
        bb = self.ax.get_window_extent()
        if b[0] < bb.x0 + 1 or b[2] > bb.x1 - 1 or b[1] < bb.y0 + 1 or b[3] > bb.y1 - 1:
            return False
        return not any(not (b[2] + self.pad <= o[0] or o[2] + self.pad <= b[0] or
                            b[3] + self.pad <= o[1] or o[3] + self.pad <= b[1])
                       for o in self.boxes)

    def place(self, xd, yd, text, size=9, color=INK_2, weight="normal", force=False):
        px, py = self.ax.transData.transform((xd, yd))
        w, h = self._extent(text, size)
        for k, (ox, oy) in enumerate(self.OFFSETS):
            ax_, ay_ = px + ox, py + oy
            ha = "left" if ox > 0 else ("right" if ox < 0 else "center")
            va = "bottom" if oy > 0 else ("top" if oy < 0 else "center")
            x0 = ax_ if ha == "left" else (ax_ - w if ha == "right" else ax_ - w / 2)
            y0 = ay_ if va == "bottom" else (ay_ - h if va == "top" else ay_ - h / 2)
            box = (x0, y0, x0 + w, y0 + h)
            if self._free(box) or force:
                self.reserve(box[0], box[1], box[2], box[3])
                lead = k >= self.LEAD_FROM
                self.ax.annotate(
                    text, (xd, yd), textcoords="offset points",
                    xytext=(ox, oy), ha=ha, va=va, fontsize=size,
                    color=color, fontweight=weight, zorder=6,
                    arrowprops=dict(arrowstyle="-", color=AXIS, lw=.75,
                                    shrinkA=1, shrinkB=4) if lead else None)
                return True
        return False


def stamp(fig):
    if BADGE["on"]:
        # 하단은 축 라벨·주석이 차지하므로 상단 우측에 둔다
        fig.text(.999, 1.004, BADGE["txt"], ha="right", va="bottom",
                 fontsize=8.5, color=ST_WARN, alpha=.95)


def save(fig, name):
    stamp(fig); fig.savefig(FIG / name); plt.close(fig)
    print(f"    · {name}")


# ── 1. CBI 랭킹 ──────────────────────────────────────────────
def fig_cbi_rank(cbi):
    d = cbi.sort_values("CBI")
    fig, ax = plt.subplots(figsize=(9.6, 8.6))
    for i, (z, r) in enumerate(d.iterrows()):
        hbar(ax, i, r["CBI"], TYPE_COLOR[r["ztype"]])
        ax.text(r["CBI"] + 1.6, i, f"{r['CBI']:.0f}", va="center",
                fontsize=T_LABEL, color=INK_2)
    ax.set_yticks(range(len(d)), d.index)
    ax.set_ylim(-0.9, len(d) - 0.1)
    mean = cbi["CBI"].mean()
    ax.axvline(mean, color=AXIS, ls=(0, (4, 3)), lw=1.1, zorder=1)
    ax.text(mean, -0.85, f" 시 평균 {mean:.0f}", color=INK_MUTE, fontsize=T_NOTE, va="center")
    ax.set_xlim(0, 106)
    ax.grid(axis="y", visible=False); _spines(ax)

    top, bot = cbi.nlargest(3, "CBI"), cbi.nsmallest(6, "CBI")
    one = lambda s: (s["ztype"].unique()[0] if s["ztype"].nunique() == 1 else None)
    tt, bt = one(top), one(bot)
    g = cbi.groupby("ztype")["CBI"].mean()
    bits = []
    if tt: bits.append(f"상위 3곳은 모두 {tt}")
    if bt: bits.append(f"하위 6곳은 모두 {bt}")
    if {"신도심", "원도심"} <= set(g.index):
        bits.append(f"권역 평균 신도심 {g['신도심']:.0f} ↔ 원도심 {g['원도심']:.0f}")
    from cbi import index_label
    label, scope = index_label(cbi)
    ax.set_xlabel(f"{label} (0~100)")
    title(ax, f"천안시 {len(cbi)}개 생활권 {label}",
          (" · ".join(bits) + f"  |  {scope}") if bits else scope)
    legend(ax, set(d["ztype"]), loc="lower right", bbox_to_anchor=(1.0, 0.02))
    save(fig, "01_CBI_랭킹.png")


# ── 2. 권역유형 × 도메인 ─────────────────────────────────────
def fig_domain_heat(cbi):
    """확보한 도메인만 그린다(미확보 도메인을 nan 칸으로 남기지 않는다)."""
    cols = [d for d in DOMAINS if f"D_{d}" in cbi.columns
            and pd.to_numeric(cbi[f"D_{d}"], errors="coerce").notna().any()]
    if len(cols) < 2:
        return
    m = cbi.groupby("ztype")[[f"D_{d}" for d in cols]].mean()
    m = m.reindex([t for t in TYPE_ORDER if t in m.index]); m.columns = cols

    fig, ax = plt.subplots(figsize=(1.55 * len(cols) + 3.4, 4.6))
    im = ax.imshow(m.values, cmap=SEQ_CMAP, aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)), cols)
    ax.set_yticks(range(len(m)), m.index)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, "—" if pd.isna(v) else f"{v:.0f}", ha="center", va="center",
                    fontsize=13, color="white" if (not pd.isna(v) and v > 52) else INK,
                    fontweight="bold")
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xticks(np.arange(-.5, m.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-.5, m.shape[0], 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2.4)
    ax.tick_params(which="minor", length=0); ax.grid(which="major", visible=False)
    colorbar(fig, im, ax, "도메인 점수", shrink=.86)

    sub = "같은 '어려움'이라도 사정이 서로 다릅니다"
    if len(cols) < len(DOMAINS):
        miss = [d for d in DOMAINS if d not in cols]
        sub += f"  ·  미확보: {', '.join(miss)}"
    title(ax, "권역유형별 도메인 점수", sub)

    # 하단 해설은 실제 수치에서 만든다(고정 문구가 데이터와 어긋나지 않도록)
    lines = []
    for ty in ("원도심", "농촌면"):
        if ty in m.index:
            row = m.loc[ty].dropna()
            if len(row) >= 2:
                lines.append(f"{ty}: {row.idxmax()} {row.max():.0f}점이 가장 높고 "
                             f"{row.idxmin()} {row.min():.0f}점이 가장 낮습니다")
    if lines:
        note(fig, "\n".join(lines) +
                  "\n→ 지수가 비슷하게 낮아도 어느 항목이 부족한지가 달라, "
                  "필요한 도움이 서로 다를 수 있습니다.")
    save(fig, "02_도메인_히트맵.png")


# ── 3. 격차 추이 ─────────────────────────────────────────────
def fig_gap_trend(panels, cbi):
    """데이터가 있는 패널만 그린다(상권 자료가 없으면 인구 한 장만)."""
    t = cbi["ztype"]
    cands = []
    for d, col, ttl in ((panels["pop"], "pop", "인구"),
                        (panels["biz"], "active", "영업 중 사업체")):
        if d is None or not len(d) or col not in d.columns:
            continue
        d = d.dropna(subset=[col])
        if d.empty or d["year"].nunique() < 2:
            continue
        cands.append((d.assign(ztype=d.zone.map(t)), col, ttl))
    if not cands:
        return

    fig, axes = plt.subplots(1, len(cands), figsize=(6.6 * len(cands), 5.0),
                             squeeze=False)
    axes = axes[0]
    for ax, (d, col, ttl) in zip(axes, cands):
        ends = []
        for ty in TYPE_ORDER:
            sr = d[d.ztype == ty].groupby("year")[col].sum()
            if len(sr) < 2:
                continue
            v = sr / sr.loc[sr.index.min()] * 100
            ax.plot(v.index, v.values, lw=2.0, color=TYPE_COLOR[ty], zorder=3,
                    solid_capstyle="round")
            ax.scatter([v.index[-1]], [v.values[-1]], s=42, color=TYPE_COLOR[ty],
                       edgecolor=SURFACE, linewidth=2, zorder=4)
            ends.append((v.index[-1], float(v.values[-1]), ty))
        if ends:
            lo = min(e[1] for e in ends); hi = max(e[1] for e in ends)
            gap = max((hi - lo) * .075, 1.6)
            ys = spread([e[1] for e in ends], gap)
            for (xe, ye, ty), yl in zip(ends, ys):
                ax.annotate(f"{ty} {ye:.0f}", (xe, ye),
                            xytext=(xe + (hi - lo) * .004 + .35, yl),
                            va="center", fontsize=T_NOTE, color=INK_2,
                            arrowprops=dict(arrowstyle="-", color=AXIS, lw=.8,
                                            shrinkA=2, shrinkB=3)
                            if abs(yl - ye) > gap * .3 else None)
        ax.axhline(100, color=AXIS, ls=(0, (4, 3)), lw=1)
        base = int(d["year"].min())
        ax.set_title(f"{ttl} 추이 ({base}=100)", loc="left", fontsize=12.5, pad=10)
        ax.set_ylabel("지수"); ax.set_xlabel("연도")
        ax.margins(x=.22); _spines(ax, keep=("bottom",))
    fig.text(.007, 1.055, "권역유형별 궤적", fontsize=T_TITLE, fontweight="bold",
             color=INK, va="bottom", ha="left")
    fig.text(.007, 1.005, "시간이 갈수록 서로 다른 방향으로 갈라집니다",
             fontsize=T_SUB, color=INK_MUTE, va="bottom", ha="left")
    fig.subplots_adjust(wspace=.30)
    save(fig, "03_격차추이.png")


# ── 4. 조기경보 ─────────────────────────────────────────────
def fig_earlywarn(res, cbi):
    d = res.merge(cbi.reset_index()[["zone", "ztype"]], on="zone")
    fig, ax = plt.subplots(figsize=(8.8, 7.0))
    lim = (-4, 106)
    ax.fill_between(lim, lim, 106, color=ST_CRITICAL, alpha=.045, zorder=0)
    ax.plot(lim, lim, color=AXIS, ls=(0, (4, 3)), lw=1.1, zorder=1)
    for ty in TYPE_ORDER:
        s = d[d.ztype == ty]
        if not len(s):
            continue
        ax.scatter(s["risk"], s["risk_pred"], s=118, color=TYPE_COLOR[ty],
                   edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.text(4, 101, "위쪽 — 지금보다 나빠질 것으로 본 구간", color=ST_CRITICAL,
            fontsize=T_LABEL, fontweight="bold", va="top")
    rise = d.nlargest(5, "risk_delta").sort_values("risk_pred")
    placed = []
    for r in rise.itertuples():
        dy = 10
        while any(abs(r.risk - px) < 15 and abs(r.risk_pred + dy * .2 - py) < 6
                  for px, py in placed):
            dy += 14
        ax.annotate(f"{r.zone} +{r.risk_delta:.0f}", (r.risk, r.risk_pred),
                    textcoords="offset points", xytext=(11, dy), fontsize=T_LABEL,
                    fontweight="bold", color=INK,
                    arrowprops=dict(arrowstyle="-", color=AXIS, lw=.9,
                                    shrinkA=0, shrinkB=5))
        placed.append((r.risk, r.risk_pred + dy * .2))
    ax.set_xlim(*lim); ax.set_ylim(*lim)
    ax.set_xlabel("현재 쇠퇴위험도 (백분위)"); ax.set_ylabel("3년 후 예측 위험도 (백분위)")
    title(ax, "미리 살펴보기 — 지금보다 나빠질 수 있는 곳",
          "대각선 위쪽에 있을수록 앞으로 살펴볼 필요가 큽니다")
    legend(ax, set(d["ztype"]), loc="lower right")
    _spines(ax)
    save(fig, "04_조기경보.png")


# ── 5. SHAP ─────────────────────────────────────────────────
def fig_shap(glob, L, res):
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.8),
                             gridspec_kw={"width_ratios": [1, 1.32], "wspace": .34})
    nm = lambda i: INDICATORS[i][1] if i in INDICATORS else _FEAT_KO.get(i, i)
    g = glob.head(9).sort_values()
    for i, (k, v) in enumerate(g.items()):
        hbar(axes[0], i, v, TYPE_COLOR["원도심"], h=.58)
        axes[0].text(v * 1.03, i, f"{v:.1f}", va="center", fontsize=T_NOTE, color=INK_2)
    axes[0].set_yticks(range(len(g)), [nm(i) for i in g.index])
    axes[0].set_xlim(0, g.max() * 1.16); axes[0].set_ylim(-.7, len(g) - .3)
    axes[0].set_xlabel("평균 |SHAP|"); axes[0].grid(axis="y", visible=False)
    _spines(axes[0])
    axes[0].set_title("어떤 항목이 변화를 설명하는가", loc="left", fontsize=12.5, pad=10)

    top = res.nlargest(8, "risk_pred")["zone"].tolist()
    cols = glob.head(8).index.tolist()
    M = L.loc[[z for z in top if z in L.index], cols]
    M.columns = [nm(c) for c in cols]
    v = np.abs(M.values).max() or 1
    im = axes[1].imshow(M.values, cmap=DIV_CMAP, aspect="auto", vmin=-v, vmax=v)
    axes[1].set_xticks(range(M.shape[1]), M.columns, rotation=32, ha="right", fontsize=T_NOTE)
    axes[1].set_yticks(range(M.shape[0]), M.index, fontsize=T_TICK)
    axes[1].set_xticks(np.arange(-.5, M.shape[1], 1), minor=True)
    axes[1].set_yticks(np.arange(-.5, M.shape[0], 1), minor=True)
    axes[1].grid(which="minor", color=SURFACE, linewidth=2.2)
    axes[1].tick_params(which="minor", length=0); axes[1].grid(which="major", visible=False)
    for s in axes[1].spines.values():
        s.set_visible(False)
    colorbar(fig, im, axes[1], "SHAP 기여도", shrink=.82)
    axes[1].set_title("위험 상위 생활권의 요인 분해  (붉을수록 위험을 끌어올린 항목)",
                      loc="left", fontsize=12.5, pad=10)
    note(fig, "→ 같은 '고위험'이라도 원인이 달라, 동네마다 필요한 도움이 다를 수 있습니다.")
    save(fig, "05_SHAP_요인분해.png")


_FEAT_KO = {"pop": "인구 규모", "pop_yoy": "전년 대비 인구증감",
            "pop_3y": "3년 인구증감률", "risk": "현재 위험도",
            "aging_ratio_y": "고령 비율", "youth_ratio_y": "청년 비율",
            "aging_trend": "고령화 진행 속도", "pop_density": "인구 밀도",
            "active": "사업체 수", "closure_rate": "폐업률",
            "biz_per_1k": "인구천명당 사업체", "net_entry": "상권 순증감",
            "open_rate": "개업률", "biz_yoy": "전년 대비 사업체",
            "biz_3y": "3년 사업체 증감", "soc_access": "생활SOC 접근성",
            "soc_per_capita": "인구당 생활SOC", "vacancy_rate": "빈집률",
            "old_building": "노후 건물 비율", "transit_density": "정류장 밀도"}


# ── 6. 생활SOC 사각지대 ──────────────────────────────────────
def fig_soc_gap(cbi):
    fig, ax = plt.subplots(figsize=(9.6, 6.8))
    xm, ym = cbi["soc_access"].median(), cbi["aging_ratio"].median()
    ax.axvspan(-3, xm, ymin=0, ymax=1, color=ST_CRITICAL, alpha=.035, zorder=0)
    ax.axvline(xm, color=AXIS, ls=(0, (4, 3)), lw=1)
    ax.axhline(ym, color=AXIS, ls=(0, (4, 3)), lw=1)
    for ty in TYPE_ORDER:
        s = cbi[cbi.ztype == ty]
        if not len(s):
            continue
        ax.scatter(s["soc_access"], s["aging_ratio"], s=np.sqrt(s["pop"]) * 2.6,
                   color=TYPE_COLOR[ty], alpha=.9, edgecolor=SURFACE,
                   linewidth=2, zorder=3)
    risk = cbi[(cbi.soc_access < xm) & (cbi.aging_ratio > ym)]
    ax.set_xlabel("생활SOC 접근성 점수 (중력모형, 0~100)")
    ax.set_ylabel("고령(65세+) 인구 비율 (%)")
    ax.set_xlim(-3, 106)
    title(ax, "생활SOC 사각지대",
          f"원의 크기는 인구 규모 · 왼쪽 위 음영은 먼저 살펴보면 좋을 곳"
          f"(고령 비율 높고 접근성 낮음) {len(risk)}곳")
    ax.figure.canvas.draw()
    lp = LabelPlacer(ax, pad=2.6, allow_lead=True)
    lp.reserve(*ax.transAxes.transform((.72, .70)), *ax.transAxes.transform((1., 1.)))
    for r in cbi.itertuples():
        lp.reserve_point(r.soc_access, r.aging_ratio, r_px=np.sqrt(r.pop) * .045 + 5)
    shown = 0
    for r in risk.sort_values("pop", ascending=False).itertuples():
        shown += lp.place(r.soc_access, r.aging_ratio, r.Index, size=T_NOTE,
                          color=INK, weight="bold")
    if shown < len(risk):
        note(fig, f"음영 구간 {len(risk)}곳 중 {shown}곳의 이름을 표시했습니다 "
                  "(겹치는 이름은 생략).")
    legend(ax, set(cbi["ztype"]), loc="upper right")
    _spines(ax)
    save(fig, "06_SOC_사각지대.png")


# ── 7. 투자 우선순위 지도 ────────────────────────────────────
def fig_site_map(R, points, cbi):
    fig, ax = plt.subplots(figsize=(10.6, 8.4))
    ax.scatter(points.lon, points.lat, s=4.5, color=GRID, zorder=1, label="기존 생활SOC")
    for z, (la, lo) in I.CENTROID.items():
        if z not in cbi.index:
            continue
        ax.scatter(lo, la, s=np.sqrt(cbi.loc[z, "pop"]) * 1.9,
                   color=TYPE_COLOR[cbi.loc[z, "ztype"]], alpha=.30,
                   edgecolor=SURFACE, linewidth=1.4, zorder=2)
    if len(R):
        ax.scatter(R.경도, R.위도, s=430, marker="*", color=ST_CRITICAL,
                   edgecolor=SURFACE, linewidth=1.8, zorder=4,
                   label="우선순위 제안 입지")
    ax.set_xlabel("경도"); ax.set_ylabel("위도")
    ax.set_aspect(1 / np.cos(np.radians(36.8)))
    la_all = [c[0] for z, c in I.CENTROID.items() if z in cbi.index]
    lo_all = [c[1] for z, c in I.CENTROID.items() if z in cbi.index]
    if len(R):
        la_all += list(R.위도); lo_all += list(R.경도)
    py_, px_ = (max(la_all) - min(la_all)) * .085, (max(lo_all) - min(lo_all)) * .085
    ax.set_xlim(min(lo_all) - px_ * 2.6, max(lo_all) + px_ * 2.2)
    ax.set_ylim(min(la_all) - py_ * 1.2, max(la_all) + py_ * 2.0)
    title(ax, "생활SOC 우선순위 입지 제안",
          "MCLP 탐욕 최적화 · 생활권당 최대 2개소 · 번호는 투자 순서")
    lg = ax.legend(loc="upper left", handlelength=1.1, borderpad=.7)
    for t in lg.get_texts():
        t.set_color(INK_2)
    _spines(ax)

    # 라벨은 겹치지 않는 것만 — 제안 입지가 있는 생활권을 우선 배치
    fig.canvas.draw()
    lp = LabelPlacer(ax, pad=3.4, allow_lead=True)
    lp.reserve(*ax.transAxes.transform((0, .84)),
               *ax.transAxes.transform((.34, 1.0)))          # 범례 영역
    site_zones = set(R["생활권"]) if len(R) else set()
    if len(R):
        for r in R.itertuples():
            lp.reserve_point(r.경도, r.위도, r_px=13)
            ax.annotate(f"{r.순위}", (r.경도, r.위도), fontsize=8.4,
                        fontweight="bold", color="white", ha="center",
                        va="center", zorder=5)
    order = sorted([z for z in I.CENTROID if z in cbi.index],
                   key=lambda z: (z not in site_zones, -cbi.loc[z, "pop"]))
    shown = 0
    for z in order:
        la, lo = I.CENTROID[z]
        lp.reserve_point(lo, la, r_px=np.sqrt(cbi.loc[z, "pop"]) * .05 + 5)
    for z in order:
        la, lo = I.CENTROID[z]
        w = "bold" if z in site_zones else "normal"
        c = INK if z in site_zones else INK_MUTE
        shown += lp.place(lo, la, z, size=8.8, color=c, weight=w)
    if shown < len(order):
        note(fig, f"생활권 {len(order)}곳 중 {shown}곳의 이름을 표시했습니다 — "
                  "도심부는 생활권이 밀집해 일부 이름을 생략했습니다. "
                  "전체 목록은 우선순위표를 참고해 주세요.")
    save(fig, "07_투자입지_지도.png")


# ── 8. 커버리지 곡선 ─────────────────────────────────────────
def fig_coverage(R):
    """
    이중 축(두 개의 y 스케일)은 쓰지 않는다. 두 계열 모두 단위가 %p 로 같지만
    크기 차이가 커서 한 축에 겹치면 막대가 읽히지 않으므로,
    x축을 공유하는 위·아래 두 패널(소형 다중)로 나눈다.
    """
    if not len(R):
        return
    x = R["순위"].values
    cum = R["누적커버리지개선률"].values
    each = R["커버리지개선률"].values

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.8, 6.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1.35, 1], "hspace": .16})

    # 위: 누적 개선
    ax1.set_ylim(0, cum.max() * 1.22)
    ax1.plot(x, cum, color=TYPE_COLOR["원도심"], lw=2.0, zorder=3, solid_capstyle="round")
    ax1.fill_between(x, cum, color=TYPE_COLOR["원도심"], alpha=.07, zorder=2)
    ax1.scatter(x, cum, s=46, color=TYPE_COLOR["원도심"], edgecolor=SURFACE,
                linewidth=2, zorder=4)
    for i in (0, len(x) // 2, len(x) - 1):
        ax1.annotate(f"+{cum[i]:.1f}%p", (x[i], cum[i]), textcoords="offset points",
                     xytext=(0, 14), fontsize=T_LABEL, color=INK,
                     fontweight="bold", ha="center")
    ax1.set_ylabel("누적 개선 (%p)")
    ax1.set_title("누적 — 여기까지 하면 이만큼", loc="left", fontsize=12, pad=8, color=INK_2)
    ax1.grid(axis="x", visible=False); _spines(ax1)

    # 아래: 개소별 개선
    ax2.set_ylim(0, each.max() * 1.30)
    for xi, yi in zip(x, each):
        vbar(ax2, xi, yi, TYPE_COLOR["신도심"], w=.62)
    for xi, yi in zip(x, each):
        ax2.text(xi, yi + each.max() * .07, f"{yi:.2f}", ha="center",
                 fontsize=T_NOTE - .5, color=INK_2)
    ax2.set_ylabel("개소별 개선 (%p)")
    ax2.set_title("개소별 — 한 곳을 더할 때마다 효과는 줄어듭니다",
                  loc="left", fontsize=12, pad=8, color=INK_2)
    ax2.set_xticks(x); ax2.set_xlim(x.min() - .8, x.max() + .8)
    ax2.set_xlabel("투자 순위 (예산 투입 순서)")
    ax2.grid(axis="x", visible=False); _spines(ax2, keep=("bottom",))

    fig.text(.007, 1.082, "한 곳씩 더할 때의 효과", fontsize=T_TITLE,
             fontweight="bold", color=INK, va="bottom", ha="left")
    fig.text(.007, 1.022, "한계효용 체감 곡선 — 어디서 멈춰도 근거가 남습니다",
             fontsize=T_SUB, color=INK_MUTE, va="bottom", ha="left")
    note(fig, f"상위 {len(R)}개소만 먼저 놓아도 취약수요 커버리지 "
              f"+{cum[-1]:.1f}%p, 새로 닿는 인구 약 {R['신규수혜인구'].sum():,}명.")
    save(fig, "08_커버리지_곡선.png")
