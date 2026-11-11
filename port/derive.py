#!/usr/bin/env python3
"""
derive.py — produce a buildable copy of the pristine winfish decompilation.

The decompilation under external/winfish is NEVER modified. This script
reads it and emits a ported copy under port/generated (gitignored) that:
  * rewrites #include <SexyAppFramework/...>  ->  <poplib/...>
  * renames framework type references to poplib equivalents
  * applies the fixups in port/fixups/

Upstream winfish updates -> re-run this script to re-derive.

Status: SCAFFOLD. The actual rewrite rules are filled in after we map
winfish's SexyAppFramework usage onto poplib's API.
"""
import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Derive a buildable winfish from the pristine decompilation.")
    ap.add_argument("--winfish", default="external/winfish/source",
                    help="path to pristine winfish source")
    ap.add_argument("--poplib", default="external/poplib",
                    help="path to poplib")
    ap.add_argument("--out", default="port/generated",
                    help="output directory (gitignored)")
    args = ap.parse_args()

    winfish = Path(args.winfish)
    if not winfish.exists():
        print(f"[derive] ERROR: winfish source not found at {winfish}",
              file=sys.stderr)
        return 1

    print(f"[derive] SCAFFOLD: would derive from {winfish} -> {args.out}")
    print("[derive] (no rewrite rules implemented yet — study poplib API first)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
