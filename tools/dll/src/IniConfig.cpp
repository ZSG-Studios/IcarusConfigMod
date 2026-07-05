#include "IniConfig.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>

namespace {
std::string trim(std::string value) {
    auto is_space = [](unsigned char ch) { return std::isspace(ch) != 0; };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), [&](char ch) { return !is_space(static_cast<unsigned char>(ch)); }));
    value.erase(std::find_if(value.rbegin(), value.rend(), [&](char ch) { return !is_space(static_cast<unsigned char>(ch)); }).base(), value.end());
    return value;
}

std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    return value;
}
}

bool IniConfig::load(const std::filesystem::path& path) {
    sections_.clear();
    std::ifstream input(path);
    if (!input) {
        return false;
    }

    std::string section;
    std::string line;
    while (std::getline(input, line)) {
        line = trim(line);
        if (line.empty() || line[0] == ';' || line[0] == '#') {
            continue;
        }
        if (line.front() == '[' && line.back() == ']') {
            section = trim(line.substr(1, line.size() - 2));
            sections_[section];
            continue;
        }
        const auto equals = line.find('=');
        if (equals == std::string::npos) {
            continue;
        }
        sections_[section][trim(line.substr(0, equals))] = trim(line.substr(equals + 1));
    }
    return true;
}

std::optional<std::string> IniConfig::get(const std::string& section, const std::string& key) const {
    const auto section_it = sections_.find(section);
    if (section_it == sections_.end()) {
        return std::nullopt;
    }
    const auto key_it = section_it->second.find(key);
    if (key_it == section_it->second.end()) {
        return std::nullopt;
    }
    return key_it->second;
}

double IniConfig::get_number(const std::string& section, const std::string& key, double fallback) const {
    const auto value = get(section, key);
    if (!value) {
        return fallback;
    }
    try {
        return std::stod(*value);
    } catch (...) {
        return fallback;
    }
}

bool IniConfig::get_bool(const std::string& section, const std::string& key, bool fallback) const {
    const auto value = get(section, key);
    if (!value) {
        return fallback;
    }
    const auto text = lower(*value);
    if (text == "1" || text == "true" || text == "yes" || text == "on") {
        return true;
    }
    if (text == "0" || text == "false" || text == "no" || text == "off") {
        return false;
    }
    return fallback;
}

std::size_t IniConfig::option_count() const {
    std::size_t count = 0;
    for (const auto& [_, section] : sections_) {
        count += section.size();
    }
    return count;
}

