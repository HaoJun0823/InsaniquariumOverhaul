# Architecture

Status: **normative design**. `AGENTS.md` is the process contract (how a change is
delivered); this document is the technical contract (where a change belongs and
why). If they disagree, stop and reconcile them deliberately.

Audience: an AI agent or a human reviewer who has to answer "where does this
code go?" without guessing. That question is the one this repository used to
answer badly, and most of the damage described in §2 is a consequence.

---

## 1. What this project is

A source-level overhaul of *Insaniquarium Deluxe*, built from the decompiled C++
in `external/winfish`, running on `external/poplib` (a cross-platform rewrite of
PopCap's SexyAppFramework: SDL3 instead of DirectDraw, OpenAL instead of
DirectSound, x64, no Win32 dependency).

Four pillars, unchanged: cross-platform, i18n, HD presentation, compatibility
fixes. This document does not re-prioritise them; it makes them buildable
without turning the repository into a pile of string substitutions.

---

## 2. Diagnosis: why the current structure feels wrong

This is not a style complaint. Each item below is a structural cause with an
observable symptom.

| # | Defect | Evidence | Consequence |
|---|---|---|---|
| D1 | **No compiled home for our own code.** The only writable C++ is a mechanically derived copy of upstream (`port/winfish/`, gitignored) which is deleted on every derive. | `port/` contains 12 scripts and zero `.cpp` files. `port/winfish/` is regenerated. | Every new feature must be smuggled into an upstream file through a byte substitution. There is no place to put a module, so nothing is a module. |
| D2 | **Five owners for one file tree.** WinFish is edited by `port.sh` inline `sed`, `apply-blocks.py`, `apply-portability.py`, `apply-portfeatures.py`, and `apply-gamefixes.py`. | 218 lines of shell + 1365 lines of Python, all writing to `port/winfish/`. | Nobody can tell which script owns which line. Ordering is implicit in `port.sh`. Re-deriving is a coin flip whenever upstream moves. |
| D3 | **Behaviour changes disguised as mechanical transforms.** `sed 's/!mPlayingDemoBuffer/true/g'` is a semantic change living in a rename pipeline. | `port/port.sh:142`. | Review cannot distinguish "translation" from "redesign". A reviewer approving renames also approves gameplay changes without noticing. |
| D4 | **Three languages, no shared library.** Bash + Python + Batch, each recomputing paths, logging formats, and exit codes. | `port/*.sh`, `port/*.py`, `port/*.bat`. | Paths drift; error handling is inconsistent; every script is a special case. |
| D5 | **No unit tests.** The only automated check is a frame-capture harness, which needs a built executable. | `port/run-capture-test.py` is the entire test suite. | Anything not visible in a screenshot is unverified. Pure logic (parsing, layout math, catalogues) cannot be tested at all. |
| D6 | **Contract language drift.** Four derivation scripts are documented in Spanish, inherited from the upstream port this was adapted from; `AGENTS.md` requires English. | Headers of `apply-blocks.py`, `apply-gamefixes.py`, `apply-portfeatures.py`. | The rules say one thing and the code says another. Drift here is how the rest of the contract starts eroding. |

D1 is the root cause. D2–D6 are what a repository looks like when every change
is forced through the only door it has.

---

## 3. Design principles

1. **Upstream stays upstream.** We never fork `winfish` or `poplib`. The value of
   this repository is that upstream can move and we can re-derive. Every design
   decision below protects that property.
2. **Change class determines mechanism.** The mechanism is not a matter of taste;
   it follows from what kind of change it is (§4). This is the single rule that
   prevents D2 and D3.
3. **Generated output is never a source of truth.** If `port/port.sh` erases an
   edit, the edit was in the wrong place.
4. **Verification is layered, and each layer answers a different question**
   (§8). A screenshot cannot prove a parser is correct; a unit test cannot prove
   a window appears.
5. **Readable beats clever.** The maintainer reads Java/Spring MVC. Explicit
   layers with one-way dependencies are a feature, not overhead.

---

## 4. The change model (normative)

Every change in this repository belongs to exactly one class. The class fixes
the mechanism, the review surface, and the evidence required.

| Class | Question it answers | Mechanism | Review surface | Evidence |
|---|---|---|---|---|
| **P1 — Pin** | Which upstream commit do we build? | gitlink in `external/` | one line | `init-deps.py --check`, build |
| **P2 — Mechanical** | How does upstream code become buildable here? | rule table in `port/derive/` | the rule table | derive log, `[FAILED]` count = 0 |
| **P3 — Behavioural** | What does the program do differently? | whole-file `port/overlay/` or `port/patch/` unified diff | the diff | before/after frames or a repro |
| **P4 — Own code** | What did we add that upstream never had? | `port/src/`, compiled into `OverhaulCore` | the source + tests | `ctest` |

