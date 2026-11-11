#!/usr/bin/env python3
"""Check out every nested dependency at the exact commit its parent pins.

Why this script exists
---------------------
Upstream poplib declares its dependencies as gitlinks, but a shallow
``git submodule update --init --recursive --depth 1`` leaves two problems:

1. poplib's own submodules get cloned at their *branch tip* instead of the
   pinned commit. With ``--depth 1`` the pinned object is not even in the
   clone, so the worktree ends up empty (only a ``.git`` pointer file).
2. SDL_ttf has a *second* level of vendored submodules (freetype, harfbuzz,
   plutosvg, plutovg) that a shallow clone leaves completely empty. SDL_ttf
   needs FreeType unconditionally, so configure fails with
   "Could not find CMakeLists.txt for harfbuzz in external/harfbuzz".

In addition, ``external/discordrpc`` points at a repository that returns 404.
We deliberately skip it: ``patches/poplib/CMakeLists.txt.patch`` guards that
``add_subdirectory`` with ``if(EXISTS .../CMakeLists.txt)``.

The fix for everything else is the same: fetch the pinned SHA with
``--depth 1`` (GitHub allows fetching a specific SHA) and detach HEAD at it.
This is idempotent -- run it again after any submodule update.

Usage
-----
    python port/init-deps.py            # fix / populate worktrees
    python port/init-deps.py --check  # report only, change nothing
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POPLIB = ROOT / "external" / "poplib"
SDL_TTF = POPLIB / "external" / "SDL_ttf"

# gitlinks in external/poplib that the build actually needs.
# discordrpc is intentionally absent (upstream 404, guarded by our patch).
POPLIB_DEPS = [
    "SDL",
    "SDL_ttf",
    "curl",
    "ogg",
    "openal",
    "tinyxml2",
    "zlib",
    "miniaudio",
    "vorbis",
]

# gitlinks one level deeper, inside external/poplib/external/SDL_ttf.
SDLTTF_DEPS = [
    "freetype",
    "harfbuzz",
    "plutosvg",
    "plutovg",
]


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command without letting a failure raise; caller inspects returncode."""
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def pinned_sha(parent: Path, rel_path: str) -> str | None:
    """Read the gitlink SHA a parent repo records for one submodule path."""
    result = run("git", "ls-tree", "HEAD", "--", rel_path, cwd=parent)
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    if not line:
        return None
    # Format: "160000 commit <sha>\t<path>"
    parts = line.split()
    return parts[2] if len(parts) >= 3 else None


def worktree_files(path: Path) -> int:
    """Count visible entries in a worktree, ignoring the .git pointer/hidden files."""
    if not path.is_dir():
        return 0
    return sum(1 for p in path.iterdir() if p.name != ".git" and not p.name.startswith(".git"))


def ensure(parent: Path, base: str, name: str, check_only: bool) -> bool:
    """Make sure parent/base/name is populated at its pinned commit.

    Returns True when the dependency is healthy (or was successfully fixed).
    """
    rel_path = f"{base}/{name}"
    path = parent / base / name
    sha = pinned_sha(parent, rel_path)
    label = f"{parent.name}/{rel_path}"

    if sha is None:
        print(f"  [SKIP   ] {label}: no gitlink in parent HEAD")
        return True

    has_git_dir = (path / ".git").exists() or path.joinpath(".git").is_file()
    files = worktree_files(path)
    head = run("git", "rev-parse", "HEAD", cwd=path).stdout.strip() if has_git_dir else ""

    if head == sha and files > 0:
        print(f"  [OK     ] {label} @ {sha[:8]} ({files} entries)")
        return True

    if check_only:
        print(f"  [MISSING] {label}: want {sha[:8]}, "
              f"head={head[:8] or 'none'}, entries={files}")
        return False

    # 1. Nothing was cloned yet -> let git create the submodule git dir.
    if not has_git_dir:
        print(f"  [INIT   ] {label}: cloning ...")
        result = run("git", "submodule", "update", "--init", "--depth", "1",
                     "--force", "--", rel_path, cwd=parent)
        if result.returncode != 0:
            print(f"  [FAILED ] {label}: init failed\n{result.stdout.strip()}")
            return False

    # 2. Make sure the pinned object is present. Shallow clones often only have
    #    the branch tip, so fetch that one SHA (small and fast).
    has_object = run("git", "cat-file", "-e", f"{sha}^{{commit}}", cwd=path)
    if has_object.returncode != 0:
        print(f"  [FETCH  ] {label}: fetching pinned {sha[:8]} ...")
        result = run("git", "fetch", "--depth", "1", "--no-tags",
                     "origin", sha, cwd=path)
        if result.returncode != 0:
            print(f"  [FAILED ] {label}: fetch failed\n{result.stdout.strip()}")
            return False

    # 3. Detach at the pinned commit and populate the worktree.
    print(f"  [CHECKOUT] {label} -> {sha[:8]} ...")
    result = run("git", "checkout", "--detach", "-f", sha, cwd=path)
    if result.returncode != 0:
        print(f"  [FAILED ] {label}: checkout failed\n{result.stdout.strip()}")
        return False

    files = worktree_files(path)
    if files == 0:
        print(f"  [FAILED ] {label}: worktree still empty")
        return False
    print(f"  [FIXED  ] {label} @ {sha[:8]} ({files} entries)")
    return True


def check_repo(parent: Path, base: str, names: list[str], check_only: bool) -> int:
    print(f"\n{parent.name} :: {base}/  ({len(names)} dependencies)")
    bad = 0
    for name in names:
        if not ensure(parent, base, name, check_only):
            bad += 1
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report only, do not modify anything")
    args = parser.parse_args()

    for repo in (POPLIB, SDL_TTF):
        if not repo.is_dir():
            print(f"[ERROR] missing repo: {repo}")
            print("        Run: git submodule update --init --recursive")
            return 1

    bad = 0
    bad += check_repo(POPLIB, "external", POPLIB_DEPS, args.check)
    bad += check_repo(SDL_TTF, "external", SDLTTF_DEPS, args.check)

    print()
    if bad:
        print(f"{bad} dependency(ies) not ready. "
              "Re-run without --check to populate them.")
        return 1
    print("All nested dependencies are checked out at their pinned commits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
