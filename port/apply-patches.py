#!/usr/bin/env python3
"""
apply-patches.py — idempotently apply/revert the reviewed PopLib patches.

    python port/apply-patches.py            # apply what is missing
    python port/apply-patches.py --check     # report only, change nothing
    python port/apply-patches.py --revert    # undo all applied patches

Patches live in port/patches/poplib/*.patch and are generated from the pristine
submodule by port/make-patches.py. They are applied to external/poplib as a
build-time step (git apply), which keeps the submodule itself UNMODIFIED in our
git history — no fork, no vendored copy, upstream can be updated freely.

Idempotency: for each patch we first try `git apply --check -R` (already
applied?), then `git apply --check` (can it apply?). Applying twice is a no-op.
"""
import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
POPLIB = ROOT / "external" / "poplib"
PATCHES = ROOT / "port" / "patches" / "poplib"


def git(*args):
    return subprocess.run(["git", "-C", str(POPLIB), *args],
                          capture_output=True, text=True)


def state(patch):
    r = git("apply", "--check", "-R", str(patch))
    if r.returncode == 0:
        return "applied"
    r = git("apply", "--check", str(patch))
    if r.returncode == 0:
        return "pending"
    return "conflict"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only")
    ap.add_argument("--revert", action="store_true", help="undo all patches")
    args = ap.parse_args()

    patches = sorted(PATCHES.glob("*.patch"))
    if not patches:
        print("No patches found. Run: python port/make-patches.py")
        return 1

    print(f"poplib:  {POPLIB}")
    print(f"patches: {len(patches)}")
    print()
    conflicts = 0
    for p in patches:
        st = state(p)
        tag = {"applied": "already applied", "pending": "will apply",
               "conflict": "CONFLICT"}[st]
        print(f"  [{st:8s}] {p.name}: {tag}")
        if st == "conflict":
            conflicts += 1
            continue
        if args.check:
            continue
        if args.revert and st == "applied":
            r = git("apply", "-R", str(p))
            print("            reverted" if r.returncode == 0 else
                  f"            REVERT FAILED: {r.stderr.strip()[:120]}")
        elif not args.revert and st == "pending":
            r = git("apply", str(p))
            print("            applied" if r.returncode == 0 else
                  f"            APPLY FAILED: {r.stderr.strip()[:120]}")

    print()
    if conflicts:
        print(f"{conflicts} patch(es) conflict: upstream changed, re-run make-patches.py")
        return 1
    if args.check:
        print("check complete, nothing changed")
    else:
        print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
