# -*- coding: utf-8 -*-
"""
소상공인시장진흥공단 상가(상권)정보 ZIP에서 '천안시' 부분만 뽑아내는 도구

사용법
    python extract_cheonan_sangga.py "소상공인시장진흥공단_상가(상권)정보_20260630.zip"

    (인자를 안 주면 현재 폴더에서 '상가' 가 들어간 zip 을 알아서 찾습니다)

하는 일
    · 압축을 풀지 않고 ZIP 안에서 바로 읽습니다 (디스크 여유가 없어도 됩니다)
    · 전국 데이터 중 시군구명이 '천안'인 행만 남깁니다
    · 분석에 쓰는 8개 컬럼만 남겨 파일을 작게 만듭니다 (수십 MB → 수 MB)
    · 결과: 천안_상가정보.csv
"""
import sys, glob, zipfile, io, os

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas 가 필요합니다.  터미널에서:  pip install pandas")

WANT = ["상가업소번호", "상호명", "상권업종대분류명", "상권업종중분류명",
        "상권업종소분류명", "시군구명", "행정동명", "법정동명",
        "도로명주소", "경도", "위도"]
ENCODINGS = ("cp949", "utf-8-sig", "euc-kr", "utf-8")


def read_csv_bytes(raw: bytes) -> "pd.DataFrame | None":
    for enc in ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc,
                               low_memory=False, on_bad_lines="skip")
        except Exception:
            continue
    return None


def main():
    if len(sys.argv) > 1:
        zips = [sys.argv[1]]
    else:
        zips = [z for z in glob.glob("*.zip") if "상가" in z or "상권" in z]
        if not zips:
            sys.exit("상가정보 zip 을 찾지 못했습니다. 파일명을 인자로 넘겨주세요.\n"
                     '  예)  python extract_cheonan_sangga.py "소상공인..._20260630.zip"')
    zpath = zips[0]
    if not os.path.exists(zpath):
        sys.exit(f"파일이 없습니다: {zpath}")
    print(f"열기: {zpath}  ({os.path.getsize(zpath)/1e6:.0f} MB)\n")

    out, total = [], 0
    with zipfile.ZipFile(zpath) as z:
        members = [m for m in z.namelist() if m.lower().endswith(".csv")]
        if not members:
            sys.exit("zip 안에 csv 가 없습니다.")
        for i, m in enumerate(members, 1):
            name = os.path.basename(m)
            with z.open(m) as f:
                d = read_csv_bytes(f.read())
            if d is None or not len(d):
                print(f"  [{i}/{len(members)}] {name}  → 읽기 실패, 건너뜀")
                continue
            total += len(d)
            col = next((c for c in d.columns if "시군구명" in str(c)), None)
            if col is None:
                print(f"  [{i}/{len(members)}] {name}  → 시군구명 컬럼 없음, 건너뜀")
                continue
            sub = d[d[col].astype(str).str.contains("천안", na=False)]
            keep = [c for c in WANT if c in sub.columns] or list(sub.columns)
            if len(sub):
                out.append(sub[keep])
            print(f"  [{i}/{len(members)}] {name}  전체 {len(d):,}건 → 천안 {len(sub):,}건")

    if not out:
        sys.exit("\n천안시 행을 찾지 못했습니다. zip 이 맞는지 확인해 주세요.")

    res = pd.concat(out, ignore_index=True)
    dst = "천안_상가정보.csv"
    res.to_csv(dst, index=False, encoding="cp949")
    mb = os.path.getsize(dst) / 1e6
    print(f"\n완료  {dst}   {len(res):,}건 · {mb:.1f} MB · 컬럼 {len(res.columns)}개")
    print(f"전국 {total:,}건 중 천안 {len(res):,}건을 남겼습니다.")
    if "행정동명" in res.columns:
        print(f"행정동 {res['행정동명'].nunique()}개")
    if mb > 12:
        print("\n※ 파일이 조금 큽니다. 그래도 일단 올려주시면 제가 받아보겠습니다.")
    print("\n이 파일을 구글 드라이브의 천안시 대회 폴더에 올려주세요.")


if __name__ == "__main__":
    main()
