# -*- coding: utf-8 -*-
"""
제출용 압축파일을 만든다.

손으로 zip 을 만들면 파일명 인코딩 플래그가 빠져 한글 윈도우에서 폴더·파일
이름이 깨진다. 파이썬 zipfile 은 이름이 ASCII 가 아니면 UTF-8 플래그(bit 11)를
자동으로 세워 주므로, 압축은 반드시 이 스크립트로 만든다.

    python3 tools/make_submission.py
"""
from __future__ import annotations
import sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELIV = ROOT / "deliverables"
FIG = ROOT / "outputs" / "figures"
TAB = ROOT / "outputs" / "tables"

TEAM = "다시봄"
WORK = "천안 균형발전 나침반"
STEM = f"{TEAM}_{WORK}"                      # 폴더명 겸 zip 이름

README = f"""2026년 천안시 AI·데이터 기반 정책 아이디어 경진대회
지정과제 ③ 지역균형발전 · 응모분야 AI 모델 개발

팀명    {TEAM}
작품명  {WORK}

─────────────────────────────────────────────
[기획서] ... .pdf      데이터 분석 기획서 (23장) — 이 파일을 먼저 봐 주세요
[기획서] ... .pptx     동일 내용 편집 가능본
[시각화] 대시보드.html  브라우저로 열면 전체 분석을 한 화면에서 보실 수 있습니다
[시각화] 그림/          기획서에 쓰인 그림 원본 8장
[참고]  분석표/         산출 근거 표 (지표 원표·가중치·모델 성능·데이터 출처)
─────────────────────────────────────────────

※ 데이터 산출 원칙
  이 문서의 모든 수치는 공공데이터에서 계산된 값이며, 임의로 채워 넣거나
  만들어낸 값이 없습니다. 출처와 수집 시점은 기획서 '활용 데이터 명세' 장과
  '[참고] 분석표/00_데이터_출처.csv' 에 그대로 적혀 있습니다.

※ 기획서 21장에 용어 풀이가 있습니다.
  엔트로피 가중법·SHAP·MCLP 등 본문에 나오는 말을 한 줄씩 적어 두었습니다.
"""


def build() -> Path:
    pptx = DELIV / "기획서_천안균형발전나침반_CBC.pptx"
    pdf = DELIV / "기획서_천안균형발전나침반_CBC.pdf"
    html = DELIV / "dashboard.html"
    need = [pptx, pdf, html]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        sys.exit(f"먼저 python3 src/run_all.py 를 실행해 주세요 — 없는 파일: {', '.join(missing)}")

    items: list[tuple[Path, str]] = [
        (pdf,  f"{STEM}/[기획서] {STEM}.pdf"),
        (pptx, f"{STEM}/[기획서] {STEM}.pptx"),
        (html, f"{STEM}/[시각화] 대시보드.html"),
    ]
    items += [(p, f"{STEM}/[시각화] 그림/{p.name}") for p in sorted(FIG.glob("*.png"))]
    items += [(p, f"{STEM}/[참고] 분석표/{p.name}") for p in sorted(TAB.glob("*.csv"))
              if p.name != "00_데이터_출처.csv"]

    out = DELIV / f"{STEM}.zip"
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(f"{STEM}/README.txt", README)
        # 출처표는 실제로 쓴 자료만 — 안 쓴 자료를 줄로 남기지 않는다
        prov = TAB / "00_데이터_출처.csv"
        if prov.exists():
            import pandas as pd
            d = pd.read_csv(prov)
            d = d[d["상태"].isin(["REAL", "PARTIAL"])]
            z.writestr(f"{STEM}/[참고] 분석표/00_데이터_출처.csv",
                       d.to_csv(index=False, encoding="utf-8-sig"))
        for src, arc in items:
            z.write(src, arc)

    # 한글 이름이 깨지지 않는지(UTF-8 플래그) 확인하고 넘긴다
    with zipfile.ZipFile(out) as z:
        bad = [i.filename for i in z.infolist()
               if not i.filename.isascii() and not i.flag_bits & 0x800]
        if bad:
            sys.exit(f"파일명 UTF-8 플래그 누락: {bad[:3]}")
        n = len(z.infolist())
    print(f"    · {out.relative_to(ROOT)}  ({out.stat().st_size / 1024 / 1024:.1f} MB, {n}개 항목)")
    print("      한글 파일명 UTF-8 플래그 확인 완료 — 윈도우에서 이름이 깨지지 않습니다")
    return out


if __name__ == "__main__":
    build()
