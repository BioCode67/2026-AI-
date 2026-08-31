# -*- coding: utf-8 -*-
"""단일 HTML 대시보드 생성 (이미지 base64 내장 → 파일 하나로 제출 가능)"""
from __future__ import annotations
import base64, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FIG, DELIV, DOMAINS, TYPE_COLOR

TITLE = "천안 균형발전 나침반(CBC)"
SUB = "천안시민 누구나 걸어서 닿는 생활환경을 바라며, 공공데이터로 살펴본 이야기"


def b64(name):
    p = FIG / name
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def img(name, cap=""):
    d = b64(name)
    if not d:
        return ""
    c = f'<figcaption>{cap}</figcaption>' if cap else ""
    return f'<figure><img src="data:image/png;base64,{d}" alt="{cap or name}">{c}</figure>'


def table(df, cls="", maxrows=30):
    d = df.head(maxrows)
    th = "".join(f"<th>{c}</th>" for c in d.columns)
    tr = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
                 for r in d.itertuples(index=False))
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def build(cbi, weights, res, shap_glob, sites, prov, S, gaps, panels):
    real = S["전체실데이터"]
    ok = S.get("예측엔진", True)
    badge = ('<span class="bdg ok">전 지표 실데이터</span>' if real else
             f'<span class="bdg warn">실데이터 지표군 {S["실데이터지표"]} · '
             '미확보 지표는 지수에서 제외</span>')
    synth = any(v == "ILLUSTRATIVE" for v in prov["상태"]) if len(prov) else False
    warn = "" if not synth else (
        '<div class="alert"><b>⚠ 데이터 상태 안내</b><br>'
        '아래 수치 중 일부는 공공데이터 미투입 구간을 <b>예시(illustrative)</b> 값으로 채운 결과입니다. '
        '<code>data/raw/</code> 에 실제 CSV를 넣고 <code>python3 src/run_all.py</code> 를 다시 실행하면 '
        '전 항목이 실데이터로 자동 갱신됩니다. <b>제출 전 반드시 실데이터로 재생성하세요.</b></div>')

    _ = ok
    kpi = [("격차 배율", f'{S["격차배율"]}배', f'신도심 {S["신도심_CBI"]} vs 원도심 {S["원도심_CBI"]}'),
           ("지니계수", f'{S["지니계수"]}', "25개 생활권 CBI 불균등도"),
           ("조기경보 방향 적중률",
            (f'{S["방향적중률"]:.0f}%' if S.get("방향적중률") == S.get("방향적중률") else "—")
            if ok else "데이터 대기",
            f'베이스라인 대비 MAE {S["MAE_개선율"]:+.1f}%' if ok else "인구 파일 필요"),
           ("추천 투자 수혜",
            f'{S["신규수혜인구"]:,}명' if S.get("처방엔진", True) else "데이터 대기",
            (f'{S["추천입지수"]}개소 · 커버리지 +{S["커버리지개선"]}%p'
             if S.get("처방엔진", True) else "생활SOC 위치 자료 필요"))]
    kpis = "".join(f'<div class="kpi"><span class="lab">{a}</span>'
                   f'<span class="val">{b}</span><span class="sub">{c}</span></div>'
                   for a, b, c in kpi)

    rank = cbi.reset_index()[["zone", "gu", "ztype", "CBI", "stage"]].copy()
    rank["CBI"] = rank["CBI"].round(1)
    rank.columns = ["생활권", "자치구", "권역유형", "CBI", "쇠퇴단계"]

    ok = S.get("예측엔진", True)
    if ok and res is not None and len(res):
        ew = res.copy().round(1)
        ew.columns = ["생활권", "현재 위험도", "3년 후 예측", "변화"]
        ew = ew.head(10)
    else:
        ew = pd.DataFrame({"안내": [S.get("예측미실행사유", "예측 엔진 미실행")]})

    w = weights.rename("가중치").to_frame()
    from config import INDICATORS
    w["도메인"] = [INDICATORS[i][0] for i in w.index]
    w["지표"] = [INDICATORS[i][1] for i in w.index]
    w["가중치"] = (w["가중치"] * 100).round(1).astype(str) + "%"
    w = w.sort_values("가중치", ascending=False)[["도메인", "지표", "가중치"]]

    cols = ["순위", "생활권", "시설유형", "신규수혜인구", "커버리지개선률", "빈집률", "CBI"]
    st = sites[[c for c in cols if c in sites.columns]].copy() if len(sites) else pd.DataFrame()
    if len(st):
        st["신규수혜인구"] = st["신규수혜인구"].map("{:,}".format)

    html = f"""<title>{TITLE}</title>
<style>
:root{{--bg:#F7F8FA;--card:#FFFFFF;--ink:#151C26;--mute:#5D6874;--line:#E3E7ED;
 --accent:#D64545;--blue:#2E7DD1;--green:#3E9B7C;--amber:#C98A1E;--shadow:0 1px 3px rgba(20,30,45,.07),0 8px 24px rgba(20,30,45,.05)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0F1419;--card:#171D25;--ink:#E9EDF2;
 --mute:#98A3B0;--line:#252D38;--accent:#F0736F;--blue:#6BA9E8;--green:#5FBF9C;--amber:#E0AB4A;
 --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3)}}}}
:root[data-theme="dark"]{{--bg:#0F1419;--card:#171D25;--ink:#E9EDF2;--mute:#98A3B0;--line:#252D38;
 --accent:#F0736F;--blue:#6BA9E8;--green:#5FBF9C;--amber:#E0AB4A;
 --shadow:0 1px 3px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.3)}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);margin:0;
 font:15px/1.65 -apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
.wrap{{max-width:1120px;margin:0 auto;padding:40px 22px 80px}}
header{{margin-bottom:30px}}
.eyebrow{{color:var(--accent);font-size:12.5px;font-weight:700;letter-spacing:.11em;text-transform:uppercase}}
h1{{font-size:clamp(27px,4.4vw,40px);line-height:1.2;margin:8px 0 6px;letter-spacing:-.02em}}
.sub{{color:var(--mute);font-size:17px;margin-bottom:14px}}
.bdg{{display:inline-block;padding:5px 13px;border-radius:999px;font-size:12.5px;font-weight:700}}
.bdg.ok{{background:rgba(27,175,122,.14);color:var(--green)}}
.bdg.warn{{background:rgba(250,178,25,.16);color:var(--warn)}}
.alert{{background:rgba(250,178,25,.10);border-left:3px solid var(--warn);
 padding:14px 18px;border-radius:8px;margin:20px 0;font-size:14px;line-height:1.7}}
.alert code{{background:rgba(125,135,150,.16);padding:1px 6px;border-radius:4px;font-size:12.5px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px;margin:26px 0 8px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:18px 20px;
 box-shadow:var(--shadow);display:flex;flex-direction:column;gap:3px}}
.kpi .lab{{font-size:12.5px;color:var(--mute);font-weight:600}}
.kpi .val{{font-size:29px;font-weight:800;letter-spacing:-.02em;line-height:1.15;
 font-variant-numeric:tabular-nums}}
.kpi .sub{{font-size:12.5px;color:var(--mute)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:15px;
 padding:28px 30px;margin:22px 0;box-shadow:var(--shadow)}}
h2{{font-size:21px;margin:0 0 6px;letter-spacing:-.015em}}
h2 .n{{color:var(--accent);font-weight:800;margin-right:9px;font-variant-numeric:tabular-nums}}
.lede{{color:var(--mute);font-size:14.5px;margin:0 0 20px}}
h3{{font-size:15.5px;margin:26px 0 10px;color:var(--ink)}}
figure{{margin:18px 0 6px}} figure img{{width:100%;border-radius:10px;border:1px solid var(--line);
 background:#fff}}
figcaption{{color:var(--mute);font-size:12.8px;margin-top:9px;text-align:center}}
.tw{{overflow-x:auto;margin:14px 0}}
table{{border-collapse:collapse;width:100%;font-size:13.4px;min-width:440px}}
th{{background:rgba(125,135,150,.09);text-align:left;padding:9px 12px;
 font-weight:700;border-bottom:2px solid var(--line);white-space:nowrap}}
td{{padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap;
 font-variant-numeric:tabular-nums}}
tbody tr:hover{{background:rgba(125,135,150,.055)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:26px}}
@media(max-width:760px){{.two{{grid-template-columns:1fr}}}}
.note{{background:rgba(42,120,214,.075);border-left:3px solid var(--blue);
 padding:13px 17px;border-radius:8px;font-size:13.6px;line-height:1.7;margin:16px 0}}
footer{{color:var(--mute);font-size:12.6px;margin-top:38px;padding-top:22px;border-top:1px solid var(--line)}}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">2026 천안시 AI·데이터 기반 정책 아이디어 경진대회 · 지역균형발전 · AI 모델 개발</div>
  <h1>{TITLE}</h1>
  <div class="sub">{SUB}</div>
  {badge}
</header>
{warn}
<div class="kpis">{kpis}</div>

<section>
  <h2><span class="n">01</span>살펴보기 — 지금 어느 정도 차이가 있을까요</h2>
  <p class="lede">25개 생활권 × 12개 지표를 <b>엔트로피 가중법</b>으로 합쳐 지수를 만들었습니다.
  가중치를 저희가 임의로 정하지 않고 데이터에서 유도했기 때문에, 누가 다시 돌려도 같은 값이 나옵니다.</p>
  {img("01_CBI_랭킹.png", "생활권별 CBI — 색상은 권역유형")}
  {img("02_도메인_히트맵.png", "권역유형 × 5대 도메인 — 낙후의 원인이 권역마다 다르다")}
  <div class="note"><b>이런 점이 보였습니다.</b> 원도심과 농촌면은 지수가 모두 낮게 나왔지만 <b>사정이 서로 달랐습니다</b>.
  원도심은 시설이 이미 갖춰져 있으나 상권과 인구가 어려웠고, 농촌면은 가까운 시설 자체가 부족했습니다.
  같은 '어려움'이라도 필요한 도움이 다를 수 있다는 뜻으로 읽었습니다. 어떤 사업이 맞을지는 현장을 아시는 분들의 판단이 필요한 부분입니다.</div>
  {img("03_격차추이.png", "권역유형별 인구·사업체 궤적")}
  <h3>생활권별 CBI 순위</h3>
  {table(rank, maxrows=25)}
</section>

<section>
  <h2><span class="n">02</span>미리 보기 — 앞으로 살펴보면 좋을 곳</h2>
  <p class="lede">t년 정보만으로 <b>t+3년 상황</b>을 살펴봅니다. 가까운 동네끼리는 닮아 있어 무작위로 나누면
  성능이 실제보다 좋아 보이므로, <b>Leave-One-Zone-Out CV</b>로 같은 생활권이 학습과 검증에 동시에 들어가지 않게 했습니다.</p>
  {img("04_조기경보.png", "현재 위험도 대비 3년 후 예측 — 대각선 위쪽이 악화 예상 구간")}
  {img("05_SHAP_요인분해.png", "SHAP 기반 전역 중요도 및 생활권별 쇠퇴요인 분해")}
  <div class="note"><b>이유까지 함께 보여드리는 까닭.</b> 숫자만 있으면 왜 그 동네인지 설명하기 어렵습니다.
  SHAP은 동네마다 어떤 항목이 결과를 끌어올렸는지 나누어 보여주므로, 검토하실 때 <b>근거로 함께 보실 수 있습니다</b>.</div>
  <div class="two">
    <div><h3>3년 후 고위험 상위 10</h3>{table(ew, maxrows=10)}</div>
    <div><h3>엔트로피 가중치</h3>{table(w, maxrows=12)}</div>
  </div>
</section>

<section>
  <h2><span class="n">03</span>순서 정하기 — 한 곳을 놓는다면 어디부터일까요</h2>
  <p class="lede">빈집·노후 밀집지를 유휴부지 후보로 두고, <b>MCLP(최대커버링입지문제)</b> 탐욕 최적화로
  "한 곳을 새로 놓았을 때 새로 닿는 분이 가장 많은 지점"을 순서대로 골랐습니다.
  계산만 그대로 두면 한 동네에 전부 몰리기 때문에, 생활권당 최대 2개소로 제한했습니다.</p>
  {img("06_SOC_사각지대.png", "고령인구 대비 생활SOC 접근성 — 좌상단이 최우선 사각지대")}
  {img("07_투자입지_지도.png", "AI 추천 신규 입지 (★) 와 기존 생활SOC 분포")}
  {img("08_커버리지_곡선.png", "투자 순위별 한계효용 — 어디서 멈춰도 근거가 남는다")}
  <h3>투자 우선순위</h3>
  {table(st, maxrows=20) if len(st) else ""}
</section>

<section>
  <h2><span class="n">04</span>활용 데이터 및 재현성</h2>
  <p class="lede">전 과정을 공개 스크립트로 재현하실 수 있습니다. <code>python3 src/run_all.py</code> 한 줄이면
  표·그림·대시보드가 똑같이 다시 만들어집니다.</p>
  {table(prov, maxrows=12)}
  <div class="note">정식 공공데이터 포털에서 합법적으로 내려받은 파일만 사용했습니다.
  크롤링이나 상업용 민간데이터는 쓰지 않았고, 개인을 식별할 수 있는 정보는 다루지 않았습니다
  (모든 지표가 생활권 단위 집계값입니다).</div>
</section>

<footer>
  2026년 천안시 AI·데이터 기반 정책 아이디어 경진대회 출품작 · 지역균형발전 부문 · AI 모델 개발<br>
  분석 단위 25개 생활권 · 지표 12종 · 군집 k={S['군집수']}(실루엣 {S['실루엣']}) ·
  조기경보 LOZO-CV R² {S['모델_R2']} · 재현 스크립트 <code>src/run_all.py</code>
</footer>
</div>"""
    out = DELIV / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"    · {out.relative_to(DELIV.parent)}  ({len(html) / 1024:.0f} KB)")
    return out
