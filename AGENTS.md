# AGENTS.md — Development Contract

This repository is developed by AI agents under human review. This file is the
contract: it defines the architecture boundary, the only acceptable change
paths, the evidence required before a change is considered done, and what a
human must personally approve.

If the code and this document disagree, stop and resolve the conflict
deliberately. Never edit this file to match an accidental implementation.

---

## 0. TL;DR

1. `external/` is **read-only**. Every behavior change lives in `port/`.
2. Never edit generated code (`port/winfish/`). Change its generator.
3. Never commit game assets, fonts, binaries, saves, or captures.
4. Build, then run the deterministic UI regression, before claiming success.
5. Every claim needs evidence: command, exit code, artifact path.
6. If you cannot reproduce a bug, say so. **Do not guess-fix.**
7. New documentation, code comments, and commit messages are in **English**.

---

## 1. Project

**Insaniquarium Overhaul** is a source-level rebuild of *Insaniquarium Deluxe*
from the decompiled C++ in `external/winfish`, running on `external/poplib`
(a cross-platform rewrite of PopCap's SexyAppFramework: SDL3 instead of
DirectDraw, OpenAL instead of DirectSound, x64, no Win32 dependency).

Four pillars, in priority order:

1. **Cross-platform** — Windows today; Linux/macOS next.
2. **Internationalization** — UTF-8, TTF fonts, externalized strings.
3. **HD presentation** — logical 640×480 now; anchored layout and HD art later.
4. **Compatibility fixes** — correct bugs in the decompiled source.

License: **AGPL-3.0**. Retail assets and font binaries are never distributed.

Current state (2026-11-11):

- L1 presentation (640×480 logical canvas + SDL letterbox) and TTF fonts: done.
- Windows x64 build, link, and headless UI regression: passing.
- L2/L3, string extraction, Linux/macOS: not started.
- Open defects: see §13.

---

## 2. Architecture: three layers, one writable layer

| Layer | Path | Mutability | Purpose |
|---|---|---|---|
| Upstream game | `external/winfish` | **read-only** submodule | Decompiled game logic (Model/Controller) |
| Upstream framework | `external/poplib` | **read-only** submodule | SDL3/OpenAL framework (View/infrastructure) |
| PopLib fixes | `port/patches/poplib/*.patch` | writable | Reviewed fixes applied to the PopLib work tree |
| Game fixes | `port/fixups/*.py`, `port/port.sh` | writable | Derivation rules for WinFish |
| Derived game source | `port/winfish/` | **generated, gitignored** | Buildable copy produced by `port.sh` |
| Runtime directory | `port/bin/` | **generated, gitignored** | exe + assets, the only valid working directory |
| Build scripts | `port/*.py`, `port/*.sh`, `port/*.bat` | writable | Tooling |

### Non-negotiable rules

- **R1.** `external/` is never modified. Do not `git add` it, do not hand-edit
  it, do not commit a changed gitlink. A dirty `external/poplib` work tree is
  the *expected* result of applying patches.
- **R2.** PopLib behavior changes go through `port/make-patches.py` (the
  generator), never directly into the patch file and never into the submodule.
- **R3.** WinFish behavior changes go through `port/fixups/*.py` or
  `port/port.sh`, never into `port/winfish/` (it is deleted on every derive).
- **R4.** `port/bin/` is runtime output. It is never a source of truth.
- **R5.** A change that survives only until the next derive is in the wrong
  place. If `bash port/port.sh` erases it, it was not a real change.

---

## 3. Source-of-truth map

| You want to change | Edit this | Then regenerate with |
|---|---|---|
| PopLib behavior / build | `port/make-patches.py` (`EDITS`, `HELPER`, `CAPTURE_FUNC`) | `make-patches.py` → `apply-patches.py` |
| Game behavior (bugs, port features) | `port/fixups/apply-gamefixes.py`, `apply-portfeatures.py`, `apply-blocks.py`, `apply-portability.py` | `bash port/port.sh` |
| CMake / targets / output name | `CMakeLists.txt`, `port/CMakeLists.txt` | `port\build-windows.bat` |
| Resource table / TTF mapping | `port/make-resources.py` | rerun the script |
| Font preparation | `port/prepare-font.py` | rerun the script |
| Asset layout | `port/copy-assets.sh` | rerun the script |
| UI / i18n design | `docs/UI-I18N-DESIGN.md` | — |
| Automated UI verification | `port/run-capture-test.py` | — |

---

## 4. Repository map

