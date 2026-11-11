cmake_minimum_required(VERSION 3.26)
project(InsaniquariumOverhaul
    VERSION 0.1.0
    DESCRIPTION "Cross-platform, i18n, HD, and compatibility overhaul of Insaniquarium"
    LANGUAGES C CXX ASM)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- Four pillars (feature switches, consumed by port/) ----
option(OVERHAUL_I18N    "Multi-language / i18n layer (TTF fonts + string tables)" ON)
option(OVERHAUL_UI      "Modern, resolution-independent UI (replaces 4:3 bitmaps)" ON)
option(OVERHAUL_HD      "High-resolution / integer-scaled rendering"              ON)
option(OVERHAUL_COMPAT  "Modern-system compatibility fixes"                     ON)

# Tests for the code we own (port/src). enable_testing() must be called at the
# top level for ctest to discover tests declared in subdirectories.
#
# include(CTest) is deliberately NOT used: it defines BUILD_TESTING, and that
# switch would then also enable the test suites of every third-party subproject
# (zlib, tinyxml2, PopLib), which `ctest` reports as "Not Run" and fails on.
# port/CMakeLists.txt owns the OVERHAUL_TESTS switch instead.
enable_testing()

# external/winfish and external/poplib are read-only submodules. They are NOT
# add_subdirectory'd here; port/CMakeLists.txt pulls in PopLib, and port/port.sh
# derives the buildable game sources from the pristine decompilation.
add_subdirectory(port)

message(STATUS "InsaniquariumOverhaul: i18n=${OVERHAUL_I18N} ui=${OVERHAUL_UI} hd=${OVERHAUL_HD} compat=${OVERHAUL_COMPAT}")
