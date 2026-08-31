# -*- coding: utf-8 -*-
"""기획서 PPTX 자동 생성 — outputs/ 의 실제 산출물 수치를 그대로 반영"""
from __future__ import annotations
import json, sys
from pathlib import Path
import pandas as pd
from pptx import Presentation
from pptx.util import Inches as In, Pt, Emu
from pptx.dml.color import RGBColor as C
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import TAB, FIG, DELIV

FONT = "맑은 고딕"
INK, MUTE, ACC = C(0x15, 0x1C, 0x26), C(0x5D, 0x68, 0x74), C(0xD6, 0x45, 0x45)
BLUE, GREEN, AMBER = C(0x2E, 0x7D, 0xD1), C(0x3E, 0x9B, 0x7C), C(0xC9, 0x8A, 0x1E)
LIGHT, LINE, WHITE = C(0xF5, 0xF7, 0xFA), C(0xE0, 0xE5, 0xEB), C(0xFF, 0xFF, 0xFF)
W, H, M = 13.333, 7.5, 0.72


def tb(sl, x, y, w, h, text, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT,
       line=1.35, space=0, font=FONT):
    s = sl.shapes.add_textbox(In(x), In(y), In(w), In(h))
    f = s.text_frame; f.word_wrap = True; f.margin_left = f.margin_right = 0
    f.margin_top = f.margin_bottom = 0
    for i, ln in enumerate(str(text).split("\n")):
        p = f.paragraphs[0] if i == 0 else f.add_paragraph()
        p.alignment = align; p.line_spacing = line
        if i: p.space_before = Pt(space)
        r = p.add_run(); r.text = ln
        r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        r.font.name = font
    return s


