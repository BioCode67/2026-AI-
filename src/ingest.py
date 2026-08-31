# -*- coding: utf-8 -*-
"""
데이터 적재 계층
──────────────────────────────────────────────────────────────
설계 원칙
 1. data/raw/ 에 실제 공공데이터 CSV가 있으면 그것을 쓴다  → status="REAL"
 2. 없으면 공개 통계로 보정한 '예시(illustrative)' 데이터를 생성한다 → status="ILLUSTRATIVE"
 3. 어떤 지표가 실데이터인지 항상 로그로 표시하고, 산출물에도 배지로 남긴다.
    (예시 데이터를 실데이터인 척 제출하는 것을 구조적으로 막기 위함)
"""
from __future__ import annotations
import re, sys, glob
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (RAW, ZONE_NAMES, ZONE_GU, ZONE_TYPE, BDONG_KEYS_SORTED,
                    BDONG2ZONE, HDONG_KEYS_SORTED, HDONG2ZONE, RANDOM_SEED,
                    STRICT)

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8", "latin1")
PROVENANCE: dict[str, dict] = {}      # 지표군 → {status, source, note, rows}
CITY_STATS: dict[str, float] = {}     # 생활권 비교엔 못 쓰지만 배경 서술에 쓰는 시 단위 수치


def log(msg): print(msg, flush=True)


def note(key, status, source, detail="", rows=0):
    PROVENANCE[key] = dict(status=status, source=source, detail=detail, rows=rows)
    badge = {"REAL": "\033[92m[REAL]\033[0m",
             "PARTIAL": "\033[96m[PARTIAL]\033[0m",
             "MISSING": "\033[90m[미확보]\033[0m"}.get(
                 status, "\033[93m[ILLUSTRATIVE]\033[0m")
    log(f"  {badge} {key:<14} {source} {('· ' + detail) if detail else ''}")


# ── 파일 IO ──────────────────────────────────────────────────
def read_any(path: Path) -> pd.DataFrame | None:
    """한국 공공데이터 CSV 인코딩 자동 판별 (cp949가 대부분)."""
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=enc, low_memory=False, on_bad_lines="skip")
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    for enc in ENCODINGS:                      # 탭/세미콜론 구분자 대비
        try:
            df = pd.read_csv(path, encoding=enc, sep=None, engine="python",
                             on_bad_lines="skip")
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    return None


def raw_files(stem: str) -> list[Path]:
    """`localdata_license.csv`, `localdata_license_1.csv` … 를 모두 수집."""
    pats = [f"{stem}.csv", f"{stem}_*.csv", f"{stem}*.csv",
            f"{stem}.CSV", f"{stem}*.xlsx"]
    out = []
    for p in pats:
        out += [Path(f) for f in glob.glob(str(RAW / p))]
    return sorted(set(out))


def load_stack(stem: str) -> pd.DataFrame | None:
    """같은 종류 파일 여러 개를 세로로 병합."""
    fs = raw_files(stem)
    if not fs:
        return None
    frames = []
    for f in fs:
        d = pd.read_excel(f) if f.suffix.lower() == ".xlsx" else read_any(f)
        if d is not None and len(d):
            frames.append(d)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def find_col(df: pd.DataFrame, *keywords, exclude=()) -> str | None:
    """컬럼명에 키워드가 포함된 첫 컬럼 반환 (공공데이터 컬럼명 변동 흡수)."""
    cols = [str(c) for c in df.columns]
    for kw in keywords:
        for c in cols:
            cc = c.replace(" ", "")
            if kw.replace(" ", "") in cc and not any(x in cc for x in exclude):
                return c
    return None


# ── 공간 매칭 ────────────────────────────────────────────────
def zone_from_address(addr) -> str | None:
    """'충청남도 천안시 동남구 신부동 123' → '신안동'"""
    if not isinstance(addr, str) or "천안" not in addr:
        return None
    for key in BDONG_KEYS_SORTED:
        if key in addr:
            return BDONG2ZONE[key]
    return None


def zone_from_hdong(name) -> str | None:
    """'천안시 동남구 원성1동' → '원성동'"""
    if not isinstance(name, str):
        return None
    for key in HDONG_KEYS_SORTED:
        if key in name:
            return HDONG2ZONE[key]
    for key in BDONG_KEYS_SORTED:
        if key in name:
            return BDONG2ZONE[key]
    return None


def only_cheonan(df: pd.DataFrame) -> pd.DataFrame:
    """
    천안시 행만 남긴다 — 생활권 매칭 **전에** 반드시 거쳐야 하는 단계.

    상가정보·표준데이터는 시도/전국 단위로 배포되는데, 행정동명 컬럼에는
    시군구가 없이 '중앙동'처럼 동 이름만 들어 있다. 그런데 중앙동·북면·동면·
    백석동·대흥동 같은 이름은 충남 다른 시군에도 존재하므로, 시군구를 먼저
    거르지 않으면 남의 동네 점포가 천안 지표에 섞여 들어간다.
    """
    for key in ("시군구명", "시군구", "행정구역", "소재지전체주소", "도로명주소",
                "소재지도로명주소", "소재지지번주소", "주소"):
        col = find_col(df, key)
        if col is not None:
            m = df[col].astype(str).str.contains("천안", na=False)
            if m.any():
                return df[m]
    return df                      # 시군구 정보가 아예 없으면 그대로 (경고는 호출부에서)


def base_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "zone": ZONE_NAMES,
        "gu":   [ZONE_GU[z] for z in ZONE_NAMES],
        "ztype": [ZONE_TYPE[z] for z in ZONE_NAMES],
    })


