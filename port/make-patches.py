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

# Unattended frame capture, injected into SDLInterface::Redraw. The automated
# UI smoke test runs the game headless (SDL_VIDEODRIVER=dummy) and reads these
# BMPs; no desktop, window focus, or injected keystroke (F11) is required.
# Zero cost when none of the OVERHAUL_CAPTURE_* variables are set.
CAPTURE_FUNC = r'''
// Overhaul: unattended frame capture for the automated UI smoke test.
//   OVERHAUL_CAPTURE_FRAMES=1,60,240   exact 1-based Redraw frame numbers
//   OVERHAUL_CAPTURE_EVERY=60          periodic sampling instead / in addition
//   OVERHAUL_CAPTURE_MAX=12            cap on periodic captures
//   OVERHAUL_CAPTURE_DIR=captures      output directory, created on demand
// Reading the composited frame BEFORE SDL_RenderPresent also works with the
// dummy video driver, so this needs no desktop, focus, or injected keystroke.
static void OverhaulMaybeCapture(SDL_Renderer *theRenderer, int theFrame)
{
	static bool sInit = false;
	static std::vector<int> sFrames;
	static int sEvery = 0;
	static int sMax = 0;
	static int sWritten = 0;
	static std::string sDir;
	if (!sInit)
	{
		sInit = true;
		const char *aSpec = std::getenv("OVERHAUL_CAPTURE_FRAMES");
		const char *aEvery = std::getenv("OVERHAUL_CAPTURE_EVERY");
		const char *aMax = std::getenv("OVERHAUL_CAPTURE_MAX");
		const char *aOut = std::getenv("OVERHAUL_CAPTURE_DIR");
		sDir = (aOut && *aOut) ? aOut : "captures";
		sEvery = aEvery ? std::atoi(aEvery) : 0;
		sMax = aMax ? std::atoi(aMax) : 0;
		if (aSpec)
		{
			std::stringstream aSS(aSpec);
			std::string aToken;
			while (std::getline(aSS, aToken, ','))
			{
				int aF = std::atoi(aToken.c_str());
				if (aF > 0)
					sFrames.push_back(aF);
			}
		}
		if (!sFrames.empty() || sEvery > 0)
		{
			std::error_code aEC;
			std::filesystem::create_directories(sDir, aEC);
			std::fprintf(stderr, "[overhaul-capture] dir=%s frames=%zu every=%d max=%d\n",
				sDir.c_str(), sFrames.size(), sEvery, sMax);
		}
	}
	bool aWant = !sFrames.empty() &&
		std::find(sFrames.begin(), sFrames.end(), theFrame) != sFrames.end();
	if (!aWant && sEvery > 0 && theFrame % sEvery == 0 && (sMax <= 0 || sWritten < sMax))
	{
		aWant = true;
		++sWritten;
	}
	if (!aWant)
		return;

	SDL_Surface *aSurface = SDL_RenderReadPixels(theRenderer, nullptr);
	if (!aSurface)
	{
		std::fprintf(stderr, "[overhaul-capture] frame %d read failed: %s\n", theFrame, SDL_GetError());
		return;
	}
	SDL_Surface *aRGB = SDL_ConvertSurface(aSurface, SDL_PIXELFORMAT_RGB24);
	char aPath[512];
	std::snprintf(aPath, sizeof(aPath), "%s/frame_%05d.bmp", sDir.c_str(), theFrame);
	bool aOK = aRGB && SDL_SaveBMP(aRGB, aPath);
	std::fprintf(stderr, "[overhaul-capture] frame %d -> %s %s\n", theFrame, aPath,
		aOK ? "ok" : (aRGB ? SDL_GetError() : "convert failed"));
	if (aRGB)
		SDL_DestroySurface(aRGB);
	SDL_DestroySurface(aSurface);
}
'''