```text
CMakeLists.txt               top-level options + add_subdirectory(port)
LICENSE                      AGPL-3.0
README.md                    user-facing entry point (see §11)
THIRD-PARTY-NOTICES.md       dependency attribution
AGENTS.md                    this contract
docs/UI-I18N-DESIGN.md       UI modernization + TTF design decisions
external/winfish             decompiled game (pinned submodule)
external/poplib              cross-platform framework (pinned submodule)
port/port.sh                 derive buildable WinFish from the pristine decomp
port/make-patches.py         generate reviewed PopLib patches from pristine
port/apply-patches.py        apply/revert/check the patch set (idempotent)
port/init-deps.py            materialize pinned nested submodules
port/build-windows.bat       MSVC x64 + Ninja build
port/prepare-font.py         copy/validate the UI font
port/make-resources.py       rewrite resources.xml to strict XML + TTF
port/copy-assets.sh          copy retail assets, properties, default.xml
port/verify-assets.py        verify every referenced resource exists
port/run-capture-test.py     deterministic headless UI regression
port/fixups/                 WinFish derivation rules and game fixes
port/patches/poplib/         generated unified diffs (the only PopLib edits)
port/winfish/                generated, gitignored
port/bin/                    runtime, gitignored
```

---

## 5. Mandatory development loop

Run the steps that apply, **in this order**. Do not skip step 6 for UI changes.

```bash
# 0. Dependencies
python port/init-deps.py --check

# 1. Edit the source of truth (never external/, never port/winfish/)

# 2. PopLib patch changed:
python port/apply-patches.py --revert
python port/make-patches.py
python port/apply-patches.py

# 3. WinFish fixup changed:
bash port/port.sh

# 4. Build
port\build-windows.bat
# In restricted sandboxes where vcvarsall/reg.exe is blocked:
#   PowerShell: $env:OVERHAUL_NO_VCVARS = "1"
#   cmd:        set OVERHAUL_NO_VCVARS=1

# 5. Deterministic UI regression
python port/run-capture-test.py

# 6. Desktop smoke test — REQUIRED for rendering, windowing, input, or audio
python port/run-capture-test.py --driver desktop --only default --seconds 15
#    Or run port/bin/Insaniquarium.exe directly with the real video driver.
#    Record: duration, exit code, crash.txt presence, last exported frame.

# 7. Documentation + commit (see §6 and §10)
```

`port\build-windows.bat` already runs `init-deps.py` and `apply-patches.py`.
Re-running it is safe and is the supported way to build.

---

## 6. Definition of Done

A change is done only when **all** applicable boxes are checked, with artifacts:

- [ ] Build exits `0`; the exe is newer than the changed sources.
- [ ] `python port/apply-patches.py --check` → `nothing changed`.
- [ ] `python port/init-deps.py --check` → all pinned commits OK.
- [ ] `python port/verify-assets.py` → all referenced resources present.
- [ ] `python port/run-capture-test.py` → `RESULT: OK`.
- [ ] No `port/bin/crash.txt` after the run.
- [ ] UI change: before/after frames exported, both from a fresh isolated
      profile, and the difference is explained.
- [ ] Rendering/windowing change: a real-driver desktop run (step 6).
- [ ] Docs updated (`README.md`, `docs/`, or this file) when behavior changes.
- [ ] Commit message and change package follow §10.

Skipping a check is allowed only with a written reason in the commit body, and
that reason must be re-checked by a human.

---

## 7. Evidence standard

**Claims without artifacts are not accepted.**

| Claim | Minimum evidence |
|---|---|
| "It builds" | build log tail + exit code + `ls -l port/bin/Insaniquarium.exe` |
| "UI is fixed" | exported frame paths + `manifest.json` + before/after diff |
| "It does not crash" | run duration, exit code, `crash.txt` absence, last frame |
| "Assets are complete" | `verify-assets.py` output |
| "Patch is clean" | `apply-patches.py --check` output |
| "Fixup is applied" | `[ok]` / `[already applied]` lines, zero `[FAILED]` |

Hard limits of headless capture (`SDL_VIDEODRIVER=dummy`):

- Proves logic, loading, 640×480 layout, and absence of fatal errors.
- Does **not** prove real-driver rendering, input handling, audio, vsync,
  window focus, or timing-dependent state.
- Never present a headless frame as proof that the desktop build works.

Never use a desktop screenshot as the *only* evidence: screenshots are not
reproducible, and the previous investigation showed two sessions can display
different states. Pair every screenshot with a manifest or a state dump.