# ─────────────────────────────────────────────────────────────
#  예시(illustrative) 데이터 생성용 정성 프로파일
#  ※ 실측치가 아니라 '천안 원도심 공동화 / 서북부 신도심 성장'이라는
#    공지된 질적 사실을 재현하기 위한 가정값. 실데이터 투입 시 전부 대체됨.
# ─────────────────────────────────────────────────────────────
PROFILE = {  # zone: (인구규모k, 인구증감톤, 고령톤, 상권톤, SOC톤)
    "중앙동": (7,  -0.9, 0.95, -0.9, 0.55), "문성동": (13, -0.7, 0.75, -0.6, 0.45),
    "원성동": (22, -0.7, 0.80, -0.6, 0.40), "봉명동": (16, -0.5, 0.60, -0.3, 0.42),
    "일봉동": (22, -0.4, 0.55, -0.2, 0.48),
    "신방동": (35, -0.1, 0.30,  0.1, 0.60), "청룡동": (33,  0.0, 0.25,  0.2, 0.58),
    "신안동": (16, -0.2, 0.20,  0.3, 0.62), "성정동": (42, -0.3, 0.45, -0.1, 0.55),
    "쌍용동": (69, -0.3, 0.40,  0.0, 0.60),
    "백석동": (33,  0.4, 0.15,  0.5, 0.70), "불당동": (72,  0.9, 0.05,  0.9, 0.85),
    "부성동": (80,  0.8, 0.10,  0.7, 0.72),
    "목천읍": (19, -0.1, 0.50, -0.1, 0.30), "성환읍": (24, -0.4, 0.65, -0.4, 0.28),
    "성거읍": (18, -0.2, 0.55, -0.2, 0.26), "직산읍": (28,  0.1, 0.40,  0.1, 0.32),
    "병천면": (7,  -0.5, 0.80, -0.4, 0.18), "풍세면": (5,  -0.5, 0.85, -0.5, 0.12),
    "광덕면": (4,  -0.7, 0.95, -0.6, 0.08), "북면":   (4,  -0.6, 0.90, -0.6, 0.10),
    "성남면": (4,  -0.6, 0.88, -0.6, 0.10), "수신면": (3,  -0.7, 0.92, -0.7, 0.07),
    "동면":   (3,  -0.7, 0.93, -0.7, 0.07), "입장면": (8,  -0.4, 0.72, -0.3, 0.16),
}
AREA_KM2 = {  # 대략적 면적(km2) — 밀도 지표 분모용
    "중앙동": 1.4, "문성동": 2.1, "원성동": 3.0, "봉명동": 1.6, "일봉동": 3.4,
    "신방동": 4.2, "청룡동": 8.5, "신안동": 12.0, "성정동": 3.6, "쌍용동": 5.4,
    "백석동": 4.8, "불당동": 4.4, "부성동": 18.0, "목천읍": 62.0, "성환읍": 57.0,
    "성거읍": 34.0, "직산읍": 39.0, "병천면": 47.0, "풍세면": 34.0, "광덕면": 71.0,
    "북면": 62.0, "성남면": 34.0, "수신면": 27.0, "동면": 46.0, "입장면": 43.0,
}


# ═════════════════════════════════════════════════════════════
#  1) 인구  ─ 행정안전부 주민등록 인구통계 (읍면동·연령별)
# ═════════════════════════════════════════════════════════════
def load_population() -> tuple[pd.DataFrame, pd.DataFrame]:
    """returns (zone_now[pop, youth_ratio, aging_ratio, pop_growth_5y], year_panel[zone,year,pop])"""
    df = load_stack("pop_jumin")
    if df is not None:
        try:
            return _parse_population(df)
        except Exception as e:                       # 형식이 달라도 파이프라인은 계속
            log(f"    ! pop_jumin 파싱 실패({e}) → 예시 데이터로 대체")
    return _illustrative_population()


