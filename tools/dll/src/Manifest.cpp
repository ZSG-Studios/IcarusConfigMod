#include "Manifest.hpp"

#include <fstream>
#include <sstream>

namespace {
int count_array_entries(const std::string& text, const std::string& key) {
    const auto key_pos = text.find("\"" + key + "\"");
    if (key_pos == std::string::npos) {
        return 0;
    }
    const auto array_start = text.find('[', key_pos);
    if (array_start == std::string::npos) {
        return 0;
    }
    int depth = 0;
    int count = 0;
    bool in_object = false;
    for (std::size_t i = array_start; i < text.size(); ++i) {
        const char ch = text[i];
        if (ch == '[') {
            ++depth;
            continue;
        }
        if (ch == ']') {
            --depth;
            if (depth == 0) {
                break;
            }
            continue;
        }
        if (depth == 1 && ch == '{' && !in_object) {
            in_object = true;
            ++count;
        } else if (depth == 1 && ch == '}') {
            in_object = false;
        }
    }
    return count;
}
}

ManifestSummary read_manifest_summary(const std::filesystem::path& path) {
    ManifestSummary summary;
    std::ifstream input(path);
    if (!input) {
        return summary;
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    const auto text = buffer.str();
    summary.table_multipliers = count_array_entries(text, "tableMultipliers");
    summary.native_groups = count_array_entries(text, "nativeGroups");
    summary.direct_settings = count_array_entries(text, "directSettings");
    summary.growth_curves = count_array_entries(text, "growthCurves");
    summary.runtime_settings = count_array_entries(text, "runtimeSettings");
    return summary;
}

std::vector<std::string> required_ini_sections() {
    return {
        "metadata",
        "table_multipliers",
        "native_groups",
        "direct_settings",
        "growth_curves",
        "runtime",
        "notes",
    };
}

