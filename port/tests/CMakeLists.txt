# port/tests — unit tests for the code we own.
#
# Scope: pure logic in port/src. Anything that needs a window, a renderer, a
# device, or a frame belongs to the capture harness (port/run-capture-test.py),
# not here. This split is what keeps the fast tests fast and independent of SDL.
add_executable(overhaul_tests test_overhaul_core.cpp)

target_link_libraries(overhaul_tests PRIVATE OverhaulCore)

if(MSVC)
	target_compile_options(overhaul_tests PRIVATE /utf-8 /W4)
	target_compile_definitions(overhaul_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
	target_compile_options(overhaul_tests PRIVATE -Wall -Wextra)
endif()

set_target_properties(overhaul_tests PROPERTIES
	RUNTIME_OUTPUT_DIRECTORY         "${CMAKE_CURRENT_BINARY_DIR}/bin"
	RUNTIME_OUTPUT_DIRECTORY_DEBUG   "${CMAKE_CURRENT_BINARY_DIR}/bin"
	RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_CURRENT_BINARY_DIR}/bin"
)

add_test(NAME overhaul_core COMMAND overhaul_tests)
set_tests_properties(overhaul_core PROPERTIES
	WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/bin")
