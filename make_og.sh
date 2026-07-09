#!/bin/sh
# Regenerate og.png + favicon.png from the Communion logo. Needs ImageMagick.
# The subtitle count is read from the dataset so it can't drift.
set -e
cd "$(dirname "$0")"

N=$(python3 -c "import json;print(len(json.load(open('data/extracted.json'))))")
TIMES="/System/Library/Fonts/Supplemental/Times New Roman.ttf"

magick -size 1200x630 xc:white \
  \( avatars/communion_logo.png -resize 132x132 \) -gravity center -geometry +0-72 -composite \
  -font "$TIMES" -pointsize 78 -fill '#171717' \
  -gravity center -annotate +0+62 'Taurus Dreamscapes' \
  -font "$TIMES" -pointsize 30 -fill '#737373' \
  -gravity center -annotate +0+132 "$N Taurus risings on Venus, north node, and Saturn" \
  -colorspace sRGB -type TrueColor -strip og.png

magick avatars/communion_logo.png -resize 180x180 -colorspace sRGB -type TrueColor -strip favicon.png

echo "wrote og.png (n=$N) and favicon.png"