def _parse_population(df):
    """
    행안부 주민등록 '연령별 인구현황' 파서.
    실제 컬럼 형식: `2026년03월_계_총인구수`, `2026년03월_계_20~29세`, `..._남_...`, `..._여_...`
    주의점 세 가지를 명시적으로 처리한다.
      ① 계/남/여가 모두 들어 있으므로 **'계'만** 쓴다 (안 그러면 인구가 2배가 된다)
      ② 한 파일에 여러 달이 들어 있으므로 **연도별 최신 월**만 쓴다 (합산하면 개월 수만큼 부풀려진다)
      ③ 65세+ 구간이 없고 10세 단위이므로 70세+ 전량 + 60~69세의 1/2로 근사한다
    """
    region_col = find_col(df, "행정구역", "행정기관", "읍면동", "구분") or df.columns[0]
    df = df.copy()
    m = df[region_col].astype(str).str.contains("천안", na=False)
    if m.any():
        df = df[m]                        # 전국 파일이 들어와도 천안만 남긴다
    df["zone"] = df[region_col].map(zone_from_hdong)
    df = df[df["zone"].notna()]
    if not len(df):
        raise ValueError("천안시 읍면동을 한 건도 매칭하지 못함")

    def num(s):
        return pd.to_numeric(
            s.astype(str).str.replace(r"[,\s\"]", "", regex=True), errors="coerce").fillna(0)

    # 컬럼명 파싱 → (연, 월, 성별, 지표)
    PAT = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월[_\s]*(계|남|여)?[_\s]*(.+?)\s*$")
    parsed = {}
    for c in df.columns:
        m = PAT.match(str(c).strip().strip('"'))
        if m:
            y, mo, g, metric = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
            parsed[c] = (y, mo, g, metric.replace(" ", ""))
    if not parsed:                                   # 연·월 표기가 없는 단순 형식
        tot = find_col(df, "총인구수", "인구수")
        if tot is None:
            raise ValueError("총인구수 컬럼을 찾을 수 없음")
        g = df.assign(v=num(df[tot])).groupby("zone")["v"].sum()
        parsed_panel = pd.DataFrame({"zone": g.index, "year": 2025, "pop": g.values})
        return _finish_population(df, parsed_panel, {}, num, 2025)

    genders = {v[2] for v in parsed.values()}
    use_g = "계" if "계" in genders else None        # ①
    sel = {c: v for c, v in parsed.items() if v[2] == use_g}

    # ② 연도별 최신 (연,월)
    ym = sorted({(v[0], v[1]) for v in sel.values()})
    latest_of_year = {}
    for y, mo in ym:
        if y not in latest_of_year or mo > latest_of_year[y]:
            latest_of_year[y] = mo

    def year_agesum(y, mo, keys):
        tot = pd.Series(0.0, index=df.index)
        for c, v in sel.items():
            if v[0] == y and v[1] == mo and v[3] in keys:
                tot += num(df[c])
        return tot

    rows = []
    for y, mo in latest_of_year.items():
        cols = [c for c, v in sel.items() if v[0] == y and v[1] == mo and v[3] == "총인구수"]
        if not cols:
            continue
        yv = year_agesum(y, mo, {"20~29세", "30~39세"})
        ov = (year_agesum(y, mo, {"70~79세", "80~89세", "90~99세", "100세이상"})
              + 0.5 * year_agesum(y, mo, {"60~69세"}))
        g = df[["zone"]].assign(pop=num(df[cols[0]]).values,
                                youth=yv.values, old=ov.values) \
                        .groupby("zone")[["pop", "youth", "old"]].sum()
        for z, r in g.iterrows():
            rows.append({"zone": z, "year": y, "pop": r["pop"],
                         "youth_ratio_y": r["youth"] / r["pop"] * 100 if r["pop"] else np.nan,
                         "aging_ratio_y": r["old"] / r["pop"] * 100 if r["pop"] else np.nan})
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise ValueError("총인구수 컬럼을 연·월 기준으로 특정하지 못함")

    last = int(panel["year"].max())
    last_mo = latest_of_year[last]
    age_cols = {v[3]: c for c, v in sel.items() if v[0] == last and v[1] == last_mo}
    return _finish_population(df, panel, age_cols, num, last, f"{last}년{last_mo:02d}월")


def _finish_population(df, panel, age_cols, num, last, stamp=None):
    agg = {"pop": "sum"}
    for c in ("youth_ratio_y", "aging_ratio_y"):
        if c in panel.columns:
            agg[c] = "mean"
    panel = panel.groupby(["zone", "year"], as_index=False).agg(agg)
    cur = panel[panel.year == last].set_index("zone")["pop"]

    avail = sorted(int(y) for y in panel["year"].unique() if int(y) != last)
    if avail:
        base_y = min(avail, key=lambda y: abs(y - (last - 5)))
        base = panel[panel.year == base_y].set_index("zone")["pop"]
        span = max(last - base_y, 1)
        growth = ((cur / base.reindex(cur.index).replace(0, np.nan)).pow(5.0 / span) - 1) * 100
        span_txt = f"{base_y}~{last}년(5년환산)"
    else:
        base_y, growth = last, pd.Series(0.0, index=cur.index)
        span_txt = f"{last}년 단일시점"
        log("    ! 단일 연도만 수집됨 → 인구증감률 0 처리. "
            "다른 연도 파일을 data/raw/pop_jumin_2.csv 로 추가하면 자동 계산됩니다.")

    def agesum(keys):
        tot = pd.Series(0.0, index=df.index)
        for k in keys:
            c = age_cols.get(k)
            if c is not None:
                tot += num(df[c])
        return tot

    youth = agesum(["20~29세", "30~39세"])
    old   = agesum(["70~79세", "80~89세", "90~99세", "100세이상"]) + 0.5 * agesum(["60~69세"])  # ③
    totp  = agesum(["총인구수"])
    tmp = df[["zone"]].assign(youth=youth.values, old=old.values, tot=totp.values)
    agg = tmp.groupby("zone")[["youth", "old", "tot"]].sum()
    agg["tot"] = agg["tot"].replace(0, np.nan)

    out = base_frame().set_index("zone")
    out["pop"]           = cur
    out["youth_ratio"]   = agg["youth"] / agg["tot"] * 100
    out["aging_ratio"]   = agg["old"]   / agg["tot"] * 100
    out["pop_growth_5y"] = growth
    if out["youth_ratio"].isna().all():
        log("    ! 연령 구간 컬럼을 찾지 못해 청년·고령 비율을 산출하지 못했습니다.")
    note("인구", "REAL", "행안부 주민등록 인구통계(jumin.mois.go.kr)",
         f"{span_txt}, {panel.zone.nunique()}개 생활권"
         + (f", 연령기준 {stamp}" if stamp else ""), len(df))
    return out.reset_index(), panel


