#pragma once

#include <string>

namespace overhaul
{
// Identity of the running executable.
//
// Why this exists: a crash report, a screenshot, or a log tail that cannot be
// tied to an exact source state is not a bug report, it is an anecdote. Every
// run therefore starts by announcing what it is (see startup.cpp).
//
// The values are baked in at configure time by port/CMakeLists.txt. They are
// deliberately compile-time constants: reading them must never fail, never
// touch the filesystem, and never report a stale value from a previous build.
struct BuildInfo
{
	static std::string Version();        // CMake project version, e.g. "0.1.0"
	static std::string Configuration();  // Debug / Release / RelWithDebInfo
	static std::string Compiler();       // e.g. "msvc-1944", "clang-18.1", "gcc-13.2"
	static std::string Architecture();   // "x64", "arm64", "x86"
	static std::string Commit();         // short git SHA at configure time

	// Single line combining all of the above, in a fixed order.
	static std::string Describe();
};

} // namespace overhaul
