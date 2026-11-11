# AGENTS.md — Development Contract

This repository is developed by AI agents under human review. This file is the
contract: it defines the architecture boundary, the only acceptable change
paths, the evidence required before a change is considered done, and what a
human must personally approve.

If the code and this document disagree, stop and resolve the conflict
deliberately. Never edit this file to match an accidental implementation.

**Companion document:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). This file
says *how* a change is delivered; that one says *where it belongs*. The change
model in its §4 (pin / mechanical / behavioural / own code) is normative and is
enforced by review.

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
- `OverhaulCore` static library with unit tests (`ctest`) and a startup banner
  carrying build identity: done (stage S1).
- Change model (pin / mechanical / behavioural / own code): documented in
  `docs/ARCHITECTURE.md`, not yet fully enforced — S2/S3 pending.
- L2/L3, string extraction, Linux/macOS: not started.
- Open defects: see §13.

---

## 2. Architecture: four change classes, one writable layer

Every change belongs to exactly one class. The class fixes the mechanism; see
`docs/ARCHITECTURE.md` §4 for the full model and the reasoning.

| Class | Layer | Path | Mutability | Purpose |
|---|---|---|---|---|
| **P1** | Upstream game | `external/winfish` | **read-only** submodule | Decompiled game logic (Model/Controller) |
| **P1** | Upstream framework | `external/poplib` | **read-only** submodule | SDL3/OpenAL framework (View/platform) |
| **P3** | PopLib fixes | `port/patches/poplib/*.patch` | writable | Reviewed diffs applied to the PopLib work tree |
| **P3** | Whole-file overlay | `port/fixups/Window.cpp` | writable | Replaces an upstream file outright (entry point + crash handler) |
| **P2** | Mechanical derivation | `port/fixups/*.py`, `port/port.sh` | writable | Renames, include rewrites, platform-API removal |
| **P4** | Our C++ | `port/src/overhaul/` | writable | New functionality, compiled and unit tested |
| **P4** | Unit tests | `port/tests/` | writable | `ctest`; no SDL, no window |
| **—** | Derived game source | `port/winfish/` | **generated, gitignored** | Buildable copy produced by `port.sh` |
| **—** | Runtime directory | `port/bin/` | **generated, gitignored** | exe + assets, the only valid working directory |
| **—** | Tooling | `port/tools/`, `port/*.py`, `*.sh`, `*.bat` | writable | One CLI in front of the scripts |

The `port/fixups/*.py` scripts are **legacy-mixed**: they contain both P2
mechanical rules and P3 behavioural fixes, in four overlapping files. Splitting
them along this table is migration stage S3 (`docs/ARCHITECTURE.md` §12). Until
then, a new edit must at least stay in the file whose stated purpose matches:
`apply-gamefixes.py` = behaviour, `apply-portability.py` / `apply-blocks.py` /
`apply-portfeatures.py` = mechanism.

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
- **R6.** **A behavioural change must never be expressed as a mechanical rule.**
  `sed 's/!mPlayingDemoBuffer/true/g'` is a redesign wearing a rename's clothes.
  If it changes what the program does, it is P3: an overlay file or a patch with
  a readable diff.
- **R7.** **A new feature must never be expressed as text appended to an upstream
  file.** It goes in `port/src/` with tests. That library exists precisely so
  this choice is available.
- **R8.** A patch under `port/patches/` must not call into `port/src/`. It would
  invert the dependency and make the patch impossible to offer upstream.

---

## 3. Source-of-truth map

Ask "which class is this change?" first (`docs/ARCHITECTURE.md` §11), then use
this table to find the file.

| You want to change | Class | Edit this | Then regenerate with |
|---|---|---|---|
| New functionality, pure logic | **P4** | `port/src/overhaul/` + `port/tests/` | `overhaul.py build`, `ctest` |
| Entry point / crash handler | **P3** | `port/fixups/Window.cpp` (whole-file overlay) | `overhaul.py derive` |
| PopLib behavior / build | **P3** | `port/make-patches.py` (`EDITS`, `HELPER`, `CAPTURE_FUNC`) | `overhaul.py patch --regenerate` |
| Game behaviour (bugs, port features) | **P3** | `port/fixups/apply-gamefixes.py` | `overhaul.py derive` |
| Mechanical renames / includes / platform API | **P2** | `port/port.sh`, `apply-portability.py`, `apply-blocks.py`, `port/include-map.txt` | `overhaul.py derive` |
| CMake / targets / output name | — | `CMakeLists.txt`, `port/CMakeLists.txt` | `overhaul.py build` |
| Resource table / TTF mapping | — | `port/make-resources.py` | rerun the script |
| Font preparation | — | `port/prepare-font.py` | rerun the script |
| Asset layout | — | `port/copy-assets.sh` | `overhaul.py assets <retail-dir>` |
| UI / i18n design decisions | — | `docs/ARCHITECTURE.md` §9–§10, `docs/UI-I18N-DESIGN.md` | — |
| Verification scenarios | — | `port/run-capture-test.py` | — |

If a change does not fit any row, the model is incomplete: update
`docs/ARCHITECTURE.md` §11 first. Do not invent a new mechanism.

---

## 4. Repository map

