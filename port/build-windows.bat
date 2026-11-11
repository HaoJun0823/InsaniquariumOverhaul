@echo off
setlocal
rem ---------------------------------------------------------------------------
rem InsaniquariumOverhaul - Windows build (MSVC x64 / Ninja)
rem
rem   1. git submodule update --init --recursive
rem   2. bash port/port.sh                  -> derive port/winfish from the decomp
rem   3. python port/init-deps.py          -> populate nested deps at pinned SHAs
rem   4. python port/apply-patches.py      -> fix upstream PopLib bugs (no fork)
rem   5. build-windows.bat                 -> this file
rem   6. bash port/copy-assets.sh "<retail game folder>"
rem
rem Normal terminals: just run this file; vcvarsall.bat sets up MSVC.
rem
rem Sandboxes that blacklist reg.exe: vcvarsall.bat queries the registry and
rem will be blocked. Set OVERHAUL_NO_VCVARS=1 before running; the script then
rem sets INCLUDE/LIB/PATH itself, which is the standard registry-free way to
rem drive cl.exe from Ninja. No workaround of the blocked program is attempted.
rem ---------------------------------------------------------------------------

set "VS=C:\Program Files\Microsoft Visual Studio\18\Community"
set "SDKROOT=C:\Program Files (x86)\Windows Kits\10"
set "CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja"
set "ROOT=%~dp0.."

rem Pick the newest installed SDK / MSVC toolset (version dirs sort correctly).
for /d %%D in ("%SDKROOT%\Include\*") do set "SDKVER=%%~nxD"
for /d %%D in ("%VS%\VC\Tools\MSVC\*") do set "VCTOOLS=%%~fD"

if "%OVERHAUL_NO_VCVARS%"=="1" goto manual_env

call "%VS%\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 (
  echo [ERROR] vcvarsall.bat failed. Edit VS= in this script to match your install.
  echo         In restricted sandboxes, try: set OVERHAUL_NO_VCVARS=1
  exit /b 1
)
goto env_ready

:manual_env
echo [INFO] Registry-free MSVC setup: %VCTOOLS%
set "INCLUDE=%VCTOOLS%\include;%SDKROOT%\Include\%SDKVER%\ucrt;%SDKROOT%\Include\%SDKVER%\um;%SDKROOT%\Include\%SDKVER%\shared;%SDKROOT%\Include\%SDKVER%\winrt"
set "LIB=%VCTOOLS%\lib\x64;%SDKROOT%\Lib\%SDKVER%\ucrt\x64;%SDKROOT%\Lib\%SDKVER%\um\x64"
set "PATH=%VCTOOLS%\bin\Hostx64\x64;%SDKROOT%\bin\%SDKVER%\x64;%NINJA%;%PATH%"

:env_ready
rem Nested submodules: shallow clones end up empty / at branch tips instead of
rem the commits poplib pins. Idempotent, safe to run on every build.
python "%ROOT%\port\init-deps.py"
if errorlevel 1 (
  echo [ERROR] Nested dependencies are not ready; see the report above.
  exit /b 1
)

rem Apply the reviewed upstream fixes to the pristine PopLib submodule.
rem Idempotent: already-applied patches are skipped.
python "%ROOT%\port\apply-patches.py"
if errorlevel 1 (
  echo [ERROR] PopLib patches conflict; update them with port\make-patches.py
  exit /b 1
)

rem rc.exe / mt.exe live in the SDK bin but vcvarsall may not add them to PATH.
rem Without these, CMake's compiler test fails with CMAKE_MT-NOTFOUND.
set "PATH=%SDKROOT%\bin\%SDKVER%\x64;%NINJA%;%PATH%"

rem IMPORTANT: -D path values are written verbatim into generated .cmake files.
rem Windows backslashes become invalid escapes there ("\P"), so use forward
rem slashes for every path passed with -D. CMake accepts them on Windows.
rem The root itself must be converted first: building "%SDKROOT%/bin/..." from a
rem backslashed root still yields "C:\Program Files (x86)\...", and CMake dies
rem with "Invalid character escape '\P'" while enabling the RC language.
set "SDKROOT_FWD=%SDKROOT:\=/%"
set "RC_FWD=%SDKROOT_FWD%/bin/%SDKVER%/x64/rc.exe"
set "MT_FWD=%SDKROOT_FWD%/bin/%SDKVER%/x64/mt.exe"

rem IMPORTANT: the source root is the REPOSITORY ROOT, not port/.
rem Configuring port/ directly (the old behaviour) silently bypassed the root
rem CMakeLists.txt, so the four pillar options, the project version, and
rem include(CTest) never took effect: the root build file was dead code and the
rem exe reported a version belonging to PopLib. Keep -S "%ROOT%".
rem If an existing build\game cache was created with -S port, CMake will refuse
rem to reuse it; delete build\game once after this change.
"%CMAKE%" -S "%ROOT%" -B "%ROOT%\build\game" -G Ninja -Wno-dev ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_RC_COMPILER="%RC_FWD%" ^
  -DCMAKE_MT="%MT_FWD%" ^
  -DBUILD_EXAMPLES=OFF -DBUILD_TOOLS=OFF -DFEATURE_DISCORD_RPC=OFF
if errorlevel 1 exit /b 1

"%CMAKE%" --build "%ROOT%\build\game" --parallel
exit /b %errorlevel%
