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

# Overhaul: native-density presentation. PopLib used a fixed 640x480 screen
# texture and let SDL scale it to the window at present time; on a fullscreen
# display that bilinear-upscales every small TTF glyph. The screen texture is
# now sized to the display area, design coordinates are mapped with
# SDL_SetRenderScale, and the final blit is 1:1. Mouse events are mapped back
# through the same transform. Scale == 1 keeps the original behaviour (which
# is what the headless 640x480 harness exercises).
PRESENTATION_HELPER = r'''
// Overhaul: design (640x480) -> native pixel transform.
namespace OverhaulPresentation {
    static float sScaleX = 1.0f;
    static float sScaleY = 1.0f;
    static float sOffsetX = 0.0f;
    static float sOffsetY = 0.0f;
    static int sBufferW = 0;
    static int sBufferH = 0;
    static int sLastWindowW = 0;
    static int sLastWindowH = 0;
}

float SDLInterface::OverhaulDrawScale() const
{
    return OverhaulPresentation::sScaleX;
}

void SDLInterface::OverhaulWindowToDesign(float theX, float theY, int &theOutX, int &theOutY) const
{
    theOutX = (int)((theX - OverhaulPresentation::sOffsetX) / OverhaulPresentation::sScaleX);
    theOutY = (int)((theY - OverhaulPresentation::sOffsetY) / OverhaulPresentation::sScaleY);
}
'''