# (relative path, list of (old, new) exact replacements)
EDITS = {
    "PopLib/common.cpp": [
        # The game's entire persistent state (registry.json, userdata/) lives
        # under GetAppDataFolder(). On a real desktop that is %LOCALAPPDATA%,
        # so a "first run" screenshot depends on whatever the previous run
        # left behind. Let the automated UI test point at a fresh, isolated
        # directory instead: same binary, deterministic first-run state, and
        # the player's real profile is never touched.
        ("#ifdef _WIN32\n"
         "std::string gAppDataFolder = std::filesystem::path(std::getenv(\"LOCALAPPDATA\")).string() + \"/\";\n"
         "#else\n"
         "std::string gAppDataFolder = std::filesystem::path(std::getenv(\"HOME\")).string() + \"/.config/\";\n"
         "#endif",
         "namespace\n"
         "{\n"
         "// Overhaul: OVERHAUL_USER_DATA_DIR overrides the user-data root so the\n"
         "// headless UI regression can start from a fresh, isolated profile.\n"
         "std::string OverhaulAppDataFolder()\n"
         "{\n"
         "\tconst char *aOverride = std::getenv(\"OVERHAUL_USER_DATA_DIR\");\n"
         "\tif (aOverride != nullptr && *aOverride != '\\0')\n"
         "\t{\n"
         "\t\tstd::string aPath(aOverride);\n"
         "\t\tif (aPath.back() != '/' && aPath.back() != '\\\\')\n"
         "\t\t\taPath += '/';\n"
         "\t\treturn aPath;\n"
         "\t}\n"
         "#ifdef _WIN32\n"
         "\treturn std::filesystem::path(std::getenv(\"LOCALAPPDATA\")).string() + \"/\";\n"
         "#else\n"
         "\treturn std::filesystem::path(std::getenv(\"HOME\")).string() + \"/.config/\";\n"
         "#endif\n"
         "}\n"
         "}\n"
         "std::string gAppDataFolder = OverhaulAppDataFolder();"),
    ],
    "CMakeLists.txt": [
        # upstream repo EclipseMenu/discord-presence is gone (404); the empty
        # submodule dir would make add_subdirectory() fail at configure time.
        ("add_subdirectory(external/discordrpc EXCLUDE_FROM_ALL)",
         "if(EXISTS ${POPLIB_ROOT_DIR}/external/discordrpc/CMakeLists.txt)\n"
         "\tadd_subdirectory(external/discordrpc EXCLUDE_FROM_ALL)\n"
         "\tendif()"),
        # `alldemos` is only created when BUILD_EXAMPLES or BUILD_TOOLS is ON,
        # but this POST_BUILD command was unconditional. We build the library
        # only (both OFF), so configure failed with
        # "No TARGET 'alldemos' has been created in this directory".
        ('if(NOT (DEFINED ENV{GITHUB_ACTIONS} AND "$ENV{GITHUB_ACTIONS}" STREQUAL "true"))',
         'if(TARGET alldemos AND NOT (DEFINED ENV{GITHUB_ACTIONS} AND "$ENV{GITHUB_ACTIONS}" STREQUAL "true"))'),
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
        # A fatal error during AppBase::Init() fires before the SDL window
        # exists (mWindow == nullptr). SDL's message-box backend is not usable
        # that early and crashes headlessly before showing any text at all.
        # Always log the message, then only use SDL once a window exists.
        ("#include \"imgui/imguimanager.hpp\"",
         "#include \"imgui/imguimanager.hpp\"\n#include <stdio.h>\n#include <stdlib.h>\n"
         "#include <cstdio>\n#include <cstdlib>\n#include <string>\n#include <vector>\n"
         "#include <sstream>\n#include <algorithm>\n#include <filesystem>\n#include <system_error>"),
        # Headless frame capture: inject the helper and call it once per
        # Redraw, before present (readback is only valid on an unpresented
        # frame). Controlled entirely by environment variables.
        ("using namespace PopLib;",
         "using namespace PopLib;\n" + CAPTURE_FUNC.lstrip("\n")),
        ("\tSDL_RenderPresent(mRenderer);",
         "\tstatic int sOverhaulFrame = 0;\n"
         "\tOverhaulMaybeCapture(mRenderer, ++sOverhaulFrame);\n\n"
         "\tSDL_RenderPresent(mRenderer);"),
        ("\tSDL_ShowSimpleMessageBox(flags, theTitle, theMessage, mWindow);",
         "\t// AppBase::Init() runs before any window exists; log so headless/CI\n"
         "\t// runs can diagnose, and only open SDL's dialog once we can.\n"
         "\tfprintf(stderr, \"[%s] %s\\n\", theTitle, theMessage);\n"
         "\tif (mWindow != nullptr)\n"
         "\t\tSDL_ShowSimpleMessageBox(flags, theTitle, theMessage, mWindow);"),
    ],
    "PopLib/graphics/sysfont.cpp": [
        # SDL_ttf returns nullptr ("Text has zero width") for an empty string or
        # a string made only of zero-width glyphs. The game draws many empty
        # labels/tooltips every frame; poplib treated each one as a FATAL error
        # and opened a modal message box. Treat zero-width as an empty draw.
        ("#include <stdlib.h>", "#include <stdlib.h>\n#include <string.h>"),
        ("\t\tmApp->mSDLInterface->MakeSimpleMessageBox(\"Failed to render text: \", SDL_GetError(), SDL_MESSAGEBOX_ERROR);",
         "\t\t// SDL_ttf reports 'Text has zero width' for empty / zero-width\n"
         "\t\t// strings. That is a normal no-op, not a fatal error dialog.\n"
         "\t\tconst char *aTtfError = SDL_GetError();\n"
         "\t\tif (aTtfError != nullptr && strstr(aTtfError, \"zero width\") != nullptr)\n"
         "\t\t\treturn;\n"
         "\t\tmApp->mSDLInterface->MakeSimpleMessageBox(\"Failed to render text: \", aTtfError, SDL_MESSAGEBOX_ERROR);"),
        # WidgetManager::DrawWidgetsTo() translates Graphics into each widget's
        # local coordinates before Draw(). ImageFont goes through
        # Graphics::DrawImage and honours that transform; SysFont used to hand
        # absolute SDL rects to BltTexture, so ALL widget text (dialog header,
        # body, button labels) was painted at the screen origin while the
        # widget art stayed in place. This is what made the first-run update
        # dialog look "completely broken" with empty buttons.
        ("\tSDL_FRect dstRect = {(float)theX, (float)theY - (float)mAscent, (float)textSurface->w, (float)textSurface->h};",
         "\t// Overhaul: honour Graphics::Translate() like Graphics::DrawImage does.\n"
         "\tconst float aTransX = g->mTransX;\n"
         "\tconst float aTransY = g->mTransY;\n"
         "\tSDL_FRect dstRect = {(float)theX + aTransX, (float)theY - (float)mAscent + aTransY,\n"
         "\t                     (float)textSurface->w, (float)textSurface->h};"),
        ("\t\tSDL_FRect shadowRect = {(float)theX + 1.f, (float)theY - (float)mAscent + 1.f, dstRect.w, dstRect.h};",
         "\t\tSDL_FRect shadowRect = {dstRect.x + 1.f, dstRect.y + 1.f, dstRect.w, dstRect.h};"),
    ],
    "PopLib/readwrite/xmlparser.cpp": [
        # resources.xml contains `cols=3` (unquoted). tinyxml2 rejects it,
        # so the whole resource manifest fails to load. Normalise before parse.
        # Anchors avoid line endings: the file is CRLF, so match without \n.
        ("#include \"xmlparser.hpp\"",
         "#include \"xmlparser.hpp\"\n#include <string>"),
        # Two normalisations needed before tinyxml2 can read PopCap XML:
        # private entities (&cr; / &nbsp;) and bare attribute values (cols=3).
        ("    const char* data = aNewWrappedBuffer.c_str();",
         "    aNewWrappedBuffer = NormalisePopCapEntities(aNewWrappedBuffer);\n"
         "    aNewWrappedBuffer = QuoteBareAttributeValues(aNewWrappedBuffer);\n"
         "    const char* data = aNewWrappedBuffer.c_str();"),
    ],
}

