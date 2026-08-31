# tools/

## qa_deck.py — 기획서 레이아웃 자동 검수
```bash
python3 tools/qa_deck.py deliverables/기획서_천안균형발전나침반_CBC.pptx
```
슬라이드 밖 이탈(OUT) · 텍스트 넘침(OVERFLOW) · 하단 이탈(BOTTOM) · 요소 겹침(COLLIDE)을 탐지한다.
PPTX를 코드로 생성하면 좌표 실수가 눈에 안 띄므로, 기획서를 수정할 때마다 이걸 돌려서 0건인지 확인할 것.

## extract_cheonan_sangga.py — 상가정보 ZIP에서 천안시만 뽑기

소상공인시장진흥공단 상가(상권)정보는 전국 파일이라 350MB가 넘는다.
압축을 풀지 않고 ZIP 안에서 바로 읽어, 천안시 행 · 분석에 쓰는 11개 컬럼만 남긴다.

```bash
pip install pandas
python tools/extract_cheonan_sangga.py "소상공인시장진흥공단_상가(상권)정보_20260630.zip"
```

결과 `천안_상가정보.csv` 를 `data/raw/store_sangga.csv` 로 옮기면
`상권`(사업체밀도·업종다양성)과 `생활SOC`(접근성·인구당 시설수) 두 축이 한 번에 실데이터가 된다.
