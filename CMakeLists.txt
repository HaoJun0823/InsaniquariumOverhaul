cmake_minimum_required(VERSION 3.20)
project(InsaniquariumOverhaul
    VERSION 0.1.0
    DESCRIPTION "Cross-platform, i18n, HD, and compatibility overhaul of Insaniquarium"
    LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- Options (four pillars) ----
option(OVERHAUL_I18N    "Enable multi-language / i18n layer"        ON)
option(OVERHAUL_HD      "Enable high-resolution rendering"         ON)
option(OVERHAUL_COMPAT  "Enable modern-system compatibility fixes" ON)
option(OVERHAUL_CROSS   "Build via portable poplib backend"        ON)

# ---- External: poplib (portable SexyAppFramework replacement) ----
# poplib provides an SDL3 / OpenAL / stb_image based backend.
# Integrate as a subdirectory once its CMake target names are confirmed.
# add_subdirectory(external/poplib)   # TODO: align with poplib's exported targets

# ---- External: winfish (pristine decompilation, read-only) ----
# Never edited in place. port/derive.py produces the buildable copy that
# replaces SexyAppFramework includes with poplib equivalents.
# The derived sources live under port/generated/ (gitignored).

# ---- Our layer ----
add_subdirectory(port)

message(STATUS "InsaniquariumOverhaul configured (skeleton)")
