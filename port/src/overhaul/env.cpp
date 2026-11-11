#include "overhaul/env.hpp"

#include "overhaul/log.hpp"

#include <cctype>
#include <cstdlib>
#include <stdexcept>

namespace overhaul
{
namespace
{
std::string Lowercase(std::string aText)
{
	for (char &aChar : aText)
		aChar = static_cast<char>(std::tolower(static_cast<unsigned char>(aChar)));
	return aText;
}

std::string Describe(const char *name, const std::string &raw) { return std::string(name) + "=\"" + raw + "\""; }
} // namespace

std::string GetEnv(const char *name)
{
	if (name == nullptr || *name == '\0')
		return std::string();

	const char *aValue = std::getenv(name);
	if (aValue == nullptr)
		return std::string();

	return std::string(aValue);
}

bool HasEnv(const char *name) { return !GetEnv(name).empty(); }

bool GetEnvBool(const char *name, bool fallback)
{
	const std::string aRaw = GetEnv(name);
	if (aRaw.empty())
		return fallback;

	const std::string aValue = Lowercase(aRaw);
	if (aValue == "1" || aValue == "true" || aValue == "yes" || aValue == "on")
		return true;
	if (aValue == "0" || aValue == "false" || aValue == "no" || aValue == "off")
		return false;

	LogWarn("ignoring " + Describe(name, aRaw) + ": expected a boolean (1/0, true/false, yes/no, on/off)");
	return fallback;
}

int GetEnvInt(const char *name, int fallback, int minimum, int maximum)
{
	const std::string aRaw = GetEnv(name);
	if (aRaw.empty())
		return fallback;

	int aNumber = 0;
	try
	{
		std::size_t aUsed = 0;
		aNumber = std::stoi(aRaw, &aUsed);
		if (aUsed != aRaw.size())
			throw std::invalid_argument("trailing characters");
	}
	catch (const std::exception &)
	{
		LogWarn("ignoring " + Describe(name, aRaw) + ": expected an integer in [" +
				std::to_string(minimum) + ", " + std::to_string(maximum) + "], using " +
				std::to_string(fallback));
		return fallback;
	}

	if (aNumber < minimum)
	{
		LogWarn("clamping " + Describe(name, aRaw) + " to " + std::to_string(minimum));
		return minimum;
	}
	if (aNumber > maximum)
	{
		LogWarn("clamping " + Describe(name, aRaw) + " to " + std::to_string(maximum));
		return maximum;
	}
	return aNumber;
}

} // namespace overhaul
