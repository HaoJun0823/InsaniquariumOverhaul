#include "overhaul/buildinfo.hpp"

// Fallbacks keep this file compilable outside the CMake build (a one-off
// compile, a syntax check, an IDE that does not see the generated defines).
// "unknown" is a valid answer; a fabricated version would not be.
#ifndef OVERHAUL_VERSION
#define OVERHAUL_VERSION "0.0.0-dev"
#endif

#ifndef OVERHAUL_BUILD_CONFIG
#define OVERHAUL_BUILD_CONFIG "unknown"
#endif

#ifndef OVERHAUL_GIT_COMMIT
#define OVERHAUL_GIT_COMMIT "unknown"
#endif

namespace overhaul
{
namespace
{
std::string CompilerTag()
{
#if defined(_MSC_VER)
	return "msvc-" + std::to_string(_MSC_VER);
#elif defined(__clang__)
	return "clang-" + std::to_string(__clang_major__) + "." + std::to_string(__clang_minor__);
#elif defined(__GNUC__)
	return "gcc-" + std::to_string(__GNUC__) + "." + std::to_string(__GNUC_MINOR__);
#else
	return "unknown-compiler";
#endif
}

std::string ArchitectureTag()
{
#if defined(_M_X64) || defined(__x86_64__)
	return "x64";
#elif defined(_M_ARM64) || defined(__aarch64__)
	return "arm64";
#elif defined(_M_IX86) || defined(__i386__)
	return "x86";
#else
	return "unknown-arch";
#endif
}
} // namespace

std::string BuildInfo::Version() { return OVERHAUL_VERSION; }

std::string BuildInfo::Configuration() { return OVERHAUL_BUILD_CONFIG; }

std::string BuildInfo::Compiler() { return CompilerTag(); }

std::string BuildInfo::Architecture() { return ArchitectureTag(); }

std::string BuildInfo::Commit() { return OVERHAUL_GIT_COMMIT; }

std::string BuildInfo::Describe()
{
	return Version() + " " + Configuration() + " " + Architecture() + " " + CompilerTag() +
		   " commit " + Commit();
}

} // namespace overhaul