def rect(sl, x, y, w, h, fill=LIGHT, lc=None, radius=True):
    sh = sl.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        In(x), In(y), In(w), In(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if lc: sh.line.color.rgb = lc; sh.line.width = Pt(1)
    else:  sh.line.fill.background()
    sh.shadow.inherit = False
    if radius:
        try: sh.adjustments[0] = 0.06
        except Exception: pass
    sh.text_frame.text = ""
    return sh


def slide(prs, eyebrow=None, title=None, lede=None):
    sl = prs.slides.add_slide(prs.slide_layouts[6])
    y = 0.52
    if eyebrow:
        tb(sl, M, y, W - 2 * M, .3, eyebrow, 11.5, True, ACC); y += .36
    if title:
        tb(sl, M, y, W - 2 * M, .62, title, 27, True, INK, line=1.18); y += .78
    if lede:
        tb(sl, M, y, W - 2 * M, .45, lede, 13.5, False, MUTE, line=1.45)
    return sl


def pic(sl, name, x, y, w=None, h=None):
    p = FIG / name
    if not p.exists(): return None
    return sl.shapes.add_picture(str(p), In(x), In(y),
                                 In(w) if w else None, In(h) if h else None)


def fit(sl, name, x, y, bw, bh):
    """박스 (bw×bh) 안에 비율 유지하며 가운데 배치"""
    from PIL import Image
    p = FIG / name
    if not p.exists(): return
    try:
        iw, ih = Image.open(p).size; ar = iw / ih
    except Exception:
        ar = 1.5
    w, h = bw, bw / ar
    if h > bh: h, w = bh, bh * ar
    sl.shapes.add_picture(str(p), In(x + (bw - w) / 2), In(y + (bh - h) / 2), In(w), In(h))


def bullets(sl, x, y, w, items, size=13.5, gap=.42, marker="▪"):
    """항목 높이를 누적해 배치한다(줄 수가 다른 본문이 겹치지 않도록)."""
    yy = y
    for head, body in items:
        tb(sl, x, yy, .25, .3, marker, size, True, ACC)
        tb(sl, x + .3, yy, w - .3, .28, head, size, True, INK)
        h = .3
        if body:
            bs = size - 1.5
            lines = sum(max(1, int(len(ln) * bs / ((w - .3) * 72) * 1.02) + 1)
                        for ln in body.split("\n"))
            bh = lines * bs * 1.42 * 1.06 / 72
            tb(sl, x + .3, yy + .3, w - .3, bh, body, bs, False, MUTE, line=1.42)
            h += bh
        yy += h + gap * .38


def kpi_card(sl, x, y, w, h, lab, val, sub, accent=ACC, vsize=24):
    h = max(h, 1.34)                       # 라벨+값(24pt)+부제 2줄이 들어갈 최소 높이
    rect(sl, x, y, w, h, WHITE, LINE)
    rect(sl, x, y, .075, h, accent, radius=False)
    tb(sl, x + .28, y + .16, w - .5, .22, lab, 10.5, True, MUTE)
    tb(sl, x + .28, y + .42, w - .5, .40, val, vsize, True, INK)
    tb(sl, x + .28, y + .92, w - .5, .38, sub, 10, False, MUTE, line=1.32)


def tablette(sl, df, x, y, w, colw=None, size=10.5, maxrows=10, head_bg=LIGHT,
             rh=.335):
    df = df.head(maxrows)
    nr, nc = len(df) + 1, len(df.columns)
    t = sl.shapes.add_table(nr, nc, In(x), In(y), In(w), In(rh * nr)).table
    if colw:
        tot = sum(colw)
        for i, c in enumerate(colw):
            t.columns[i].width = Emu(int(In(w) * c / tot))
    for j, cname in enumerate(df.columns):
        cell = t.cell(0, j); cell.text = str(cname)
        cell.fill.solid(); cell.fill.fore_color.rgb = head_bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.runs[0]; r.font.size = Pt(size); r.font.bold = True
        r.font.color.rgb = INK; r.font.name = FONT
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            cell = t.cell(i, j); cell.text = str(v)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if j else PP_ALIGN.LEFT
            r = p.runs[0]; r.font.size = Pt(size - .5)
            r.font.color.rgb = INK; r.font.name = FONT
    for i in range(nr):
        t.rows[i].height = In(rh)
    return t


def footer(sl, n, txt="천안 균형발전 나침반(CBC)"):
    tb(sl, M, H - .46, 6, .3, txt, 9.5, False, MUTE)
    tb(sl, W - M - 1, H - .46, 1, .3, str(n), 9.5, False, MUTE, align=PP_ALIGN.RIGHT)


def build(team="○○팀", members="홍길동"):
    S = json.loads((TAB / "09_요약지표.json").read_text(encoding="utf-8"))
    prov = pd.read_csv(TAB / "00_데이터_출처.csv")
    cbi  = pd.read_csv(TAB / "02_CBI_균형발전지수.csv")
    _ewp = TAB / "04_쇠퇴조기경보_예측.csv"
    ew   = pd.read_csv(_ewp) if _ewp.exists() else pd.DataFrame(
        columns=["zone", "risk", "risk_pred", "risk_delta"])
    sites = pd.read_csv(TAB / "08_생활SOC_투자우선순위.csv")
    real = S["전체실데이터"]

    prs = Presentation()
    prs.slide_width, prs.slide_height = In(W), In(H)
    n = 0

    # ══ 1. 표지 ══════════════════════════════════════════════
    sl = prs.slides.add_slide(prs.slide_layouts[6])
    rect(sl, 0, 0, W, H, C(0x11, 0x18, 0x22), radius=False)
    rect(sl, 0, 0, .13, H, ACC, radius=False)
    tb(sl, 1.15, 1.55, 11, .35, "2026년 천안시 AI·데이터 기반 정책 아이디어 경진대회",
       13, True, C(0xE0, 0x8A, 0x8A))
    tb(sl, 1.15, 2.08, 11.2, .95, "천안 균형발전 나침반", 54, True, WHITE, line=1.1)
    tb(sl, 1.15, 3.12, 11.2, .5, "Cheonan Balance Compass", 20, False,
       C(0x8A, 0x97, 0xA8))
    rect(sl, 1.15, 3.85, 5.6, .045, ACC, radius=False)
    tb(sl, 1.15, 4.12, 11, 1.0,
       "원도심 쇠퇴를 3년 먼저 경보하고,\n생활SOC 예산의 투입 순서를 정하는 AI",
       23, True, C(0xE9, 0xED, 0xF2), line=1.35)
    for i, (lab, val) in enumerate([("지정과제", "③ 지역균형발전"),
                                    ("응모분야", "AI 모델 개발"),
                                    ("분석단위", f"{S['생활권수']}개 생활권 · 지표 {S['지표수']}종")]):
        x = 1.15 + i * 3.55
        tb(sl, x, 5.72, 3.3, .25, lab, 10.5, True, C(0x6E, 0x7B, 0x8C))
        tb(sl, x, 6.0, 3.3, .3, val, 14, True, WHITE)
    tb(sl, 1.15, 6.72, 5.4, .3, f"{team} · {members}", 12, False, C(0x8A, 0x97, 0xA8))
    if not real:
        tb(sl, W - M - 5.2, 6.72, 5.2, .3,
           "※ 일부 지표 예시 데이터 — 실데이터 재실행 후 제출", 10, True, AMBER,
           align=PP_ALIGN.RIGHT)

    # ══ 2. 한 장 요약 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "EXECUTIVE SUMMARY", "한 장으로 보는 제안",
               "천안의 이중격차를 진단하고, 다음에 무너질 곳을 예측하며, 예산 투입 순서를 정한다.")
    cards = [("격차 배율", f'{S["격차배율"]}배', f'신도심 {S["신도심_CBI"]} vs 원도심 {S["원도심_CBI"]}', ACC),
             ("불균등도(지니)", f'{S["지니계수"]}', f'{S["생활권수"]}개 생활권 CBI 기준', AMBER),
             ("조기경보 정확도",
              f'R² {S["모델_R2"]}' if S.get("예측엔진", True) else "데이터 대기",
              f'베이스라인 대비 MAE {S["MAE_개선율"]}%↓' if S.get("예측엔진", True)
              else "다른 연도 인구 파일 투입 시 활성화", BLUE),
             ("투자 수혜", f'{S["신규수혜인구"]:,}명', f'{S["추천입지수"]}개소 · 커버리지 +{S["커버리지개선"]}%p', GREEN)]
    for i, (a, b, c, col) in enumerate(cards):
        kpi_card(sl, M + i * 3.06, 2.26, 2.86, 1.40, a, b, c, col, vsize=22)
    cols = [("문제", "한 도시 안의 이중격차",
             "서북부 신도심은 팽창하는데 동남부 원도심은 비어간다.\n"
             "그런데 재생·SOC 사업지 선정은 여전히 정성평가와\n사후 대응에 의존한다."),
            ("해법", "진단 → 예측 → 처방 3-엔진",
             "12개 지표를 엔트로피 가중으로 합성해 격차를 계량하고,\n"
             "LightGBM으로 3년 후 쇠퇴를 경보하며,\n"
             "MCLP 최적화로 투자 우선순위를 산출한다."),
            ("성과", "예산 집행 근거가 되는 산출물",
             f"생활권별 CBI·쇠퇴단계, 3년 후 위험도와 SHAP 요인분해,\n"
             f"{S['추천입지수']}개소 투자 순위표. 모두 스크립트 한 줄로 재현된다.")]
    for i, (tag, head, body) in enumerate(cols):
        x = M + i * 4.09
        rect(sl, x, 4.02, 3.89, 2.62, WHITE, LINE)
        rect(sl, x, 4.02, 3.89, .075, [ACC, BLUE, GREEN][i], radius=False)
        tb(sl, x + .28, 4.28, 3.3, .25, tag, 11, True, [ACC, BLUE, GREEN][i])
        tb(sl, x + .28, 4.58, 3.35, .5, head, 15.5, True, INK, line=1.25)
        tb(sl, x + .28, 5.24, 3.35, 1.3, body, 11.5, False, MUTE, line=1.5)
    footer(sl, n)

    # ══ 3. 문제 정의 ═════════════════════════════════════════
    n += 1
    sl = slide(prs, "PROBLEM", "천안은 한 도시 안에 두 개의 시간이 흐른다",
               "수도권 전철·KTX와 산업단지를 축으로 서북부가 팽창하는 사이, 동남부 원도심과 농촌면은 반대로 움직였다.")
    lo = cbi.nsmallest(5, "CBI")[["zone", "CBI"]]
    hi = cbi.nlargest(3, "CBI")[["zone", "CBI"]]
    rect(sl, M, 2.42, 6.0, 3.9, WHITE, LINE)
    tb(sl, M + .32, 2.66, 5.4, .3, "데이터가 말하는 격차", 14.5, True, INK)
    facts = [(f'{S["격차배율"]}배', f'신도심 평균 CBI {S["신도심_CBI"]} vs 원도심 평균 {S["원도심_CBI"]}'),
             (f'{S["지니계수"]}', f'25개 생활권 CBI 지니계수 — 변동계수 {S["변동계수"]}%'),
             (f'{S["최고"].split()[0]} ↔ {S["최저"].split()[0]}',
              f'최상위 {S["최고"].split()[1]}점 ↔ 최하위 {S["최저"].split()[1]}점, 같은 시(市)'),
             (f'{len(cbi[cbi.stage == "쇠퇴"])}개 생활권', '군집분석상 이미 "쇠퇴" 단계로 분류')]
    for i, (big, small) in enumerate(facts):
        y = 3.12 + i * .78
        tb(sl, M + .32, y, 2.55, .38, big, 19, True, ACC)
        tb(sl, M + .32, y + .38, 5.4, .3, small, 11.5, False, MUTE, line=1.35)
    rect(sl, M + 6.35, 2.42, 5.55, 3.9, LIGHT)
    tb(sl, M + 6.65, 2.66, 5, .3, "왜 지금 개입해야 하는가", 14.5, True, INK)
    bullets(sl, M + 6.65, 3.14, 4.95, [
        ("쇠퇴는 임계점을 넘으면 되돌리기 어렵다",
         "상권이 비면 유동인구가 줄고, 그래서 더 비는 자기강화 고리가 작동한다.\n"
         "이미 무너진 뒤 투입하는 예산은 같은 돈으로 훨씬 적은 효과를 낸다."),
        ("현행 선정 방식은 이 시점을 못 잡는다",
         "민원·정성평가는 '이미 나빠진 곳'을 뒤늦게 가리킨다.\n"
         "필요한 것은 아직 안 나빠졌지만 곧 나빠질 곳을 찾는 선행지표다."),
        ("천안은 그 실험에 가장 적합한 도시다",
         "신도심·기성시가지·원도심·읍·농촌면이 한 시(市) 안에 모두 있어\n"
         "유형별 처방을 동시에 검증할 수 있다."),
    ], size=12.5, gap=.44)
    footer(sl, n)

    # ══ 4. 기존 접근의 한계 ═══════════════════════════════════
    n += 1
    sl = slide(prs, "GAP", "무엇을 바꾸는가",
               "아이디어의 핵심은 새로운 데이터가 아니라, 의사결정의 네 가지 지점을 바꾸는 것이다.")
    comp = pd.DataFrame({
        "의사결정 지점": ["사업지 선정 근거", "개입 시점", "예산 배분", "설명 책임"],
        "현행 방식": ["정성평가·민원·경험", "쇠퇴가 확정된 뒤 사후 대응",
                    "지역별 총액 안분", "선정 사유를 사후 서술"],
        "CBC 제안": [f"{S['지표수']}개 지표 엔트로피 가중 정량지수",
                    "3년 선행 쇠퇴 경보(조기 개입)",
                    "한계효용 기반 투입 순서 산출",
                    "SHAP 요인분해로 근거 자동 생성"]})
    tablette(sl, comp, M, 2.62, W - 2 * M, colw=[1.5, 2.4, 2.9], size=13, maxrows=4)
    rect(sl, M, 4.62, W - 2 * M, 1.5, LIGHT)
    tb(sl, M + .35, 4.86, 11.4, .32,
       "핵심 주장 — 우리는 '더 많은 데이터'가 아니라 '같은 데이터로 더 이른 시점에, 순서를 매겨' 쓰자고 제안한다.",
       15, True, INK)
    tb(sl, M + .35, 5.32, 11.4, .7,
       "천안시가 이미 접근 가능한 공공데이터만으로 세 가지 산출물(격차지수·조기경보·투자순위표)을 만들 수 있다.\n"
       "추가 데이터 구매나 신규 센서 설치 없이, 스크립트 한 줄로 매년 갱신되는 상시 진단체계가 된다.",
       12.5, False, MUTE, line=1.5)
    footer(sl, n)

    # ══ 5. 아키텍처 ══════════════════════════════════════════
    n += 1
    sl = slide(prs, "ARCHITECTURE", "3-엔진 파이프라인",
               "공공데이터 입력부터 정책 산출물까지 단일 스크립트로 연결된다.")
    stages = [("INPUT", "공공데이터", "주민등록 인구\nLOCALDATA 인허가\n상가정보·생활SOC\n빈집·버스정류장", MUTE),
              ("① DIAGNOSE", "진단 엔진", "엔트로피 가중 CBI\nK-means 유형화\n5대 도메인 분해", ACC),
              ("② PREDICT", "예측 엔진", "LightGBM 회귀\nLeave-One-Zone-Out CV\nSHAP 요인분해", BLUE),
              ("③ PRESCRIBE", "처방 엔진", "MCLP 탐욕 최적화\n형평성 제약\n한계효용 곡선", GREEN),
              ("OUTPUT", "정책 산출물", "생활권 CBI 지도\n3년 후 위험 경보\n투자 우선순위표", INK)]
    bw, gap = 2.24, .28
    for i, (tag, head, body, col) in enumerate(stages):
        x = M + i * (bw + gap)
        rect(sl, x, 2.66, bw, 2.55, WHITE, LINE)
        rect(sl, x, 2.66, bw, .075, col, radius=False)
        tb(sl, x + .2, 2.88, bw - .35, .25, tag, 9.5, True, col)
        tb(sl, x + .2, 3.18, bw - .35, .32, head, 14.5, True, INK)
        tb(sl, x + .2, 3.62, bw - .35, 1.4, body, 11, False, MUTE, line=1.55)
        if i < 4:
            tb(sl, x + bw + .02, 3.72, .26, .3, "▶", 13, True, C(0xB8, 0xC0, 0xCA))
    rect(sl, M, 5.52, W - 2 * M, .95, LIGHT)
    tb(sl, M + .35, 5.74, 11.4, .55,
       "설계 원칙 ① 재현성 — 모든 단계가 공개 스크립트(`python3 src/run_all.py`)로 동일 재현\n"
       "설계 원칙 ② 정직성 — 실데이터/예시데이터 상태를 로그·산출물에 항상 표기해 오인 제출을 차단",
       12.5, False, INK, line=1.55)
    footer(sl, n)

    # ══ 6. 활용 데이터 명세 ═══════════════════════════════════
    n += 1
    sl = slide(prs, "DATA", "활용 데이터 명세",
               "전부 정식 공공 포털에서 합법적으로 내려받은 파일이며, 개인식별정보를 포함하지 않는다.")
    ds = pd.DataFrame({
        "데이터셋": ["주민등록 인구통계(연령별)", "지방행정 인허가데이터", "소상공인 상가(상권)정보",
                  "생활SOC 표준데이터 6종", "빈집 통계", "버스정류소 현황"],
        "제공기관": ["행정안전부", "행정안전부", "소상공인시장진흥공단",
                  "공공데이터포털", "통계청 / 한국부동산원", "천안시"],
        "출처 URL": ["jumin.mois.go.kr", "localdata.go.kr", "data.go.kr",
                   "data.go.kr", "kosis.kr / emptyhomes.kr", "cheonan.go.kr"],
        "주요 컬럼": ["행정구역, 총인구수, 연령대별 인구", "인허가일자, 폐업일자, 영업상태명, 소재지주소, 업태",
                   "상권업종분류, 행정동명, 위경도", "시설명, 소재지주소, 위경도",
                   "시군구, 빈집수, 빈집사유", "정류소명, 소재지"],
        "산출 지표": ["인구증감률·청년비율·고령비율", "상권 순증감·폐업률·업종다양성",
                   "사업체밀도·생활편의시설", "생활SOC 접근성·인구당 SOC수",
                   "빈집률", "정류장 밀도"]})
    tablette(sl, ds, M, 2.52, W - 2 * M, colw=[2.0, 1.3, 1.5, 2.6, 2.2], size=10.5, maxrows=6)
    tb(sl, M, 4.86, W - 2 * M, .3, "수집 시점 및 데이터 상태", 13.5, True, INK)
    pv = prov.copy()
    pv["상태"] = pv["상태"].map({"REAL": "실데이터", "ILLUSTRATIVE": "예시(미투입)"})
    tablette(sl, pv[["지표군", "상태", "출처", "비고"]], M, 5.2, W - 2 * M,
             colw=[1.1, 1.3, 3.4, 3.4], size=10, maxrows=6)
    footer(sl, n)

    # ══ 7. 공간단위 설계 ═════════════════════════════════════
    n += 1
    sl = slide(prs, "METHOD · 01", "분석 공간단위를 25개 '생활권'으로 재설계한 이유",
               "데이터마다 공간 키가 달라서 생기는 오차를, 지표를 만들기 전에 먼저 제거했다.")
    rect(sl, M, 2.55, 5.75, 1.72, C(0xFD, 0xF2, 0xF2))
    tb(sl, M + .3, 2.78, 5.2, .3, "문제 — 공간 키 불일치", 13.5, True, ACC)
    tb(sl, M + .3, 3.16, 5.2, 1.0,
       "· 주민등록 인구통계는 행정동 기준 (성정1동 / 성정2동)\n"
       "· 인허가·상가정보는 주소 문자열 = 법정동 기준 (성정동 하나)\n"
       "· 주소만으로는 성정동 점포를 1동·2동으로 나눌 근거가 없다",
       11.5, False, INK, line=1.6)
    rect(sl, M + 6.1, 2.55, 5.8, 1.72, C(0xF0, 0xF7, 0xF2))
    tb(sl, M + 6.4, 2.78, 5.2, .3, "해결 — 1:1 대응이 되는 수준까지 통합", 13.5, True, GREEN)
    tb(sl, M + 6.4, 3.16, 5.2, 1.0,
       "· 성정1·2동 → 성정동 / 쌍용1·2·3동 → 쌍용동\n"
       "· 원성1·2동 → 원성동 / 불당1·2동 → 불당동 / 부성1·2동 → 부성동\n"
       "· 결과: 31개 행정동 → 분석 가능한 25개 생활권",
       11.5, False, INK, line=1.6)
    tb(sl, M, 4.55, W - 2 * M, .3,
       "왜 이 단계가 중요한가 — 생태학적 오류(ecological fallacy)의 사전 차단", 14, True, INK)
    tb(sl, M, 4.92, W - 2 * M, .78,
       "공간 키가 다른 데이터를 억지로 맞추려면 인구 비례 안분 같은 가정이 필요한데, 그 가정이 틀리면 지표 전체가 조용히 오염된다.\n"
       "격차 분석은 '어느 동이 더 나쁜가'를 다투는 작업이라 배분 오차가 곧 결론의 오차가 된다. 정밀도를 조금 포기하는 대신 "
       "배분 가정을 아예 쓰지 않는 쪽을 택했다.",
       12, False, MUTE, line=1.5)
    grp = cbi.groupby("ztype")["zone"].apply(lambda s: ", ".join(s.head(6))).reset_index()
    grp.columns = ["권역유형", "소속 생활권"]
    tablette(sl, grp, M, 5.62, W - 2 * M, colw=[1.2, 6.0], size=9.5, maxrows=5, rh=.30)
    footer(sl, n)

    n = _part2(prs, S, cbi, ew, sites, prov, n)
    return prs, S, cbi, ew, sites, prov, n