```text
CMakeLists.txt               THE build entry: version, four pillar options,
                             include(CTest), add_subdirectory(port)
LICENSE                      AGPL-3.0
README.md                    user-facing entry point (see §11)
THIRD-PARTY-NOTICES.md       dependency attribution
AGENTS.md                    this contract
docs/ARCHITECTURE.md         change model, layering, target layout, migration
docs/UI-I18N-DESIGN.md       UI modernization + TTF design decisions (legacy)
external/winfish             decompiled game (pinned submodule, read-only)
external/poplib              cross-platform framework (pinned submodule, read-only)
port/CMakeLists.txt          OverhaulCore + WinFish + tests
port/src/overhaul/           OUR C++ (P4): buildinfo, env, log, startup
port/tests/                  unit tests, no SDL, ctest
port/tools/overhaul.py       single entry point for every command
port/port.sh                 derive buildable WinFish from the pristine decomp
port/make-patches.py         generate reviewed PopLib patches from pristine
port/apply-patches.py        apply/revert/check the patch set (idempotent)
port/init-deps.py            materialize pinned nested submodules
port/build-windows.bat       MSVC x64 + Ninja build (configures the repo root)
port/prepare-font.py         copy/validate the UI font
port/make-resources.py       rewrite resources.xml to strict XML + TTF
port/copy-assets.sh          copy retail assets, properties, default.xml
port/verify-assets.py        verify every referenced resource exists
port/run-capture-test.py     deterministic headless/desktop UI regression
port/fixups/                 WinFish derivation rules, game fixes, Window.cpp overlay
port/patches/poplib/         generated unified diffs (the only PopLib edits)
port/winfish/                generated, gitignored
port/bin/                    runtime, gitignored
```

The build configures the **repository root**. Configuring `port/` directly used
to bypass the root `CMakeLists.txt`, which silently disabled the four pillar
options, the project version, and `include(CTest)`. Do not reintroduce `-S port`.

---

## 5. Mandatory development loop

Run the steps that apply, **in this order**. Do not skip step 5 for UI changes.

```bash
# 0. Is the tree healthy?
python port/tools/overhaul.py doctor

# 1. Edit the source of truth (§3). Never external/, never port/winfish/.

# 2. PopLib patch changed
python port/tools/overhaul.py patch --regenerate

# 3. WinFish rules or the entry point changed
python port/tools/overhaul.py derive

# 4. Build + unit tests
python port/tools/overhaul.py build
# In restricted sandboxes where vcvarsall/reg.exe is blocked, set
# OVERHAUL_NO_VCVARS=1 before running; the build script then sets INCLUDE/LIB/PATH
# itself.

# 5. Deterministic UI regression
python port/tools/overhaul.py test

# 6. Desktop smoke test — REQUIRED for rendering, windowing, input, or audio
python port/tools/overhaul.py test --driver desktop --only default --seconds 15

# 7. Documentation + commit (see §6 and §10)
```

`overhaul.py build` already runs `init-deps.py` and `apply-patches.py` (through
`build-windows.bat`). Re-running it is safe and is the supported way to build.
`overhaul.py all` runs the whole chain in order.

---

## 6. Definition of Done

A change is done only when **all** applicable boxes are checked, with artifacts:

- [ ] Build exits `0`; the exe is newer than the changed sources.
- [ ] `ctest` green for `OverhaulCore` (required when `port/src/` changed).
- [ ] `overhaul.py doctor` → `all checks passed`.
- [ ] The change is in the class its file declares (§2 R6–R8).
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
| P2 | The four `port/fixups/*.py` scripts mix mechanical rules and behavioural fixes, and three of them are documented in Spanish. | Stage S3 in `docs/ARCHITECTURE.md` §12. Until then, new edits must stay in the file whose stated purpose matches the class. |

Resolved in stage S1 (2026-11-11): the build configured `port/` instead of the
repository root, so the root `CMakeLists.txt` — four pillar options, project
version, `include(CTest)` — was dead code and the exe reported PopLib's version.
Fixed in `port/build-windows.bat` (`-S "%ROOT%"`). Every run now also logs build
identity, so a crash report finally carries the commit, configuration, and
architecture it came from.

---

## 14. Command cheat sheet

One entry point. The verbs delegate to the script that owns each concern, so
these commands stay stable even when the scripts move.

```bash
python port/tools/overhaul.py doctor      # read-only health check
python port/tools/overhaul.py deps --fix  # materialise pinned nested submodules
python port/tools/overhaul.py patch --check
python port/tools/overhaul.py patch --regenerate
python port/tools/overhaul.py derive
python port/tools/overhaul.py build
python port/tools/overhaul.py test
python port/tools/overhaul.py test --driver desktop --only default --seconds 15
python port/tools/overhaul.py assets "<RETAIL_DIR>"
python port/tools/overhaul.py all         # the full chain, in order
```

Unit tests only (fast, no SDL, no build of the game):

```bash
ctest --test-dir build/game --output-on-failure
# or, if ctest is not on PATH, run build/game/tests/bin/overhaul_tests.exe
```

Run the game (working directory matters: it resolves `properties/` relative to
the exe):

```bash
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
| `OVERHAUL_LOG_FILE` | mirror diagnostics into a file (double-click launches) |

Every switch that is set is echoed in the startup banner, so a log always
explains its own run. A new switch must be added to
`port/src/overhaul/startup.cpp` (`kReportedSwitches`) or it will not appear.

---

## 15. Changing this contract

A change to `AGENTS.md` is a process change, not a code change. It requires:

1. a stated failure mode that the current contract allowed;
2. the smallest rule that prevents it;
3. human approval.

Do not add rules that cannot be checked by a command or a reviewer.
