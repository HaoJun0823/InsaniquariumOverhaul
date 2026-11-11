#pragma once

#include <string>

namespace overhaul
{
enum class LogLevel
{
	Info,
	Warn,
	Error
};

// Diagnostic channel for overhaul code.
//
// It writes to stderr, never to stdout. stdout belongs to SDL, BASS and any
// launcher in front of us; a diagnostic that can be mistaken for program output
// is not a diagnostic. stderr also survives `> log.txt` redirection without
// mixing with real output, and is what the automation harness captures.
void LogLine(LogLevel level, const std::string &message);

void LogInfo(const std::string &message);
void LogWarn(const std::string &message);
void LogError(const std::string &message);

// Mirrors every subsequent line into `path` (append mode).
//
// This is the only way to recover diagnostics when the executable is started by
// double-click and no console exists. The game never creates a log file on its
// own: a surprise file in the working directory is a side effect nobody asked
// for. Callers opt in through OVERHAUL_LOG_FILE.
void SetLogFile(const std::string &path);
void ClearLogFile();

} // namespace overhaul
