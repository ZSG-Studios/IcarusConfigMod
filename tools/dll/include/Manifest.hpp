#pragma once

#include <filesystem>
#include <string>
#include <vector>

struct ManifestSummary {
    int table_multipliers = 0;
    int native_groups = 0;
    int direct_settings = 0;
    int growth_curves = 0;
    int runtime_settings = 0;
};

ManifestSummary read_manifest_summary(const std::filesystem::path& path);
std::vector<std::string> required_ini_sections();

