#!/usr/bin/env bash
# 기획서 PPTX → PDF (LibreOffice Impress)
#
# 맑은 고딕이 없는 환경에서는 fontconfig 로 나눔고딕으로 치환한다.
# (치환 규칙은 tools/fonts.conf 참조 — 없으면 한글이 네모로 깨진다)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$(ls "$ROOT"/deliverables/기획서_*.pptx 2>/dev/null | head -1)"
[ -z "$SRC" ] && { echo "기획서 pptx 가 없습니다. 먼저 python3 src/run_all.py 를 실행하세요."; exit 1; }
DST="${SRC%.pptx}.pdf"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp "$SRC" "$TMP/deck.pptx"
( cd "$TMP" && soffice --headless --nologo --norestore \
    --convert-to pdf --outdir "$TMP" deck.pptx >/dev/null 2>&1 )
[ -f "$TMP/deck.pdf" ] || { echo "변환 실패 — LibreOffice Impress 가 설치되어 있는지 확인하세요."; exit 1; }
cp "$TMP/deck.pdf" "$DST"
echo "    · $(basename "$DST")  ($(du -k "$DST" | cut -f1) KB, $(pdfinfo "$DST" 2>/dev/null | awk '/^Pages/{print $2}')장)"
