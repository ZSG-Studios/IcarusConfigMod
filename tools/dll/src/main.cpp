#include "IniConfig.hpp"
#include "Manifest.hpp"

#include <DynamicOutput/Output.hpp>
#include <Helpers/Casting.hpp>
#include <Mod/CppUserModBase.hpp>
#include <Unreal/Hooks.hpp>
#include <Unreal/Core/Containers/Map.hpp>
#include <Unreal/NameTypes.hpp>
#include <Unreal/Property/FArrayProperty.hpp>
#include <Unreal/Property/FNumericProperty.hpp>
#include <Unreal/Property/FStructProperty.hpp>
#include <Unreal/Core/Containers/ScriptArray.hpp>
#include <Unreal/TypeChecker.hpp>
#include <Unreal/TObjectPtr.hpp>
#include <Unreal/UObject.hpp>
#include <Unreal/UObjectGlobals.hpp>
#include <Unreal/UScriptStruct.hpp>
#include <Unreal/UStruct.hpp>
#include <Unreal/UnrealFlags.hpp>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
constexpr std::string_view kModName = "Configuration_Mod";

std::filesystem::path this_module_path() {
    HMODULE module{};
    const auto address = reinterpret_cast<LPCWSTR>(&this_module_path);
    if (!GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            address,
            &module
        )) {
        return {};
    }

    wchar_t buffer[MAX_PATH]{};
    const auto length = GetModuleFileNameW(module, buffer, MAX_PATH);
    if (length == 0 || length >= MAX_PATH) {
        return {};
    }
    return std::filesystem::path(buffer);
}

std::filesystem::path mod_dir() {
    const auto module = this_module_path();
    if (!module.empty()) {
        const auto dlls = module.parent_path();
        if (dlls.filename() == "dlls") {
            return dlls.parent_path();
        }
    }
    return std::filesystem::current_path() / "Mods" / std::string(kModName);
}

void append_log(const std::filesystem::path& root, const std::string& message) {
    std::ofstream output(root / "runtime_dll.log", std::ios::app);
    if (output) {
        output << message << "\n";
    }
}

std::filesystem::path find_unified_ini(const std::filesystem::path& root) {
    const auto preferred = root / "settings.ini";
    if (std::filesystem::is_regular_file(preferred)) {
        return preferred;
    }

    std::error_code error;
    for (const auto& entry : std::filesystem::directory_iterator(root, error)) {
        if (!error && entry.is_regular_file() && entry.path().extension() == ".ini") {
            return entry.path();
        }
    }
    return preferred;
}

std::string narrow(const std::filesystem::path& path) {
    return path.string();
}

struct RuntimeSettings {
    double air_control{1.0};
    double camera_tilt{1.0};
};

enum class NumericMode {
    Multiply,
    Divide,
};

enum class NumericResult {
    Float,
    Floor,
    Nearest,
};

struct NumericTableRule {
    const char* key;
    const char* section;
    const char* table_stem;
    std::vector<const char*> fields;
    NumericMode mode{NumericMode::Multiply};
    NumericResult result{NumericResult::Float};
    double minimum{0.0};
    std::vector<const char*> row_names{};
    std::vector<const char*> exclude_suffixes{};
};

struct RangeGroupRule {
    const char* key_prefix;
    const char* table_stem;
    const char* field;
    std::vector<std::pair<double, double>> ranges;
    double minimum{0.0};
    std::vector<const char*> exclude_contains{};
};

struct ArrayNumericRule {
    const char* key;
    const char* section;
    const char* table_stem;
    const char* array_field;
    const char* numeric_field;
    NumericMode mode{NumericMode::Multiply};
    NumericResult result{NumericResult::Float};
    double minimum{0.0};
    std::vector<const char*> exclude_contains{};
};

struct ArrayRangeGroupRule {
    const char* key_prefix;
    const char* table_stem;
    const char* array_field;
    const char* numeric_field;
    std::vector<std::pair<double, double>> ranges;
    double minimum{0.0};
    std::vector<const char*> exclude_contains{};
};

struct GrowthCurveRule {
    const char* key;
    const char* asset_stem;
};

struct UnsupportedSettingRule {
    const char* section;
    const char* key;
    double fallback;
    const char* reason;
};

