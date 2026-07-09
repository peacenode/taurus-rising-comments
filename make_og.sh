#!/bin/sh
# Regenerate og.png + favicon.png from the Communion logo. Needs ImageMagick.
set -e
cd "$(dirname "$0")"

TIMES="/System/Library/Fonts/Supplemental/Times New Roman.ttf"

magick -size 1200x630 xc:white \
  \( avatars/communion_logo.png -resize 140x140 \) -gravity center -geometry +0-70 -composite \
  -font "$TIMES" -pointsize 84 -fill '#171717' \
  -gravity center -annotate +0+70 'Taurus Dreamscapes' \
  -colorspace sRGB -type TrueColor -strip og.png

magick avatars/communion_logo.png -resize 180x180 -colorspace sRGB -type TrueColor -strip favicon.png

echo "wrote og.png and favicon.png"
