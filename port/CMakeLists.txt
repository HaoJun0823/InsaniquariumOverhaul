# port/ — the only place we modify.
# Four pillars are implemented here on top of external/winfish (logic)
# and external/poplib (portable backend).

# TODO: after studying poplib's API surface, add:
#   - derive step (invoke port/derive.py on external/winfish)
#   - i18n target
#   - hd target
#   - compat patches

add_library(overhaul_port INTERFACE)
target_include_directories(overhaul_port INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
