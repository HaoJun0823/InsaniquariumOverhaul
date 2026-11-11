#pragma once

#include <string>

namespace overhaul
{
// Access to the OVERHAUL_* environment switches.
//
// Rules, because these switches change what a run does and are therefore part
// of every bug report:
//
//  - GetEnv returns an empty string when the variable is unset. Callers must
//    handle absence explicitly; there is no "sensible default" hiding here.
//  - The typed parsers never fail silently. A malformed value is reported on
//    the log channel and the caller's fallback is used, so a typo in a switch
//    is never later mistaken for a code bug.
//  - Numeric values are clamped to the caller's range, and clamping is logged.
std::string GetEnv(const char *name);

bool HasEnv(const char *name);

bool GetEnvBool(const char *name, bool fallback);

// Returns `fallback` for unparsable input, and clamps to [minimum, maximum].
int GetEnvInt(const char *name, int fallback, int minimum, int maximum);

} // namespace overhaul