**Crash claims require**: exact command, build identity (commit + exe hash),
exit code, `crash.txt` (or an explicit statement that it is absent), and a
minimal reproduction. "It crashed" alone is not a report.

---

## 8. Known traps

| Trap | Symptom | Rule |
|---|---|---|
| CRLF anchors | `make-patches.py` reports anchor not found on `PopLib/common.cpp` | Multi-line anchors must tolerate CRLF; the generator retries automatically. Keep new anchors single-line when possible. |
| Submodule dirty | `external/poplib` shows `m` | Expected after `apply-patches.py`. Never `git add external/`. |
| Nested gitlinks | empty submodule work trees / wrong SHA | `init-deps.py`; never bump a pin without human review. |
| Missing `bass.dll` | exe starts then exits, or no audio | `port/CMakeLists.txt` copies it POST_BUILD; verify `port/bin/bass.dll`. |
| `default.xml` moved | resource load failure / English fallback | An old CN patch moved it under `old_cn_patch/`; `copy-assets.sh` searches several paths. |
| Persistent state | first-run UI differs between sessions | PopLib stores `registry.json` + `userdata/` under `%LOCALAPPDATA%`. Use `OVERHAUL_USER_DATA_DIR` for tests; never delete the player's real profile. |
| TTF metrics | widget text at the top-left, empty buttons | `SysFont::DrawString` must apply `Graphics::Translate()` (`mTransX`/`mTransY`). `ImageFont` gets this via `DrawImage`. |
| SDL dummy | passes headless, fails on the desktop | Dummy is not a rendering test. Real-driver smoke test is mandatory for UI. |
| PopCap XML dialect | `XML_ERROR_PARSING_ATTRIBUTE` | Bare attributes (`cols=3`) and private entities (`&cr;`, `&nbsp;`) are normalized in `xmlparser.cpp`. |
| 256-glyph `ImageFont` | CJK missing or wrong glyphs | Never use `ImageFont` for CJK. Use `SysFont` (SDL_ttf). |
| Hardcoded 640×480 | layout breaks at other sizes | L1 letterboxes; L2 must use anchors, not new magic coordinates. |
| Ungraceful shutdown | update prompt appears on next launch | `InProgress: 1` means "previous run did not exit cleanly". Do not kill the process during normal testing. |

---

## 9. Code rules

- **C++17**, matching the existing style. Do not introduce a new framework,
  allocator, or abstraction layer without explicit approval.
- **Readable beats clever.** Explicit names, small functions, no template
  metaprogramming for its own sake. The maintainer reads Java/Spring MVC; treat
  clear boundaries as a feature.
- **One concern per patch/fixup.** A patch that fixes two unrelated things must
  be split.
- **Comments explain *why***, not *what*. Record the observed symptom, the
  cause, and why this fix is correct.
- **No silent failure.** If a resource, font, texture, or file is missing,
  log it and fail visibly. Never return a plausible default.
- **No new magic numbers.** Name constants. UI coordinates belong to the design
  layer (§12), not to gameplay code.
- **UTF-8 only.** `/utf-8` is mandatory for MSVC; `PopString` is `std::string`.
- **No Win32-only APIs in `port/`.** Use SDL/PopLib so Linux/macOS remain viable.
- **Never fix generated output.** Fix `port.sh` / `make-patches.py` / `fixups/`.

---

## 10. Review protocol (human in the loop)

AI agents may implement end-to-end, but **may not self-approve**. Every change
is delivered as a review package:

```markdown
## Intent
What user-visible problem this solves, and why now.

## Files
Exact paths changed, and which layer each belongs to.

## Evidence
Commands + exit codes + artifact paths (frames, manifest, logs).

## Risks / rollback
What can break; how to revert (commit hash / `apply-patches.py --revert`).

## Follow-ups
Known gaps intentionally left out of this change.
```

Human reviewer checklist:

1. No `external/` modification and no gitlink change.
2. No generated file (`port/winfish/`, `port/bin/`) edited or staged.
3. No assets, fonts, saves, or binaries staged.
4. Evidence is reproducible from a clean state, not from a warm work tree.
5. Docs and `AGENTS.md` are still true.
6. License and font obligations respected.

**Requires explicit human approval, never auto-merged:**

- changing a submodule pin or adding a dependency;
- changing `LICENSE`, `THIRD-PARTY-NOTICES.md`, or the font license;
- adding binary assets or fonts to the repository;
- changing CI, release, or publishing configuration;
- disabling or weakening any check in §6.

