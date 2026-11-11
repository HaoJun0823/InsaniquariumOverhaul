@echo off
setlocal
rem ---------------------------------------------------------------------------
rem InsaniquariumOverhaul - Windows build (MSVC x64 / Ninja)
rem
rem Run from a normal terminal (not inside an agent sandbox): vcvarsall.bat
rem queries the registry, which some sandboxes block.
rem
rem   1. bash port/port.sh        -> derive port/winfish from external/winfish
rem   2. build-windows.bat        -> this file
rem   3. bash port/copy-assets.sh <your retail game folder>
rem ---------------------------------------------------------------------------

set "VS=C:\Program Files\Microsoft Visual Studio\18\Community"
set "CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja"
set "SDK=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64"
set "ROOT=%~dp0.."

call "%VS%\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 (
  echo [ERROR] vcvarsall.bat failed. Edit VS= in this script to match your install.
  exit /b 1
)

rem rc.exe / mt.exe live in the SDK bin but vcvarsall may not add them to PATH.
rem Without these, CMake's compiler test fails with CMAKE_MT-NOTFOUND.
set "PATH=%SDK%;%NINJA%;%PATH%"

"%CMAKE%" -S "%ROOT%\port" -B "%ROOT%\build\game" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_RC_COMPILER="%SDK%\rc.exe" ^
  -DCMAKE_MT="%SDK%\mt.exe" ^
  -DBUILD_EXAMPLES=OFF -DBUILD_TOOLS=OFF -DFEATURE_DISCORD_RPC=OFF
if errorlevel 1 exit /b 1

"%CMAKE%" --build "%ROOT%\build\game" --parallel
exit /b %errorlevel%
