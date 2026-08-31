# tools/

## qa_deck.py — 기획서 레이아웃 자동 검수
```bash
python3 tools/qa_deck.py deliverables/기획서_천안균형발전나침반_CBC.pptx
```
슬라이드 밖 이탈(OUT) · 텍스트 넘침(OVERFLOW) · 하단 이탈(BOTTOM) · 요소 겹침(COLLIDE)을 탐지한다.
PPTX를 코드로 생성하면 좌표 실수가 눈에 안 띄므로, 기획서를 수정할 때마다 이걸 돌려서 0건인지 확인할 것.
