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
    python port/run-capture-test.py --driver desktop --only default

`--driver headless` (default) uses SDL's dummy video driver and the software
renderer: fast, no window, proves logic and 640x480 layout.

`--driver desktop` leaves SDL's real video/render drivers alone and opens a
real window. Use it for rendering, windowing, input, or audio changes: the
dummy path cannot reproduce driver-specific failures. An early exit in this
mode is a test failure, and the manifest records the exit code, the last
exported frame and whether crash.txt exists.

The game is expected to still be running when the timeout fires; that is a
successful run, not a crash. A real crash is signalled by an early non-zero
exit or by port/bin/crash.txt.

Functional scenarios
--------------------
Besides the three static scenarios above, ``newuser`` and ``play`` inject
scripted REAL SDL input (via OVERHAUL_INPUT_SCRIPT) to walk the UI state
machine: title -> PLAY -> new-user dialog -> GameSelector -> Help -> Board.
Each scenario declares an ``expect_widget``; the manifest records the widget
classes seen in the state trace, and the run fails if the expected screen is
never reached. This is what makes "clicking PLAY crashes" a reproducible,
automated test instead of a hand-written bug report.
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

# One scripted click stream = one user journey. Frames are AppBase update
# counts; each step waits ~30 frames so the previous screen settles first.
CLICK_PLAY = "100:click:240,427"
NEW_USER_FLOW = (
    "100:click:240,427;"     # title -> GameSelector (+ NewUserDialog)
    "130:text:Tester;"       # type a player name into the focused edit box
    "160:click:230,285"      # OK -> close dialog, profile created
)
PLAY_FLOW = (
    NEW_USER_FLOW + ";"
    "220:click:465,81;"      # Adventure button -> Help screen (first play)
    "280:click:320,427"      # Continue -> Board (the actual level)
)

# scenario -> (extra env, expected widget class substring in the state trace)
SCENARIOS = {
    # Normal play: the dead check-for-updates prompt must NOT appear.
    "default": ({}, None),
    # Regression guard for the dialog renderer: force the modal so we can see
    # that its header/body/button labels are drawn inside the box.
    "force": ({"OVERHAUL_UPDATE_DIALOG": "force"}, None),
    # Reproduce the original first-run condition (fresh profile => prompt).
    "legacy": ({"OVERHAUL_UPDATE_DIALOG": "legacy"}, None),
    # Click PLAY on a fresh profile: used to crash in NewUserDialog because
    # SysFont::Duplicate() shared a TTF_Font* that a destroyed copy closed.
    "newuser": ({"OVERHAUL_INPUT_SCRIPT": CLICK_PLAY}, "NewUserDialog"),
    # Walk all the way into a live board: title -> user -> selector -> help
    # -> tank. Proves the whole "enter game" path, not just the first dialog.
    "play": ({"OVERHAUL_INPUT_SCRIPT": PLAY_FLOW}, "Board"),
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


def run_scenario(name, spec, seconds, driver):
    extra_env, expect_widget = spec
    label = name if driver == "headless" else f"{name}-{driver}"
    work = OUT / label
    profile = work / "profile"
    captures = work / "frames"
    trace_path = work / "state.ndjson"

    # Only ever remove directories inside build/ui-regression. The player's
    # real %LOCALAPPDATA% profile is never touched.
    if work.exists():
        shutil.rmtree(work)
    profile.mkdir(parents=True)
    captures.mkdir(parents=True)

    env = os.environ.copy()
    # Never inherit a driver choice from the caller: the mode is explicit.
    env.pop("SDL_VIDEODRIVER", None)
    env.pop("SDL_RENDER_DRIVER", None)
    if driver == "headless":
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_RENDER_DRIVER"] = "software"
    env.update({
        "OVERHAUL_USER_DATA_DIR": profile.as_posix(),
        "OVERHAUL_CAPTURE_FRAMES": FRAMES,
        "OVERHAUL_CAPTURE_EVERY": "60",
        "OVERHAUL_CAPTURE_MAX": "10",
        "OVERHAUL_CAPTURE_DIR": captures.as_posix(),
        "OVERHAUL_STATE_FILE": trace_path.as_posix(),
        "OVERHAUL_STATE_EVERY": "10",
        "OVERHAUL_STATE_LAST": (work / "state-last.json").as_posix(),
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

    # Collect the distinct widget classes the UI passed through. This is the
    # state-machine evidence: "play" must reach Board, "newuser" must reach
    # NewUserDialog. A scenario that exits early never gets there.
    widgets_seen = set()
    trace_samples = 0
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8",
                                         errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            trace_samples += 1
            for entry in record.get("widgets", "").split("|"):
                if "::" in entry:
                    widgets_seen.add(entry.rsplit("::", 1)[-1].strip())
                elif entry.strip():
                    widgets_seen.add(entry.strip())

    manifest = {
        "scenario": name,
        "label": label,
        "driver": driver,
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
        "state_trace": str(trace_path) if trace_path.exists() else None,
        "state_samples": trace_samples,
        "expect_widget": expect_widget,
        "widgets_seen": sorted(widgets_seen),
        "last_frame": frames[-1]["name"] if frames else None,
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
    if expect_widget and expect_widget not in widgets_seen:
        problems.append(
            f"never reached expected widget {expect_widget!r} "
            f"(saw: {sorted(widgets_seen)})")
    if not frames:
        problems.append("no frames exported")
    for f in frames:
        if not f or (f["width"], f["height"]) != (640, 480):
            problems.append(f"{f and f['name']}: not a 640x480 BMP")
        elif f["bytes"] < 100_000 or f["distinct_sample_bytes"] < 8:
            problems.append(f"{f['name']}: blank or uniform frame")

    print(f"[{label}] driver={driver} frames={len(frames)} "
          f"widgets={len(widgets_seen)} "
          f"expect={expect_widget or '-'} "
          f"registry_keys={len(registry) if isinstance(registry, dict) else 0} "
          f"timeout_ok={timed_out} returncode={proc.returncode} "
          f"problems={len(problems)}")
    for p in problems:
        print(f"    ! {p}")
    print(f"    manifest: {work / 'manifest.json'}")
    print(f"    frames:   {captures}")
    return not problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(SCENARIOS) + ["all"], default="all")
    ap.add_argument("--driver", choices=["headless", "desktop"], default="headless",
                    help="headless=dummy+software; desktop=real SDL drivers")
    ap.add_argument("--seconds", type=int, default=20,
                    help="let the game run this long before terminating it")
    args = ap.parse_args()

    if not EXE.exists():
        print(f"missing {EXE}; run port/build-windows.bat first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    # Scripted journeys need more frames to reach their target screen than a
    # static title capture. Give them a floor regardless of --seconds.
    min_seconds = {"newuser": 14, "play": 24}
    names = list(SCENARIOS) if args.only == "all" else [args.only]
    ok = True
    for name in names:
        seconds = max(args.seconds, min_seconds.get(name, 0))
        if args.driver == "desktop":
            seconds = max(seconds, 30 if name == "play" else 20)
        ok &= run_scenario(name, SCENARIOS[name], seconds, args.driver)

    print("\nRESULT:", "OK" if ok else "FAILED")
    print("All captures used a freshly created, isolated profile; see each "
          "manifest.json for the exact state.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