HELPER = r'''
// PopCap's properties/*.xml use two private entities tinyxml2 does not know:
//   &cr;   = carriage return (line break inside a string)
//   &nbsp; = non-breaking space
// tinyxml2 only decodes quot/amp/apos/lt/gt plus numeric references, so turn
// them into equivalent numeric character references before parsing.
static std::string NormalisePopCapEntities(const std::string &s)
{
	const std::string pairs[][2] = {
		{"&cr;", "&#13;"},
		{"&nbsp;", "&#160;"},
	};
	std::string out = s;
	for (const auto &p : pairs)
	{
		size_t pos = 0;
		while ((pos = out.find(p[0], pos)) != std::string::npos)
		{
			out.replace(pos, p[0].size(), p[1]);
			pos += p[1].size();
		}
	}
	return out;
}

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
				// keep the spaces AND the '=' itself; dropping the '=' here
				// turns id="X" into id"X" and tinyxml2 reports
				// XML_ERROR_PARSING_ATTRIBUTE on every ordinary tag.
				out.append(s, i, look - i + 1);
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
                # A few upstream files are CRLF while most are LF. Retry the
                # same multi-line anchor with CRLF endings, and keep the
                # inserted lines in the same style so the diff stays clean.
                crlf_old = old.replace("\n", "\r\n")
                if "\n" in old and text.count(crlf_old):
                    old, new = crlf_old, new.replace("\n", "\r\n")
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