---

## 11. Documentation and language

- **All new documentation is written in English**: this file, the PR template,
  design notes, code comments, commit messages, and script output intended for
  developers.
- `README.md` and `docs/UI-I18N-DESIGN.md` are legacy Chinese documents. They
  must be migrated to English when substantially edited; until then, keep them
  accurate rather than translating them piecemeal.
- User-facing text in the game is **not** documentation: it belongs in the
  resource table and is subject to the i18n rules in §12.
- Commit messages: imperative subject, English body, evidence in the body.

---

## 12. Roadmap constraints

### Presentation layers

- **L1 (done)**: fixed 640×480 logical canvas, SDL letterbox. Game logic keeps
  its original coordinates. Do not add new absolute coordinates outside L1.
- **L2 (next)**: anchored layout. Introduce a `LayoutContext` (design size,
  actual size, safe area, scale) and place UI relative to anchors. Wide screens
  must gain space, not stretch art.
- **L3 (later)**: HD/vector art as a separate asset set. Never upscale the 4:3
  bitmaps at runtime and call it HD.

### Fonts and i18n

- TTF only for new UI. The baked bitmap fonts are legacy; `ImageFont` is
  limited to 256 glyphs and cannot carry CJK.
- Every user-visible string comes from `properties/*.xml` or `default.xml`.
  No concatenated grammar, no hardcoded English in new code.
- UTF-8 end-to-end. Test with a CJK string and a long Latin string.
- The repository must not contain font binaries. The development font
  (`ui.ttf`) is a local system-font copy; releases require an OFL-licensed
  font (see `port/assets/fonts/README.md`).

### Platforms

- Windows x64 is the reference build.
- Linux/macOS work must not regress Windows; use PopLib/SDL abstractions.
- Any new platform-specific code needs a `#ifdef` with a portable fallback.

---

## 13. Known issues (2026-11-11)

| Severity | Issue | Status / next step |
|---|---|---|
| **P0** | User reports "crash on entry" (2026-11-11). Automated desktop-driver runs are **stable**: 12 s, 6 frames, no `crash.txt`, clean timeout. The earlier `exit 127` came from `timeout`/background-shell handling of a GUI process, not from the game. | Needs a minimal user-side repro: exact exe path, command, screen where it stops, exit code. Do not change code until it is reproduced. |
| **P0** | No automated input injection. The path title → PLAY → game selector → level is not covered by any test. | Add a frame-scheduled input hook (mouse/key) to the capture channel, then extend `run-capture-test.py`. |
| P1 | `ui.ttf` is a local copy of a system font. | Replace with an OFL font before any release. |
| P1 | L2/L3, string extraction, Linux/macOS. | See §12. |
| P2 | Two legacy FishSongMgr fixups were reporting false `[FAILED]` because upstream already contains the fix. | Anchors corrected; the derive log is now clean. |

---

## 14. Command cheat sheet

```bash
# dependencies
python port/init-deps.py --check

# PopLib patch set
python port/apply-patches.py --check
python port/apply-patches.py --revert
python port/make-patches.py
python port/apply-patches.py

# derive WinFish
bash port/port.sh

# build
port\build-windows.bat

# deterministic UI regression (3 scenarios, isolated profiles)
python port/run-capture-test.py
python port/run-capture-test.py --only force

# assets
bash port/copy-assets.sh "<RETAIL_DIR>"
python port/verify-assets.py

# run (working directory matters)
cd port/bin && ./Insaniquarium.exe
```

Useful environment variables:

| Variable | Effect |
|---|---|
| `OVERHAUL_NO_VCVARS=1` | build without `vcvarsall.bat` (restricted sandbox) |
| `OVERHAUL_USER_DATA_DIR` | isolated registry/userdata root (tests only) |
| `OVERHAUL_CAPTURE_FRAMES` | exact frame numbers to export |
| `OVERHAUL_CAPTURE_EVERY` | periodic frame sampling |
| `OVERHAUL_CAPTURE_MAX` | cap on sampled frames |
| `OVERHAUL_CAPTURE_DIR` | capture output directory |
| `OVERHAUL_UPDATE_DIALOG` | `legacy` or `force`; unset disables the dead update prompt |

---

## 15. Changing this contract

A change to `AGENTS.md` is a process change, not a code change. It requires:

1. a stated failure mode that the current contract allowed;
2. the smallest rule that prevents it;
3. human approval.

Do not add rules that cannot be checked by a command or a reviewer.
