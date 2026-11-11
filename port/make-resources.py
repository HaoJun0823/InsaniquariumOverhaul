#!/usr/bin/env python3
"""
make-resources.py — derive a TTF-based resources.xml from the retail original.

    python port/make-resources.py "<game dir>/properties/resources.xml"

Writes port/assets/properties/resources.xml (checked into git).

What it changes
--------------
Only the 14 <Font> declarations. Example:

    <Font id="JUNGLEFEVER10OUTLINE" path="JungleFever10outline.txt" />
 -> <Font id="JUNGLEFEVER10OUTLINE" path="!sys:fonts/ui.ttf" size="10" />

Why this is all TTF needs: PopLib's ResourceManager sees the "!sys:" prefix and
builds a SysFont (SDL_ttf) instead of an ImageFont. Game code still calls
GetFontThrow("FONT_XXX") and receives a Font* — zero game-logic changes.
PopLib also skips the SetDefaults path prefix for paths starting with '!'.

The font file itself is NOT shipped (size + licensing). See
port/assets/fonts/README.md for how to drop in an OFL-licensed CJK font.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "port" / "assets" / "properties" / "resources.xml"

# Fonts whose baked outline/shadow we approximate with SDL_ttf attributes.
OUTLINE_HINT = re.compile(r"OUTLINE|TINYBOLD", re.I)
BOLD_HINT = re.compile(r"BOLD|CONTINUUM", re.I)


def size_for(font_id):
    m = re.search(r"(\d+)", font_id)
    return int(m.group(1)) if m else 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="retail properties/resources.xml")
    ap.add_argument("--font", default="fonts/ui.ttf",
                    help="font path relative to the game working directory")
    args = ap.parse_args()

    src = pathlib.Path(args.source)
    if not src.is_file():
        print("ERROR: not found:", src)
        return 1
    text = src.read_text(encoding="utf-8", errors="replace")

    original_fonts = re.findall(r'<Font\s+id="([^"]+)"\s+path="([^"]+)"', text)
    if not original_fonts:
        print("ERROR: no <Font> declarations found")
        return 1

    count = 0

    def replace_font(m):
        nonlocal count
        count += 1
        font_id = m.group(1)
        size = size_for(font_id)
        # PopLib only checks whether the attribute exists, but valueless
        # attributes are not valid XML. Write them with values.
        attrs = ""
        if BOLD_HINT.search(font_id) or "OUTLINE" in font_id.upper():
            attrs += ' bold="1"'
        if OUTLINE_HINT.search(font_id):
            attrs += ' shadow="1"'
        return (f'<Font id="{font_id}" path="!sys:{args.font}" '
                f'size="{size}"{attrs} />')

    new_text, n = re.subn(
        r'<Font\s+id="([^"]+)"\s+path="([^"]+)"\s*/>',
        replace_font, text)

    if n != len(original_fonts):
        print(f"WARN: matched {n} of {len(original_fonts)} fonts")

    # The retail manifest has bare attribute values (cols=3). Our PopLib
    # xmlparser patch tolerates them, but our derived manifest should be
    # strict XML on its own so any parser can read it.
    new_text, nq = re.subn(r'\b([A-Za-z_][A-Za-z0-9_]*)=([0-9]+)(?=[\s/>])',
                           r'\1="\2"', new_text)
    # PopCap also used valueless boolean attributes (ddsurface, ...).
    # PopLib only checks for the attribute's presence, so an empty value is
    # equivalent and makes the manifest valid XML.
    new_text, nv = re.subn(r'\s(ddsurface)(?=\s*/?>)', r' \1=""', new_text)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(new_text, encoding="utf-8", newline="")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"rewrote {n} font declarations -> !sys:{args.font}")
    print(f"quoted {nq} bare values, {nv} valueless flags")
    print("sample:")
    shown = 0
    for line in new_text.splitlines():
        if "<Font" in line and shown < 4:
            print(" ", line.strip())
            shown += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