def _illustrative_population():
    if STRICT:
        out = base_frame()
        for c in ("pop", "youth_ratio", "aging_ratio", "pop_growth_5y"):
            out[c] = np.nan
        note("인구", "MISSING", "미확보",
             "data/raw/pop_jumin*.csv 를 넣으면 산출됩니다")
        return out, pd.DataFrame(columns=["zone", "year", "pop"])
    rng = np.random.default_rng(RANDOM_SEED)
    rows, panel = [], []
    for z, (pk, gtone, atone, _, _) in PROFILE.items():
        pop = pk * 1000
        g   = gtone * 6 + rng.normal(0, 1.2)
        rows.append(dict(zone=z, pop=pop,
                         youth_ratio=np.clip(30 - atone * 18 + rng.normal(0, 1.5), 6, 36),
                         aging_ratio=np.clip(9 + atone * 32 + rng.normal(0, 1.5), 8, 48),
                         pop_growth_5y=g))
        for i, y in enumerate(range(2018, 2026)):
            panel.append(dict(zone=z, year=y, pop=pop * (1 + g / 100) ** ((i - 7) / 5)))
    out = base_frame().merge(pd.DataFrame(rows), on="zone")
    note("인구", "ILLUSTRATIVE", "예시 생성(seed=%d)" % RANDOM_SEED,
         "data/raw/pop_jumin.csv 투입 시 자동 대체")
    return out, pd.DataFrame(panel)


# ═════════════════════════════════════════════════════════════
#  2) 상권  ─ LOCALDATA 지방행정 인허가 데이터
# ═════════════════════════════════════════════════════════════
def load_business() -> tuple[pd.DataFrame, pd.DataFrame]:
    """returns (zone_now[biz_density..], year_panel[zone,year,open,close,active])"""
    df = load_stack("localdata_license")
    if df is not None:
        try:
            return _parse_business(df)
        except Exception as e:
            log(f"    ! localdata_license 파싱 실패({e}) → 상가정보로 대체 시도")
    # LOCALDATA가 없어도 상가정보만으로 경제활력 지표 대부분을 복원한다.
    sg = load_stack("store_sangga")
    if sg is not None:
        try:
            return _business_from_sangga(sg)
        except Exception as e:
            log(f"    ! store_sangga 파싱 실패({e}) → 예시 데이터로 대체")
    return _illustrative_business()


def _business_from_sangga(sg):
    """
    소상공인 상가(상권)정보만으로 경제활력을 산출.
    · 확보: 사업체 수(active_biz) · 업종 다양성(Shannon)
    · 불가: 개·폐업 시계열이 없으므로 상권순증감/폐업률은 산출 불가 → NaN 으로 두고
            CBI 계산에서 자동 제외한다(있는 지표만으로 가중치를 다시 계산).
    """
    hd = find_col(sg, "행정동명")
    adr = find_col(sg, "도로명주소", "지번주소", "소재지")
    mid = find_col(sg, "상권업종중분류명", "상권업종대분류명", "표준산업분류명")
    n_all = len(sg)
    d = only_cheonan(sg).copy()          # ← 동 이름 매칭 전에 시군구부터 거른다
    if len(d) == n_all and find_col(sg, "시군구명") is None:
        log("    ! 시군구 컬럼이 없어 천안 선별을 건너뜁니다 — 다른 시군이 섞일 수 있습니다")
    if hd is not None:
        d["zone"] = d[hd].map(zone_from_hdong)
    if hd is None or d["zone"].notna().sum() == 0:
        if adr is None:
            raise ValueError("행정동명/주소 컬럼 없음")
        d["zone"] = d[adr].map(zone_from_address)
    d = d[d["zone"].notna()]
    if not len(d):
        raise ValueError("천안시 행정동을 한 건도 매칭하지 못함")

    out = base_frame().set_index("zone")
    out["active_biz"] = d.groupby("zone").size()
    out["active_biz"] = out["active_biz"].fillna(0)
    if mid is not None:
        div = {}
        for z, g in d.groupby("zone"):
            pr = g[mid].astype(str).value_counts(normalize=True).values
            div[z] = float(-(pr * np.log(pr + 1e-12)).sum())
        out["biz_diversity"] = pd.Series(div)
    else:
        out["biz_diversity"] = np.nan
    out["biz_net_growth"] = np.nan          # 시계열 부재 → CBI에서 자동 제외
    out["closure_rate"]   = np.nan

    yr = 2025
    panel = pd.DataFrame({"zone": out.index, "year": yr,
                          "opened": np.nan, "closed": np.nan,
                          "active": out["active_biz"].values})
    note("상권", "PARTIAL", "소상공인 상가(상권)정보(data.go.kr)",
         f"{len(d):,}건 매칭 / {d.zone.nunique()}개 생활권 · 개폐업 시계열 없음", len(d))
    return out.reset_index(), panel