def _part2(prs, S, cbi, ew, sites, prov, n):
    mode_xsec = S.get("모델_모드") == "cross-section"

    # ══ 8. 진단 방법론 ═══════════════════════════════════════
    n += 1
    sl = slide(prs, "METHOD · 02", "진단 엔진 — 엔트로피 가중 균형발전지수(CBI)",
               "가중치를 연구자가 정하지 않는다. 데이터의 변별력에서 가중치를 유도한다.")
    doms = [("인구활력", "5년 인구증감률 · 청년비율 · 고령비율", ACC),
            ("경제활력", "인구천명당 사업체수 · 상권 순증감 · 폐업률 · 업종 다양성", AMBER),
            ("생활SOC", "생활SOC 접근성(중력모형) · 인구천명당 SOC수", BLUE),
            ("주거", "빈집 추정률 · 노후(30년+) 건물 비율", GREEN),
            ("이동성", "km²당 버스정류장 수", C(0x8A, 0x7F, 0xB5))]
    tb(sl, M, 2.5, 6.1, .3, f"5대 도메인 · {S['지표수']}개 지표", 14, True, INK)
    for i, (d, ind, col) in enumerate(doms):
        y = 2.92 + i * .62
        rect(sl, M, y, .075, .48, col, radius=False)
        tb(sl, M + .24, y + .02, 1.3, .28, d, 12.5, True, INK)
        tb(sl, M + 1.66, y + .04, 4.35, .42, ind, 10.5, False, MUTE, line=1.35)
    rect(sl, M + 6.35, 2.5, 5.55, 3.55, LIGHT)
    tb(sl, M + 6.65, 2.74, 5, .3, "왜 엔트로피 가중법인가", 14, True, INK)
    tb(sl, M + 6.65, 3.14, 5, .6,
       "pⱼ = zⱼ / Σzⱼ    eⱼ = −k·Σ pⱼ ln pⱼ    wⱼ ∝ (1 − eⱼ)",
       12.5, True, ACC, line=1.4, font="Consolas")
    tb(sl, M + 6.65, 3.72, 5, 2.1,
       "생활권 간 차이를 잘 벌리는 지표일수록(=엔트로피가 낮을수록) 큰 가중치를 받는다.\n\n"
       "· 전문가 설문·AHP 방식과 달리 사람이 개입하지 않아 누가 돌려도 같은 값이 나온다\n"
       "· 지표가 추가·제외돼도 가중치가 자동 재배분되어 지수가 계속 유효하다\n"
       "· 심사·감사 과정에서 '왜 이 가중치인가'를 수식 한 줄로 답할 수 있다",
       11.5, False, MUTE, line=1.55)
    rect(sl, M, 6.12, W - 2 * M, .78, C(0xF0, 0xF7, 0xF2))
    tb(sl, M + .3, 6.32, 11.5, .45,
       "정직성 장치 — 데이터가 없어 산출 불가한 지표는 임의값으로 채우지 않고 지수에서 제외하며,\n"
       "제외 사실을 로그와 산출물에 남긴다. 결측을 평균으로 메워 순위를 왜곡하는 흔한 실수를 구조적으로 막는다.",
       11.5, False, INK, line=1.5)
    footer(sl, n)

    # ══ 9. 진단 결과 ═════════════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 01", "진단 결과 — 25개 생활권 CBI",
               f"최상위 {S['최고']}점, 최하위 {S['최저']}점. 같은 시(市) 안의 격차다.")
    fit(sl, "01_CBI_랭킹.png", M, 2.28, 7.0, 4.5)
    x = M + 7.3
    kpi_card(sl, x, 2.32, 4.55, 1.34, "신도심 ↔ 원도심 격차",
             f'{S["격차배율"]}배', f'{S["신도심_CBI"]} vs {S["원도심_CBI"]}', ACC)
    kpi_card(sl, x, 3.76, 4.55, 1.34, "CBI 지니계수",
             f'{S["지니계수"]}', f'변동계수 {S["변동계수"]}%', AMBER)
    kpi_card(sl, x, 5.20, 4.55, 1.34, "군집 유형화",
             f'{S["군집수"]}개 유형', f'실루엣 계수 {S["실루엣"]}', BLUE)
    tb(sl, x, 6.62, 4.55, .32,
       "쇠퇴단계는 CBI 순위가 아니라 다차원 패턴으로 분류된다.",
       10, False, MUTE, line=1.35)
    footer(sl, n)

    # ══ 10. 핵심 인사이트 ════════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 02", "핵심 발견 — 같은 '낙후'인데 처방은 정반대여야 한다",
               "원도심과 농촌면은 CBI가 모두 낮다. 그런데 도메인을 뜯어보면 원인이 완전히 다르다.")
    fit(sl, "02_도메인_히트맵.png", M, 2.36, 7.35, 3.5)
    x = M + 7.65
    rect(sl, x, 2.36, 4.2, 1.72, C(0xFD, 0xF2, 0xF2))
    tb(sl, x + .26, 2.58, 3.7, .28, "원도심", 13.5, True, ACC)
    tb(sl, x + .26, 2.92, 3.7, 1.05,
       "생활SOC는 이미 갖췄다.\n무너진 건 경제활력과 인구활력이다.\n"
       "→ 시설을 더 짓는 게 아니라, 비어 있는 공간을 다시 쓰게 만드는 처방",
       11, False, INK, line=1.5)
    rect(sl, x, 4.22, 4.2, 1.72, C(0xF3, 0xF0, 0xF9))
    tb(sl, x + .26, 4.44, 3.7, .28, "농촌면 · 읍지역", 13.5, True, C(0x6B, 0x5F, 0x9E))
    tb(sl, x + .26, 4.78, 3.7, 1.05,
       "생활SOC 자체가 없다.\n이동성 점수는 사실상 바닥이다.\n"
       "→ 거점 복합 SOC 신설과 수요응답형 교통 연계가 먼저",
       11, False, INK, line=1.5)
    rect(sl, M, 6.08, W - 2 * M, .82, LIGHT)
    tb(sl, M + .3, 6.28, 11.5, .5,
       "정책적 함의 — 현행처럼 '낙후지역'을 한 덩어리로 묶어 같은 사업을 배분하면, 두 지역 모두에서 예산이 헛돈다.\n"
       "CBC는 낙후의 유형을 구분해 주므로, 같은 예산으로 각각에 맞는 사업을 고를 수 있다.",
       12, False, INK, line=1.5)
    footer(sl, n)

    # ══ 11. 격차 추이 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 03", "격차는 수렴하지 않고 벌어지고 있다",
               "권역유형별 인구·사업체 궤적이 시간이 갈수록 분기한다. 개입하지 않으면 자동으로 좁혀지지 않는다.")
    fit(sl, "03_격차추이.png", M, 2.5, W - 2 * M, 3.5)
    rect(sl, M, 6.18, W - 2 * M, .78, C(0xFD, 0xF2, 0xF2))
    tb(sl, M + .3, 6.38, 11.5, .45,
       "이 그림이 조기경보 엔진의 출발점이다 — 추세가 이미 갈라졌다면, 다음에 갈라질 곳도 지금의 구조에서 읽어낼 수 있다.",
       12.5, True, INK, line=1.5)
    footer(sl, n)

    # ══ 12. 예측 설계 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "MODEL", "예측 엔진 — 쇠퇴 조기경보",
               "'이미 나빠진 곳'이 아니라 '곧 나빠질 곳'을 찾는 것이 이 모델의 목적이다.")
    left = [("문제 정의",
             "t년 시점에 관측 가능한 정보만으로 t+3년 쇠퇴위험도를 예측한다.\n"
             "예산 편성이 1년, 사업 착수가 1~2년 걸리므로 3년은 실제 개입 가능한 최소 선행폭이다."),
            ("모델", "LightGBM 회귀 — 지표 수 대비 표본이 적어 규제를 강하게 걸고 얕은 트리를 쓴다."),
            ("검증 — Leave-One-Zone-Out CV",
             "같은 생활권이 학습·검증에 동시에 들어가지 않게 한다. 공간 자기상관 탓에\n"
             "무작위 분할은 성능을 부풀리는데, 이를 원천 차단한 설계다."),
            ("해석 — SHAP",
             "생활권마다 위험을 밀어올린 요인을 분해한다. 모델 출력이 곧 근거 문서가 된다.")]
    bullets(sl, M, 2.5, 6.3, left, size=12, gap=.38)
    rect(sl, M + 6.75, 2.55, 5.15, 3.6, WHITE, LINE)
    tb(sl, M + 7.05, 2.8, 4.5, .3, "성능 (현재 데이터 기준)", 13.5, True, INK)
    _ok = S.get("예측엔진", True)
    perf = [("검증 방식", "Leave-One-Zone-Out CV"),
            ("모드", "횡단면(구조지표→인구유출)" if mode_xsec else "패널 t → t+3"),
            ("R²", f'{S["모델_R2"]}' if _ok else "— (데이터 대기)"),
            ("MAE", f'{S["모델_MAE"]}' if _ok else "—"),
            ("베이스라인 대비", f'MAE {S["MAE_개선율"]}% 개선' if _ok else "—")]
    for i, (k, v) in enumerate(perf):
        y = 3.24 + i * .48
        tb(sl, M + 7.05, y, 2.0, .3, k, 11.5, False, MUTE)
        tb(sl, M + 9.15, y, 2.5, .3, v, 12, True, INK)
    tb(sl, M + 7.05, 5.72, 4.5, .35,
       "베이스라인은 '현 상태가 그대로 간다'는 가정. 이를 이겨야 예측 가치가 있다.",
       10.5, False, MUTE, line=1.4)
    rect(sl, M, 6.32, W - 2 * M, .62, LIGHT)
    tb(sl, M + .3, 6.48, 11.5, .35,
       "데이터 상황에 따라 모드가 자동 전환된다 — 개·폐업 시계열이 확보되면 패널 예측(t→t+3)으로, "
       "없으면 구조지표 횡단면 모드로 돌아간다.", 11.5, False, INK, line=1.45)
    footer(sl, n)

    # ══ 13. 예측 결과 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 04", "예측 결과 — 다음 3년, 어디를 봐야 하는가",
               "대각선 위쪽은 현재보다 위험이 더 올라갈 것으로 예측된 생활권이다.")
    fit(sl, "04_조기경보.png", M, 2.3, 5.6, 4.35)
    fit(sl, "05_SHAP_요인분해.png", M + 5.8, 2.3, 6.1, 3.1)
    if not len(ew):
        rect(sl, M + 5.8, 5.5, 6.1, .9, C(0xFD, 0xF8, 0xEC))
        tb(sl, M + 6.05, 5.68, 5.6, .55,
           "예측 엔진 미실행 — " + S.get("예측미실행사유", ""), 10.5, False, INK, line=1.4)
        footer(sl, n); return _part3(prs, S, cbi, ew, sites, prov, n)
    e = ew.head(6).copy()
    e["risk"] = e["risk"].round(0).astype(int); e["risk_pred"] = e["risk_pred"].round(0).astype(int)
    e["risk_delta"] = e["risk_delta"].round(0).astype(int).map(lambda v: f"{v:+d}")
    e.columns = ["생활권", "현재", "3년 후", "변화"]
    tablette(sl, e, M + 5.8, 5.5, 6.1, colw=[2.2, 1.2, 1.2, 1.2], size=10, maxrows=6)
    footer(sl, n)
    return _part3(prs, S, cbi, ew, sites, prov, n)