# Unattended input + state probe, injected into AppBase::ProcessDeferredMessages.
# This is the headless-mode backbone: it pushes REAL SDL events, so injected
# clicks traverse exactly the same path (AppBase -> WidgetManager -> Widget)
# as a physical mouse. No direct widget calls, no test-only backdoors.
#
#   OVERHAUL_INPUT_SCRIPT = "90:move:240,427;95:click:240,427;180:text:Tester;200:click:465,81"
#       frame:action:arg  -- action = move | click | key | text | focus | resize
#       focus synthesizes SDL_EVENT_WINDOW_FOCUS_GAINED (arg ignored); needed
#       on real-driver runs where a background window has no OS focus.
#       resize W,H calls SDL_SetWindowSize so the native-density presentation
#       path (scale > 1) can be exercised without relying on the desktop size.
#       frames are AppBase::mUpdateCount values; events are pushed when the
#       count first reaches the frame, then consumed by the real event pump.
#   OVERHAUL_STATE_FILE  = path to an NDJSON trace of widget-tree state
#   OVERHAUL_STATE_EVERY = sample period in update frames (default 30)
#   OVERHAUL_STATE_LAST  = path overwritten with the most recent sample
#
# Zero cost when none of the variables are set.
HEADLESS_FUNC = r'''
// Overhaul: deterministic headless input + state probe.
namespace
{
struct OverhaulInputAction
{
	int mFrame;
	int mKind;
	int mX;
	int mY;
};

struct OverhaulHeadlessCtx
{
	bool mInit;
	std::vector<OverhaulInputAction> mActions;
	std::vector<std::string> mTexts;
	size_t mNext;
	size_t mTextNext;
	std::string mStateFile;
	std::string mLastFile;
	FILE *mStateFP;
	int mStateEvery;
	int mLastFrame;
	OverhaulHeadlessCtx() : mInit(false), mNext(0), mTextNext(0), mStateFP(nullptr),
		mStateEvery(30), mLastFrame(-1) {}
};

OverhaulHeadlessCtx &OverhaulHeadless()
{
	static OverhaulHeadlessCtx aCtx;
	return aCtx;
}

std::string OverhaulTypeName(Widget *theWidget)
{
	if (theWidget == nullptr)
		return "null";
	return typeid(*theWidget).name();
}

void OverhaulWriteState(AppBase *theApp, int theFrame)
{
	OverhaulHeadlessCtx &aCtx = OverhaulHeadless();
	if (aCtx.mStateFP == nullptr)
		return;

	std::string aFocus = OverhaulTypeName(theApp->mWidgetManager->mFocusWidget);
	std::string aWidgets;
	for (Widget *aWidget : theApp->mWidgetManager->mWidgets)
	{
		if (aWidget == nullptr || !aWidget->mVisible)
			continue;
		if (!aWidgets.empty())
			aWidgets += "|";
		aWidgets += OverhaulTypeName(aWidget);
	}

	std::string aOver = OverhaulTypeName(theApp->mWidgetManager->mOverWidget);
	std::string aDown = OverhaulTypeName(theApp->mWidgetManager->mLastDownWidget);

	const char *aJson = "{\"frame\":%d,\"update\":%d,\"focus\":\"%s\","
		"\"over\":\"%s\",\"down\":\"%s\",\"widgets\":\"%s\","
		"\"has_focus\":%d,\"mouse_in\":%d}\n";
	std::fprintf(aCtx.mStateFP, aJson, theFrame, theApp->mUpdateCount,
		aFocus.c_str(), aOver.c_str(), aDown.c_str(), aWidgets.c_str(),
		theApp->mWidgetManager->mHasFocus ? 1 : 0,
		theApp->mWidgetManager->mMouseIn ? 1 : 0);
	std::fflush(aCtx.mStateFP);

	if (!aCtx.mLastFile.empty())
	{
		FILE *aLast = std::fopen(aCtx.mLastFile.c_str(), "w");
		if (aLast != nullptr)
		{
			std::fprintf(aLast, aJson, theFrame, theApp->mUpdateCount,
				aFocus.c_str(), aOver.c_str(), aDown.c_str(), aWidgets.c_str(),
				theApp->mWidgetManager->mHasFocus ? 1 : 0,
				theApp->mWidgetManager->mMouseIn ? 1 : 0);
			std::fclose(aLast);
		}
	}
}

void OverhaulPushMouse(SDL_EventType theType, int theX, int theY, bool theDown)
{
	SDL_Event aEvent;
	std::memset(&aEvent, 0, sizeof(aEvent));
	aEvent.type = theType;
	if (theType == SDL_EVENT_MOUSE_MOTION)
	{
		aEvent.motion.x = (float)theX;
		aEvent.motion.y = (float)theY;
	}
	else
	{
		aEvent.button.x = (float)theX;
		aEvent.button.y = (float)theY;
		aEvent.button.button = SDL_BUTTON_LEFT;
		aEvent.button.down = theDown;
		aEvent.button.clicks = 1;
	}
	SDL_PushEvent(&aEvent);
}

void OverhaulHeadlessTick(AppBase *theApp)
{
	OverhaulHeadlessCtx &aCtx = OverhaulHeadless();
	if (!aCtx.mInit)
	{
		aCtx.mInit = true;
		const char *aScript = std::getenv("OVERHAUL_INPUT_SCRIPT");
		const char *aState = std::getenv("OVERHAUL_STATE_FILE");
		const char *aEvery = std::getenv("OVERHAUL_STATE_EVERY");
		const char *aLast = std::getenv("OVERHAUL_STATE_LAST");
		if (aEvery != nullptr && *aEvery != '\0')
			aCtx.mStateEvery = std::atoi(aEvery);
		if (aCtx.mStateEvery <= 0)
			aCtx.mStateEvery = 30;
		if (aState != nullptr && *aState != '\0')
		{
			aCtx.mStateFile = aState;
			aCtx.mStateFP = std::fopen(aCtx.mStateFile.c_str(), "w");
		}
		if (aLast != nullptr && *aLast != '\0')
			aCtx.mLastFile = aLast;

		if (aScript != nullptr && *aScript != '\0')
		{
			std::stringstream aSS(aScript);
			std::string aToken;
			while (std::getline(aSS, aToken, ';'))
			{
				std::stringstream aParts(aToken);
				std::string aFrame, aAction, aArg;
				if (!std::getline(aParts, aFrame, ':') ||
					!std::getline(aParts, aAction, ':') ||
					!std::getline(aParts, aArg, ':'))
					continue;
				int aF = std::atoi(aFrame.c_str());
				if (aF <= 0)
					continue;
				int aKind = -1;
				if (aAction == "move") aKind = 0;
				else if (aAction == "click") aKind = 1;
				else if (aAction == "key") aKind = 2;
				else if (aAction == "text") aKind = 3;
				else if (aAction == "focus") aKind = 4;
				else if (aAction == "resize") aKind = 5;
				if (aKind < 0)
					continue;
				int aX = 0, aY = 0;
				if (aKind == 0 || aKind == 1 || aKind == 5)
				{
					size_t aComma = aArg.find(',');
					if (aComma == std::string::npos) continue;
					aX = std::atoi(aArg.substr(0, aComma).c_str());
					aY = std::atoi(aArg.substr(aComma + 1).c_str());
				}
				else if (aKind == 2)
					aX = std::atoi(aArg.c_str());
				// kind 3 (text): store the string pointer in mX/mY below via a
				// dedicated text list; the action keeps insertion order.
				if (aKind == 3)
				{
					aCtx.mActions.push_back({aF, aKind, 0, 0});
					aCtx.mTexts.push_back(aArg);
				}
				else
					aCtx.mActions.push_back({aF, aKind, aX, aY});
			}
			std::fprintf(stderr, "[overhaul-input] scripted actions=%zu\n",
				aCtx.mActions.size());
		}
	}

	const int aFrame = theApp->mUpdateCount;

	while (aCtx.mNext < aCtx.mActions.size() &&
		aCtx.mActions[aCtx.mNext].mFrame <= aFrame)
	{
		const OverhaulInputAction &aAct = aCtx.mActions[aCtx.mNext++];
		std::fprintf(stderr, "[overhaul-input] dispatching kind=%d frame=%d\n",
			aAct.mKind, aFrame);
		std::fflush(stderr);
		if (aAct.mKind == 0)
		{
			OverhaulPushMouse(SDL_EVENT_MOUSE_MOTION, aAct.mX, aAct.mY, false);
			std::fprintf(stderr, "[overhaul-input] frame=%d move %d,%d\n",
				aFrame, aAct.mX, aAct.mY);
		}
		else if (aAct.mKind == 1)
		{
			OverhaulPushMouse(SDL_EVENT_MOUSE_MOTION, aAct.mX, aAct.mY, false);
			OverhaulPushMouse(SDL_EVENT_MOUSE_BUTTON_DOWN, aAct.mX, aAct.mY, true);
			OverhaulPushMouse(SDL_EVENT_MOUSE_BUTTON_UP, aAct.mX, aAct.mY, false);
			std::fprintf(stderr, "[overhaul-input] frame=%d click %d,%d\n",
				aFrame, aAct.mX, aAct.mY);
		}
		else if (aAct.mKind == 2)
		{
			SDL_Event aEvent;
			std::memset(&aEvent, 0, sizeof(aEvent));
			aEvent.type = SDL_EVENT_KEY_DOWN;
			aEvent.key.key = (SDL_Keycode)aAct.mX;
			SDL_PushEvent(&aEvent);
			std::fprintf(stderr, "[overhaul-input] frame=%d key %d\n",
				aFrame, aAct.mX);
		}
		else if (aAct.mKind == 4)
		{
			// A real-driver window started in the background has mActive=false
			// after SDL_EVENT_WINDOW_FOCUS_LOST, so WidgetManager ignores clicks.
			// A human focuses the window before clicking; synthesize that event
			// so desktop scripted runs follow the same path.
			SDL_Event aEvent;
			std::memset(&aEvent, 0, sizeof(aEvent));
			aEvent.type = SDL_EVENT_WINDOW_FOCUS_GAINED;
			SDL_PushEvent(&aEvent);
			std::fprintf(stderr, "[overhaul-input] frame=%d focus gained\n",
				aFrame);
		}
		else if (aAct.mKind == 5)
		{
			// Resize the real SDL window so UpdateViewport() exercises the
			// native-density path (scale > 1). This is the same window event a
			// user generates by dragging or entering fullscreen; the harness
			// does not bypass any rendering or input code.
			SDL_SetWindowSize(theApp->mSDLInterface->mWindow, aAct.mX, aAct.mY);
			std::fprintf(stderr, "[overhaul-input] frame=%d resize %d,%d\n",
				aFrame, aAct.mX, aAct.mY);
		}
		else
		{
			// TEXT_INPUT feeds EditWidget (new-user name, fish names).
			if (aCtx.mTextNext < aCtx.mTexts.size())
			{
				const std::string &aText = aCtx.mTexts[aCtx.mTextNext++];
				SDL_Event aEvent;
				std::memset(&aEvent, 0, sizeof(aEvent));
				aEvent.type = SDL_EVENT_TEXT_INPUT;
				aEvent.text.text = aText.c_str();
				SDL_PushEvent(&aEvent);
				std::fprintf(stderr, "[overhaul-input] frame=%d text %s\n",
					aFrame, aText.c_str());
			}
		}
	}

	if (aCtx.mStateFP != nullptr && aFrame != aCtx.mLastFrame &&
		aFrame % aCtx.mStateEvery == 0)
	{
		aCtx.mLastFrame = aFrame;
		OverhaulWriteState(theApp, aFrame);
	}
}
}
'''