def _parse_business(df):
    a1 = find_col(df, "소재지전체주소", "소재지주소", "지번주소")
    a2 = find_col(df, "도로명전체주소", "도로명주소")
    oc = find_col(df, "인허가일자", "인허가일")
    cc = find_col(df, "폐업일자", "폐업일")
    sc = find_col(df, "영업상태명", "상세영업상태명", "영업상태")
    kc = find_col(df, "업태구분명", "개방서비스명", "업종")
    if oc is None or (a1 is None and a2 is None):
        raise ValueError("인허가일자/주소 컬럼을 찾을 수 없음")

    d = df.copy()
    addr = d[a1].astype(str) if a1 else pd.Series("", index=d.index)
    if a2:
        addr = addr.where(addr.str.contains("천안", na=False), d[a2].astype(str))
    d["zone"] = addr.map(zone_from_address)
    d = d[d["zone"].notna()].copy()
    if not len(d):
        raise ValueError("천안시 주소를 한 건도 매칭하지 못함")

    todate = lambda s: pd.to_datetime(
        s.astype(str).str.replace(r"[^0-9]", "", regex=True).str[:8],
        format="%Y%m%d", errors="coerce")
    d["open_dt"]  = todate(d[oc])
    d["close_dt"] = todate(d[cc]) if cc else pd.NaT
    d["is_open"]  = (d[sc].astype(str).str.contains("영업|정상", na=False)
                     if sc else d["close_dt"].isna())
    d["kind"] = d[kc].astype(str) if kc else "기타"

    yrs = list(range(2015, 2026))
    rows = []
    for z, g in d.groupby("zone"):
        for y in yrs:
            op = int((g.open_dt.dt.year == y).sum())
            cl = int((g.close_dt.dt.year == y).sum())
            act = int(((g.open_dt.dt.year <= y) &
                       (g.close_dt.isna() | (g.close_dt.dt.year > y))).sum())
            rows.append(dict(zone=z, year=y, opened=op, closed=cl, active=act))
    panel = pd.DataFrame(rows)

    last = 2025
    cur = panel[panel.year == last].set_index("zone")
    prev = panel[panel.year == last - 3].set_index("zone")
    out = base_frame().set_index("zone")
    out["active_biz"]    = cur["active"]
    out["biz_net_growth"] = ((cur["active"] / prev["active"].replace(0, np.nan) - 1) * 100)
    recent = panel[panel.year.between(last - 2, last)].groupby("zone")[["opened", "closed"]].sum()
    out["closure_rate"]  = recent["closed"] / cur["active"].replace(0, np.nan) * 100

    # 업종 다양성 (Shannon entropy)
    alive = d[d.is_open]
    div = {}
    for z, g in alive.groupby("zone"):
        p = g["kind"].value_counts(normalize=True).values
        div[z] = float(-(p * np.log(p + 1e-12)).sum())
    out["biz_diversity"] = pd.Series(div)

    # 생존분석용 원자료
    surv = d[["zone", "open_dt", "close_dt", "is_open", "kind"]].copy()
    surv.to_parquet(RAW.parent / "processed" / "survival.parquet", index=False) \
        if hasattr(pd.DataFrame, "to_parquet") else None
    note("상권", "REAL", "LOCALDATA 지방행정인허가(localdata.go.kr)",
         f"{len(d):,}건 매칭 / {d.zone.nunique()}개 생활권", len(d))
    return out.reset_index(), panel


def _illustrative_business():
    if STRICT:
        out = base_frame()
        for c in ("active_biz", "biz_net_growth", "closure_rate", "biz_diversity"):
            out[c] = np.nan
        note("상권", "MISSING", "미확보",
             "상가정보 또는 LOCALDATA 인허가 파일을 넣으면 산출됩니다")
        return out, pd.DataFrame(columns=["zone", "year", "opened", "closed", "active"])
    rng = np.random.default_rng(RANDOM_SEED + 1)
    rows, panel = [], []
    for z, (pk, _, atone, btone, _) in PROFILE.items():
        base = max(40, int(pk * 22 * (0.7 + 0.5 * (btone + 1) / 2)))
        for y in range(2015, 2026):
            drift = (1 + btone * 0.022) ** (y - 2015)
            act = int(base * drift * rng.normal(1, 0.02))
            panel.append(dict(zone=z, year=y,
                              opened=int(act * (0.10 + 0.03 * btone)),
                              closed=int(act * (0.11 - 0.03 * btone)), active=act))
        cur = panel[-1]["active"]; prev = panel[-4]["active"]
        rows.append(dict(zone=z, active_biz=cur,
                         biz_net_growth=(cur / prev - 1) * 100,
                         closure_rate=np.clip(11 - btone * 3.5 + rng.normal(0, 0.8), 3, 22),
                         biz_diversity=np.clip(2.5 + btone * 0.45 + rng.normal(0, .08), 1.2, 3.4)))
    out = base_frame().merge(pd.DataFrame(rows), on="zone")
    note("상권", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 1),
         "data/raw/localdata_license*.csv 투입 시 자동 대체")
    return out, pd.DataFrame(panel)


# 생활권 대표좌표(근사 중심점) — 지도형 시각화 · 거리계산 기준점.
# 실제 시설 좌표가 들어오면 시설별 실좌표를 사용하고, 이 값은 표시용으로만 쓴다.
CENTROID = {
    "중앙동": (36.808, 127.152), "문성동": (36.820, 127.156), "원성동": (36.816, 127.162),
    "봉명동": (36.800, 127.140), "일봉동": (36.797, 127.152), "신방동": (36.780, 127.130),
    "청룡동": (36.775, 127.156), "신안동": (36.831, 127.176), "성정동": (36.822, 127.135),
    "쌍용동": (36.795, 127.120), "백석동": (36.800, 127.105), "불당동": (36.815, 127.100),
    "부성동": (36.842, 127.120), "목천읍": (36.780, 127.230), "성환읍": (36.915, 127.130),
    "성거읍": (36.870, 127.156), "직산읍": (36.885, 127.135), "병천면": (36.760, 127.300),
    "풍세면": (36.750, 127.110), "광덕면": (36.700, 127.130), "북면":   (36.740, 127.250),
    "성남면": (36.760, 127.200), "수신면": (36.730, 127.230), "동면":   (36.700, 127.280),
    "입장면": (36.900, 127.190),
}

# 생활SOC 6대 유형 · 가중치(시민 이용빈도·정책 우선도 반영)
SOC_TYPES = {"의료": 1.30, "보육": 1.20, "공원": 1.00, "문화": 0.95, "체육": 0.90, "복지": 1.15}