def _part3(prs, S, cbi, ew, sites, prov, n):

    # ══ 14. 처방 설계 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "MODEL", "처방 엔진 — 생활SOC 투자 우선순위 최적화",
               "'얼마를 줄 것인가'가 아니라 '어디부터 지을 것인가'를 푼다.")
    tb(sl, M, 2.5, 6.2, .3, "MCLP — 최대커버링 입지문제", 14, True, INK)
    tb(sl, M, 2.88, 6.2, .5,
       "max  Σ  dᵢ · yᵢ      s.t.  yᵢ ≤ Σ xⱼ ,  Σ xⱼ = p\n"
       "        i∈수요격자                    j∈Nᵢ",
       12, True, ACC, line=1.5, font="Consolas")
    bullets(sl, M, 3.52, 6.2, [
        ("수요 dᵢ — 취약가중 인구",
         "격자 인구에 고령화율과 CBI 열위를 가중한다. 같은 1명이라도 취약지역의 1명을 더 크게 센다."),
        ("커버 Nᵢ — 반경 1.0km",
         "도보 15분권. '15분 도시' 개념과 맞추고 행정경계를 넘는 이용도 반영한다."),
        ("후보지 xⱼ — 빈집·노후 밀집 격자",
         "새 땅을 사는 대신 이미 비어 있는 공간을 후보로 둔다. 도시재생 사업과 바로 접속된다."),
        ("탐욕 근사의 보장",
         "submodular 목적함수이므로 탐욕해가 최적해의 (1−1/e)≈63% 이상을 보장한다."),
    ], size=11.5, gap=.38)
    rect(sl, M + 6.65, 2.5, 5.25, 3.05, C(0xF0, 0xF7, 0xF2))
    tb(sl, M + 6.95, 2.74, 4.7, .3, "형평성 제약을 넣은 이유", 13.5, True, GREEN)
    tb(sl, M + 6.95, 3.14, 4.7, 2.2,
       "순수 MCLP는 커버 효율이 가장 높은 한 지역에 예산을 몰아준다. 수학적으로는 옳지만 "
       "'균형발전' 사업으로는 성립하지 않는다.\n\n"
       "그래서 생활권당 최대 2개소 제약을 걸었다. 총 커버리지는 조금 줄지만, "
       "예산이 여러 생활권에 분산되어 실제 집행 가능한 안이 된다.\n\n"
       "제약 값은 파라미터라, 시 예산 규모에 맞춰 바로 조정할 수 있다.",
       11, False, INK, line=1.55)
    rect(sl, M + 6.65, 5.68, 5.25, 1.22, LIGHT)
    tb(sl, M + 6.95, 5.88, 4.7, .85,
       "산출물은 '순위 · 생활권 · 시설유형 · 신규 수혜인구 · 커버리지 개선폭'이 적힌 표 한 장이다.\n"
       "그대로 예산 요구서의 근거 자료가 된다.", 11, False, INK, line=1.5)
    footer(sl, n)

    # ══ 15. 처방 결과 ════════════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 05", "처방 결과 — 투자 우선순위",
               f"상위 {S['추천입지수']}개소 우선 투자 시 취약수요 커버리지 +{S['커버리지개선']}%p, "
               f"신규 수혜인구 약 {S['신규수혜인구']:,}명.")
    fit(sl, "07_투자입지_지도.png", M, 2.42, 5.3, 4.3)
    st = sites[["순위", "생활권", "시설유형", "신규수혜인구", "커버리지개선률"]].head(10).copy()
    st["신규수혜인구"] = st["신규수혜인구"].map("{:,}".format)
    st["커버리지개선률"] = st["커버리지개선률"].map(lambda v: f"+{v}%p")
    st.columns = ["순위", "생활권", "시설유형", "신규 수혜인구", "커버리지 개선"]
    tb(sl, M + 5.6, 2.42, 6.3, .3, "AI 추천 투자 순위 (상위 10)", 13.5, True, INK)
    tablette(sl, st, M + 5.6, 2.8, 6.3, colw=[.7, 1.4, 1.2, 1.6, 1.4], size=10, maxrows=10)
    footer(sl, n)

    # ══ 16. 예산 배분 곡선 ═══════════════════════════════════
    n += 1
    sl = slide(prs, "FINDING · 06", "어디서 멈춰도 근거가 남는다",
               "한계효용 체감 곡선이 있으면 예산이 깎여도 '몇 개소까지가 합리적인가'를 답할 수 있다.")
    fit(sl, "08_커버리지_곡선.png", M, 2.42, 7.2, 3.5)
    fit(sl, "06_SOC_사각지대.png", M + 7.5, 2.42, 4.4, 3.5)
    rect(sl, M, 6.1, W - 2 * M, .82, LIGHT)
    tb(sl, M + .3, 6.3, 11.5, .5,
       "실무적 가치 — 예산 심의에서 가장 자주 나오는 질문은 '이걸 왜 이 순서로 하느냐'와 '반만 하면 어떻게 되느냐'다.\n"
       "이 곡선은 두 질문에 동시에 답한다. 좌측 그림의 좌상단 영역(고령↑·SOC↓)이 최우선 사각지대다.",
       12, False, INK, line=1.5)
    footer(sl, n)

    # ══ 17. 정책 활용 시나리오 ═══════════════════════════════
    n += 1
    sl = slide(prs, "APPLICATION", "천안시는 이것을 어떻게 쓰는가",
               "연구 결과가 아니라 연간 행정 사이클에 얹히는 운영 도구로 설계했다.")
    users = [("도시재생 부서", "사업지 선정 · 공모 대응",
              "CBI 하위 생활권과 3년 후 고위험 생활권을 교차해 후보지를 추린다.\n"
              "국토부 도시재생 공모 신청서의 '쇠퇴도 진단' 항목에 그대로 인용 가능."),
             ("복지·보건 부서", "생활SOC 신설 입지 결정",
              "투자 우선순위표의 시설유형별 추천 좌표를 그대로 검토안으로 쓴다.\n"
              "'왜 이 동인가'를 SHAP 요인분해로 설명한다."),
             ("예산 부서", "배분 심의 근거",
              "한계효용 곡선으로 사업 규모별 기대효과를 비교한다.\n"
              "예산 삭감 시 어디까지 유지할지 판단 근거가 된다."),
             ("기획·감사", "정책 효과 사후검증",
              "매년 같은 스크립트를 돌려 CBI 변화를 추적한다.\n"
              "투입한 사업이 실제로 지수를 올렸는지 정량 확인한다.")]
    for i, (who, what, how) in enumerate(users):
        x = M + (i % 2) * 6.1
        y = 2.5 + (i // 2) * 1.72
        rect(sl, x, y, 5.75, 1.5, WHITE, LINE)
        rect(sl, x, y, .075, 1.5, [ACC, BLUE, GREEN, AMBER][i], radius=False)
        tb(sl, x + .28, y + .18, 2.4, .28, who, 12.5, True, [ACC, BLUE, GREEN, AMBER][i])
        tb(sl, x + .28, y + .5, 5.1, .28, what, 13.5, True, INK)
        tb(sl, x + .28, y + .84, 5.1, .6, how, 10.8, False, MUTE, line=1.45)
    rect(sl, M, 6.06, W - 2 * M, .86, C(0xF0, 0xF7, 0xF2))
    tb(sl, M + .3, 6.24, 11.5, .55,
       "운영 방식 — 연 1회 공공데이터를 갱신하고 스크립트를 실행하면 모든 산출물이 자동으로 재생성된다.\n"
       "별도 시스템 구축이나 데이터 구매 없이, 담당자 1명이 반나절이면 그 해의 진단을 끝낼 수 있다.",
       12, False, INK, line=1.5)
    footer(sl, n)

    # ══ 18. 기대효과 & 로드맵 ════════════════════════════════
    n += 1
    sl = slide(prs, "IMPACT", "기대효과와 실행 로드맵", None)
    tb(sl, M, 2.28, 6.0, .3, "기대효과", 14.5, True, INK)
    eff = [("예산 효율", "커버리지 기준 상위 지점부터 투입 — 같은 예산으로 더 많은 취약수요를 커버"),
           ("개입 시점", "쇠퇴 확정 후 대응 → 3년 선행 경보로 전환"),
           ("설명 책임", "선정 근거를 SHAP 요인분해로 문서화 — 감사·의회 대응 부담 감소"),
           ("행정 비용", "추가 데이터 구매·시스템 구축 없음 — 스크립트 재실행만으로 연간 갱신")]
    for i, (k, v) in enumerate(eff):
        y = 2.7 + i * .82
        rect(sl, M, y, .075, .62, ACC, radius=False)
        tb(sl, M + .24, y, 5.6, .28, k, 12.5, True, INK)
        tb(sl, M + .24, y + .3, 5.6, .4, v, 11, False, MUTE, line=1.4)
    tb(sl, M + 6.4, 2.28, 5.5, .3, "실행 로드맵", 14.5, True, INK)
    road = [("1단계 · 즉시", "본 스크립트로 천안시 25개 생활권 기준선 진단 확정", GREEN),
            ("2단계 · 3개월", "천안시 내부 행정데이터(인허가 원장·건축물대장·복지수급) 연계로 지표 정밀화", BLUE),
            ("3단계 · 6개월", "500m 격자 단위로 공간해상도 상향 — 표본 확대로 예측모델 성능 개선", AMBER),
            ("4단계 · 1년", "천안시 행정포털 대시보드 내재화, 연 1회 자동 갱신 체계 정착", ACC)]
    for i, (t_, d_, col) in enumerate(road):
        y = 2.7 + i * .82
        rect(sl, M + 6.4, y, .075, .62, col, radius=False)
        tb(sl, M + 6.64, y, 5.2, .28, t_, 12.5, True, col)
        tb(sl, M + 6.64, y + .3, 5.2, .4, d_, 11, False, MUTE, line=1.4)
    rect(sl, M, 6.02, W - 2 * M, .9, LIGHT)
    tb(sl, M + .3, 6.22, 11.5, .55,
       "확장 가능성 — 공간단위 정의(config.py)만 바꾸면 아산·청주 등 다른 도시에 그대로 적용된다.\n"
       "'구도심 공동화'는 천안만의 문제가 아니므로, 검증되면 충남 시군 공통 진단도구로 확장할 수 있다.",
       12, False, INK, line=1.5)
    footer(sl, n)

    # ══ 19. 한계와 보완 ══════════════════════════════════════
    n += 1
    sl = slide(prs, "LIMITATION", "알고 있는 한계와 보완 계획",
               "모델의 한계를 감추면 정책 도구로 쓸 수 없다. 무엇을 아직 못 하는지 먼저 밝힌다.")
    lim = [("표본 크기", f"분석 단위가 {S['생활권수']}개 생활권이라 머신러닝 표본으로는 작다.",
            "500m 격자 단위로 내리면 표본이 수천 개로 늘어난다. 현재는 규제를 강하게 걸고 "
            "Leave-One-Zone-Out CV와 베이스라인 비교로 과적합 여부를 확인하고 있다."),
           ("공간 해상도", "생활권 내부의 격차(같은 동 안의 편차)는 잡히지 않는다.",
            "집계구·격자 데이터로 전환하면 해결된다. 공간단위 정의만 교체하면 되도록 설계했다."),
           ("빈집 데이터 정밀도", "빈집 통계는 시군구 단위 공표가 많아 읍면동 배분에 가정이 들어간다.",
            "천안시 빈집실태조사 원자료를 연계하면 가정 없이 대체된다."),
           ("인과 아닌 상관", "본 모델은 쇠퇴를 예측할 뿐, 사업의 인과효과를 증명하지 않는다.",
            "사업 시행 전후 이중차분(DID) 설계를 붙이면 효과 검증까지 확장 가능하다.")]
    for i, (k, prob, fix) in enumerate(lim):
        y = 2.5 + i * 1.12
        rect(sl, M, y, W - 2 * M, .98, WHITE, LINE)
        rect(sl, M, y, .075, .98, AMBER, radius=False)
        tb(sl, M + .3, y + .14, 2.3, .28, k, 12.5, True, AMBER)
        tb(sl, M + 2.75, y + .14, 8.8, .28, prob, 12, True, INK)
        tb(sl, M + 2.75, y + .46, 8.8, .42, "→ " + fix, 10.8, False, MUTE, line=1.4)
    footer(sl, n)

    # ══ 20. 재현성·윤리 ══════════════════════════════════════
    n += 1
    sl = slide(prs, "INTEGRITY", "재현성과 데이터 윤리", None)
    boxes = [("재현성", GREEN, [
        "전 과정이 공개 스크립트로 실행 — `python3 src/run_all.py` 한 줄",
        "난수 시드 고정(20260831) — 군집·모델 결과가 실행마다 동일",
        "그림 8종·분석표 9종·대시보드가 같은 실행에서 함께 생성됨",
        "지표 정의·가중치·모델 파라미터가 전부 코드에 명시"]),
        ("데이터 윤리", BLUE, [
        "정식 공공데이터 포털에서 내려받은 파일만 사용 — 크롤링 없음",
        "상업 목적 민간데이터 무단 사용 없음",
        "전 지표가 생활권 단위 집계값 — 개인식별정보 미취급",
        "출처·수집시점·컬럼을 `00_데이터_출처.csv` 에 자동 기록"])]
    for i, (title_, col, items) in enumerate(boxes):
        x = M + i * 6.1
        rect(sl, x, 2.32, 5.75, 2.72, WHITE, LINE)
        rect(sl, x, 2.32, 5.75, .075, col, radius=False)
        tb(sl, x + .3, 2.56, 4.5, .3, title_, 14.5, True, col)
        for j, it in enumerate(items):
            tb(sl, x + .3, 3.0 + j * .52, .2, .28, "·", 13, True, col)
            tb(sl, x + .52, 3.0 + j * .52, 5.0, .45, it, 11, False, INK, line=1.4)
    rect(sl, M, 5.26, W - 2 * M, 1.15, C(0xFD, 0xF2, 0xF2))
    tb(sl, M + .32, 5.48, 11.4, .32, "실데이터 / 예시데이터 구분 장치", 13.5, True, ACC)
    tb(sl, M + .32, 5.84, 11.4, .5,
       "파이프라인은 각 지표가 실데이터인지 예시(illustrative) 값인지를 매 실행마다 판정해 로그·대시보드·본 기획서에 표기한다.\n"
       "예시 데이터를 실측치로 오인해 제출하는 사고를 막기 위한 장치이며, 실데이터를 넣으면 해당 표기가 자동으로 사라진다.",
       11.5, False, INK, line=1.5)
    tb(sl, M, 6.62, W - 2 * M, .3,
       f"현재 상태: 실데이터 지표 {S['실데이터지표']}"
       + ("  ·  전 지표 실데이터로 제출 가능" if S["전체실데이터"]
          else "  ·  제출 전 실데이터 투입 후 재실행 필요"),
       12, True, GREEN if S["전체실데이터"] else ACC)
    footer(sl, n)
    return n


def save(team="○○팀", members="홍길동"):
    prs, *_ = build(team, members)
    out = DELIV / "기획서_천안균형발전나침반_CBC.pptx"
    prs.save(str(out))
    print(f"    · {out.relative_to(DELIV.parent)}  ({out.stat().st_size / 1024:.0f} KB, "
          f"{len(prs.slides.__iter__.__self__._sldIdLst)}장)")
    return out
