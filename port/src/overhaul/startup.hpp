#pragma once

namespace overhaul
{
// Announces this run on the diagnostic channel: build identity, executable
// path, and every OVERHAUL_* switch that is in effect.
//
// Called exactly once, from main(), before anything can fail. The point is that
// a log or a bug report always starts with enough context to reproduce it:
// which build, which architecture, which overrides, which directory.
void LogStartupBanner(const char *executablePath);

} // namespace overhaul