# Automated runs must not make noise: BGM playback still differs from retail
# (the decompiled title path remaps 2:45 -> Insaniq2.mo3), so hearing it during
# a headless/desktop regression is both distracting and misleading.
# Clamp every volume setter instead of just
# the initial volume -- OptionsDialog and the game itself call these setters
# later, and a one-time mute would silently be undone.
#
#   OVERHAUL_NO_AUDIO=1 (or "true") -> music, SFX and master forced to 0
#
# The audio devices are still created, so this cannot turn a missing audio
# device into a different crash path; it only guarantees silence.
AUDIO_FUNC = r'''
// Overhaul: unconditional silence for automated runs.
namespace
{
bool OverhaulAudioMuted()
{
	static const bool sMuted = []() {
		const char *aValue = std::getenv("OVERHAUL_NO_AUDIO");
		if (aValue == nullptr)
			return false;
		bool aMuted = (std::string(aValue) == "1" || std::string(aValue) == "true");
		if (aMuted)
			std::fprintf(stderr, "[overhaul-audio] muted (OVERHAUL_NO_AUDIO=%s)\n", aValue);
		return aMuted;
	}();
	return sMuted;
}
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
    "PopLib/appbase.cpp": [
        # Headless backbone: scripted REAL SDL input + widget-tree state probe.
        # Added after the include block and before the namespace opens, so it
        # can see AppBase/WidgetManager complete types and use typeid.
        ("using namespace PopLib;",
         "using namespace PopLib;\n" + AUDIO_FUNC.lstrip("\n") + HEADLESS_FUNC.lstrip("\n")),
        ("bool AppBase::ProcessDeferredMessages(bool singleMessage)\n{\n\tSDL_Event event;",
         "bool AppBase::ProcessDeferredMessages(bool singleMessage)\n{\n"
         "\t// Overhaul: headless input/script and state probe. No-op unless\n"
         "\t// OVERHAUL_INPUT_SCRIPT or OVERHAUL_STATE_FILE is set.\n"
         "\tOverhaulHeadlessTick(this);\n\n\tSDL_Event event;"),
        # Silent automated runs. Clamp at the setter, not just at init: the
        # game (OptionsDialog, PlayMusic, ...) can raise the volume later.
        ("void AppBase::SetMusicVolume(double theVolume)\n{\n\tmMusicVolume = theVolume;\n\n"
         "\tif (mMusicInterface != nullptr)\n"
         "\t\tmMusicInterface->SetVolume((mMuteCount > 0) ? 0.0 : mMusicVolume * 10);\n}",
         "void AppBase::SetMusicVolume(double theVolume)\n{\n"
         "\tif (OverhaulAudioMuted())\n\t\ttheVolume = 0.0;\n"
         "\tmMusicVolume = theVolume;\n\n"
         "\tif (mMusicInterface != nullptr)\n"
         "\t\tmMusicInterface->SetVolume((mMuteCount > 0) ? 0.0 : mMusicVolume * 10);\n}"),
        ("void AppBase::SetSfxVolume(double theVolume)\n{\n\tmSfxVolume = theVolume;\n\n"
         "\tif (mSoundManager != nullptr)\n"
         "\t\tmSoundManager->SetVolume((mMuteCount > 0) ? 0.0 : mSfxVolume);\n}",
         "void AppBase::SetSfxVolume(double theVolume)\n{\n"
         "\tif (OverhaulAudioMuted())\n\t\ttheVolume = 0.0;\n"
         "\tmSfxVolume = theVolume;\n\n"
         "\tif (mSoundManager != nullptr)\n"
         "\t\tmSoundManager->SetVolume((mMuteCount > 0) ? 0.0 : mSfxVolume);\n}"),
        ("void AppBase::SetMasterVolume(double theMasterVolume)\n{\n"
         "\tmSfxVolume = theMasterVolume;\n\tmSoundManager->SetMasterVolume(mSfxVolume);\n}",
         "void AppBase::SetMasterVolume(double theMasterVolume)\n{\n"
         "\tif (OverhaulAudioMuted())\n\t\ttheMasterVolume = 0.0;\n"
         "\tmSfxVolume = theMasterVolume;\n"
         "\tmSoundManager->SetMasterVolume(mSfxVolume);\n}"),
        # Event trace: record the exact SDL event processed before it is
        # handled, so a crash can be attributed to a specific input. Only
        # active when a state trace is requested (diagnostic builds/tests).
        ("\tif (SDL_PollEvent(&event))\n\t{\n\t\tImGui_ImplSDL3_ProcessEvent(&event);",
         "\tif (SDL_PollEvent(&event))\n\t{\n"
         "\t\tif (std::getenv(\"OVERHAUL_STATE_FILE\") != nullptr)\n"
         "\t\t{\n"
         "\t\t\tstd::fprintf(stderr, \"[overhaul-event] type=%llu\\n\",\n"
         "\t\t\t\t(unsigned long long)event.type);\n"
         "\t\t\tstd::fflush(stderr);\n"
         "\t\t}\n"
         "\t\tImGui_ImplSDL3_ProcessEvent(&event);"),
        # Native-density presentation means SDL no longer maps mouse events
        # into design space. Both motion and button events must be mapped back
        # through the same transform as rendering, or fullscreen clicks miss.
        ("\t\t\t\tint x = event.motion.x;\n\t\t\t\tint y = event.motion.y;",
         "\t\t\t\tint x = 0, y = 0;\n"
         "\t\t\t\tmSDLInterface->OverhaulWindowToDesign(event.motion.x, event.motion.y, x, y);"),
        ("\t\t\t\tint renderWidth, renderHeight;\n"
         "\t\t\t\tSDL_GetCurrentRenderOutputSize(mSDLInterface->mRenderer, &renderWidth, &renderHeight);\n\n"
         "\t\t\t\tint scaledX = static_cast<int>(event.button.x * ((float)mWidth / renderWidth));\n"
         "\t\t\t\tint scaledY = static_cast<int>(event.button.y * ((float)mHeight / renderHeight));",
         "\t\t\t\tint scaledX = 0, scaledY = 0;\n"
         "\t\t\t\tmSDLInterface->OverhaulWindowToDesign(event.button.x, event.button.y, scaledX, scaledY);"),
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
        # L1.5: rasterise the design canvas at native pixel density. SDL's
        # logical presentation used to bilinear-upscale the 640x480 texture on
        # present, which is what made small TTF glyphs blurry in fullscreen.
        # Keep the game's design coordinates, scale every draw onto a native
        # screen texture, and blit 1:1 with an explicit letterbox.
        ("\tif (!SDL_SetRenderLogicalPresentation(mRenderer, windowWidth, windowHeight, SDL_LOGICAL_PRESENTATION_LETTERBOX))\n\t\treturn;",
         "\t// Redraw also calls this; skip the work when nothing changed.\n"
         "\tif (OverhaulPresentation::sBufferW != 0 &&\n"
         "\t    windowWidth == OverhaulPresentation::sLastWindowW &&\n"
         "\t    windowHeight == OverhaulPresentation::sLastWindowH)\n"
         "\t\treturn;\n"
         "\tOverhaulPresentation::sLastWindowW = windowWidth;\n"
         "\tOverhaulPresentation::sLastWindowH = windowHeight;\n"
         "\n"
         "\t// Overhaul: native-density screen texture. The game still draws in\n"
         "\t// 640x480 design coordinates, but the texture is as large as the\n"
         "\t// display area so glyphs are rasterised at final pixel density.\n"
         "\tfloat aScale = std::min((float)windowWidth / (float)mWidth,\n"
         "\t                        (float)windowHeight / (float)mHeight);\n"
         "\tif (aScale <= 0.0f)\n"
         "\t\taScale = 1.0f;\n"
         "\tint aBufferW = std::max(1, (int)std::floor((float)mWidth * aScale));\n"
         "\tint aBufferH = std::max(1, (int)std::floor((float)mHeight * aScale));\n"
         "\n"
         "\t// We letterbox ourselves in Redraw; SDL must not scale a second time.\n"
         "\tSDL_SetRenderLogicalPresentation(mRenderer, windowWidth, windowHeight,\n"
         "\t                                 SDL_LOGICAL_PRESENTATION_DISABLED);\n"
         "\n"
         "\tif (mScreenTexture != nullptr &&\n"
         "\t    (aBufferW != OverhaulPresentation::sBufferW ||\n"
         "\t     aBufferH != OverhaulPresentation::sBufferH))\n"
         "\t{\n"
         "\t\tSDL_DestroyTexture(mScreenTexture);\n"
         "\t\tmScreenTexture = SDL_CreateTexture(mRenderer, SDL_PIXELFORMAT_RGBA8888,\n"
         "\t\t                                  SDL_TEXTUREACCESS_TARGET, aBufferW, aBufferH);\n"
         "\t\tif (mScreenTexture == nullptr)\n"
         "\t\t{\n"
         "\t\t\tstd::fprintf(stderr, \"[overhaul] screen texture %dx%d failed: %s\\n\",\n"
         "\t\t\t             aBufferW, aBufferH, SDL_GetError());\n"
         "\t\t\treturn;\n"
         "\t\t}\n"
         "\t}\n"
         "\tOverhaulPresentation::sBufferW = aBufferW;\n"
         "\tOverhaulPresentation::sBufferH = aBufferH;\n"
         "\tOverhaulPresentation::sScaleX = (float)aBufferW / (float)mWidth;\n"
         "\tOverhaulPresentation::sScaleY = (float)aBufferH / (float)mHeight;\n"
         "\tOverhaulPresentation::sOffsetX = (float)(windowWidth - aBufferW) * 0.5f;\n"
         "\tOverhaulPresentation::sOffsetY = (float)(windowHeight - aBufferH) * 0.5f;"),
        ("mPresentationRect = Rect(0, 0, windowWidth, windowHeight);",
         "mPresentationRect = Rect(0, 0, mWidth, mHeight);"),
        # Every draw goes into the native screen texture; map design coords
        # with the same transform used to size that texture.
        ("\tSDL_SetRenderTarget(mRenderer, mScreenTexture);",
         "\tSDL_SetRenderTarget(mRenderer, mScreenTexture);\n"
         "\tSDL_SetRenderScale(mRenderer, OverhaulPresentation::sScaleX, OverhaulPresentation::sScaleY);"),
        # Present 1:1 into the letterboxed area instead of letting SDL scale.
        ("\tSDL_RenderClear(mRenderer);\n\n"
         "\tSDL_Rect clipRect =\n"
         "\t\ttheClipRect\n"
         "\t\t\t? SDL_Rect{theClipRect->mX, theClipRect->mY, theClipRect->mWidth, theClipRect->mHeight}\n"
         "\t\t\t: SDL_Rect{mPresentationRect.mX, mPresentationRect.mY, mPresentationRect.mWidth, mPresentationRect.mHeight};\n\n"
         "\tSDL_SetRenderClipRect(mRenderer, &clipRect);\n\n"
         "\tPopLib::gSDLInterfacePreDrawError = (SDL_RenderTexture(mRenderer, mScreenTexture, nullptr, nullptr) < 0);",
         "\tSDL_RenderClear(mRenderer);\n\n"
         "\tSDL_FRect aDest = {OverhaulPresentation::sOffsetX, OverhaulPresentation::sOffsetY,\n"
         "\t                   (float)OverhaulPresentation::sBufferW, (float)OverhaulPresentation::sBufferH};\n"
         "\tSDL_FRect aClip = aDest;\n"
         "\tif (theClipRect != nullptr)\n"
         "\t{\n"
         "\t\taClip.x = aDest.x + (float)theClipRect->mX * OverhaulPresentation::sScaleX;\n"
         "\t\taClip.y = aDest.y + (float)theClipRect->mY * OverhaulPresentation::sScaleY;\n"
         "\t\taClip.w = (float)theClipRect->mWidth * OverhaulPresentation::sScaleX;\n"
         "\t\taClip.h = (float)theClipRect->mHeight * OverhaulPresentation::sScaleY;\n"
         "\t}\n"
         "\tSDL_Rect clipRect = {(int)aClip.x, (int)aClip.y, (int)aClip.w, (int)aClip.h};\n"
         "\tSDL_SetRenderClipRect(mRenderer, &clipRect);\n\n"
         "\tPopLib::gSDLInterfacePreDrawError =\n"
         "\t\t(SDL_RenderTexture(mRenderer, mScreenTexture, nullptr, &aDest) < 0);"),
        ("\tSDL_SetRenderTarget(mRenderer, nullptr);\n\n\tSDL_SetRenderDrawColor(mRenderer, 0, 0, 0, 0);",
         "\t// Re-read the window size every frame. Scripted resizes and some\n"
         "\t// window-manager transitions do not deliver RESIZED reliably.\n"
         "\tUpdateViewport();\n"
         "\tSDL_SetRenderTarget(mRenderer, nullptr);\n\tSDL_SetRenderScale(mRenderer, 1.0f, 1.0f);\n\n"
         "\tSDL_SetRenderDrawColor(mRenderer, 0, 0, 0, 255);"),
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
         "using namespace PopLib;\n" + CAPTURE_FUNC.lstrip("\n") +
         PRESENTATION_HELPER.lstrip("\n")),
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
    "PopLib/graphics/sdlinterface.hpp": [
        # Expose the presentation transform to text rendering and input
        # mapping. Both must use the same scale or text stays small/blurry
        # and clicks land at the wrong place on a fullscreen display.
        ("\tvoid UpdateViewport();",
         "\tvoid UpdateViewport();\n"
         "\tfloat OverhaulDrawScale() const;\n"
         "\tvoid OverhaulWindowToDesign(float theX, float theY, int &theOutX, int &theOutY) const;"),
    ],
    "PopLib/graphics/sysfont.hpp": [
        # A SysFont copy used to share the raw TTF_Font* with its source, but
        # every copy closed it in its destructor. Widgets call Duplicate()
        # constantly (Dialog::SetHeaderFont, ButtonWidget::SetFont, ...), so
        # the first destroyed copy freed a font still in use by the original:
        # the next TTF call crashed while ENTERING a dialog (clicking PLAY on a
        # fresh profile creates NewUserDialog and died in SetButtonFont).
        # Share ownership with a ref count; close only on the last release.
        ("\tTTF_Font *mTTFFont;\n\tAppBase *mApp;",
         "\tTTF_Font *mTTFFont;\n\tint *mRefCount;\n\tAppBase *mApp;"),
        # The point size is needed to render glyphs at native density. The
        # TTF_Font* itself is shared (refcounted), so never store a second
        # font handle here.
        ("\tint *mRefCount;\n\tAppBase *mApp;",
         "\tint *mRefCount;\n\tint mPointSize;\n\tAppBase *mApp;"),
    ],
    "PopLib/graphics/sysfont.cpp": [
        # Initialise the ref count on every construction path. Keep the point
        # size too: TTF is temporarily opened larger for native-density draws.
        ("\tmApp = theApp;\n\tSDL_IOStream *io = SDL_IOFromConstMem((void *)aData, aDataSize);",
         "\tmApp = theApp;\n\tmRefCount = new int(1);\n\tmPointSize = thePointSize;\n"
         "\tSDL_IOStream *io = SDL_IOFromConstMem((void *)aData, aDataSize);"),
        ("\tmApp = theApp;\n\n\tmTTFFont = TTF_OpenFont(theFace.c_str(), thePointSize);",
         "\tmApp = theApp;\n\tmRefCount = new int(1);\n\tmPointSize = thePointSize;\n\n"
         "\tmTTFFont = TTF_OpenFont(theFace.c_str(), thePointSize);"),
        # Copy shares the font and increments the count.
        ("SysFont::SysFont(const SysFont &theSysFont)\n{\n\tmTTFFont = theSysFont.mTTFFont;",
         "SysFont::SysFont(const SysFont &theSysFont)\n{\n"
         "\tmTTFFont = theSysFont.mTTFFont;\n"
         "\tmRefCount = theSysFont.mRefCount;\n"
         "\tmPointSize = theSysFont.mPointSize;\n"
         "\t++(*mRefCount);"),
        # Only the last owner closes the font; a null font is a no-op for
        # TTF_CloseFont but dereferencing a null ref count is not.
        ("SysFont::~SysFont()\n{\n\tTTF_CloseFont(mTTFFont);\n}",
         "SysFont::~SysFont()\n{\n"
         "\tif (mRefCount != nullptr && --(*mRefCount) == 0)\n"
         "\t{\n"
         "\t\tif (mTTFFont != nullptr)\n"
         "\t\t\tTTF_CloseFont(mTTFFont);\n"
         "\t\tdelete mRefCount;\n"
         "\t}\n"
         "\tmTTFFont = nullptr;\n"
         "\tmRefCount = nullptr;\n}"),
        # SDL_ttf returns nullptr ("Text has zero width") for an empty string or
        # a string made only of zero-width glyphs. The game draws many empty
        # labels/tooltips every frame; poplib treated each one as a FATAL error
        # and opened a modal message box. Treat zero-width as an empty draw.
        ("#include <stdlib.h>", "#include <stdlib.h>\n#include <string.h>\n#include <algorithm>\n#include <cmath>"),
        # Render glyphs at native pixel density. The screen texture is
        # aScale times the 640x480 design size; a design-size glyph texture
        # stretched by that factor is exactly what looked blurry fullscreen.
        # Temporarily open the shared font at the scaled point size, render,
        # then restore it before any other caller uses the font.
        ("\tSDL_Surface *textSurface =\n\t\tTTF_RenderText_Blended(mTTFFont, theString.c_str(), 0, aColor);",
         "\tconst float aSS = mApp->mSDLInterface->OverhaulDrawScale();\n"
         "\tconst int aRenderSize = std::max(1, (int)std::lround((float)mPointSize * aSS));\n"
         "\tconst bool aFontResized = (aRenderSize != mPointSize);\n"
         "\tif (aFontResized)\n"
         "\t\tTTF_SetFontSize(mTTFFont, aRenderSize);\n"
         "\tSDL_Surface *textSurface =\n"
         "\t\tTTF_RenderText_Blended(mTTFFont, theString.c_str(), 0, aColor);"),
        ("\t\tmApp->mSDLInterface->MakeSimpleMessageBox(\"Failed to render text: \", SDL_GetError(), SDL_MESSAGEBOX_ERROR);",
         "\t\t// SDL_ttf reports 'Text has zero width' for empty / zero-width\n"
         "\t\t// strings. That is a normal no-op, not a fatal error dialog.\n"
         "\t\tconst char *aTtfError = SDL_GetError();\n"
         "\t\tif (aFontResized)\n"
         "\t\t\tTTF_SetFontSize(mTTFFont, mPointSize);\n"
         "\t\tif (aTtfError != nullptr && strstr(aTtfError, \"zero width\") != nullptr)\n"
         "\t\t\treturn;\n"
         "\t\tmApp->mSDLInterface->MakeSimpleMessageBox(\"Failed to render text: \", aTtfError, SDL_MESSAGEBOX_ERROR);"),
        ("\tSDL_Texture *textTexture = SDL_CreateTextureFromSurface(renderer, textSurface);",
         "\tif (aFontResized)\n"
         "\t\tTTF_SetFontSize(mTTFFont, mPointSize);\n"
         "\tSDL_Texture *textTexture = SDL_CreateTextureFromSurface(renderer, textSurface);"),
        # WidgetManager::DrawWidgetsTo() translates Graphics into each widget's
        # local coordinates before Draw(). ImageFont goes through
        # Graphics::DrawImage and honours that transform; SysFont used to hand
        # absolute SDL rects to BltTexture, so ALL widget text (dialog header,
        # body, button labels) was painted at the screen origin while the
        # widget art stayed in place. This is what made the first-run update
        # dialog look "completely broken" with empty buttons.
        ("\tSDL_FRect dstRect = {(float)theX, (float)theY - (float)mAscent, (float)textSurface->w, (float)textSurface->h};",
         "\t// Overhaul: honour Graphics::Translate() like Graphics::DrawImage does.\n"
         "\t// The glyph texture is aSS times larger than the design rect; draw\n"
         "\t// it back at design size so the native-density screen texture maps\n"
         "\t// it 1:1 instead of upscaling a small texture.\n"
         "\tconst float aTransX = g->mTransX;\n"
         "\tconst float aTransY = g->mTransY;\n"
         "\tSDL_FRect dstRect = {(float)theX + aTransX, (float)theY - (float)mAscent + aTransY,\n"
         "\t                     (float)textSurface->w / aSS, (float)textSurface->h / aSS};"),
        ("\t\tSDL_FRect shadowRect = {(float)theX + 1.f, (float)theY - (float)mAscent + 1.f, dstRect.w, dstRect.h};",
         "\t\tSDL_FRect shadowRect = {dstRect.x + 1.f, dstRect.y + 1.f, dstRect.w, dstRect.h};"),
        # ImageFont::DrawString clips each glyph to theClipRect. SysFont (TTF)
        # ignored it, so EditWidget's two-pass draw painted the black
        # COLOR_HILITE_TEXT pass over the WHOLE string instead of only the
        # selection/cursor sliver: the typed name became black-on-dark and
        # unreadable. Intersect the destination rect with the clip rect and
        # shrink the source rect by the same amount. theClipRect is already in
        # screen space (Graphics::ClipRect applies mTransX/Y), as is dstRect.
        ("\tSDL_FRect srcRect = {0, 0, dstRect.w, dstRect.h};\n\tSDL_DestroySurface(textSurface);",
         "\tSDL_FRect srcRect = {0, 0, (float)textSurface->w, (float)textSurface->h};\n"
         "\t// Overhaul: honour theClipRect like ImageFont does. The clip is in\n"
         "\t// design space, the source rect in supersampled glyph pixels.\n"
         "\tfloat aCX0 = (float)theClipRect.mX, aCY0 = (float)theClipRect.mY;\n"
         "\tfloat aCX1 = aCX0 + (float)theClipRect.mWidth, aCY1 = aCY0 + (float)theClipRect.mHeight;\n"
         "\tfloat aX0 = std::max(dstRect.x, aCX0), aY0 = std::max(dstRect.y, aCY0);\n"
         "\tfloat aX1 = std::min(dstRect.x + dstRect.w, aCX1), aY1 = std::min(dstRect.y + dstRect.h, aCY1);\n"
         "\tif (aX1 > aX0 && aY1 > aY0)\n"
         "\t{\n"
         "\t\tsrcRect.x = (aX0 - dstRect.x) * aSS;\n"
         "\t\tsrcRect.y = (aY0 - dstRect.y) * aSS;\n"
         "\t\tsrcRect.w = (aX1 - aX0) * aSS;\n"
         "\t\tsrcRect.h = (aY1 - aY0) * aSS;\n"
         "\t\tdstRect.x = aX0; dstRect.y = aY0; dstRect.w = aX1 - aX0; dstRect.h = aY1 - aY0;\n"
         "\t}\n"
         "\telse\n"
         "\t{\n"
         "\t\tSDL_DestroyTexture(textTexture);\n"
         "\t\tSDL_DestroySurface(textSurface);\n"
         "\t\treturn;\n"
         "\t}\n"
         "\tSDL_DestroySurface(textSurface);"),
        # The shadow rect is derived from dstRect; recompute its src offset so
        # the 1px shadow uses the matching slice of the glyph atlas.
        ("\t\tSDL_FRect shadowRect = {dstRect.x + 1.f, dstRect.y + 1.f, dstRect.w, dstRect.h};\n"
         "\t\tmApp->mSDLInterface->BltTexture(textTexture, srcRect, shadowRect, Color(0, 0, 0), g->GetDrawMode());",
         "\t\tSDL_FRect shadowRect = {dstRect.x + 1.f, dstRect.y + 1.f, dstRect.w, dstRect.h};\n"
         "\t\tmApp->mSDLInterface->BltTexture(textTexture, srcRect, shadowRect, Color(0, 0, 0), g->GetDrawMode());"),
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
