#pragma once

#include <filesystem>
#include <map>
#include <optional>
#include <string>

class IniConfig {
public:
    using Section = std::map<std::string, std::string>;

    bool load(const std::filesystem::path& path);
    std::optional<std::string> get(const std::string& section, const std::string& key) const;
    double get_number(const std::string& section, const std::string& key, double fallback) const;
    bool get_bool(const std::string& section, const std::string& key, bool fallback) const;
    std::size_t option_count() const;

private:
    std::map<std::string, Section> sections_;
};

