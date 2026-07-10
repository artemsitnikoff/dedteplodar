#!/usr/bin/env bash
# Rebuild the bot-flow diagram PDF from the local HTML source.
# No dependencies beyond a Chromium-based browser (Chrome/Chromium/Edge/Brave).
#
# Usage:
#   ./docs/build_pdf.sh                 # -> docs/teplodar-bot-flow.pdf
#   ./docs/build_pdf.sh ~/Desktop/x.pdf # -> custom output path
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
src="$here/teplodar-bot-flow.html"
out="${1:-$here/teplodar-bot-flow.pdf}"

[ -f "$src" ] || { echo "Source not found: $src" >&2; exit 1; }

chrome=""
for c in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium" \
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  "$(command -v google-chrome 2>/dev/null || true)" \
  "$(command -v chromium 2>/dev/null || true)" \
  "$(command -v chromium-browser 2>/dev/null || true)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then chrome="$c"; break; fi
done

if [ -z "$chrome" ]; then
  echo "No Chromium-based browser found." >&2
  echo "Either install Google Chrome, or open $src in a browser and print to PDF (Cmd+P)." >&2
  exit 1
fi

# Page size / orientation come from the @page rule inside the HTML (A4 landscape).
"$chrome" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$out" "file://$src" 2>/dev/null

echo "PDF written: $out"