# ═════════════════════════════════════════════════════════════
#  3) 생활SOC  ─ 표준데이터 facility_*.csv + 상가정보
# ═════════════════════════════════════════════════════════════
def load_facilities() -> tuple[pd.DataFrame, pd.DataFrame]:
    """returns (zone_now[soc_cnt_*, soc_access, soc_per_capita 전 단계], points[lat,lon,zone,soc])"""
    files = sorted(glob.glob(str(RAW / "facility_*.csv"))) + \
            sorted(glob.glob(str(RAW / "facility_*.xlsx")))
    pts, srcs = [], []
    for f in files:
        f = Path(f)
        d = pd.read_excel(f) if f.suffix.lower() == ".xlsx" else read_any(f)
        if d is None or not len(d):
            continue
        soc = _soc_type_of(f.stem)
        lat = find_col(d, "위도", "latitude", "lat", "Y좌표", "좌표정보(y)")
        lon = find_col(d, "경도", "longitude", "lon", "X좌표", "좌표정보(x)")
        d = only_cheonan(d)
        adr = find_col(d, "소재지도로명주소", "도로명주소", "소재지지번주소",
                       "소재지전체주소", "주소")
        z = d[adr].map(zone_from_address) if adr else None
        if z is None or z.notna().sum() == 0:
            continue
        sub = pd.DataFrame({"zone": z, "soc": soc})
        if lat and lon:
            sub["lat"] = pd.to_numeric(d[lat], errors="coerce")
            sub["lon"] = pd.to_numeric(d[lon], errors="coerce")
        sub = sub[sub.zone.notna()]
        if len(sub):
            pts.append(sub); srcs.append(f"{f.name}({len(sub)})")

    # 상가정보에서 생활편의(의료/교육) 보강
    sg = load_stack("store_sangga")
    if sg is not None:
        hd = find_col(sg, "행정동명"); big = find_col(sg, "상권업종대분류명")
        lat = find_col(sg, "위도"); lon = find_col(sg, "경도")
        if hd is not None:
            s = only_cheonan(sg).copy()
            s["zone"] = s[hd].map(zone_from_hdong)
            s = s[s.zone.notna()]
            if big:
                m = {"의료": "의료", "학문": "문화", "교육": "문화", "스포츠": "체육", "생활": "복지"}
                s["soc"] = s[big].astype(str).str[:2].map(m)
                s = s[s.soc.notna()]
            else:
                s["soc"] = "복지"
            sub = s[["zone", "soc"]].copy()
            if lat and lon:
                sub["lat"] = pd.to_numeric(s[lat], errors="coerce")
                sub["lon"] = pd.to_numeric(s[lon], errors="coerce")
            if len(sub):
                pts.append(sub); srcs.append(f"상가정보({len(sub)})")

    if pts:
        P = pd.concat(pts, ignore_index=True)
        if "lat" not in P:
            P["lat"] = np.nan; P["lon"] = np.nan
        P = _fill_missing_coords(P)
        cnt = P.pivot_table(index="zone", columns="soc", aggfunc="size", fill_value=0)
        out = base_frame().set_index("zone").join(cnt).fillna(0)
        src_txt = ("소상공인 상가(상권)정보에서 생활SOC 시설 추출"
                   if all(x.startswith("상가정보") for x in srcs)
                   else "공공데이터포털 표준데이터 + 상가정보")
        note("생활SOC", "REAL", src_txt, " / ".join(srcs)[:90], len(P))
        return out.reset_index(), P
    return _illustrative_facilities()


def _soc_type_of(stem: str) -> str:
    s = stem.lower()
    for key, val in [("park", "공원"), ("공원", "공원"), ("daycare", "보육"), ("어린이집", "보육"),
                     ("유치원", "보육"), ("hospital", "의료"), ("병원", "의료"), ("의원", "의료"),
                     ("library", "문화"), ("도서관", "문화"), ("문화", "문화"),
                     ("sports", "체육"), ("체육", "체육"), ("senior", "복지"),
                     ("경로당", "복지"), ("복지", "복지")]:
        if key in s:
            return val
    return "복지"


def _fill_missing_coords(P):
    """좌표 없는 시설은 생활권 중심점 근처로 배치(밀도 계산에는 영향 없음, 지도 표시용)."""
    rng = np.random.default_rng(RANDOM_SEED + 7)
    miss = P.lat.isna() | P.lon.isna()
    if miss.any():
        c = P.loc[miss, "zone"].map(lambda z: CENTROID.get(z, (36.81, 127.14)))
        P.loc[miss, "lat"] = [t[0] for t in c] + rng.normal(0, .004, miss.sum())
        P.loc[miss, "lon"] = [t[1] for t in c] + rng.normal(0, .005, miss.sum())
    return P


def _illustrative_facilities():
    if STRICT:
        out = base_frame()
        for soc in SOC_TYPES:
            out[soc] = np.nan
        note("생활SOC", "MISSING", "미확보",
             "facility_*.csv 또는 상가정보를 넣으면 산출됩니다")
        return out, pd.DataFrame(columns=["zone", "soc", "lat", "lon"])
    rng = np.random.default_rng(RANDOM_SEED + 2)
    rows, pts = [], []
    for z, (pk, _, _, _, stone) in PROFILE.items():
        r = {"zone": z}
        for soc in SOC_TYPES:
            n = max(0, int(pk * (0.35 + stone * 1.1) * rng.normal(1, .18)))
            r[soc] = n
            la, lo = CENTROID[z]
            sp = 0.004 + 0.03 * (AREA_KM2[z] > 25)
            for _ in range(n):
                pts.append(dict(zone=z, soc=soc,
                                lat=la + rng.normal(0, sp), lon=lo + rng.normal(0, sp * 1.2)))
        rows.append(r)
    out = base_frame().merge(pd.DataFrame(rows), on="zone")
    note("생활SOC", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 2),
         "data/raw/facility_*.csv 투입 시 자동 대체")
    return out, pd.DataFrame(pts)


