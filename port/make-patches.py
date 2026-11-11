#!/usr/bin/env python3
"""
make-patches.py — generate port/patches/poplib/*.patch from the PRISTINE
PopLib submodule by applying our reviewed edits and diffing.

Run this once after updating the external/poplib submodule:
    python port/make-patches.py

It never modifies external/poplib. It writes one unified diff per file into
port/patches/poplib/, which port/apply-patches.py later applies with git.
Keeping real .patch files (rather than hard-coded string replacements) means
the fixes stay reviewable and survive upstream line-number changes.
"""
import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
POPLIB = ROOT / "external" / "poplib"
OUT = ROOT / "port" / "patches" / "poplib"

# (relative path, list of (old, new) exact replacements)
EDITS = {
    "CMakeLists.txt": [
        # upstream repo EclipseMenu/discord-presence is gone (404); the empty
        # submodule dir would make add_subdirectory() fail at configure time.
        ("add_subdirectory(external/discordrpc EXCLUDE_FROM_ALL)",
         "if(EXISTS ${POPLIB_ROOT_DIR}/external/discordrpc/CMakeLists.txt)\n"
         "\tadd_subdirectory(external/discordrpc EXCLUDE_FROM_ALL)\n"
         "\tendif()"),
    ],
    "PopLib/math/mtrand.hpp": [
        # restore the mask SexyAppFramework had; without it ~half of Rand()
        # draws are negative and fish drop coins every frame.
        ("\t\treturn dist_int(engine);",
         "\t\treturn dist_int(engine) & 0x7FFFFFFF;"),
    ],
    "PopLib/graphics/imagefont.hpp": [
        # kerning offsets are negative; plain char is unsigned on ARM.
        ("\tchar mKerningOffsets[256];",
         "\tsigned char mKerningOffsets[256];"),
    ],
    "PopLib/graphics/sdlinterface.cpp": [
        # SDL_FColor is 0.0-1.0, not 0-255; unscaled values clamp to white.
        # This exact line appears TWICE (DrawTriangle and DrawTriangleTex).
        ("SDL_FColor aColor = {theColor.GetRed(), theColor.GetGreen(), theColor.GetBlue(), theColor.GetAlpha()};",
         "SDL_FColor aColor = {theColor.GetRed() / 255.0f, theColor.GetGreen() / 255.0f, "
         "theColor.GetBlue() / 255.0f, theColor.GetAlpha() / 255.0f};"),
        ("SDL_FColor color = {(v.color >> 16) & 0xFF, (v.color >> 8) & 0xFF, v.color & 0xFF, (v.color >> 24) & 0xFF};",
         "SDL_FColor color = {((v.color >> 16) & 0xFF) / 255.0f, ((v.color >> 8) & 0xFF) / 255.0f, "
         "(v.color & 0xFF) / 255.0f, ((v.color >> 24) & 0xFF) / 255.0f};"),
        # L1: present at the DESIGN resolution so SDL scales/letterboxes the
        # 640x480 canvas to whatever the window is.
        ("SDL_SetRenderLogicalPresentation(mRenderer, windowWidth, windowHeight, SDL_LOGICAL_PRESENTATION_LETTERBOX)",
         "SDL_SetRenderLogicalPresentation(mRenderer, mWidth, mHeight, SDL_LOGICAL_PRESENTATION_LETTERBOX)"),
        ("mPresentationRect = Rect(0, 0, windowWidth, windowHeight);",
         "mPresentationRect = Rect(0, 0, mWidth, mHeight);"),
    ],
    "PopLib/readwrite/xmlparser.cpp": [
        # resources.xml contains `cols=3` (unquoted). tinyxml2 rejects it,
        # so the whole resource manifest fails to load. Normalise before parse.
        # Anchors avoid line endings: the file is CRLF, so match without \n.
        ("#include \"xmlparser.hpp\"",
         "#include \"xmlparser.hpp\"\n#include <string>"),
        ("    const char* data = aNewWrappedBuffer.c_str();",
         "    aNewWrappedBuffer = QuoteBareAttributeValues(aNewWrappedBuffer);\n"
         "    const char* data = aNewWrappedBuffer.c_str();"),
    ],
}

HELPER = r'''
// PopCap's resources.xml is not valid XML: attributes such as cols=3 are
// unquoted. The original hand-written parser accepted them; tinyxml2 does not.
// Rewrite only inside tags, copying comments/CDATA/text verbatim.
static std::string QuoteBareAttributeValues(const std::string &s)
{
	std::string out;
	out.reserve(s.size() + 64);
	const size_t n = s.size();
	size_t i = 0;
	auto space = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
	while (i < n)
	{
		if (s.compare(i, 4, "<!--") == 0 || s.compare(i, 9, "<![CDATA[") == 0)
		{
			bool cdata = s.compare(i, 9, "<![CDATA[") == 0;
			const char *end = cdata ? "]]>" : "-->";
			size_t j = s.find(end, i);
			if (j == std::string::npos) { out.append(s, i, n - i); break; }
			j += 3;
			out.append(s, i, j - i);
			i = j;
			continue;
		}
		if (s[i] != '<') { out += s[i++]; continue; }
		out += s[i++];
		while (i < n && s[i] != '>')
		{
			if (space(s[i])) { out += s[i++]; continue; }
			if (s[i] == '/' || s[i] == '?') { out += s[i++]; continue; }
			size_t nameStart = i;
			while (i < n && !space(s[i]) && s[i] != '=' && s[i] != '>' && s[i] != '/') ++i;
			out.append(s, nameStart, i - nameStart);
			size_t look = i;
			while (look < n && space(s[look])) ++look;
			if (look < n && s[look] == '=')
			{
				out.append(s, i, look - i);
				i = look + 1;
				while (i < n && space(s[i])) out += s[i++];
				if (i < n && (s[i] == '"' || s[i] == '\''))
				{
					char q = s[i];
					out += s[i++];
					while (i < n && s[i] != q) out += s[i++];
					if (i < n) out += s[i++];
				}
				else
				{
					out += '"';
					size_t valStart = i;
					while (i < n && !space(s[i]) && s[i] != '>' && s[i] != '/') ++i;
					out.append(s, valStart, i - valStart);
					out += '"';
				}
			}
		}
		if (i < n && s[i] == '>') out += s[i++];
	}
	return out;
}

'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True
    for rel, edits in EDITS.items():
        src = POPLIB / rel
        if not src.exists():
            print(f"ERROR missing {rel}")
            ok = False
            continue
        original = src.read_text(encoding="utf-8", newline="")
        text = original
        for old, new in edits:
            n = text.count(old)
            if n == 0:
                print(f"ERROR anchor not found in {rel}: {old[:60]!r}")
                ok = False
                continue
            # replace ALL occurrences: identical FColor lines appear twice.
            text = text.replace(old, new)
            if n > 1:
                print(f"  note: replaced {n} occurrences in {rel}")

        if rel.endswith("xmlparser.cpp"):
            anchor = "bool XMLParser::"
            pos = text.find(anchor)
            if pos < 0:
                print("ERROR: xmlparser insertion anchor missing")
                ok = False
            else:
                text = text[:pos] + HELPER.lstrip("\n") + text[pos:]

        if text == original:
            print(f"SKIP {rel}: no change")
            continue
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}")
        body = "".join(diff)
        name = rel.replace("/", "__") + ".patch"
        (OUT / name).write_text(body, encoding="utf-8", newline="")
        print(f"WROTE port/patches/poplib/{name} ({len(body.splitlines())} lines)")

    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
