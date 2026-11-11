#include "overhaul/startup.hpp"

#include "overhaul/buildinfo.hpp"
#include "overhaul/env.hpp"
#include "overhaul/log.hpp"

#include <string>

namespace overhaul
{
namespace
{
// Every switch that can change observable behaviour. A switch missing from this
// list makes a run unexplainable from its log, which is the exact failure this
// banner exists to prevent: add new switches here when you add them.
const char *const kReportedSwitches[] = {
	"OVERHAUL_USER_DATA_DIR",   // isolated profile root (tests, parallel runs)
	"OVERHAUL_UPDATE_DIALOG",   // legacy / force: dead update prompt
	"OVERHAUL_CAPTURE_FRAMES",  // exact frame numbers to export
	"OVERHAUL_CAPTURE_EVERY",   // periodic frame sampling interval
	"OVERHAUL_CAPTURE_MAX",     // cap on sampled frames
	"OVERHAUL_CAPTURE_DIR",     // capture output directory
	"OVERHAUL_LOG_FILE",        // mirror diagnostics into a file
};
} // namespace

void LogStartupBanner(const char *executablePath)
{
	LogInfo("Insaniquarium Overhaul " + BuildInfo::Describe());
	LogInfo(std::string("executable: ") + (executablePath != nullptr ? executablePath : "(unknown)"));

	bool anyOverride = false;
	for (const char *aName : kReportedSwitches)
	{
		if (!HasEnv(aName))
			continue;
		if (!anyOverride)
		{
			LogInfo("overrides:");
			anyOverride = true;
		}
		LogInfo(std::string("  ") + aName + "=" + GetEnv(aName));
	}

	if (!anyOverride)
		LogInfo("overrides: none");
}

} // namespace overhaul
