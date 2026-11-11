#!/bin/bash
# Copy the original game assets next to the ported executable, then overlay
# our TTF/i18n resource manifest and font.
# The decompilation ships no assets: they come from your own retail copy.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Pass the folder holding your copy of the game, or drop it in ./game.
SRC="${1:-$ROOT/game}"
DST="$ROOT/port/bin"

[ -d "$SRC" ] || { echo "cannot find the original game at: $SRC"; exit 1; }
mkdir -p "$DST"

# Retail releases keep everything loose (no main.pak), so it is copied as is.
for d in data images music properties sounds fishsongs; do
  if [ -d "$SRC/$d" ]; then
    cp -r "$SRC/$d" "$DST/" && echo "  $d"
  else
    echo "  MISSING: $d"
  fi
done

# AppBase::LoadProperties() requires properties/default.xml (the string table).
# Clean installs keep it in properties/ and the loop above already copied it.
# Modded installs (e.g. an old Chinese patch) often move it into a subfolder,
# so search the known locations before giving up. Without it the game pops a
# fatal error during Init() and never reaches the menu.
if [ ! -f "$DST/properties/default.xml" ]; then
  for cand in \
    "$SRC/properties/default.xml" \
    "$SRC/old_cn_patch/patch_cn/properties/default.xml" \
    "$SRC/mod/data/l10n_source/default.xml" \
    "$SRC/chs/properties/default.xml"
  do
    if [ -f "$cand" ]; then
      mkdir -p "$DST/properties"
      cp "$cand" "$DST/properties/default.xml" \
        && echo "  properties/default.xml (from ${cand#"$SRC"/})"
      break
    fi
  done
fi
if [ ! -f "$DST/properties/default.xml" ]; then
  echo "  WARNING: properties/default.xml not found - the game will fail at startup"
fi

# --- our overlays (kept in port/assets/, checked into git) -----------------
echo
echo "applying port/ overlays..."

if [ -f "$ROOT/port/assets/properties/resources.xml" ]; then
  mkdir -p "$DST/properties"
  cp "$ROOT/port/assets/properties/resources.xml" "$DST/properties/" \
    && echo "  properties/resources.xml -> TTF (!sys:)"
else
  echo "  WARNING: no TTF manifest. Run: python port/make-resources.py <game>/properties/resources.xml"
fi

if [ -f "$ROOT/port/assets/fonts/ui.ttf" ]; then
  mkdir -p "$DST/fonts"
  cp "$ROOT/port/assets/fonts/ui.ttf" "$DST/fonts/" && echo "  fonts/ui.ttf"
else
  echo "  WARNING: fonts/ui.ttf missing. Run: python port/prepare-font.py --system"
  echo "           (or drop an OFL font there; see port/assets/fonts/README.md)"
fi

echo "assets in $DST ($(du -sh "$DST" | cut -f1))"

# --- check everything resources.xml references is actually there -------------
echo
echo "verifying resources referenced by resources.xml..."
python "$ROOT/port/verify-assets.py" || exit 1
