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

# external/winfish and external/poplib are read-only submodules. They are NOT
# add_subdirectory'd here; port/CMakeLists.txt pulls in PopLib, and port/port.sh
# derives the buildable game sources from the pristine decompilation.
add_subdirectory(port)

message(STATUS "InsaniquariumOverhaul: i18n=${OVERHAUL_I18N} ui=${OVERHAUL_UI} hd=${OVERHAUL_HD} compat=${OVERHAUL_COMPAT}")
