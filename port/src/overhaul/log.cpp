#include "overhaul/log.hpp"

#include <cstdio>

namespace overhaul
{
namespace
{
std::string &LogFilePath()
{
	// Function-local static: no static initialisation order problem, and the
	// path is available before main() runs if anything ever logs that early.
	static std::string sPath;
	return sPath;
}

const char *LevelName(LogLevel level)
{
	switch (level)
	{
	case LogLevel::Warn:
		return "warn";
	case LogLevel::Error:
		return "error";
	case LogLevel::Info:
	default:
		return "info";
	}
}
} // namespace

void SetLogFile(const std::string &path) { LogFilePath() = path; }

void ClearLogFile() { LogFilePath().clear(); }

void LogLine(LogLevel level, const std::string &message)
{
	const char *aName = LevelName(level);

	std::fprintf(stderr, "[overhaul][%s] %s\n", aName, message.c_str());
	std::fflush(stderr);

	const std::string &aPath = LogFilePath();
	if (aPath.empty())
		return;

	// Opened per line on purpose. Diagnostics are few and must survive a crash:
	// a buffered handle would lose exactly the lines that matter when the
	// process dies, and close-on-shutdown never runs for an access violation.
	FILE *aFile = std::fopen(aPath.c_str(), "a");
	if (aFile == nullptr)
		return;
	std::fprintf(aFile, "[overhaul][%s] %s\n", aName, message.c_str());
	std::fclose(aFile);
}

void LogInfo(const std::string &message) { LogLine(LogLevel::Info, message); }

void LogWarn(const std::string &message) { LogLine(LogLevel::Warn, message); }

void LogError(const std::string &message) { LogLine(LogLevel::Error, message); }

} // namespace overhaul
