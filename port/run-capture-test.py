#!/usr/bin/env python3
"""
run-capture-test.py -- deterministic, unattended UI regression.

Why this exists
---------------
A headless capture and a real desktop session used to show completely
different screens. PopLib keeps registry.json and userdata/ under
%LOCALAPPDATA%, and SexyApp::ShouldCheckForUpdate() raises an "Updates"
modal on the first run of every fresh profile (and after any ungraceful
shutdown). Whatever the previous run left behind therefore decided what the
next screenshot looked like -- which made visual verification untrustworthy.

The patched build supports two things this script relies on:

  OVERHAUL_USER_DATA_DIR   isolated user-data root (PopLib/common.cpp patch)
  OVERHAUL_CAPTURE_*       frame export without a desktop or keystrokes
                           (PopLib/graphics/sdlinterface.cpp patch)

Every scenario starts from a freshly created profile, exports frames and
writes a manifest recording the exact environment and persistent state, so
any capture is reproducible and self-describing.

Usage
-----
    python port/run-capture-test.py
    python port/run-capture-test.py --only default
    python port/run-capture-test.py --only force
    python port/run-capture-test.py --seconds 25

The game is expected to still be running when the timeout fires; that is a
successful run, not a crash. A real crash is signalled by an early non-zero
exit or by port/bin/crash.txt.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "port" / "bin"
EXE = BIN / "Insaniquarium.exe"
OUT = ROOT / "build" / "ui-regression"

# Frame numbers cover loading, the title screen and the settled state.
FRAMES = "1,30,60,90,120,180,240"

SCENARIOS = {
    # Normal play: the dead check-for-updates prompt must NOT appear.
    "default": {},
    # Regression guard for the dialog renderer: force the modal so we can see
    # that its header/body/button labels are drawn inside the box.
    "force": {"OVERHAUL_UPDATE_DIALOG": "force"},
    # Reproduce the original first-run condition (fresh profile => prompt).
    "legacy": {"OVERHAUL_UPDATE_DIALOG": "legacy"},
}


def bmp_info(path):
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        return None
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    pixels = data[offset:]
    sample = pixels[::997]
    return {
        "name": path.name,
        "bytes": len(data),
        "width": abs(width),
        "height": abs(height),
        "distinct_sample_bytes": len(set(sample)),
        "md5": hashlib.md5(data).hexdigest(),
    }


def run_scenario(name, extra_env, seconds):
    work = OUT / name
    profile = work / "profile"
    captures = work / "frames"

    # Only ever remove directories inside build/ui-regression. The player's
    # real %LOCALAPPDATA% profile is never touched.
    if work.exists():
        shutil.rmtree(work)
    profile.mkdir(parents=True)
    captures.mkdir(parents=True)

    env = os.environ.copy()
    env.update({
        "SDL_VIDEODRIVER": "dummy",
        "SDL_RENDER_DRIVER": "software",
        "OVERHAUL_USER_DATA_DIR": profile.as_posix(),
        "OVERHAUL_CAPTURE_FRAMES": FRAMES,
        "OVERHAUL_CAPTURE_EVERY": "60",
        "OVERHAUL_CAPTURE_MAX": "10",
        "OVERHAUL_CAPTURE_DIR": captures.as_posix(),
    })
    env.update(extra_env)

    proc = subprocess.Popen(
        [str(EXE)], cwd=str(BIN), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        stdout, stderr = proc.communicate()

    out_text = (stdout or b"").decode("utf-8", "replace")
    err_text = (stderr or b"").decode("utf-8", "replace")

    registry_path = None
    registry = None
    for candidate in profile.rglob("registry.json"):
        registry_path = candidate
        try:
            registry = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as exc:
            registry = {"parse_error": str(exc)}
        break

    frame_files = sorted(captures.glob("*.bmp"))
    frames = [bmp_info(p) for p in frame_files]
    crash = BIN / "crash.txt"

    manifest = {
        "scenario": name,
        "exe": str(EXE),
        "exe_md5": hashlib.md5(EXE.read_bytes()).hexdigest() if EXE.exists() else None,
        "profile": str(profile),
        "overrides": {k: env[k] for k in (
            "SDL_VIDEODRIVER", "SDL_RENDER_DRIVER", "OVERHAUL_USER_DATA_DIR",
            "OVERHAUL_CAPTURE_FRAMES", "OVERHAUL_CAPTURE_EVERY",
            "OVERHAUL_CAPTURE_MAX", "OVERHAUL_CAPTURE_DIR",
            "OVERHAUL_UPDATE_DIALOG") if k in env},
        "expected_running_at_timeout": True,
        "timed_out_as_expected": timed_out,
        "returncode": proc.returncode,
        "registry_path": str(registry_path) if registry_path else None,
        "registry": registry,
        "crash_txt": str(crash) if crash.exists() else None,
        "frames": frames,
        "stderr_tail": err_text.splitlines()[-25:],
        "stdout_tail": out_text.splitlines()[-10:],
    }
    (work / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    problems = []
    if not timed_out and proc.returncode != 0:
        problems.append(f"process exited early with {proc.returncode}")
    if crash.exists():
        problems.append("crash.txt exists")
    if not frames:
        problems.append("no frames exported")
    for f in frames:
        if not f or (f["width"], f["height"]) != (640, 480):
            problems.append(f"{f and f['name']}: not a 640x480 BMP")
        elif f["bytes"] < 100_000 or f["distinct_sample_bytes"] < 8:
            problems.append(f"{f['name']}: blank or uniform frame")

    print(f"[{name}] frames={len(frames)} "
          f"registry_keys={len(registry) if isinstance(registry, dict) else 0} "
          f"timeout_ok={timed_out} problems={len(problems)}")
    for p in problems:
        print(f"    ! {p}")
    print(f"    manifest: {work / 'manifest.json'}")
    print(f"    frames:   {captures}")
    return not problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(SCENARIOS) + ["all"], default="all")
    ap.add_argument("--seconds", type=int, default=20,
                    help="let the game run this long before terminating it")
    args = ap.parse_args()

    if not EXE.exists():
        print(f"missing {EXE}; run port/build-windows.bat first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    names = list(SCENARIOS) if args.only == "all" else [args.only]
    ok = True
    for name in names:
        ok &= run_scenario(name, SCENARIOS[name], args.seconds)

    print("\nRESULT:", "OK" if ok else "FAILED")
    print("All captures used a freshly created, isolated profile; see each "
          "manifest.json for the exact state.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