const NumericTableRule kNumericTableRules[] = {
    {"mining_speed", "table_multipliers", "D_OreDeposit", {"MiningTimeSeconds"}, NumericMode::Divide, NumericResult::Floor, 1.0},
    {"mining_yield", "table_multipliers", "D_ToolDamage", {"Mining_Efficiency"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"ore_density", "table_multipliers", "D_VoxelSetupData", {"DensityMultiplier"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"wood_yield", "table_multipliers", "D_ToolDamage", {"Felling_Efficiency"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"skinning_yield", "table_multipliers", "D_ToolDamage", {"Skinning_Efficiency"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"reaping_yield", "table_multipliers", "D_ToolDamage", {"Reaping_Efficiency"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"processing_speed", "table_multipliers", "D_ProcessorRecipes", {"RequiredMillijoules"}, NumericMode::Divide, NumericResult::Floor, 1.0},
    {"processing_speed", "table_multipliers", "D_ExtractorRecipes", {"RequiredMillijoules"}, NumericMode::Divide, NumericResult::Floor, 1.0},
    {"crafting_xp", "table_multipliers", "D_ItemsStatic", {"CraftingExperience"}, NumericMode::Multiply, NumericResult::Nearest, 0.0},
    {"fuel_duration", "table_multipliers", "D_Combustible", {"MillijoulesProvided"}, NumericMode::Multiply, NumericResult::Nearest, 1.0},
    {"weight_reduction", "table_multipliers", "D_Itemable", {"Weight"}, NumericMode::Divide, NumericResult::Floor, 1.0},
    {"durability", "table_multipliers", "D_Durable", {"Max_Durability"}, NumericMode::Multiply, NumericResult::Nearest, 1.0},
    {"spoil_duration", "table_multipliers", "D_Decayable", {"DecayTime", "SpoilTime"}, NumericMode::Multiply, NumericResult::Nearest, 1.0},
    {"food_buff_duration", "table_multipliers", "D_Consumable", {"ModifierLifetime"}, NumericMode::Multiply, NumericResult::Nearest, 1.0},
    {"food_buff_potency", "table_multipliers", "D_Consumable", {"ModifierEffectiveness"}, NumericMode::Multiply, NumericResult::Float, 0.01},
    {"crop_speed", "table_multipliers", "D_FarmingGrowthStates", {"TimeToNextState"}, NumericMode::Divide, NumericResult::Floor, 1.0, {}, {"_Dead"}},
    {"fishing_speed", "table_multipliers", "D_GameplayConfig", {"FloatValue"}, NumericMode::Divide, NumericResult::Float, 0.1, {"BaseMinFishingTime", "BaseMaxFishingTime"}},
    {"melee_damage", "table_multipliers", "D_ToolDamage", {"Melee_Damage"}, NumericMode::Multiply, NumericResult::Float, 0.0},
    {"ranged_damage", "table_multipliers", "D_AmmoTypes", {"ProjectileDamage"}, NumericMode::Multiply, NumericResult::Float, 0.0},
    {"reload_speed", "table_multipliers", "D_FirearmData", {"ReloadTime", "WeaponReloadTime"}, NumericMode::Divide, NumericResult::Float, 0.05},
    {"reload_speed", "table_multipliers", "D_RangedWeaponData", {"ReloadTime", "WeaponReloadTime"}, NumericMode::Divide, NumericResult::Float, 0.05},
    {"backpack_slots", "direct_settings", "D_InventoryInfo", {"StartingSlots"}, NumericMode::Multiply, NumericResult::Nearest, 1.0, {"Backpack"}},
};

const RangeGroupRule kRangeGroupRules[] = {
    {"xpGroup", "D_ExperienceEvents", "ExperienceGranted", {{1, 10}, {11, 25}, {26, 50}, {51, 100}, {101, 250}, {251, 500}, {501, 1000}, {1001, 1000000}}, 0.0},
    {"stackGroup", "D_Itemable", "MaxStack", {{2, 10}, {11, 25}, {26, 50}, {51, 100}, {101, 250}, {251, 500}, {501, 1000000}}, 1.0, {"_Kitchen_"}},
    {"slotGroup", "D_InventoryInfo", "StartingSlots", {{1, 1}, {2, 5}, {6, 10}, {11, 25}, {26, 50}, {51, 1000}}, 1.0},
};

const ArrayNumericRule kArrayNumericRules[] = {
    {"material_efficiency", "table_multipliers", "D_ProcessorRecipes", "Inputs", "Count", NumericMode::Divide, NumericResult::Floor, 1.0},
};

const ArrayRangeGroupRule kArrayRangeGroupRules[] = {
    {"recipeOutputGroup", "D_ProcessorRecipes", "Outputs", "Count", {{2, 5}, {6, 10}, {11, 25}, {26, 50}, {51, 1000}}, 1.0, {"_Kitchen_"}},
    {"missionCurrencyGroup", "D_FactionMissions", "CurrencyRewarded", "Amount", {{1, 25}, {26, 50}, {51, 100}, {101, 250}, {251, 500}, {501, 1000}, {1001, 1000000}}, 0.0},
};

const GrowthCurveRule kGrowthCurveRules[] = {
    {"player_talent_growth", "C_PlayerTalentGrowth"},
    {"solo_talent_growth", "C_SoloTalentGrowth"},
    {"player_blueprint_growth", "C_PlayerBlueprintGrowth"},
    {"mount_talent_growth", "C_MountTalentGrowth"},
    {"pet_talent_growth", "C_PetTalentGrowth"},
};

const UnsupportedSettingRule kUnsupportedMultiplierRules[] = {
    {"runtime", "camera_tilt", 1.0, "camera_property_not_verified"},
    {"table_multipliers", "health", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "stamina", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "carry_capacity", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "movement_speed", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "health_regen", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "stamina_regen", 1.0, "runtime_stat_not_implemented"},
    {"table_multipliers", "needs_duration", 1.0, "runtime_stat_not_implemented"},
    {"direct_settings", "starter_ren", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "starter_exotics", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "starter_red_exotics", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "starter_biomass", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "starter_uranium", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "starter_licence", 0.0, "mission_reward_direct_not_implemented"},
    {"direct_settings", "lucky_strike_chance", 1.0, "talent_stat_not_implemented"},
};

bool array_range_group_mutation_enabled(const ArrayRangeGroupRule& rule) {
    const auto key = std::string_view(rule.key_prefix);
    return key == "missionCurrencyGroup" || key == "recipeOutputGroup";
}

double clamped_multiplier(double value, double minimum, double maximum) {
    if (!std::isfinite(value)) {
        return 1.0;
    }
    return std::clamp(value, minimum, maximum);
}

bool is_vanilla_multiplier(double value) {
    return std::abs(value - 1.0) < 0.000001;
}

RC::StringType wide_from_ascii(std::string_view text) {
    RC::StringType result;
    result.reserve(text.size());
    for (const char ch : text) {
        result.push_back(static_cast<RC::CharType>(static_cast<unsigned char>(ch)));
    }
    return result;
}

std::string narrow_unreal(const RC::StringType& text) {
    std::string result;
    result.reserve(text.size());
    for (const auto ch : text) {
        result.push_back(static_cast<char>(ch <= 0x7f ? ch : '?'));
    }
    return result;
}

bool contains_text(std::string_view haystack, std::string_view needle) {
    return haystack.find(needle) != std::string_view::npos;
}

bool ends_with_text(std::string_view text, std::string_view suffix) {
    return text.size() >= suffix.size() && text.substr(text.size() - suffix.size()) == suffix;
}

RC::Unreal::FProperty* find_struct_property_by_name(RC::Unreal::UStruct* row_struct, const char* field_name) {
    if (!row_struct || !field_name) {
        return nullptr;
    }

    for (auto* property : row_struct->ForEachPropertyInChain()) {
        if (!property) {
            continue;
        }
        if (narrow_unreal(property->GetName()) == field_name) {
            return property;
        }
    }

    const auto field_wide = wide_from_ascii(field_name);
    return row_struct->FindProperty(RC::Unreal::FName(field_wide.c_str()));
}

RC::Unreal::FNumericProperty* as_numeric_property(RC::Unreal::FProperty* property) {
    if (!property) {
        return nullptr;
    }

    if (auto* numeric = RC::Unreal::CastField<RC::Unreal::FNumericProperty>(property)) {
        return numeric;
    }

    try {
        if (property->GetClass().HasAnyCastFlags(RC::Unreal::CASTCLASS_FNumericProperty)) {
            return static_cast<RC::Unreal::FNumericProperty*>(property);
        }
    } catch (...) {
    }
    return nullptr;
}

std::string property_class_name(RC::Unreal::FProperty* property) {
    if (!property) {
        return "<missing>";
    }
    try {
        return narrow_unreal(property->GetClass().GetName());
    } catch (...) {
        return "<class_error>";
    }
}

std::string struct_property_list(RC::Unreal::UStruct* row_struct, std::size_t limit = 80) {
    if (!row_struct) {
        return "<missing>";
    }

    std::string properties;
    std::size_t property_count = 0;
    for (auto* property : row_struct->ForEachPropertyInChain()) {
        if (!property) {
            continue;
        }
        if (!properties.empty()) {
            properties += ",";
        }
        properties += narrow_unreal(property->GetName());
        ++property_count;
        if (property_count >= limit) {
            properties += ",...";
            break;
        }
    }
    return properties;
}

bool listed_row(std::string_view row, const std::vector<const char*>& names) {
    if (names.size() == 0) {
        return true;
    }
    return std::any_of(names.begin(), names.end(), [&](const char* name) { return row == name; });
}

bool excluded_row(
    std::string_view row,
    const std::vector<const char*>& contains,
    const std::vector<const char*>& suffixes = {}
) {
    for (const char* needle : contains) {
        if (contains_text(row, needle)) {
            return true;
        }
    }
    for (const char* suffix : suffixes) {
        if (ends_with_text(row, suffix)) {
            return true;
        }
    }
    return false;
}

double adjusted_numeric(double baseline, double multiplier, NumericMode mode, NumericResult result, double minimum) {
    double value = mode == NumericMode::Divide
        ? (multiplier == 0.0 ? baseline : baseline / multiplier)
        : baseline * multiplier;
    value = (std::max)(value, minimum);
    if (result == NumericResult::Floor) {
        value = std::floor(value);
    } else if (result == NumericResult::Nearest) {
        value = std::round(value);
    }
    return value;
}
}

namespace ConfigurationMod {
class RuntimeMod final : public RC::CppUserModBase {
public:
    RuntimeMod() {
        ModVersion = STR("1.0.0");
        ModName = STR("Configuration_Mod");
        ModAuthors = STR("Zachary Rose");
        ModDescription = STR("INI-driven Icarus configuration runtime");

        root_ = mod_dir();
        append_log(root_, "Configuration_Mod C++ runtime DLL constructed.");
        RC::Output::send<RC::LogLevel::Warning>(STR("[Configuration_Mod] C++ runtime constructed.\n"));
        load_config("constructor");
    }

    ~RuntimeMod() override {
        append_log(root_, "Configuration_Mod C++ runtime unloaded.");
    }

    auto on_program_start() -> void override {
        append_log(root_, "UE4SS on_program_start fired.");
    }

    auto on_unreal_init() -> void override {
        append_log(root_, "UE4SS on_unreal_init fired.");
        load_config("on_unreal_init");
        register_hooks();
        append_log(root_, "VALIDATION StartupMode=deferred EarlyTableScan=false StaticConstructHook=false");
    }

    auto on_update() -> void override {
        const ULONGLONG now = GetTickCount64();
        if (next_runtime_scan_ms_ == 0) {
            next_runtime_scan_ms_ = now + 1000;
            next_schema_diagnostic_ms_ = now + 15000;
            return;
        }

        if (now >= next_runtime_scan_ms_ && runtime_scan_count_ < 120) {
            next_runtime_scan_ms_ = now + 5000;
            ++runtime_scan_count_;
            load_config("update_scan");
            apply_runtime_settings("update_scan");
        }

        if (!schema_diagnostics_logged_ && now >= next_schema_diagnostic_ms_) {
            schema_diagnostics_logged_ = true;
            log_table_schema_diagnostics("update_schema_probe");
            tables_applied_ = apply_table_settings("update_table_apply_once");
            next_table_apply_ms_ = now + 15000;
        } else if (!tables_applied_ && schema_diagnostics_logged_ && now >= next_table_apply_ms_ && table_apply_attempts_ < 20) {
            next_table_apply_ms_ = now + 15000;
            ++table_apply_attempts_;
            tables_applied_ = apply_table_settings("update_table_retry_" + std::to_string(table_apply_attempts_));
        }
    }

private:
    void register_hooks() {
        if (hooks_registered_) {
            return;
        }
        hooks_registered_ = true;

        RC::Unreal::Hook::RegisterBeginPlayPostCallback([this]([[maybe_unused]] RC::Unreal::AActor* actor) {
            if (begin_play_applied_) {
                return;
            }
            begin_play_applied_ = true;
            apply_runtime_settings("begin_play_once");
            append_log(root_, "VALIDATION ApplyStatus=tables Phase=begin_play_once TableMutationStatus=deferred_until_schema_probe");
        });

        append_log(root_, "Registered UE4SS runtime hooks: BeginPlayPost.");
    }

    void load_config(std::string_view phase) {
        try {
            IniConfig config;
            const auto ini_path = find_unified_ini(root_);
            const bool ini_read = config.load(ini_path);
            const auto manifest_path = root_ / "option_manifest.json";
            const auto manifest = read_manifest_summary(manifest_path);
            const bool manifest_read = std::filesystem::is_regular_file(manifest_path);

            if (!ini_read) {
                append_log(root_, "ERROR: failed to read unified INI: " + narrow(ini_path));
            }
            settings_.air_control = clamped_multiplier(config.get_number("runtime", "air_control", config.get_number("runtime", "airControl", 1.0)), 0.0, 20.0);
            settings_.camera_tilt = clamped_multiplier(config.get_number("runtime", "camera_tilt", config.get_number("runtime", "cameraTilt", 1.0)), 0.0, 20.0);

            append_log(root_, "Phase=" + std::string(phase));
            append_log(root_, "INI path: " + narrow(ini_path));
            append_log(root_, "INI options read: " + std::to_string(config.option_count()));
            append_log(
                root_,
                "Runtime settings: air_control=" + std::to_string(settings_.air_control)
                    + " camera_tilt=" + std::to_string(settings_.camera_tilt)
            );
            append_log(
                root_,
                "Manifest counts: table=" + std::to_string(manifest.table_multipliers)
                    + " groups=" + std::to_string(manifest.native_groups)
                    + " direct=" + std::to_string(manifest.direct_settings)
                    + " curves=" + std::to_string(manifest.growth_curves)
                    + " runtime=" + std::to_string(manifest.runtime_settings)
            );
            append_log(
                root_,
                "VALIDATION DllLoaded=true IniRead=" + std::string(ini_read ? "true" : "false")
                    + " ManifestRead=" + std::string(manifest_read ? "true" : "false")
                    + " IniOptions=" + std::to_string(config.option_count())
                    + " TableOptions=" + std::to_string(manifest.table_multipliers)
                    + " NativeGroups=" + std::to_string(manifest.native_groups)
                    + " DirectOptions=" + std::to_string(manifest.direct_settings)
                    + " CurveOptions=" + std::to_string(manifest.growth_curves)
                    + " RuntimeOptions=" + std::to_string(manifest.runtime_settings)
                    + " Backend=UE4SS_CPP_DLL"
            );
            append_unsupported_active_options(config, phase);
        } catch (const std::exception& error) {
            append_log(root_, std::string("ERROR: C++ runtime exception: ") + error.what());
        } catch (...) {
            append_log(root_, "ERROR: unknown C++ runtime exception.");
        }
    }

    void apply_runtime_settings(std::string_view phase) {
        try {
            std::vector<RC::Unreal::UObject*> movement_components;
            RC::Unreal::UObjectGlobals::FindAllOf(STR("CharacterMovementComponent"), movement_components);

            std::size_t air_applied = 0;
            std::size_t air_missing = 0;
            for (RC::Unreal::UObject* object : movement_components) {
                if (apply_air_control(object)) {
                    ++air_applied;
                } else {
                    ++air_missing;
                }
            }

            append_log(
                root_,
                "VALIDATION ApplyStatus=runtime Phase=" + std::string(phase)
                    + " AirControlMultiplier=" + std::to_string(settings_.air_control)
                    + " AirControlAppliedObjects=" + std::to_string(air_applied)
                    + " AirControlMissingObjects=" + std::to_string(air_missing)
                    + " CameraTiltStatus=" + camera_tilt_status()
                    + " TableMutationStatus=deferred_to_table_phase"
                    + " CurveMutationStatus=deferred_to_table_phase"
            );
            append_log(
                root_,
                "SETTING_STATUS Phase=" + std::string(phase)
                    + " Id=runtime.air_control"
                    + " Result=" + std::string(is_vanilla_multiplier(settings_.air_control) ? "inactive" : (air_applied > 0 ? "applied" : "pending"))
                    + " Active=" + std::string(is_vanilla_multiplier(settings_.air_control) ? "false" : "true")
                    + " Supported=true"
                    + " Value=" + std::to_string(settings_.air_control)
                    + " TargetsSeen=" + std::to_string(movement_components.size())
                    + " TargetsMatched=" + std::to_string(air_applied + air_missing)
                    + " Applied=" + std::to_string(air_applied)
                    + " Missing=" + std::to_string(air_missing)
                    + " Skipped=0"
                    + " Reason="
            );
            append_log(
                root_,
                "SETTING_STATUS Phase=" + std::string(phase)
                    + " Id=runtime.camera_tilt"
                    + " Result=" + std::string(is_vanilla_multiplier(settings_.camera_tilt) ? "inactive" : "unsupported")
                    + " Active=" + std::string(is_vanilla_multiplier(settings_.camera_tilt) ? "false" : "true")
                    + " Supported=false"
                    + " Value=" + std::to_string(settings_.camera_tilt)
                    + " TargetsSeen=0 TargetsMatched=0 Applied=0 Missing=0 Skipped=0"
                    + " Reason=" + camera_tilt_status()
            );
        } catch (const std::exception& error) {
            append_log(root_, std::string("ERROR: apply_runtime_settings exception: ") + error.what());
        } catch (...) {
            append_log(root_, "ERROR: unknown apply_runtime_settings exception.");
        }
    }

    void apply_runtime_object(RC::Unreal::UObject* object, std::string_view phase) {
        if (!object || !RC::Unreal::UObject::IsReal(object)) {
            return;
        }
        if (object->HasAnyFlags(RC::Unreal::RF_ClassDefaultObject)) {
            return;
        }
        if (apply_air_control(object)) {
            append_log(root_, "VALIDATION ApplyStatus=runtime_object Phase=" + std::string(phase) + " AirControlAppliedObjects=1");
        }
    }

    bool apply_air_control(RC::Unreal::UObject* object) {
        if (!object || object->HasAnyFlags(RC::Unreal::RF_ClassDefaultObject)) {
            return false;
        }

        auto* air_control = object->GetValuePtrByPropertyNameInChain<float>(STR("AirControl"));
        if (!air_control) {
            return false;
        }

        auto [baseline_it, inserted] = air_control_baselines_.try_emplace(object, *air_control);
        const float baseline = baseline_it->second;
        const auto adjusted = static_cast<float>(std::clamp(static_cast<double>(baseline) * settings_.air_control, 0.0, 1.0));
        if (*air_control != adjusted) {
            *air_control = adjusted;
        }
        return true;
    }

    std::string camera_tilt_status() const {
        if (settings_.camera_tilt == 1.0) {
            return "vanilla";
        }
        return "not_enabled_without_verified_icarus_camera_property";
    }

    struct SettingStatus {
        std::string section;
        std::string key;
        double value{1.0};
        bool active{false};
        bool supported{true};
        std::string reason;
        std::size_t targets_seen{0};
        std::size_t targets_matched{0};
        std::size_t applied{0};
        std::size_t missing{0};
        std::size_t skipped{0};
    };

    using SettingStatusMap = std::unordered_map<std::string, SettingStatus>;

    static std::string setting_id(std::string_view section, std::string_view key) {
        return std::string(section) + "." + std::string(key);
    }

    SettingStatus& ensure_setting_status(
        SettingStatusMap& statuses,
        const char* section,
        const char* key,
        double value,
        bool active,
        bool supported = true,
        std::string reason = {}
    ) const {
        auto id = setting_id(section, key);
        auto [it, inserted] = statuses.try_emplace(id);
        auto& status = it->second;
        if (inserted) {
            status.section = section;
            status.key = key;
        }
        status.value = value;
        status.active = status.active || active;
        status.supported = status.supported && supported;
        if (!reason.empty()) {
            status.reason = std::move(reason);
        }
        return status;
    }

    SettingStatusMap initialize_setting_statuses(const IniConfig& config, std::size_t data_tables_seen, std::size_t curve_objects_seen) const {
        SettingStatusMap statuses;

        for (const auto& rule : kNumericTableRules) {
            const double value = config.get_number(rule.section, rule.key, 1.0);
            auto& status = ensure_setting_status(statuses, rule.section, rule.key, value, !is_vanilla_multiplier(value));
            status.targets_seen += data_tables_seen;
        }
        for (const auto& rule : kRangeGroupRules) {
            auto& status = ensure_setting_status(statuses, "native_groups", rule.key_prefix, 1.0, false);
            status.targets_seen += data_tables_seen;
            for (std::size_t index = 0; index < rule.ranges.size(); ++index) {
                const double value = config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(index + 1), 1.0);
                if (!is_vanilla_multiplier(value)) {
                    status.active = true;
                    status.value = value;
                }
            }
        }
        for (const auto& rule : kArrayNumericRules) {
            const double value = config.get_number(rule.section, rule.key, 1.0);
            auto& status = ensure_setting_status(statuses, rule.section, rule.key, value, !is_vanilla_multiplier(value));
            status.targets_seen += data_tables_seen;
        }
        for (const auto& rule : kArrayRangeGroupRules) {
            const bool supported = array_range_group_mutation_enabled(rule);
            auto& status = ensure_setting_status(
                statuses,
                "native_groups",
                rule.key_prefix,
                1.0,
                false,
                supported,
                supported ? "" : "array_mutation_disabled"
            );
            status.targets_seen += data_tables_seen;
            for (std::size_t index = 0; index < rule.ranges.size(); ++index) {
                const double value = config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(index + 1), 1.0);
                if (!is_vanilla_multiplier(value)) {
                    status.active = true;
                    status.value = value;
                }
            }
        }
        for (const auto& rule : kGrowthCurveRules) {
            const double value = config.get_number("growth_curves", rule.key, 1.0);
            auto& status = ensure_setting_status(statuses, "growth_curves", rule.key, value, !is_vanilla_multiplier(value));
            status.targets_seen += curve_objects_seen;
        }
        for (const auto& rule : kUnsupportedMultiplierRules) {
            const double value = config.get_number(rule.section, rule.key, rule.fallback);
            ensure_setting_status(statuses, rule.section, rule.key, value, std::isfinite(value) && value != rule.fallback, false, rule.reason);
        }
        ensure_setting_status(statuses, "direct_settings", "remove_shelter_requirement", config.get_bool("direct_settings", "remove_shelter_requirement", false) ? 1.0 : 0.0, config.get_bool("direct_settings", "remove_shelter_requirement", false), false, "direct_table_not_implemented");
        ensure_setting_status(statuses, "direct_settings", "weatherproof_deployables", config.get_bool("direct_settings", "weatherproof_deployables", false) ? 1.0 : 0.0, config.get_bool("direct_settings", "weatherproof_deployables", false), false, "direct_table_not_implemented");
        ensure_setting_status(statuses, "direct_settings", "free_craft", config.get_bool("direct_settings", "free_craft", false) ? 1.0 : 0.0, config.get_bool("direct_settings", "free_craft", false));

        return statuses;
    }

    void log_setting_statuses(const SettingStatusMap& statuses, std::string_view phase) {
        std::size_t total = 0;
        std::size_t inactive = 0;
        std::size_t applied = 0;
        std::size_t pending = 0;
        std::size_t skipped = 0;
        std::size_t unsupported = 0;
        std::size_t partial = 0;
        std::size_t active_total = 0;
        std::size_t missing_fields = 0;

        for (const auto& [id, status] : statuses) {
            ++total;
            std::string result;
            std::string reason = status.reason;
            if (!status.active) {
                result = "inactive";
                ++inactive;
            } else if (!status.supported) {
                ++active_total;
                result = "unsupported";
                ++unsupported;
                if (reason.empty()) {
                    reason = "not_implemented";
                }
            } else if (status.skipped > 0 && status.applied == 0) {
                ++active_total;
                result = "skipped";
                ++skipped;
                if (reason.empty()) {
                    reason = "safety_or_schema_skip";
                }
            } else if (status.applied > 0 && status.missing > 0) {
                ++active_total;
                ++partial;
                missing_fields += status.missing;
                result = "partial";
                if (reason.empty()) {
                    reason = "some_targets_or_fields_missing";
                }
            } else if (status.applied > 0) {
                ++active_total;
                result = "applied";
                ++applied;
            } else {
                ++active_total;
                result = "pending";
                ++pending;
                if (reason.empty()) {
                    reason = status.targets_matched == 0 ? "target_not_seen_yet" : "target_seen_but_no_fields_applied";
                }
            }

            append_log(
                root_,
                "SETTING_STATUS Phase=" + std::string(phase)
                    + " Id=" + id
                    + " Result=" + result
                    + " Active=" + std::string(status.active ? "true" : "false")
                    + " Supported=" + std::string(status.supported ? "true" : "false")
                    + " Value=" + std::to_string(status.value)
                    + " TargetsSeen=" + std::to_string(status.targets_seen)
                    + " TargetsMatched=" + std::to_string(status.targets_matched)
                    + " Applied=" + std::to_string(status.applied)
                    + " Missing=" + std::to_string(status.missing)
                    + " Skipped=" + std::to_string(status.skipped)
                    + " Reason=" + reason
            );
        }

        append_log(
            root_,
            "VALIDATION SettingsSummary Phase=" + std::string(phase)
                + " Total=" + std::to_string(total)
                + " Active=" + std::to_string(active_total)
                + " Applied=" + std::to_string(applied)
                + " Partial=" + std::to_string(partial)
                + " Pending=" + std::to_string(pending)
                + " Skipped=" + std::to_string(skipped)
                + " Unsupported=" + std::to_string(unsupported)
                + " MissingFields=" + std::to_string(missing_fields)
                + " Inactive=" + std::to_string(inactive)
        );
        append_log(
            root_,
            "VALIDATION GreenLight Phase=" + std::string(phase)
                + " GreenLight=" + std::string((partial == 0 && pending == 0 && skipped == 0 && unsupported == 0) ? "YES" : "NO")
                + " Active=" + std::to_string(active_total)
                + " Applied=" + std::to_string(applied)
                + " Partial=" + std::to_string(partial)
                + " Pending=" + std::to_string(pending)
                + " Skipped=" + std::to_string(skipped)
                + " Unsupported=" + std::to_string(unsupported)
                + " MissingFields=" + std::to_string(missing_fields)
        );
    }

    void append_unsupported_active_options(const IniConfig& config, std::string_view phase) {
        std::vector<std::string> active;

        const auto note_multiplier = [&](const char* section, const char* key, double fallback, const char* reason) {
            const double value = config.get_number(section, key, fallback);
            if (std::isfinite(value) && value != fallback) {
                active.push_back(std::string(key) + "(" + reason + ")");
            }
        };
        const auto note_bool = [&](const char* section, const char* key, const char* reason) {
            if (config.get_bool(section, key, false)) {
                active.push_back(std::string(key) + "(" + reason + ")");
            }
        };

        for (const auto& rule : kUnsupportedMultiplierRules) {
            note_multiplier(rule.section, rule.key, rule.fallback, rule.reason);
        }
        note_bool("direct_settings", "remove_shelter_requirement", "direct_table_not_implemented");
        note_bool("direct_settings", "weatherproof_deployables", "direct_table_not_implemented");

        if (active.empty()) {
            return;
        }

        std::ostringstream joined;
        for (std::size_t index = 0; index < active.size(); ++index) {
            if (index != 0) {
                joined << ",";
            }
            joined << active[index];
        }
        append_log(
            root_,
            "VALIDATION UnsupportedActiveOptions Phase=" + std::string(phase)
                + " Count=" + std::to_string(active.size())
                + " Options=" + joined.str()
        );
    }

    bool apply_table_settings(std::string_view phase) {
        try {
            IniConfig config;
            const bool ini_read = config.load(find_unified_ini(root_));
            if (!ini_read) {
                append_log(root_, "ERROR: table apply skipped because settings.ini could not be read.");
                return false;
            }

            std::vector<RC::Unreal::UObject*> data_tables;
            RC::Unreal::UObjectGlobals::FindAllOf(STR("DataTable"), data_tables);

            std::size_t tables_seen = data_tables.size();
            std::vector<RC::Unreal::UObject*> curve_objects_for_validation;
            RC::Unreal::UObjectGlobals::FindAllOf(STR("CurveFloat"), curve_objects_for_validation);
            auto setting_statuses = initialize_setting_statuses(config, tables_seen, curve_objects_for_validation.size());
            std::size_t tables_matched = 0;
            std::size_t numeric_fields_applied = 0;
            std::size_t numeric_fields_missing = 0;
            std::size_t range_fields_applied = 0;
            std::size_t range_fields_missing = 0;
            std::size_t array_fields_applied = 0;
            std::size_t array_fields_missing = 0;
            std::size_t arrays_cleared = 0;
            std::size_t arrays_clear_missing = 0;
            const auto curve_result = apply_growth_curves(config, phase);

            for (RC::Unreal::UObject* table : data_tables) {
                if (!table || !RC::Unreal::UObject::IsReal(table)) {
                    continue;
                }
                const auto table_name = narrow_unreal(table->GetFullName());
                if (contains_text(table_name, "_METATABLE")) {
                    continue;
                }
                bool matched_this_table = false;

                for (const auto& rule : kNumericTableRules) {
                    if (!contains_text(table_name, rule.table_stem)) {
                        continue;
                    }
                    matched_this_table = true;
                    auto& status = setting_statuses[setting_id(rule.section, rule.key)];
                    ++status.targets_matched;
                    const double multiplier = clamped_multiplier(config.get_number(rule.section, rule.key, 1.0), 0.0, 1000000.0);
                    if (is_vanilla_multiplier(multiplier)) {
                        continue;
                    }
                    for (const char* field : rule.fields) {
                        const auto applied = apply_numeric_table_field(table, rule, field, multiplier);
                        numeric_fields_applied += applied.first;
                        numeric_fields_missing += applied.second;
                        status.applied += applied.first;
                        status.missing += applied.second;
                    }
                }

                for (const auto& rule : kRangeGroupRules) {
                    if (!contains_text(table_name, rule.table_stem)) {
                        continue;
                    }
                    matched_this_table = true;
                    auto& status = setting_statuses[setting_id("native_groups", rule.key_prefix)];
                    ++status.targets_matched;
                    if (!range_group_has_active_setting(rule, config)) {
                        continue;
                    }
                    const auto applied = apply_range_group(table, rule, config);
                    range_fields_applied += applied.first;
                    range_fields_missing += applied.second;
                    status.applied += applied.first;
                    status.missing += applied.second;
                }

                for (const auto& rule : kArrayNumericRules) {
                    if (!contains_text(table_name, rule.table_stem)) {
                        continue;
                    }
                    matched_this_table = true;
                    auto& status = setting_statuses[setting_id(rule.section, rule.key)];
                    ++status.targets_matched;
                    const double multiplier = clamped_multiplier(config.get_number(rule.section, rule.key, 1.0), 0.0, 1000000.0);
                    if (is_vanilla_multiplier(multiplier)) {
                        continue;
                    }
                    const auto applied = apply_array_numeric_field(table, rule, multiplier);
                    array_fields_applied += applied.first;
                    array_fields_missing += applied.second;
                    status.applied += applied.first;
                    status.missing += applied.second;
                }

                for (const auto& rule : kArrayRangeGroupRules) {
                    if (!contains_text(table_name, rule.table_stem)) {
                        continue;
                    }
                    matched_this_table = true;
                    auto& status = setting_statuses[setting_id("native_groups", rule.key_prefix)];
                    ++status.targets_matched;
                    if (!array_range_group_has_active_setting(rule, config)) {
                        continue;
                    }
                    if (!array_range_group_mutation_enabled(rule)) {
                        ++status.skipped;
                        status.reason = "array_mutation_disabled";
                        append_log(root_, "SAFETY_SKIP ArrayMutationDisabled Table=" + table_name + " KeyPrefix=" + std::string(rule.key_prefix));
                        continue;
                    }
                    const auto applied = apply_array_range_group(table, rule, config);
                    array_fields_applied += applied.first;
                    array_fields_missing += applied.second;
                    status.applied += applied.first;
                    status.missing += applied.second;
                }

                if (contains_text(table_name, "D_ProcessorRecipes")) {
                    matched_this_table = true;
                    if (config.get_bool("direct_settings", "free_craft", config.get_bool("direct_settings", "freeCraft", false))) {
                        auto& status = setting_statuses[setting_id("direct_settings", "free_craft")];
                        ++status.targets_matched;
                        const auto inputs = clear_array_field(table, "Inputs");
                        const auto query_inputs = clear_array_field(table, "QueryInputs");
                        const auto resource_inputs = clear_array_field(table, "ResourceInputs");
                        const std::size_t cleared = inputs.first + query_inputs.first + resource_inputs.first;
                        const std::size_t missing = inputs.second + query_inputs.second + resource_inputs.second;
                        array_fields_applied += cleared;
                        array_fields_missing += missing;
                        status.applied += cleared;
                        status.missing += missing;
                    }
                }

                if (matched_this_table) {
                    ++tables_matched;
                }
            }

            append_log(
                root_,
                "VALIDATION ApplyStatus=tables Phase=" + std::string(phase)
                    + " DataTablesSeen=" + std::to_string(tables_seen)
                    + " DataTablesMatched=" + std::to_string(tables_matched)
                    + " NumericFieldsApplied=" + std::to_string(numeric_fields_applied)
                    + " NumericFieldsMissing=" + std::to_string(numeric_fields_missing)
                    + " RangeFieldsApplied=" + std::to_string(range_fields_applied)
                    + " RangeFieldsMissing=" + std::to_string(range_fields_missing)
                    + " ArrayFieldsApplied=" + std::to_string(array_fields_applied)
                    + " ArrayFieldsMissing=" + std::to_string(array_fields_missing)
                    + " ArraysCleared=" + std::to_string(arrays_cleared)
                    + " ArraysClearMissing=" + std::to_string(arrays_clear_missing)
                    + " CurveMutationStatus=" + curve_result.status
                    + " CurveObjectsSeen=" + std::to_string(curve_result.objects_seen)
                    + " CurveObjectsMatched=" + std::to_string(curve_result.objects_matched)
                    + " CurveKeysApplied=" + std::to_string(curve_result.keys_applied)
                    + " CurveKeysMissing=" + std::to_string(curve_result.keys_missing)
            );
            merge_curve_statuses(setting_statuses, curve_result);
            log_setting_statuses(setting_statuses, phase);
            return numeric_fields_applied > 0
                || range_fields_applied > 0
                || array_fields_applied > 0
                || arrays_cleared > 0
                || curve_result.keys_applied > 0;
        } catch (const std::exception& error) {
            append_log(root_, std::string("ERROR: apply_table_settings exception: ") + error.what());
        } catch (...) {
            append_log(root_, "ERROR: unknown apply_table_settings exception.");
        }
        return false;
    }

    struct CurveRuleStatus {
        std::size_t matched{0};
        std::size_t applied{0};
        std::size_t missing{0};
        std::size_t skipped{0};
        std::string reason;
    };

    struct CurveApplyResult {
        std::string status{"no_active_curve_settings"};
        std::size_t objects_seen{0};
        std::size_t objects_matched{0};
        std::size_t keys_applied{0};
        std::size_t keys_missing{0};
        std::unordered_map<std::string, CurveRuleStatus> rules;
    };

    void merge_curve_statuses(SettingStatusMap& setting_statuses, const CurveApplyResult& curve_result) {
        for (const auto& [key, curve_status] : curve_result.rules) {
            auto id = setting_id("growth_curves", key);
            auto found = setting_statuses.find(id);
            if (found == setting_statuses.end()) {
                continue;
            }
            auto& status = found->second;
            status.targets_matched += curve_status.matched;
            status.applied += curve_status.applied;
            status.missing += curve_status.missing;
            status.skipped += curve_status.skipped;
            if (!curve_status.reason.empty()) {
                status.reason = curve_status.reason;
            }
        }
    }

    CurveApplyResult apply_growth_curves(const IniConfig& config, std::string_view phase) {
        CurveApplyResult result{};

        std::vector<RC::Unreal::UObject*> curve_objects;
        RC::Unreal::UObjectGlobals::FindAllOf(STR("CurveFloat"), curve_objects);
        result.objects_seen = curve_objects.size();

        bool any_active = false;
        bool any_schema_miss = false;
        bool any_asset_missing = false;

        for (const auto& rule : kGrowthCurveRules) {
            const double multiplier = clamped_multiplier(config.get_number("growth_curves", rule.key, 1.0), 0.0, 1000000.0);
            if (is_vanilla_multiplier(multiplier)) {
                continue;
            }
            any_active = true;
            auto& rule_status = result.rules[rule.key];

            bool matched_rule = false;
            for (RC::Unreal::UObject* curve : curve_objects) {
                if (!curve || !RC::Unreal::UObject::IsReal(curve)) {
                    continue;
                }

                const auto curve_name = narrow_unreal(curve->GetFullName());
                if (!contains_text(curve_name, rule.asset_stem)) {
                    continue;
                }

                matched_rule = true;
                ++rule_status.matched;
                ++result.objects_matched;
                const auto applied = apply_curve_float_keys(curve, rule, multiplier, phase);
                rule_status.applied += applied.first;
                rule_status.missing += applied.second;
                result.keys_applied += applied.first;
                result.keys_missing += applied.second;
                if (applied.first == 0) {
                    any_schema_miss = true;
                    rule_status.reason = "curve_schema_miss_or_no_keys";
                }
            }

            if (!matched_rule) {
                any_asset_missing = true;
                rule_status.reason = "curve_asset_not_loaded_or_not_found";
                append_log(
                    root_,
                    "CURVE_MISS Phase=" + std::string(phase)
                        + " Key=" + rule.key
                        + " AssetStem=" + rule.asset_stem
                        + " Reason=curve_asset_not_loaded_or_not_found"
                );
            }
        }

        if (!any_active) {
            result.status = "no_active_curve_settings";
        } else if (result.keys_applied > 0) {
            result.status = "applied";
        } else if (any_schema_miss) {
            result.status = "schema_miss";
        } else if (any_asset_missing) {
            result.status = "curve_assets_not_loaded";
        } else {
            result.status = "no_curve_keys_applied";
        }

        return result;
    }

    std::pair<std::size_t, std::size_t> apply_curve_float_keys(
        RC::Unreal::UObject* curve,
        const GrowthCurveRule& rule,
        double multiplier,
        std::string_view phase
    ) {
        if (!curve) {
            return {0, 1};
        }

        auto* float_curve_property_base = curve->GetPropertyByNameInChain(STR("FloatCurve"));
        auto* float_curve_property = float_curve_property_base ? RC::Unreal::CastField<RC::Unreal::FStructProperty>(float_curve_property_base) : nullptr;
        void* float_curve = curve->GetValuePtrByPropertyNameInChain<void>(STR("FloatCurve"));
        RC::Unreal::UScriptStruct* rich_curve_struct = float_curve_property ? float_curve_property->GetStruct() : nullptr;
        if (!float_curve || !rich_curve_struct) {
            log_curve_schema_miss(phase, curve, rule, "float_curve_missing", float_curve_property_base);
            return {0, 1};
        }

        auto* keys_property_base = find_struct_property_by_name(rich_curve_struct, "Keys");
        auto* keys_property = keys_property_base ? RC::Unreal::CastField<RC::Unreal::FArrayProperty>(keys_property_base) : nullptr;
        auto* key_struct_property = keys_property ? RC::Unreal::CastField<RC::Unreal::FStructProperty>(keys_property->GetInner()) : nullptr;
        RC::Unreal::UScriptStruct* key_struct = key_struct_property ? key_struct_property->GetStruct() : nullptr;
        if (!keys_property || !key_struct) {
            log_curve_schema_miss(phase, curve, rule, "keys_array_missing", keys_property_base);
            return {0, 1};
        }

        auto* value_property_base = find_struct_property_by_name(key_struct, "Value");
        auto* value_property = as_numeric_property(value_property_base);
        if (!value_property) {
            log_curve_schema_miss(phase, curve, rule, "key_value_missing_or_not_numeric", value_property_base);
            return {0, 1};
        }

        void* keys_ptr = keys_property->ContainerPtrToValuePtr<void>(float_curve);
        auto* keys = static_cast<RC::Unreal::FScriptArray*>(keys_ptr);
        if (!keys) {
            log_curve_schema_miss(phase, curve, rule, "keys_array_value_missing", keys_property_base);
            return {0, 1};
        }

        const int32_t element_size = keys_property->GetInner()->GetElementSize();
        const int32_t count = keys->Num();
        std::size_t applied = 0;
        std::size_t missing = 0;
        for (int32_t index = 0; index < count; ++index) {
            auto* key = static_cast<unsigned char*>(keys->GetData()) + (index * element_size);
            void* value_ptr = key ? value_property->ContainerPtrToValuePtr<void>(static_cast<void*>(key)) : nullptr;
            if (!value_ptr) {
                ++missing;
                continue;
            }

            const double current = value_property->IsFloatingPoint()
                ? value_property->GetFloatingPointPropertyValue(value_ptr)
                : static_cast<double>(value_property->GetSignedIntPropertyValue(value_ptr));
            const double baseline = curve_key_baselines_.try_emplace(value_ptr, current).first->second;
            const double adjusted = std::max(0.0, baseline * multiplier);
            if (value_property->IsFloatingPoint()) {
                value_property->SetFloatingPointPropertyValue(value_ptr, adjusted);
            } else {
                value_property->SetIntPropertyValue(value_ptr, static_cast<int64_t>(std::llround(adjusted)));
            }
            ++applied;
        }

        append_log(
            root_,
            "CURVE_APPLY Phase=" + std::string(phase)
                + " Key=" + rule.key
                + " Curve=" + narrow_unreal(curve->GetFullName())
                + " Multiplier=" + std::to_string(multiplier)
                + " KeysApplied=" + std::to_string(applied)
                + " KeysMissing=" + std::to_string(missing)
        );
        return {applied, missing};
    }

    void log_curve_schema_miss(
        std::string_view phase,
        RC::Unreal::UObject* curve,
        const GrowthCurveRule& rule,
        const char* reason,
        RC::Unreal::FProperty* property
    ) {
        append_log(
            root_,
            "CURVE_SCHEMA_MISS Phase=" + std::string(phase)
                + " Key=" + rule.key
                + " Curve=" + (curve ? narrow_unreal(curve->GetFullName()) : std::string("<missing>"))
                + " Reason=" + reason
                + " PropertyClass=" + property_class_name(property)
        );
    }

    void log_table_schema_diagnostics(std::string_view phase) {
        try {
            std::vector<RC::Unreal::UObject*> data_tables;
            RC::Unreal::UObjectGlobals::FindAllOf(STR("DataTable"), data_tables);

            std::size_t matched = 0;
            std::size_t logged = 0;
            for (RC::Unreal::UObject* table : data_tables) {
                if (!table || !RC::Unreal::UObject::IsReal(table)) {
                    continue;
                }

                const auto table_name = narrow_unreal(table->GetFullName());
                if (!is_config_table(table_name)) {
                    continue;
                }
                ++matched;
                if (logged >= 80) {
                    continue;
                }

                const auto rows = get_table_rows(table, phase);
                if (!rows || !rows->row_struct) {
                    append_log(root_, "SCHEMA Phase=" + std::string(phase) + " Table=" + table_name + " RowStruct=<missing>");
                    ++logged;
                    continue;
                }
                RC::Unreal::UScriptStruct* row_struct = rows->row_struct;

                const std::string properties = struct_property_list(row_struct, 120);

                append_log(
                    root_,
                    "SCHEMA Phase=" + std::string(phase)
                        + " Table=" + table_name
                        + " RowStruct=" + narrow_unreal(row_struct->GetFullName())
                        + " Properties=" + properties
                );
                log_nested_schema_details(phase, table_name, row_struct);
                ++logged;
            }

            append_log(
                root_,
                "VALIDATION SchemaDiagnostics Phase=" + std::string(phase)
                    + " DataTablesSeen=" + std::to_string(data_tables.size())
                    + " ConfigTablesMatched=" + std::to_string(matched)
                    + " SchemaRowsLogged=" + std::to_string(logged)
                    + " TableMutationStatus=schema_probe_complete"
            );
        } catch (const std::exception& error) {
            append_log(root_, std::string("ERROR: log_table_schema_diagnostics exception: ") + error.what());
        } catch (...) {
            append_log(root_, "ERROR: unknown log_table_schema_diagnostics exception.");
        }
    }

    void log_nested_schema_details(std::string_view phase, const std::string& table_name, RC::Unreal::UScriptStruct* row_struct) {
        if (!row_struct) {
            return;
        }

        std::size_t detail_count = 0;
        for (auto* property : row_struct->ForEachPropertyInChain()) {
            if (!property || detail_count >= 40) {
                continue;
            }

            const auto property_name = narrow_unreal(property->GetName());
            auto* array_property = RC::Unreal::CastField<RC::Unreal::FArrayProperty>(property);
            auto* inner_struct_property = array_property ? RC::Unreal::CastField<RC::Unreal::FStructProperty>(array_property->GetInner()) : nullptr;
            if (inner_struct_property && inner_struct_property->GetStruct()) {
                append_log(
                    root_,
                    "SCHEMA_DETAIL Phase=" + std::string(phase)
                        + " Table=" + table_name
                        + " ArrayProperty=" + property_name
                        + " InnerStruct=" + narrow_unreal(inner_struct_property->GetStruct()->GetFullName())
                        + " InnerProperties=" + struct_property_list(inner_struct_property->GetStruct(), 80)
                );
                ++detail_count;
                continue;
            }

            auto* struct_property = RC::Unreal::CastField<RC::Unreal::FStructProperty>(property);
            if (struct_property && struct_property->GetStruct()) {
                append_log(
                    root_,
                    "SCHEMA_DETAIL Phase=" + std::string(phase)
                        + " Table=" + table_name
                        + " StructProperty=" + property_name
                        + " InnerStruct=" + narrow_unreal(struct_property->GetStruct()->GetFullName())
                        + " InnerProperties=" + struct_property_list(struct_property->GetStruct(), 80)
                );
                ++detail_count;
            }
        }
    }

    struct TableRows {
        RC::Unreal::TMap<RC::Unreal::FName, unsigned char*>* row_map{};
        RC::Unreal::UScriptStruct* row_struct{};
    };

    std::optional<TableRows> get_table_rows(RC::Unreal::UObject* table, std::string_view phase) {
        if (!table) {
            return std::nullopt;
        }

        try {
            auto** row_struct_ptr = table->GetValuePtrByPropertyNameInChain<RC::Unreal::UScriptStruct*>(STR("RowStruct"));
            auto* row_struct = row_struct_ptr ? *row_struct_ptr : nullptr;
            if (!row_struct_ptr || !row_struct) {
                append_log(
                    root_,
                    "TABLE_ACCESS_MISS Phase=" + std::string(phase)
                        + " Table=" + narrow_unreal(table->GetFullName())
                        + " Reason=row_struct_missing"
                );
                return std::nullopt;
            }

            const auto table_address = reinterpret_cast<std::uintptr_t>(table);
            const auto row_struct_address = reinterpret_cast<std::uintptr_t>(row_struct_ptr);
            if (row_struct_address <= table_address) {
                append_log(
                    root_,
                    "TABLE_ACCESS_MISS Phase=" + std::string(phase)
                        + " Table=" + narrow_unreal(table->GetFullName())
                        + " Reason=row_struct_offset_invalid"
                );
                return std::nullopt;
            }

            const auto row_struct_offset = static_cast<int32_t>(row_struct_address - table_address);
            const auto row_map_offset = row_struct_offset + static_cast<int32_t>(sizeof(void*));
            auto* row_map = RC::Helper::Casting::ptr_cast<RC::Unreal::TMap<RC::Unreal::FName, unsigned char*>*>(table, row_map_offset);
            if (!row_map) {
                append_log(
                    root_,
                    "TABLE_ACCESS_MISS Phase=" + std::string(phase)
                        + " Table=" + narrow_unreal(table->GetFullName())
                        + " Reason=row_map_missing"
                );
                return std::nullopt;
            }
            return TableRows{row_map, row_struct};
        } catch (const std::exception& error) {
            append_log(
                root_,
                "TABLE_ACCESS_MISS Phase=" + std::string(phase)
                    + " Table=" + narrow_unreal(table->GetFullName())
                    + " Reason=row_access_failed Error=" + error.what()
            );
        } catch (...) {
            append_log(
                root_,
                "TABLE_ACCESS_MISS Phase=" + std::string(phase)
                    + " Table=" + narrow_unreal(table->GetFullName())
                    + " Reason=row_access_failed_unknown"
            );
        }
        return std::nullopt;
    }

    bool is_config_table(std::string_view table_name) const {
        if (contains_text(table_name, "_METATABLE")) {
            return false;
        }
        for (const auto& rule : kNumericTableRules) {
            if (contains_text(table_name, rule.table_stem)) {
                return true;
            }
        }
        for (const auto& rule : kRangeGroupRules) {
            if (contains_text(table_name, rule.table_stem)) {
                return true;
            }
        }
        for (const auto& rule : kArrayNumericRules) {
            if (contains_text(table_name, rule.table_stem)) {
                return true;
            }
        }
        for (const auto& rule : kArrayRangeGroupRules) {
            if (contains_text(table_name, rule.table_stem)) {
                return true;
            }
        }
        return false;
    }

    bool range_group_has_active_setting(const RangeGroupRule& rule, const IniConfig& config) const {
        for (std::size_t index = 0; index < rule.ranges.size(); ++index) {
            const double multiplier = clamped_multiplier(
                config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(index + 1), 1.0),
                0.0,
                1000000.0
            );
            if (!is_vanilla_multiplier(multiplier)) {
                return true;
            }
        }
        return false;
    }

    bool array_range_group_has_active_setting(const ArrayRangeGroupRule& rule, const IniConfig& config) const {
        for (std::size_t index = 0; index < rule.ranges.size(); ++index) {
            const double multiplier = clamped_multiplier(
                config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(index + 1), 1.0),
                0.0,
                1000000.0
            );
            if (!is_vanilla_multiplier(multiplier)) {
                return true;
            }
        }
        return false;
    }

    std::pair<std::size_t, std::size_t> apply_numeric_table_field(
        RC::Unreal::UObject* table,
        const NumericTableRule& rule,
        const char* field_name,
        double multiplier
    ) {
        const auto rows = get_table_rows(table, "numeric_field");
        if (!rows) {
            return {0, 1};
        }
        auto* row_map = rows->row_map;
        auto* row_struct = rows->row_struct;

        RC::Unreal::FProperty* property = find_struct_property_by_name(row_struct, field_name);
        auto* numeric_property = as_numeric_property(property);
        if (!numeric_property) {
            append_log(
                root_,
                "FIELD_MISS Table=" + narrow_unreal(table->GetFullName())
                    + " Field=" + field_name
                    + " PropertyClass=" + property_class_name(property)
                    + " Reason=not_numeric"
            );
            return {0, 1};
        }

        std::size_t applied = 0;
        std::size_t missing = 0;
        for (auto it = row_map->CreateIterator(); it; ++it) {
            const auto row_name = narrow_unreal(it.Key().ToString());
            if (!listed_row(row_name, rule.row_names) || excluded_row(row_name, {}, rule.exclude_suffixes)) {
                continue;
            }
            unsigned char* row = it.Value();
            if (!row) {
                ++missing;
                continue;
            }
            void* value_ptr = numeric_property->ContainerPtrToValuePtr<void>(static_cast<void*>(row));
            if (!value_ptr) {
                ++missing;
                continue;
            }
            const double current = numeric_property->IsFloatingPoint()
                ? numeric_property->GetFloatingPointPropertyValue(value_ptr)
                : static_cast<double>(numeric_property->GetSignedIntPropertyValue(value_ptr));
            const double baseline = numeric_baselines_.try_emplace(value_ptr, current).first->second;
            const double adjusted = adjusted_numeric(baseline, multiplier, rule.mode, rule.result, rule.minimum);
            if (numeric_property->IsFloatingPoint()) {
                numeric_property->SetFloatingPointPropertyValue(value_ptr, adjusted);
            } else {
                numeric_property->SetIntPropertyValue(value_ptr, static_cast<int64_t>(std::llround(adjusted)));
            }
            ++applied;
        }
        return {applied, missing};
    }

    std::pair<std::size_t, std::size_t> apply_array_numeric_field(
        RC::Unreal::UObject* table,
        const ArrayNumericRule& rule,
        double multiplier
    ) {
        const auto rows = get_table_rows(table, "array_numeric_field");
        if (!rows) {
            return {0, 1};
        }
        auto* row_map = rows->row_map;
        auto* row_struct = rows->row_struct;

        auto* array_property_base = find_struct_property_by_name(row_struct, rule.array_field);
        auto* array_property = array_property_base ? RC::Unreal::CastField<RC::Unreal::FArrayProperty>(array_property_base) : nullptr;
        auto* inner_struct_property = array_property ? RC::Unreal::CastField<RC::Unreal::FStructProperty>(array_property->GetInner()) : nullptr;
        RC::Unreal::UScriptStruct* inner_struct = inner_struct_property ? inner_struct_property->GetStruct() : nullptr;
        if (!array_property || !inner_struct) {
            return {0, 1};
        }

        auto* numeric_property_base = find_struct_property_by_name(inner_struct, rule.numeric_field);
        auto* numeric_property = as_numeric_property(numeric_property_base);
        if (!numeric_property) {
            append_log(
                root_,
                "FIELD_MISS Table=" + narrow_unreal(table->GetFullName())
                    + " ArrayField=" + rule.array_field
                    + " Field=" + rule.numeric_field
                    + " PropertyClass=" + property_class_name(numeric_property_base)
                    + " Reason=array_inner_not_numeric"
            );
            return {0, 1};
        }

        std::size_t applied = 0;
        std::size_t missing = 0;
        for (auto it = row_map->CreateIterator(); it; ++it) {
            const auto row_name = narrow_unreal(it.Key().ToString());
            if (excluded_row(row_name, rule.exclude_contains)) {
                continue;
            }
            unsigned char* row = it.Value();
            void* array_ptr = row ? array_property->ContainerPtrToValuePtr<void>(static_cast<void*>(row)) : nullptr;
            if (!array_ptr) {
                ++missing;
                continue;
            }
            auto* array = static_cast<RC::Unreal::FScriptArray*>(array_ptr);
            const int32_t element_size = array_property->GetInner()->GetElementSize();
            const int32_t count = array ? array->Num() : 0;
            for (int32_t index = 0; index < count; ++index) {
                auto* element = static_cast<unsigned char*>(array->GetData()) + (index * element_size);
                if (!element) {
                    ++missing;
                    continue;
                }
                void* value_ptr = numeric_property->ContainerPtrToValuePtr<void>(static_cast<void*>(element));
                if (!value_ptr) {
                    ++missing;
                    continue;
                }
                const double current = numeric_property->IsFloatingPoint()
                    ? numeric_property->GetFloatingPointPropertyValue(value_ptr)
                    : static_cast<double>(numeric_property->GetSignedIntPropertyValue(value_ptr));
                const double baseline = numeric_baselines_.try_emplace(value_ptr, current).first->second;
                const double adjusted = adjusted_numeric(baseline, multiplier, rule.mode, rule.result, rule.minimum);
                if (numeric_property->IsFloatingPoint()) {
                    numeric_property->SetFloatingPointPropertyValue(value_ptr, adjusted);
                } else {
                    numeric_property->SetIntPropertyValue(value_ptr, static_cast<int64_t>(std::llround(adjusted)));
                }
                ++applied;
            }
        }
        return {applied, missing};
    }

    std::pair<std::size_t, std::size_t> apply_array_range_group(
        RC::Unreal::UObject* table,
        const ArrayRangeGroupRule& rule,
        const IniConfig& config
    ) {
        if (!array_range_group_mutation_enabled(rule)) {
            append_log(root_, "SAFETY_SKIP ArrayRangeHelperDisabled KeyPrefix=" + std::string(rule.key_prefix));
            return {0, 0};
        }

        const auto rows = get_table_rows(table, "array_range_group");
        if (!rows) {
            return {0, 1};
        }
        auto* row_map = rows->row_map;
        auto* row_struct = rows->row_struct;

        auto* array_property_base = find_struct_property_by_name(row_struct, rule.array_field);
        auto* array_property = array_property_base ? RC::Unreal::CastField<RC::Unreal::FArrayProperty>(array_property_base) : nullptr;
        auto* inner_struct_property = array_property ? RC::Unreal::CastField<RC::Unreal::FStructProperty>(array_property->GetInner()) : nullptr;
        RC::Unreal::UScriptStruct* inner_struct = inner_struct_property ? inner_struct_property->GetStruct() : nullptr;
        if (!array_property || !inner_struct) {
            return {0, 1};
        }

        auto* numeric_property_base = find_struct_property_by_name(inner_struct, rule.numeric_field);
        auto* numeric_property = as_numeric_property(numeric_property_base);
        if (!numeric_property) {
            append_log(
                root_,
                "FIELD_MISS Table=" + narrow_unreal(table->GetFullName())
                    + " ArrayField=" + rule.array_field
                    + " Field=" + rule.numeric_field
                    + " PropertyClass=" + property_class_name(numeric_property_base)
                    + " Reason=array_range_inner_not_numeric"
            );
            return {0, 1};
        }

        std::size_t applied = 0;
        std::size_t missing = 0;
        for (auto it = row_map->CreateIterator(); it; ++it) {
            const auto row_name = narrow_unreal(it.Key().ToString());
            if (excluded_row(row_name, rule.exclude_contains)) {
                continue;
            }
            unsigned char* row = it.Value();
            void* array_ptr = row ? array_property->ContainerPtrToValuePtr<void>(static_cast<void*>(row)) : nullptr;
            if (!array_ptr) {
                ++missing;
                continue;
            }
            auto* array = static_cast<RC::Unreal::FScriptArray*>(array_ptr);
            const int32_t element_size = array_property->GetInner()->GetElementSize();
            const int32_t count = array ? array->Num() : 0;
            for (int32_t index = 0; index < count; ++index) {
                auto* element = static_cast<unsigned char*>(array->GetData()) + (index * element_size);
                void* value_ptr = element ? numeric_property->ContainerPtrToValuePtr<void>(static_cast<void*>(element)) : nullptr;
                if (!value_ptr) {
                    ++missing;
                    continue;
                }
                const double current = numeric_property->IsFloatingPoint()
                    ? numeric_property->GetFloatingPointPropertyValue(value_ptr)
                    : static_cast<double>(numeric_property->GetSignedIntPropertyValue(value_ptr));
                const double baseline = numeric_baselines_.try_emplace(value_ptr, current).first->second;
                int range_index = 1;
                double multiplier = 1.0;
                bool matched_range = false;
                for (const auto& [minimum, maximum] : rule.ranges) {
                    if (baseline >= minimum && baseline <= maximum) {
                        multiplier = config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(range_index), 1.0);
                        matched_range = true;
                        break;
                    }
                    ++range_index;
                }
                if (!matched_range) {
                    continue;
                }
                const double adjusted = adjusted_numeric(baseline, multiplier, NumericMode::Multiply, NumericResult::Nearest, rule.minimum);
                if (numeric_property->IsFloatingPoint()) {
                    numeric_property->SetFloatingPointPropertyValue(value_ptr, adjusted);
                } else {
                    numeric_property->SetIntPropertyValue(value_ptr, static_cast<int64_t>(std::llround(adjusted)));
                }
                ++applied;
            }
        }
        return {applied, missing};
    }

    std::pair<std::size_t, std::size_t> clear_array_field(RC::Unreal::UObject* table, const char* array_field) {
        const auto rows = get_table_rows(table, "clear_array_field");
        if (!rows) {
            return {0, 1};
        }
        auto* row_map = rows->row_map;
        auto* row_struct = rows->row_struct;
        auto* array_property_base = find_struct_property_by_name(row_struct, array_field);
        auto* array_property = array_property_base ? RC::Unreal::CastField<RC::Unreal::FArrayProperty>(array_property_base) : nullptr;
        if (!array_property) {
            return {0, 1};
        }

        std::size_t cleared = 0;
        std::size_t missing = 0;
        for (auto it = row_map->CreateIterator(); it; ++it) {
            unsigned char* row = it.Value();
            void* array_ptr = row ? array_property->ContainerPtrToValuePtr<void>(static_cast<void*>(row)) : nullptr;
            if (!array_ptr) {
                ++missing;
                continue;
            }
            auto* array = static_cast<RC::Unreal::FScriptArray*>(array_ptr);
            if (array && array->Num() > 0) {
                const auto* inner = array_property->GetInner();
                array->Empty(0, inner->GetElementSize(), inner->GetMinAlignment());
                ++cleared;
            }
        }
        return {cleared, missing};
    }

    std::pair<std::size_t, std::size_t> apply_range_group(
        RC::Unreal::UObject* table,
        const RangeGroupRule& rule,
        const IniConfig& config
    ) {
        const auto rows = get_table_rows(table, "range_group");
        if (!rows) {
            return {0, 1};
        }
        auto* row_map = rows->row_map;
        auto* row_struct = rows->row_struct;

        RC::Unreal::FProperty* property = find_struct_property_by_name(row_struct, rule.field);
        auto* numeric_property = as_numeric_property(property);
        if (!numeric_property) {
            append_log(
                root_,
                "FIELD_MISS Table=" + narrow_unreal(table->GetFullName())
                    + " Field=" + rule.field
                    + " PropertyClass=" + property_class_name(property)
                    + " Reason=range_not_numeric"
            );
            return {0, 1};
        }

        std::size_t applied = 0;
        std::size_t missing = 0;
        for (auto it = row_map->CreateIterator(); it; ++it) {
            const auto row_name = narrow_unreal(it.Key().ToString());
            if (excluded_row(row_name, rule.exclude_contains)) {
                continue;
            }
            unsigned char* row = it.Value();
            if (!row) {
                ++missing;
                continue;
            }
            void* value_ptr = numeric_property->ContainerPtrToValuePtr<void>(static_cast<void*>(row));
            if (!value_ptr) {
                ++missing;
                continue;
            }
            const double current = numeric_property->IsFloatingPoint()
                ? numeric_property->GetFloatingPointPropertyValue(value_ptr)
                : static_cast<double>(numeric_property->GetSignedIntPropertyValue(value_ptr));
            const double baseline = numeric_baselines_.try_emplace(value_ptr, current).first->second;
            int range_index = 1;
            double multiplier = 1.0;
            bool matched_range = false;
            for (const auto& [minimum, maximum] : rule.ranges) {
                if (baseline >= minimum && baseline <= maximum) {
                    multiplier = config.get_number("native_groups", std::string(rule.key_prefix) + std::to_string(range_index), 1.0);
                    matched_range = true;
                    break;
                }
                ++range_index;
            }
            if (!matched_range) {
                continue;
            }
            const double adjusted = adjusted_numeric(baseline, multiplier, NumericMode::Multiply, NumericResult::Nearest, rule.minimum);
            if (numeric_property->IsFloatingPoint()) {
                numeric_property->SetFloatingPointPropertyValue(value_ptr, adjusted);
            } else {
                numeric_property->SetIntPropertyValue(value_ptr, static_cast<int64_t>(std::llround(adjusted)));
            }
            ++applied;
        }
        return {applied, missing};
    }

    std::filesystem::path root_;
    RuntimeSettings settings_{};
    bool hooks_registered_{false};
    bool begin_play_applied_{false};
    bool schema_diagnostics_logged_{false};
    bool tables_applied_{false};
    ULONGLONG next_runtime_scan_ms_{0};
    ULONGLONG next_schema_diagnostic_ms_{0};
    ULONGLONG next_table_apply_ms_{0};
    std::size_t runtime_scan_count_{0};
    std::size_t table_apply_attempts_{0};
    std::unordered_map<RC::Unreal::UObject*, float> air_control_baselines_;
    std::unordered_map<void*, double> numeric_baselines_;
    std::unordered_map<void*, double> curve_key_baselines_;
};
}

#define MOD_EXPORT __declspec(dllexport)
extern "C" {
MOD_EXPORT RC::CppUserModBase* start_mod() {
    return new ConfigurationMod::RuntimeMod();
}

MOD_EXPORT void uninstall_mod(RC::CppUserModBase* mod) {
    delete mod;
}
}
