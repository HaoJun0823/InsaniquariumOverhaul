#!/usr/bin/env python3
"""
prepare-font.py — put a TTF at port/assets/fonts/ui.ttf for local testing.

    python port/prepare-font.py --system      # copy a Windows system font
    python port/prepare-font.py path/to/NotoSansSC-Regular.otf

For real distribution use an OFL-licensed font (see assets/fonts/README.md).
The resulting ui.ttf is gitignored and must NOT be committed.
"""
import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DST = ROOT / "port" / "assets" / "fonts" / "ui.ttf"

SYSTEM_CANDIDATES = [
    pathlib.Path("C:/Windows/Fonts/simhei.ttf"),
    pathlib.Path("C:/Windows/Fonts/msyh.ttc"),
    pathlib.Path("C:/Windows/Fonts/simsun.ttc"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", help="TTF/OTF/TTC to use")
    ap.add_argument("--system", action="store_true",
                    help="use a Windows system font (local testing only)")
    args = ap.parse_args()

    if args.system:
        src = next((p for p in SYSTEM_CANDIDATES if p.is_file()), None)
        if src is None:
            print("ERROR: no Windows system CJK font found")
            return 1
    elif args.source:
        src = pathlib.Path(args.source)
        if not src.is_file():
            print("ERROR: not found:", src)
            return 1
    else:
        print("ERROR: give a font path or --system")
        return 1

    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, DST)
    print(f"copied {src} -> {DST.relative_to(ROOT)} ({DST.stat().st_size:,} bytes)")
    if args.system:
        print("NOTE: system fonts are not redistributable; local testing only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