# ═════════════════════════════════════════════════════════════
#  4) 주거  ─ 빈집 · 노후건축물
# ═════════════════════════════════════════════════════════════
def load_housing(pop: pd.DataFrame) -> pd.DataFrame:
    """
    빈집 지표.
    KOSIS 공표 단위가 대부분 **시군구(동남구/서북구)** 이므로 읍면동 매칭이 안 된다.
    → 구 단위 값이 들어오면 해당 구에 속한 생활권 전체에 같은 값을 적용하고,
      '구 단위 배분'임을 출처에 명시한다(가정을 숨기지 않기 위함).
    """
    df = load_stack("vacant_house")
    out = base_frame().set_index("zone")
    if df is not None:
        try:
            got = _parse_vacancy(df, pop, out)
            if got is not None:
                out["vacancy_rate"] = got
                out["old_building"] = _illustrative_old_building()
                return out.reset_index()
        except Exception as e:
            log(f"    ! vacant_house 파싱 실패({e}) → 예시 데이터로 대체")
    if STRICT:
        out["vacancy_rate"] = np.nan
        out["old_building"] = np.nan
        if PROVENANCE.get("주거", {}).get("status") == "PARTIAL":
            pass                      # _parse_vacancy 가 이미 더 자세히 기록했다
        elif CITY_STATS.get("빈집률") is not None:
            note("주거", "PARTIAL", "KOSIS 미거주주택(빈집)비율",
                 f"천안시 전체 {CITY_STATS['빈집률']:.1f}%"
                 + (f" · {CITY_STATS['빈집수']:,}호" if "빈집수" in CITY_STATS else "")
                 + " — 시 단위 단일값이라 생활권 비교지표에서는 제외하고 배경 수치로만 사용")
        else:
            note("주거", "MISSING", "미확보",
                 "빈집 통계(천안시 동남구·서북구 단위)를 넣으면 생활권 지표로 산출됩니다")
        return out.reset_index()
    rng = np.random.default_rng(RANDOM_SEED + 3)
    out["vacancy_rate"] = pd.Series({
        z: np.clip(2.2 + PROFILE[z][2] * 13 - PROFILE[z][3] * 2 + rng.normal(0, .7), 0.6, 26)
        for z in ZONE_NAMES})
    out["old_building"] = _illustrative_old_building()
    note("주거", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 3),
         "data/raw/vacant_house.csv 투입 시 자동 대체")
    return out.reset_index()


def _parse_vacancy(df, pop, out):
    """읍면동 → 구 → 시 순으로 가장 세밀한 단위를 찾아 빈집률을 만든다."""
    # KOSIS 는 지역명을 여러 컬럼으로 쪼개 준다
    # (예: 행정구역별(1)=충청남도 / (2)=천안시 / (3)=동남구).
    # 한 컬럼만 보면 천안을 놓치므로 지역 관련 컬럼을 모두 이어 붙여 판단한다.
    rcs = [c for c in df.columns
           if any(k in str(c) for k in ("행정구역", "시군구", "지역", "읍면동"))]
    if not rcs:
        rcs = [df.columns[0]]
    d = df.copy()
    # KOSIS 는 하위 행에서 상위 지역칸을 비워 둔다
    # (충청남도 / 천안시 / 소계  →  다음 행은 (1)(2)가 비고 (3)만 '동남구').
    # 그대로 이어 붙이면 하위 행에 '천안'이 없어 필터에서 탈락하므로 먼저 채워 넣는다.
    parts = []
    for c in rcs:
        col = d[c].astype("string").str.strip()
        col = col.where(~col.isin(["nan", ""]), pd.NA).ffill().fillna("")
        col = col.where(~col.isin(["소계", "계"]), "")
        parts.append(col.astype(str))
    d["_region"] = parts[0]
    for col in parts[1:]:
        d["_region"] = (d["_region"] + " " + col).str.strip()
    d = d[d["_region"].str.contains("천안", na=False)]
    if not len(d):
        return None
    reg = d["_region"]

    def num(col):
        return pd.to_numeric(col.astype(str).str.replace(r"[,\s%]", "", regex=True),
                             errors="coerce")

    # 값 컬럼: '비율'이 있으면 그대로, 없으면 빈집 호수 / 세대수로 계산
    ratio_col = find_col(d, "비율", "율")
    # 개수 컬럼을 찾을 때 '비율'이 들어간 컬럼을 집지 않도록 제외한다
    cnt_col = find_col(d, "미거주주택(빈집)수", "빈집수", "공가수", "호수",
                       "미거주", "빈집", "공가", exclude=("비율", "율", "전체주택"))

    # ① 읍면동 단위인가?
    z = reg.map(zone_from_hdong)
    if z.notna().sum() >= 10:
        v = num(d[ratio_col]) if ratio_col else None
        if v is None and cnt_col is not None:
            hh = pop.set_index("zone")["pop"] / 2.3
            v = num(d[cnt_col]) / z.map(hh) * 100
        g = pd.DataFrame({"zone": z, "v": v}).dropna().groupby("zone")["v"].mean()
        note("주거", "REAL", "KOSIS 미거주주택(빈집) 통계", f"읍면동 단위 {len(g)}곳", len(d))
        return g.reindex(out.index)

    # ② 시 단위(천안시 한 값)인가? — 비교 지수로는 못 쓰지만 배경 수치로 기록한다
    if reg.str.contains("천안시", na=False).any() and not reg.str.contains("동남구|서북구",
                                                                        na=False).any():
        v = num(d[ratio_col]) if ratio_col else None
        cnt = num(d[cnt_col]) if cnt_col is not None else None
        row = d[reg.str.contains("천안시", na=False)]
        if v is not None and len(row):
            i = row.index[0]
            CITY_STATS["빈집률"] = float(v.loc[i])
            if cnt is not None:
                CITY_STATS["빈집수"] = int(cnt.loc[i])
            note("주거", "PARTIAL", "KOSIS 미거주주택(빈집)비율(시도/시/군/구)",
                 f"천안시 전체 {CITY_STATS['빈집률']:.1f}%"
                 + (f" · {CITY_STATS.get('빈집수', 0):,}호" if "빈집수" in CITY_STATS else "")
                 + " — 시 단위 단일값이라 배경 수치로만 사용",
                 len(d))
            return None          # 전 생활권 동일값 → 지수에서 자동 제외
    # ③ 구 단위(동남구/서북구)인가?
    gu = reg.str.extract(r"(동남구|서북구)")[0]
    if gu.notna().any():
        v = num(d[ratio_col]) if ratio_col else (
            num(d[cnt_col]) if cnt_col is not None else None)
        if v is None:
            return None
        # 연도 컬럼이 여러 개면 가장 최근 값을 쓰도록 숫자 컬럼 중 마지막을 사용
        if ratio_col is None and cnt_col is None:
            return None
        gv = pd.DataFrame({"gu": gu, "v": v}).dropna().groupby("gu")["v"].mean()
        res = out["gu"].map(gv) if "gu" in out.columns else \
            pd.Series(out.index.map(lambda z_: gv.get(ZONE_GU[z_], np.nan)), index=out.index)
        note("주거", "PARTIAL", "KOSIS 미거주주택(빈집) 통계",
             f"자치구 단위({', '.join(f'{k} {x:.1f}%' for k, x in gv.items())}) "
             "→ 구에 속한 생활권에 동일 적용", len(d))
        return res
    return None