### The one rule

> **A P3 change must never be expressed as a P2 mechanism, and a P4 module must
> never be expressed as a P3 patch.**

Corollaries:

- A mechanical transform must be **total and meaning-preserving**. If a reviewer
  cannot agree "this cannot change behaviour" by reading the rule, it is not P2.
- A behavioural change must be a **diff a human can read**. If it is currently a
  `sed` line, it is a bug in the structure, not a shortcut.
- New functionality must be **new files with tests**, not text appended to an
  upstream file. `OverhaulCore` exists so that this is possible.
- A patch must never call into `port/src/`. That inverts the dependency (§5) and
  makes the patch impossible to offer upstream.

### Classifying is mandatory

`port/derive/` and `port/patch/` each carry a header stating what they may
contain. A pull request that puts a behaviour change in `derive/` is rejected on
structure, regardless of whether it works.

---

## 5. Layering and dependency direction

Mapping to the vocabulary of a server-side MVC codebase, which is the mental
model this project is maintained with:

| MVC role | In this codebase | Notes |
|---|---|---|
| **Model** | Game state: tanks, fish, economy, progression (`Board`, `Fish`, `ProfileMgr`, …) | Should not know how it is drawn. Today it often does; see §5.1. |
| **View** | `PopLib` widgets + our layout/theme layer (`port/src/ui/`, planned) | Owns pixels, fonts, scaling. |
| **Controller** | `WinFishApp` screen state machine (title → selector → level) | Owns transitions, not pixels. |
| **Content** | `properties/*.xml`, `default.xml`, fonts, images, audio | Data, not code. Localisable. |
| **Platform** | `PopLib` + SDL3/OpenAL/BASS/SDL_ttf | The only layer allowed to call an OS API. |

Allowed dependency direction — arrows point *down*, never up:

```text
        ┌──────────────────────────────────────────┐
        │ port/src  (OverhaulCore, P4)             │
        │ diagnostics · layout · i18n · scripting  │
        └───────────────▲──────────────────────────┘
                        │ used by
        ┌───────────────┴──────────────────────────┐
        │ derived game (Model + Controller, P2/P3) │
        └───────────────▲──────────────────────────┘
                        │ uses
        ┌───────────────┴──────────────────────────┐
        │ PopLib (View + Platform, P1/P3-patch)    │
        └───────────────▲──────────────────────────┘
                        │ uses
        ┌───────────────┴──────────────────────────┐
        │ SDL3 · OpenAL · BASS · SDL_ttf · FreeType│
        └──────────────────────────────────────────┘
```

Forbidden arrows, with the reason:

- **PopLib → `port/src`**: a patch that calls our library cannot be upstreamed
  and cannot be tested without us. Patched framework code stays self-contained.
- **Model → SDL/PopLib graphics types**: simulation must be testable without a
  window. When Model needs a size, it asks a value object, not the renderer.
- **View → direct file/database access**: resources go through
  `ResourceManager`, settings through the app's registry abstraction.
- **`OverhaulCore` → PopLib**: the library must stay linkable into the unit test
  binary, which has no SDL. Pure modules include only the standard library.

### 5.1 Honest scope of this boundary

The decompiled game is a 2001-era 2D codebase in which `Board::Draw` and
`Board::Update` live in the same class. A big-bang MVC refactor would trade a
working build for an unverifiable one, which violates principle 4.

Therefore: **the boundary is enforced for new code and for code we touch, not
retroactively by decree.** Concretely — new files go in the correct layer; an
existing file is only split when a change already requires editing it and the
seam is cheap; no refactor is proposed whose only justification is architectural
purity.

---

## 6. Repository layout (target)

The target layout is where the repository is going. The **stage** column says
when each part lands; `AGENTS.md §7` tracks the current stage.

