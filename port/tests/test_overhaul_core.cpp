// Unit tests for OverhaulCore.
//
// Deliberately framework-free: this repository has no test dependency, and the
// cost of a hand-written CHECK macro is lower than the cost of explaining a
// package manager to a build that otherwise only needs CMake and a compiler.
// Run with: ctest --test-dir build/game --output-on-failure

#include "overhaul/buildinfo.hpp"
#include "overhaul/env.hpp"
#include "overhaul/log.hpp"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>

namespace
{
int gFailures = 0;

void Check(bool aCondition, const char *aExpression, const char *aFile, int aLine)
{
	if (aCondition)
		return;
	++gFailures;
	std::fprintf(stderr, "FAIL %s:%d  %s\n", aFile, aLine, aExpression);
}

#define CHECK(expr) Check((expr), #expr, __FILE__, __LINE__)

// Each test sets the environment it depends on, so running the binary by hand
// and running it through CTest behave identically.
void SetVar(const char *aName, const char *aValue)
{
#if defined(_WIN32)
	_putenv_s(aName, aValue);
#else
	setenv(aName, aValue, 1);
#endif
}

void ClearVar(const char *aName)
{
#if defined(_WIN32)
	_putenv_s(aName, "");
#else
	unsetenv(aName);
#endif
}

void TestEnvPresence()
{
	CHECK(overhaul::GetEnv("OVERHAUL_TEST_UNSET_VARIABLE").empty());
	CHECK(!overhaul::HasEnv("OVERHAUL_TEST_UNSET_VARIABLE"));

	SetVar("OVERHAUL_TEST_PLAIN", "hello");
	CHECK(overhaul::GetEnv("OVERHAUL_TEST_PLAIN") == "hello");
	CHECK(overhaul::HasEnv("OVERHAUL_TEST_PLAIN"));
	ClearVar("OVERHAUL_TEST_PLAIN");
}

void TestEnvBool()
{
	const bool aFallback = true;

	SetVar("OVERHAUL_TEST_BOOL", "1");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", !aFallback) == true);
	SetVar("OVERHAUL_TEST_BOOL", "TRUE");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", !aFallback) == true);
	SetVar("OVERHAUL_TEST_BOOL", "yes");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", !aFallback) == true);
	SetVar("OVERHAUL_TEST_BOOL", "On");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", !aFallback) == true);

	SetVar("OVERHAUL_TEST_BOOL", "0");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == false);
	SetVar("OVERHAUL_TEST_BOOL", "false");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == false);
	SetVar("OVERHAUL_TEST_BOOL", "NO");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == false);
	SetVar("OVERHAUL_TEST_BOOL", "off");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == false);

	// Malformed input must fall back, not guess.
	SetVar("OVERHAUL_TEST_BOOL", "maybe");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == aFallback);

	ClearVar("OVERHAUL_TEST_BOOL");
	CHECK(overhaul::GetEnvBool("OVERHAUL_TEST_BOOL", aFallback) == aFallback);
}

void TestEnvInt()
{
	SetVar("OVERHAUL_TEST_INT", "7");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 0, 0, 10) == 7);

	// Out of range clamps to the nearest bound instead of overflowing or
	// silently disabling the feature.
	SetVar("OVERHAUL_TEST_INT", "999");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 0, 0, 10) == 10);
	SetVar("OVERHAUL_TEST_INT", "-5");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 0, 0, 10) == 0);

	// Garbage falls back.
	SetVar("OVERHAUL_TEST_INT", "12abc");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 3, 0, 10) == 3);
	SetVar("OVERHAUL_TEST_INT", "abc");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 3, 0, 10) == 3);

	ClearVar("OVERHAUL_TEST_INT");
	CHECK(overhaul::GetEnvInt("OVERHAUL_TEST_INT", 3, 0, 10) == 3);
}

void TestBuildInfo()
{
	CHECK(!overhaul::BuildInfo::Version().empty());
	CHECK(!overhaul::BuildInfo::Configuration().empty());
	CHECK(!overhaul::BuildInfo::Compiler().empty());
	CHECK(overhaul::BuildInfo::Compiler() != "unknown-compiler");
	CHECK(overhaul::BuildInfo::Architecture() != "unknown-arch");

	const std::string aDescription = overhaul::BuildInfo::Describe();
	CHECK(aDescription.find("commit") != std::string::npos);
	CHECK(aDescription.find(overhaul::BuildInfo::Version()) != std::string::npos);
}

void TestLogMirror()
{
	const char *aPath = "overhaul-test-log.txt";
	std::remove(aPath);

	overhaul::SetLogFile(aPath);
	overhaul::LogInfo("mirror check: 中文与 ASCII");
	overhaul::ClearLogFile();

	std::ifstream aFile(aPath, std::ios::binary);
	CHECK(aFile.good());

	std::string aContents((std::istreambuf_iterator<char>(aFile)), std::istreambuf_iterator<char>());
	aFile.close();

	CHECK(aContents.find("[overhaul][info] mirror check: 中文与 ASCII") != std::string::npos);

	std::remove(aPath);
}
} // namespace

int main()
{
	TestEnvPresence();
	TestEnvBool();
	TestEnvInt();
	TestBuildInfo();
	TestLogMirror();

	if (gFailures == 0)
	{
		std::fprintf(stderr, "overhaul_tests: all checks passed\n");
		return 0;
	}

	std::fprintf(stderr, "overhaul_tests: %d check(s) failed\n", gFailures);
	return 1;
}
