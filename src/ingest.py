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
                    BDONG2ZONE, HDONG_KEYS_SORTED, HDONG2ZONE, RANDOM_SEED)

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8", "latin1")
PROVENANCE: dict[str, dict] = {}      # 지표군 → {status, source, note, rows}


def log(msg): print(msg, flush=True)


def note(key, status, source, detail="", rows=0):
    PROVENANCE[key] = dict(status=status, source=source, detail=detail, rows=rows)
    badge = {"REAL": "\033[92m[REAL]\033[0m",
             "PARTIAL": "\033[96m[PARTIAL]\033[0m"}.get(
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
    d = sg.copy()
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
        adr = find_col(d, "소재지도로명주소", "도로명주소", "소재지지번주소", "소재지전체주소", "주소")
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
            s = sg.copy()
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
        note("생활SOC", "REAL", "공공데이터포털 표준데이터 + 상가정보",
             " / ".join(srcs)[:90], len(P))
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
    df = load_stack("vacant_house")
    out = base_frame().set_index("zone")
    if df is not None:
        try:
            rc = find_col(df, "행정구역", "읍면동", "지역", "동", "시군구")
            vc = find_col(df, "빈집", "빈 집", "공가")
            if rc and vc:
                d = df.copy()
                d["zone"] = d[rc].map(zone_from_hdong)
                d = d[d.zone.notna()]
                v = pd.to_numeric(d[vc].astype(str).str.replace(",", ""), errors="coerce")
                g = d.assign(v=v).groupby("zone")["v"].sum()
                hh = pop.set_index("zone")["pop"] / 2.3         # 세대 근사
                out["vacancy_rate"] = (g / hh * 100).clip(0, 40)
                note("주거", "REAL", "빈집 통계(KOSIS/부동산원)", f"{len(d)}행", len(d))
                out["old_building"] = _illustrative_old_building()
                return out.reset_index()
        except Exception as e:
            log(f"    ! vacant_house 파싱 실패({e}) → 예시 데이터로 대체")
    rng = np.random.default_rng(RANDOM_SEED + 3)
    out["vacancy_rate"] = pd.Series({
        z: np.clip(2.2 + PROFILE[z][2] * 13 - PROFILE[z][3] * 2 + rng.normal(0, .7), 0.6, 26)
        for z in ZONE_NAMES})
    out["old_building"] = _illustrative_old_building()
    note("주거", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 3),
         "data/raw/vacant_house.csv 투입 시 자동 대체")
    return out.reset_index()


def _illustrative_old_building():
    rng = np.random.default_rng(RANDOM_SEED + 4)
    return pd.Series({z: np.clip(18 + PROFILE[z][2] * 52 + rng.normal(0, 3), 6, 88)
                      for z in ZONE_NAMES})


# ═════════════════════════════════════════════════════════════
#  5) 이동성  ─ 버스정류장
# ═════════════════════════════════════════════════════════════
def load_transit() -> pd.DataFrame:
    df = load_stack("bus_stop")
    out = base_frame().set_index("zone")
    if df is not None:
        try:
            adr = find_col(df, "소재지", "주소", "정류소명", "위치")
            if adr:
                d = df.copy(); d["zone"] = d[adr].map(zone_from_address)
                g = d[d.zone.notna()].groupby("zone").size()
                out["transit_density"] = g / pd.Series(AREA_KM2)
                note("이동성", "REAL", "버스정류소 현황", f"{int(g.sum())}개소", len(d))
                return out.reset_index()
        except Exception as e:
            log(f"    ! bus_stop 파싱 실패({e})")
    rng = np.random.default_rng(RANDOM_SEED + 5)
    out["transit_density"] = pd.Series({
        z: max(0.25, (2.0 + PROFILE[z][4] * 9) * rng.normal(1, .12) *
               (1 if AREA_KM2[z] < 25 else 0.16)) for z in ZONE_NAMES})
    note("이동성", "ILLUSTRATIVE", "예시 생성(seed=%d)" % (RANDOM_SEED + 5),
         "data/raw/bus_stop.csv 투입 시 자동 대체")
    return out.reset_index()