```text
CMakeLists.txt              top-level options, CTest, add_subdirectory(port)
AGENTS.md                   process contract
docs/ARCHITECTURE.md        this document
docs/UI-I18N-DESIGN.md      detailed UI/i18n decisions (legacy, migrates on edit)

external/                   P1: pinned submodules, read-only, never staged
  winfish/                  decompiled game
  poplib/                   framework

port/
  CMakeLists.txt            build entry: OverhaulCore, WinFish, tests
  src/overhaul/             P4: our C++, the only place new code lives
    buildinfo.*             build identity
    env.*                   OVERHAUL_* switch parsing
    log.*                   diagnostic channel
    startup.*               run banner
  tests/                    P4: unit tests, no SDL, ctest
  overlay/                  P3: whole-file replacements of upstream files     [S3]
  patch/                    P3: unified diffs + generator + applier          [S2]
  derive/                   P2: mechanical transforms only                    [S2]
    include-map.txt
    rules/                  rename, include, platform-API removal
  tools/                    tooling, one entry point
    overhaul.py             CLI: doctor/deps/patch/derive/build/test/assets
  assets/                   resource tables, fonts, i18n catalogues
  bin/                      runtime output, gitignored, never a source
```

Notation: `[S2]`/`[S3]` are migration stages from §12 — the directory does not
exist yet at the time of writing.

Why `overlay/` is separate from `patch/`: a whole-file replacement is reviewable
as a file (read it, compare it), while a diff is reviewable as a delta. Mixing
them makes both harder. Today `port/fixups/Window.cpp` is an overlay living in
the wrong folder.

---

## 7. Build targets

| Target | Type | Contents | Must not contain |
|---|---|---|---|
| `OverhaulCore` | static lib | `port/src/**` | SDL, PopLib, game headers |
| `WinFish` | executable | derived game + `OverhaulCore` + `PopLib` | generated files edited by hand |
| `overhaul_tests` | executable | `port/tests/**` | SDL, a window, a device |

`overhaul_tests` links `OverhaulCore` only. If a test needs a renderer, it is not
a unit test — it belongs to the capture harness.

---

## 8. Verification pyramid

Each layer answers a question the layer below cannot.

| Layer | Tool | Question | Fails when |
|---|---|---|---|
| 1. Unit | `ctest` | Is the pure logic correct? | parser, layout math, catalogue lookup |
| 2. Integrity | `overhaul.py doctor` | Is the tree in a valid state? | pin drift, patch not applicable, missing asset, dirty generated output |
| 3. Headless capture | `OVERHAUL_CAPTURE_*` + `run-capture-test.py` | Does it load, lay out, and reach the expected screen? | resources, layout, state machine |
| 4. Desktop capture | same, real video driver | Does it work outside SDL's dummy driver? | windowing, focus, vsync, input |
| 5. Human review | eyes | Does it look right? | taste, typography, animation feel |

Layers 1–4 are automated and must be green before a review request. Layer 5 is
the reviewer's job and cannot be delegated to a script; a capture frame narrows
what to look at, it does not replace looking.

---

## 9. UI architecture

Three presentation layers, sequential, never mixed:

- **L1 — fixed logical canvas (done).** Game logic keeps its original 640×480
  coordinates. SDL scales the canvas into the window and letterboxes the rest.
  No new absolute coordinates may be introduced outside the design layer.
- **L2 — anchored layout (next).** UI is placed relative to anchors. A wide
  window gains space; it does not stretch 4:3 art.
- **L3 — HD assets (later).** A separate asset set. Runtime upscaling of the
  original bitmaps is not HD and must not be labelled as such.

### L2 interface (target, not yet implemented)

```cpp
namespace overhaul::ui {

struct Size { int width; int height; };
struct Rect { int x; int y; int width; int height; };

// Value type: cheap to copy, no globals, no SDL. Constructed from the window
// size, consumed by screens that need to place something.
class LayoutContext
{
public:
    static constexpr int kDesignWidth  = 640;
    static constexpr int kDesignHeight = 480;

    static LayoutContext FromWindow(Size window);

    Size   design() const;    // 640x480
    Size   window() const;
    double scale() const;     // uniform: min(w/dw, h/dh)
    Rect   viewport() const;  // centred letterbox rect, integer pixels
    bool   isWide() const;    // window aspect ratio > design aspect ratio
    int    extraWidth() const;  // pixels a wide window gained; anchors use this
};

} // namespace overhaul::ui
```

Rules for L2:

- Anchors are declared as `(edge, offset, size rule)`, not as absolute numbers.
- A screen that still uses absolute coordinates is a screen that has not been
  migrated; it must not be half-migrated (mixed anchors and constants).
- `LayoutContext` is pure math so it can be unit-tested at every window size
  from 640×480 to 3840×2160, including degenerate sizes.

### Fonts

TTF only for new UI. `ImageFont` is a 256-slot bitmap font and cannot carry CJK;
it is legacy and must not gain new text. `SysFont` (SDL_ttf) is the only text
path, and it must honour `Graphics::Translate()` — a past bug where it did not
put every dialog's text at the top-left corner of the screen.

---

## 10. i18n architecture