def _illustrative_old_building():
    rng = np.random.default_rng(RANDOM_SEED + 4)
    return pd.Series({z: np.clip(18 + PROFILE[z][2] * 52 + rng.normal(0, 3), 6, 88)
                      for z in ZONE_NAMES})


# ═════════════════════════════════════════════════════════════
#  5) 이동성  ─ 버스정류장
# ═════════════════════════════════════════════════════════════
def load_transit() -> pd.DataFrame:
    """
    정류장 밀도.
    주소가 있으면 주소로, 없으면 **좌표로** 생활권을 판정한다.
    (국토부 TAGO 버스정류소정보 API 는 주소 없이 위경도만 준다)
    """
    df = load_stack("bus_stop")
    out = base_frame().set_index("zone")
    if df is not None:
        try:
            z = _transit_zones(df)
            if z is not None and z.notna().sum() >= 50:
                g = z.value_counts()
                out["transit_density"] = (g / pd.Series(AREA_KM2)).reindex(out.index)
                note("이동성", "REAL", "국토교통부 TAGO 버스정류소정보 / 정류소 현황",
                     f"{int(z.notna().sum()):,}개소 · {z.nunique()}개 생활권", len(df))
                return out.reset_index()
            log("    ! 정류소를 천안 생활권에 충분히 매칭하지 못했습니다"
                f" (매칭 {0 if z is None else int(z.notna().sum())}개)")
        except Exception as e:
            log(f"    ! bus_stop 파싱 실패({e})")
    if STRICT:
        out["transit_density"] = np.nan
        note("이동성", "MISSING", "미확보",
             "정류소 위치(좌표 또는 주소)가 담긴 파일이 필요합니다(노선 현황만으로는 불가)")
        return out.reset_index()
    rng = np.random.default_rng(RANDOM_SEED + 5)
    out["transit_density"] = pd.Series({
        z_: max(0.25, (2.0 + PROFILE[z_][4] * 9) * rng.normal(1, .12) *
                (1 if AREA_KM2[z_] < 25 else 0.16)) for z_ in ZONE_NAMES})
    note("이동성", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 5),
         "data/raw/bus_stop.csv 투입 시 자동 대체")
    return out.reset_index()


def _transit_zones(df: pd.DataFrame) -> "pd.Series | None":
    """정류소 행 → 생활권. 주소 우선, 없으면 좌표 최근접 생활권."""
    adr = find_col(df, "소재지", "주소", "위치", "정류소위치")
    if adr is not None:
        z = df[adr].map(zone_from_address)
        if z.notna().sum() >= 50:
            return z
    la = find_col(df, "gpslati", "위도", "latitude", "lat", "gpsylat", "y좌표")
    lo = find_col(df, "gpslong", "경도", "longitude", "lon", "gpsxlong", "x좌표")
    if la is None or lo is None:
        return None
    lat = pd.to_numeric(df[la], errors="coerce")
    lon = pd.to_numeric(df[lo], errors="coerce")
    m = lat.between(36.5, 37.1) & lon.between(126.9, 127.5)     # 천안 일대만
    if m.sum() < 50:
        return None
    zs = list(CENTROID); cla = np.array([CENTROID[z][0] for z in zs])
    clo = np.array([CENTROID[z][1] for z in zs])
    R = 6371.0
    p1 = np.radians(lat[m].values)[:, None]; p2 = np.radians(cla)[None, :]
    dp = p2 - p1; dl = np.radians(clo[None, :] - lon[m].values[:, None])
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    d = 2 * R * np.arcsin(np.sqrt(a))
    near = np.array(zs)[d.argmin(1)]
    # 어느 생활권 중심에서도 지나치게 먼 점은 천안 밖으로 보고 제외
    near = np.where(d.min(1) <= 12.0, near, None)
    out = pd.Series(index=df.index, dtype=object)
    out.loc[lat[m].index] = near
    return out
