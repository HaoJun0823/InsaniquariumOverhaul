#!/usr/bin/env python3
"""
overhaul.py - the single entry point for working on this repository.

Why this exists: the pipeline used to be twelve commands in three languages
(Python, Bash, Batch), documented only in a cheat sheet. Nobody could tell which
command was safe to run, and the answer to "how do I check the tree?" depended on
who you asked. This CLI is the stable interface; the scripts behind it are an
implementation detail that may be moved or rewritten.

Design rule: this file orchestrates, it does not implement. Asset copying,
deriving, patching, building and capture all delegate to the script that owns
that concern. Verification (doctor) is the one thing implemented here, because
"is the tree healthy?" must not depend on a collector script that drifts.

Usage:
    python port/tools/overhaul.py doctor
    python port/tools/overhaul.py deps [--fix]
    python port/tools/overhaul.py patch [--check|--revert|--regenerate]
    python port/tools/overhaul.py derive
    python port/tools/overhaul.py build
    python port/tools/overhaul.py test [--driver headless|desktop] [--only NAME]
    python port/tools/overhaul.py assets <retail-dir>
    python port/tools/overhaul.py assets --verify
    python port/tools/overhaul.py all
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT / "port"
BUILD = ROOT / "build" / "game"

INIT_DEPS = PORT / "init-deps.py"
MAKE_PATCHES = PORT / "make-patches.py"
APPLY_PATCHES = PORT / "apply-patches.py"
DERIVE = PORT / "port.sh"
BUILD_BAT = PORT / "build-windows.bat"
COPY_ASSETS = PORT / "copy-assets.sh"
VERIFY_ASSETS = PORT / "verify-assets.py"
CAPTURE = PORT / "run-capture-test.py"

IS_WINDOWS = os.name == "nt"


class Failure(Exception):
    pass


def say(message=""):
    print(message, flush=True)


def run(command, cwd=ROOT, capture=False, required=True):
    """Run a command. Streams output unless capture=True.

    Streaming is the default because a silently buffering build is
    indistinguishable from a hung one, and this project builds for minutes.
    """
    display = " ".join(str(part) for part in command)
    if not capture:
        say(f"$ {display}")

    completed = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd),
        text=True,
        capture_output=capture,
    )

    if completed.returncode != 0 and required:
        if capture:
            say(completed.stdout or "")
            say(completed.stderr or "", file=sys.stderr)
        raise Failure(f"command failed with exit code {completed.returncode}: {display}")

    return completed


def python(script, *arguments, **kwargs):
    return run([sys.executable, script, *arguments], **kwargs)


def require(path):
    if not path.exists():
        raise Failure(f"missing {path.relative_to(ROOT)}; run 'overhaul.py derive' first")
    return path


# ---------------------------------------------------------------------------
# verbs
# ---------------------------------------------------------------------------


def verb_doctor(_args):
    """Read-only health check. Writes nothing; safe to run at any time."""
    checks = []

    def check(name, function):
        try:
            detail = function() or ""
            checks.append((True, name, detail))
        except Failure as error:
            checks.append((False, name, str(error)))
        except Exception as error:  # noqa: BLE001 - a check must never abort the report
            checks.append((False, name, f"{type(error).__name__}: {error}"))

    def dependencies():
        python(INIT_DEPS, "--check", capture=True)
        return "pinned submodules at their recorded commits"

    def patches():
        python(APPLY_PATCHES, "--check", capture=True)
        return "poplib patch set applies cleanly"

    def assets():
        completed = python(VERIFY_ASSETS, capture=True)
        tail = (completed.stdout or "").strip().splitlines()
        return tail[-1] if tail else "all referenced resources present"

    def derived():
        require(PORT / "winfish")
        count = len(list((PORT / "winfish").glob("*.cpp")))
        if count == 0:
            raise Failure("no derived sources; run 'overhaul.py derive'")
        return f"{count} derived translation units"

    def executable():
        exe = PORT / "bin" / ("Insaniquarium.exe" if IS_WINDOWS else "Insaniquarium")
        require(exe)
        age = exe.stat().st_mtime
        newest_source = max(
            (path.stat().st_mtime for path in (PORT / "winfish").glob("*.cpp")),
            default=0,
        )
        if age < newest_source:
            raise Failure("exe is older than the derived sources; rebuild")
        return f"{exe.name}, {exe.stat().st_size // (1024 * 1024)} MB"

    def unit_tests():
        candidates = sorted(BUILD.glob("**/overhaul_tests.exe")) + sorted(
            BUILD.glob("**/overhaul_tests")
        )
        if not candidates:
            raise Failure("overhaul_tests not built; run 'overhaul.py build'")
        completed = subprocess.run(
            [str(candidates[0])],
            cwd=str(candidates[0].parent),
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise Failure((completed.stderr or completed.stdout or "").strip() or "tests failed")
        return "OverhaulCore unit tests pass"

    def crash_artifacts():
        crash = PORT / "bin" / "crash.txt"
        if crash.exists():
            raise Failure(f"port/bin/crash.txt exists ({crash.stat().st_size} bytes); investigate")
        return "no crash.txt in the runtime directory"

    check("pinned dependencies", dependencies)
    check("poplib patch set", patches)
    check("asset references", assets)
    check("derived sources", derived)
    check("executable", executable)
    check("unit tests", unit_tests)
    check("crash artifacts", crash_artifacts)

    say()
    width = max(len(name) for _, name, _ in checks)
    failures = 0
    for ok, name, detail in checks:
        marker = "ok  " if ok else "FAIL"
        if not ok:
            failures += 1
        say(f"[{marker}] {name.ljust(width)}  {detail}")

    say()
    if failures:
        say(f"doctor: {failures} check(s) failed")
        return 1
    say("doctor: all checks passed")
    return 0


def verb_deps(args):
    python(INIT_DEPS, *(("--fix",) if args.fix else ()))
    return 0


def verb_patch(args):
    if args.check:
        python(APPLY_PATCHES, "--check")
    elif args.revert:
        python(APPLY_PATCHES, "--revert")
    elif args.regenerate:
        # The supported order matters: revert to pristine first, or the
        # generator diffs our edits against themselves and produces nothing.
        python(APPLY_PATCHES, "--revert")
        python(MAKE_PATCHES)
        python(APPLY_PATCHES)
    else:
        python(APPLY_PATCHES)
    return 0


def verb_derive(_args):
    if not shutil.which("bash"):
        raise Failure("bash is required to run port/port.sh (Git Bash on Windows)")
    run(["bash", DERIVE])
    return 0


def verb_build(_args):
    if IS_WINDOWS:
        run(["cmd", "/c", BUILD_BAT])
    else:
        run(["cmake", "--build", BUILD])
    return 0


def verb_test(args):
    command = [sys.executable, CAPTURE]
    if args.driver:
        command += ["--driver", args.driver]
    if args.only:
        command += ["--only", args.only]
    if args.seconds:
        command += ["--seconds", str(args.seconds)]
    run(command)
    return 0


def verb_assets(args):
    if args.verify:
        python(VERIFY_ASSETS)
        return 0
    if not args.retail_dir:
        raise Failure("assets requires a retail directory, or --verify")
    run(["bash", COPY_ASSETS, args.retail_dir])
    python(VERIFY_ASSETS)
    return 0


def verb_all(args):
    """The full pipeline, in the order that makes each step meaningful."""
    python(INIT_DEPS, "--check")
    python(APPLY_PATCHES, "--check")
    python(VERIFY_ASSETS)
    verb_derive(args)
    verb_build(args)
    verb_test(args)
    return verb_doctor(args)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="overhaul.py",
        description="Single entry point for building and verifying InsaniquariumOverhaul.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Where a change belongs is defined in docs/ARCHITECTURE.md (change model).\n"
            "How a change is delivered is defined in AGENTS.md (process contract)."
        ),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    verbs.add_parser("doctor", help="read-only health check of the tree").set_defaults(
        function=verb_doctor
    )

    deps = verbs.add_parser("deps", help="verify or materialise pinned nested submodules")
    deps.add_argument("--fix", action="store_true", help="fetch the pinned commits")
    deps.set_defaults(function=verb_deps)

    patch = verbs.add_parser("patch", help="apply, check, revert, or regenerate poplib patches")
    group = patch.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="verify idempotence without writing")
    group.add_argument("--revert", action="store_true", help="restore the pristine submodule")
    group.add_argument(
        "--regenerate", action="store_true", help="revert, regenerate from make-patches.py, apply"
    )
    patch.set_defaults(function=verb_patch)

    verbs.add_parser("derive", help="regenerate port/winfish from the pristine decomp").set_defaults(
        function=verb_derive
    )
    verbs.add_parser("build", help="configure and build with MSVC + Ninja").set_defaults(
        function=verb_build
    )

    test = verbs.add_parser("test", help="deterministic capture regression")
    test.add_argument("--driver", choices=("headless", "desktop"), default=None)
    test.add_argument("--only", default=None, help="single scenario, e.g. default")
    test.add_argument("--seconds", type=int, default=None)
    test.set_defaults(function=verb_test)

    assets = verbs.add_parser("assets", help="copy retail assets, or verify references")
    assets.add_argument("retail_dir", nargs="?", default=None)
    assets.add_argument("--verify", action="store_true")
    assets.set_defaults(function=verb_assets)

    all_verb = verbs.add_parser(
        "all", help="deps -> patch -> assets -> derive -> build -> test -> doctor"
    )
    all_verb.add_argument("--driver", choices=("headless", "desktop"), default=None)
    all_verb.add_argument("--only", default=None, help="single scenario, e.g. default")
    all_verb.add_argument("--seconds", type=int, default=None)
    all_verb.set_defaults(function=verb_all)
    return parser


def main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.function(args)
    except Failure as error:
        say(f"overhaul: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