- **Container**: the existing PopCap resource XML. No new format, no new parser,
  no parallel string table. Strings are addressed by their existing IDs.
- **Resolution order**: `OVERHAUL_LOCALE` → stored player setting → system
  locale → `en`. The resolved locale is printed in the startup banner, so a
  screenshot always says which language produced it.
- **No concatenation.** A sentence assembled from fragments cannot be translated.
  Word order, plurals, and gender belong inside one string.
- **Pseudo-locale** (`qps`): every string accented and 30% longer. Any layout
  that survives the pseudo-locale survives most real languages; this is the only
  cheap way to test a layout without speaking twelve languages.
- **Fonts are content, not code.** The repository ships no font binary; releases
  require an OFL-licensed font.

---

## 11. Adding code: decision tree

Answer in order; the first match wins.

1. **Does it change which upstream commit we build?** → P1. Stop; needs human
   approval.
2. **Does it change behaviour of upstream code?** → P3.
   - Replacing most of a file → `port/overlay/`.
   - A surgical change → `port/patch/` (generated from a rule, applied to a
     pristine tree).
3. **Is it new functionality that upstream never had?** → P4, `port/src/`, with
   a unit test in `port/tests/`.
4. **Is it a rename, an include rewrite, or the removal of a platform-only API
   with a portable equivalent?** → P2, `port/derive/`.
5. **Is it a resource, a translation, or a font?** → `port/assets/`.
6. **None of the above** → the model is incomplete. Fix this document first;
   do not invent a seventh mechanism.

---

## 12. Migration stages

Each stage is independently reviewable, and **no stage may contain unrelated
feature work**. Exit criteria are commands, not opinions.

| Stage | Scope | Exit criteria |
|---|---|---|
| **S0** (done) | Process contract + deterministic capture | `AGENTS.md` exists; three capture scenarios pass from isolated profiles |
| **S1** (done) | `OverhaulCore` + unit tests + startup banner | `ctest` green; every run logs build identity; `WinFish` links the library |
| **S2** | Tooling consolidation: `port/tools/overhaul.py` as the only documented entry point; move commands to `port/tools/commands/`, diffs to `port/patch/`, mechanical rules to `port/derive/` | `overhaul.py doctor` green; `AGENTS.md` cheat sheet lists only CLI verbs; zero behaviour change |
| **S3** | Split the five WinFish editors along §4: mechanical rules out of `apply-gamefixes.py`; `Window.cpp` into `overlay/`; Spanish headers translated | each script's header states its class; no `sed` line changes behaviour |
| **S4** | L2 layout: `LayoutContext` + anchors for the six screens | unit tests at 5 resolutions; before/after frames; no stretched art |
| **S5** | i18n extraction: catalogue + locale resolution + pseudo-locale run | pseudo-locale frames show no clipped or overlapping text |
| **S6** | Linux/macOS | build + capture harness green on both; Windows unregressed |

S2 and S3 are pure restructuring: they must not change a single pixel. That is
what makes them safe to do before feature work resumes.

---

## 13. Rejected alternatives

| Alternative | Why it was rejected |
|---|---|
| **Fork `poplib`** and edit in place | Loses upstream sync. A patch set fails loudly when upstream moves; a fork fails silently by drifting. |
| **Rewrite in Rust** | ~219k lines of game logic. The rewrite would consume the project and produce no playable build for months. |
| **Move all sources into `src/`** | Abandons re-derivation from upstream, which is the only reason this project is maintainable across decompiler updates. |
| **Adopt a UI framework** (Dear ImGui, CEGUI) | The game's screens are custom-drawn art. A second UI system would duplicate layout, theming, and input, and would still not draw the game. |
| **Big-bang MVC refactor** | No test coverage to protect the refactor. It would replace a working build with an unverifiable one. |
| **Keep everything in `sed`** | Fast to write, impossible to review, and it is what produced D2/D3. |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Pin** | The exact upstream commit baked into a gitlink. |
| **Derive** | Produce a buildable tree from pristine upstream by mechanical transformation. |
| **Overlay** | A whole file that replaces its upstream counterpart. |
| **Patch** | A unified diff applied to a pristine tree, generated from a reviewed rule. |
| **Fixup** | Legacy name for any post-derive edit. Being retired in S3 in favour of P2/P3. |
| **Logical canvas** | The 640×480 coordinate space game logic draws in. |
| **Letterbox** | Uniform scaling of the canvas into the window, with bars where the aspect ratio does not match. |
| **Pseudo-locale** | A fake translation (accented, 30% longer) used to test layout robustness. |
