from __future__ import annotations

import json
import filecmp
import base64
import os
import re
import shutil
import subprocess
import sys
import traceback
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Icarus Balance Configurator"
APP_VERSION = "0.1.3-beta"
UE4SS_RELEASES_API = "https://api.github.com/repos/UE4SS-RE/RE-UE4SS/releases"
RUNTIME_MOD_FOLDER = "Configuration_Mod"
RUNTIME_INI_NAME = "settings.ini"
CURVE_RUNTIME_ENABLED = True
IS_BUNDLED_APP = (
    getattr(sys, "frozen", False)
    or "__compiled__" in globals()
    or Path(sys.executable).name.casefold() == "icarusconfigmod.exe"
)
APP_BASE_DIR = (
    Path(sys.executable).resolve().parent
    if IS_BUNDLED_APP
    else Path(__file__).resolve().parent.parent
)


def user_state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ZSG Studios" / "IcarusConfigMod"
    return Path.home() / "AppData" / "Local" / "ZSG Studios" / "IcarusConfigMod"


APP_STATE_DIR = user_state_dir()
USER_SETTINGS_PATH = APP_STATE_DIR / "user_settings.json"
BUNDLED_UE4SS_DLLS = (
    APP_BASE_DIR / "UE4SS.dll",
    APP_BASE_DIR / "tools" / "ue4ss" / "UE4SS.dll",
    APP_BASE_DIR / "tools" / "dll" / "out" / "UE4SS.dll",
)

UI_BG = "#071014"
UI_PANEL = "#10191d"
UI_PANEL_ALT = "#142226"
UI_BORDER = "#25444a"
UI_TEAL = "#56d7d9"
UI_TEAL_DARK = "#1b6f72"
UI_AMBER = "#f2a93b"
UI_TEXT = "#e8f2f0"
UI_MUTED = "#9fb3b0"
UI_STATUS = "#0b1418"
UI_INPUT_BG = "#dce8e6"
UI_INPUT_TEXT = "#071014"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    category: str
    label: str
    description: str
    files: tuple[str, ...]
    kind: str
    fields: tuple[str, ...]
    direction: str = "multiply"
    result: str = "float"
    minimum_result: float | None = None
    positive_only: bool = True
    greater_than_one: bool = False
    row_names: tuple[str, ...] = ()
    exclude_name_suffixes: tuple[str, ...] = ()
    caution: bool = False


@dataclass(frozen=True)
class NativeGroupSpec:
    key: str
    category: str
    label: str
    file: str
    field: str
    kind: str
    ranges: tuple[tuple[int, int], ...]
    description: str
    result: str = "nearest"
    minimum_result: int = 0
    exclude_name_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectSettingSpec:
    key: str
    category: str
    label: str
    description: str
    file: str
    kind: str
    default: str = "1"
    choices: tuple[str, ...] = ("0.5", "0.75", "1", "1.25", "1.5", "2", "3", "5", "10")
    row_name: str = ""
    field: str = ""
    minimum_result: int = 0
    currency: str = ""


@dataclass(frozen=True)
class CurveSettingSpec:
    key: str
    category: str
    label: str
    description: str
    asset: str
    checks: tuple[tuple[int, float, int, float], ...]


@dataclass(frozen=True)
class RuntimeSettingSpec:
    key: str
    category: str
    label: str
    description: str
    default: str = "1"
    choices: tuple[str, ...] = ("0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2", "3", "5", "10")
    minimum: Decimal = Decimal("0")
    maximum: Decimal = Decimal("100")


GROUP_WORDING: dict[str, tuple[str, str, str]] = {
    "xpGroup": (
        "Vanilla XP reward",
        "XP events",
        "Affects individual XP events such as gathering, mining, kills, and discoveries. It does not change crafting XP, talent points, or blueprint points.",
    ),
    "stackGroup": (
        "Vanilla stack limit",
        "items",
        "Warning: rewrites item stack limits and can invalidate saved inventory items. Back up saves before changing.",
    ),
    "slotGroup": (
        "Vanilla slot count",
        "containers",
        "Warning: rewrites inventory slot counts and can delete saved items if lowered below current contents.",
    ),
    "recipeOutputGroup": (
        "Vanilla items per craft",
        "recipes",
        "Warning: edits recipe output arrays. Test on backup saves before using on an existing character.",
    ),
    "missionCurrencyGroup": (
        "Vanilla currency reward",
        "missions",
        "Affects each normal mission currency payout. Starter rewards from OLY_Forest_Recon use the separate Starter Reward controls.",
    ),
}


NATIVE_GROUPS: tuple[NativeGroupSpec, ...] = (
    NativeGroupSpec(
        "xpGroup", "Progression", "XP rewards", "Experience/D_ExperienceEvents.json", "ExperienceGranted", "rows",
        ((1, 10), (11, 25), (26, 50), (51, 100), (101, 250), (251, 500), (501, 1000), (1001, 1000000)),
        GROUP_WORDING["xpGroup"][2],
    ),
    NativeGroupSpec(
        "stackGroup", "Inventory", "Stack sizes", "Traits/D_Itemable.json", "MaxStack", "rows",
        ((2, 10), (11, 25), (26, 50), (51, 100), (101, 250), (251, 500), (501, 1000000)),
        GROUP_WORDING["stackGroup"][2],
        minimum_result=1,
        exclude_name_patterns=("*_Kitchen_*",),
    ),
    NativeGroupSpec(
        "slotGroup", "Inventory", "Container slots", "Inventory/D_InventoryInfo.json", "StartingSlots", "rows",
        ((1, 1), (2, 5), (6, 10), (11, 25), (26, 50), (51, 1000)),
        GROUP_WORDING["slotGroup"][2],
        minimum_result=1,
    ),
    NativeGroupSpec(
        "recipeOutputGroup", "Crafting", "Recipe output quantities", "Crafting/D_ProcessorRecipes.json", "Count", "recipe_outputs",
        ((2, 5), (6, 10), (11, 25), (26, 50), (51, 1000)),
        GROUP_WORDING["recipeOutputGroup"][2],
        minimum_result=1,
        exclude_name_patterns=("*_Kitchen_*",),
    ),
    NativeGroupSpec(
        "missionCurrencyGroup", "Rewards", "Mission currency rewards", "Factions/D_FactionMissions.json", "Amount", "currency_rewards",
        ((1, 25), (26, 50), (51, 100), (101, 250), (251, 500), (501, 1000), (1001, 1000000)),
        GROUP_WORDING["missionCurrencyGroup"][2],
        minimum_result=0,
    ),
)


DIRECT_SETTINGS: tuple[DirectSettingSpec, ...] = (
    DirectSettingSpec(
        "backpack_slots", "Inventory", "Backpack slots",
        "Warning: rewrites backpack slot count and can delete saved items if lowered below current contents.",
        "Inventory/D_InventoryInfo.json", "row_field_multiplier",
        row_name="Backpack", field="StartingSlots", minimum_result=1,
    ),
    DirectSettingSpec(
        "remove_shelter_requirement", "Survival", "Craft without shelter",
        "Sets processing stations' native shelter requirement to false.",
        "Traits/D_Processing.json", "processing_shelter_false",
        default="0", choices=("0", "1"),
    ),
    DirectSettingSpec(
        "weatherproof_deployables", "Survival", "Weatherproof deployables",
        "Forces deployables' native EffectedByWeather flag to false where present.",
        "Traits/D_Deployable.json", "deployable_weather_false",
        default="0", choices=("0", "1"),
    ),
    DirectSettingSpec(
        "free_craft", "Crafting", "Free crafting",
        "Warning: clears processor recipe input arrays. Test on backup saves before using on an existing character.",
        "Crafting/D_ProcessorRecipes.json", "free_craft_inputs",
        default="0", choices=("0", "1"),
    ),
    DirectSettingSpec(
        "starter_ren", "Rewards", "Starter Ren",
        "Sets OLY_Forest_Recon's Ren reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Credits",
    ),
    DirectSettingSpec(
        "starter_exotics", "Rewards", "Starter Exotics",
        "Sets OLY_Forest_Recon's Exotics reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Exotic1",
    ),
    DirectSettingSpec(
        "starter_red_exotics", "Rewards", "Starter Red Exotics",
        "Sets OLY_Forest_Recon's Red Exotics reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Exotic_Red",
    ),
    DirectSettingSpec(
        "starter_biomass", "Rewards", "Starter Legendary Biomass",
        "Sets OLY_Forest_Recon's Legendary Biomass reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Biomass",
    ),
    DirectSettingSpec(
        "starter_uranium", "Rewards", "Starter Uranium Rod currency",
        "Sets OLY_Forest_Recon's Uranium Rod reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Exotic_Uranium",
    ),
    DirectSettingSpec(
        "starter_licence", "Rewards", "Starter Legendary Licences",
        "Sets OLY_Forest_Recon's Legendary Licence reward amount.",
        "Factions/D_FactionMissions.json", "mission_currency_amount",
        default="0", choices=(), row_name="OLY_Forest_Recon", currency="Licence",
    ),
    DirectSettingSpec(
        "lucky_strike_chance", "Progression", "Lucky Strike talent chance",
        "Multiplies Lucky Strike's native BaseChanceToMineVoxelInstantly stat in D_Talents.",
        "Talents/D_Talents.json", "talent_reward_stat_multiplier",
        row_name="Resources_Voxel_Instant", field='(Value="BaseChanceToMineVoxelInstantly_+%")',
    ),
)


CURVE_SETTINGS: tuple[CurveSettingSpec, ...] = (
    CurveSettingSpec(
        "player_talent_growth", "Progression", "Player talent points",
        "Multiplies the native cooked player talent-point growth curve.",
        "Data/Character/C_PlayerTalentGrowth",
        ((0xA5, 50.0, 0xA9, 75.0), (0xC0, 60.0, 0xC4, 90.0)),
    ),
    CurveSettingSpec(
        "solo_talent_growth", "Progression", "Solo talent points",
        "Multiplies the native cooked solo talent-point growth curve.",
        "Data/Character/C_SoloTalentGrowth",
        ((0xA5, 50.0, 0xA9, 25.0), (0xC0, 60.0, 0xC4, 30.0)),
    ),
    CurveSettingSpec(
        "player_blueprint_growth", "Progression", "Blueprint points",
        "Multiplies the native cooked blueprint-point growth curve.",
        "Data/Character/C_PlayerBlueprintGrowth",
        ((0xA5, 1.0, 0xA9, 4.0), (0xC0, 51.0, 0xC4, 179.0)),
    ),
    CurveSettingSpec(
        "mount_talent_growth", "Progression", "Mount talent points",
        "Multiplies the native cooked mount talent-point growth curve.",
        "Data/Character/C_MountTalentGrowth",
        ((0xA5, 50.0, 0xA9, 50.0),),
    ),
    CurveSettingSpec(
        "pet_talent_growth", "Progression", "Pet talent points",
        "Multiplies the native cooked pet talent-point growth curve.",
        "Data/Character/C_PetTalentGrowth",
        ((0xA5, 25.0, 0xA9, 25.0),),
    ),
)

CURVE_INI_KEYS: dict[str, tuple[str, ...]] = {
    "player_talent_growth": ("playerTalentGrowth", "playerTalentGrowth2"),
    "solo_talent_growth": ("soloTalentGrowth", "soloTalentGrowth2"),
    "player_blueprint_growth": ("playerBlueprintGrowth", "playerBlueprintGrowth2"),
    "mount_talent_growth": ("mountTalentGrowth",),
    "pet_talent_growth": ("petTalentGrowth",),
}

DIRECT_INI_KEYS: dict[str, str] = {
    "backpack_slots": "inventorySlots",
    "free_craft": "freeCraft",
    "remove_shelter_requirement": "removeShelterRequirement",
    "weatherproof_deployables": "removeEffectedByWeather",
    "starter_ren": "ren",
    "starter_exotics": "exotics",
    "starter_red_exotics": "stabilizedExotics",
    "starter_biomass": "legendaryBiomass",
    "starter_uranium": "uraniumRod",
    "starter_licence": "legendaryLicence",
}

RUNTIME_INI_KEYS: dict[str, str] = {
    "air_control": "airControl",
    "camera_tilt": "cameraTilt",
}


RUNTIME_SETTINGS: tuple[RuntimeSettingSpec, ...] = (
    RuntimeSettingSpec(
        "air_control", "Movement", "Air steering",
        "Runtime movement override. Multiplies Unreal CharacterMovement AirControl and clamps it to the safe 0-1 range. Higher values let you steer more while falling or jumping.",
        choices=("0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2", "3", "5", "10"),
    ),
    RuntimeSettingSpec(
        "camera_tilt", "Movement", "Camera tilt strength",
        "Runtime camera override. 1 keeps vanilla roll/tilt, 0 removes camera roll, and values between them soften lean-style camera tilt.",
        choices=("0", "0.25", "0.5", "0.75", "1", "1.25", "1.5", "2"),
    ),
)

UE4SS_BUILTIN_MODS_TO_DISABLE = {
    "CheatManagerEnablerMod",
    "ActorDumperMod",
    "ConsoleCommandsMod",
    "ConsoleEnablerMod",
    "SplitScreenMod",
    "LineTraceMod",
    "BPModLoaderMod",
    "BPML_GenericFunctions",
    "jsbLuaProfilerMod",
}

OLD_RUNTIME_MOD_NAMES = {
    "ZSG_Balance_w235_Runtime",
    "ZSG_Balance",
    "ZSG_Balance_Runtime",
    "ConfigurationMod",
    "Configuration_Mod_Runtime",
}

MOD_FOLDERS_TO_CLEAN = UE4SS_BUILTIN_MODS_TO_DISABLE | OLD_RUNTIME_MOD_NAMES


SETTINGS: tuple[SettingSpec, ...] = (
    SettingSpec(
        "mining_speed", "Gathering", "Deep-mining speed",
        "Shortens deep-mining extractor cycles while preserving ore-to-ore timing differences.",
        ("World/D_OreDeposit.json",), "field", ("MiningTimeSeconds",),
        direction="divide", result="floor", minimum_result=1,
    ),
    SettingSpec(
        "mining_yield", "Gathering", "Mining yield",
        "Changes how much material each pickaxe hit produces. Better pickaxes remain better than lower tiers.",
        ("Tools/D_ToolDamage.json",), "field", ("Mining_Efficiency",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "ore_density", "Gathering", "Ore-node density",
        "Changes how much material a mineable rock contains. Normal and dense rocks keep their relative differences.",
        ("World/D_VoxelSetupData.json",), "field", ("DensityMultiplier",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "wood_yield", "Gathering", "Woodcutting efficiency",
        "Scales axe felling efficiency without changing melee damage.",
        ("Tools/D_ToolDamage.json",), "field", ("Felling_Efficiency",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "skinning_yield", "Gathering", "Skinning efficiency",
        "Scales skinning-tool efficiency and keeps tool tiers proportional.",
        ("Tools/D_ToolDamage.json",), "field", ("Skinning_Efficiency",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "reaping_yield", "Gathering", "Reaping efficiency",
        "Scales sickle and reaping efficiency.",
        ("Tools/D_ToolDamage.json",), "field", ("Reaping_Efficiency",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "processing_speed", "Crafting", "Processing speed",
        "Makes furnaces, benches, and extractors finish recipes faster by reducing the work required per recipe.",
        ("Crafting/D_ProcessorRecipes.json", "Crafting/D_ExtractorRecipes.json"),
        "field", ("RequiredMillijoules",), direction="divide", result="floor", minimum_result=1,
    ),
    SettingSpec(
        "material_efficiency", "Crafting", "Material efficiency",
        "Warning: edits recipe input arrays. Test on backup saves before using on an existing character.",
        ("Crafting/D_ProcessorRecipes.json",), "recipe_inputs", ("Count",),
        direction="divide", result="floor", minimum_result=1,
    ),
    SettingSpec(
        "crafting_xp", "Crafting", "Crafting XP",
        "Scales XP assigned to crafted items; recipe balance is otherwise unchanged.",
        ("Items/D_ItemsStatic.json",), "field", ("CraftingExperience",),
        result="nearest", minimum_result=0,
    ),
    SettingSpec(
        "fuel_duration", "Crafting", "Fuel duration",
        "Scales energy supplied by sticks, wood, biofuel, and other combustible fuels.",
        ("Traits/D_Combustible.json",), "field", ("MillijoulesProvided",),
        result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "weight_reduction", "Inventory", "Item weight reduction",
        "Divides item weights by this value. Relative item weights are retained.",
        ("Traits/D_Itemable.json",), "field", ("Weight",),
        direction="divide", result="floor", minimum_result=1,
    ),
    SettingSpec(
        "durability", "Inventory", "Item durability",
        "Scales tool, weapon, armor, and deployable durability.",
        ("Traits/D_Durable.json",), "field", ("Max_Durability",),
        result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "spoil_duration", "Survival", "Food and item lifetime",
        "Scales spoil and decay timers. Longer values make perishables last longer.",
        ("Traits/D_Decayable.json",), "field", ("DecayTime", "SpoilTime"),
        result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "food_buff_duration", "Survival", "Food buff duration",
        "Scales consumable modifier durations while retaining food-to-food differences.",
        ("Traits/D_Consumable.json",), "field", ("ModifierLifetime",),
        result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "food_buff_potency", "Survival", "Food buff effectiveness",
        "Changes the strength of food effects that define an effectiveness value. Basic recovery amounts are unchanged.",
        ("Traits/D_Consumable.json",), "field", ("ModifierEffectiveness",),
        result="float", minimum_result=0.01,
    ),
    SettingSpec(
        "crop_speed", "Survival", "Crop growth speed",
        "Shortens living crop growth stages without changing dead-crop cleanup timers.",
        ("Farming/D_FarmingGrowthStates.json",), "field", ("TimeToNextState",),
        direction="divide", result="floor", minimum_result=1,
        exclude_name_suffixes=("_Dead",),
    ),
    SettingSpec(
        "fishing_speed", "Survival", "Fishing bite speed",
        "Shortens the configured minimum and maximum fishing wait times.",
        ("Config/D_GameplayConfig.json",), "rows", ("FloatValue",),
        direction="divide", result="float", minimum_result=0.1,
        row_names=("BaseMinFishingTime", "BaseMaxFishingTime"),
    ),
    SettingSpec(
        "health", "Player", "Maximum health",
        "Scales the player's base maximum health.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseMaximumHealth_+")',), result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "stamina", "Player", "Maximum stamina",
        "Scales the player's base maximum stamina.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseMaximumStamina_+")',), result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "carry_capacity", "Player", "Carry capacity",
        "Scales the player's base weight capacity.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseWeightCapacity_+")',), result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "movement_speed", "Movement", "Movement speed",
        "Scales base walking movement speed. Sprint remains proportional.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseMovementSpeed_+")',), result="nearest", minimum_result=1,
        caution=True,
    ),
    SettingSpec(
        "health_regen", "Player", "Health regeneration",
        "Scales base health regenerated per minute.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseHealthRegenPerMinute_+")',), result="nearest", minimum_result=0,
    ),
    SettingSpec(
        "stamina_regen", "Player", "Stamina regeneration",
        "Scales base stamina regenerated per minute.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        ('(Value="BaseStaminaRegenPerMinute_+")',), result="nearest", minimum_result=0,
    ),
    SettingSpec(
        "needs_duration", "Player", "Food / water / oxygen duration",
        "Divides base consumption rates, making all three survival meters last proportionally longer.",
        ("Stats/D_CharacterStartingStats.json",), "stats",
        (
            '(Value="BaseFoodConsumptionPerHour_+")',
            '(Value="BaseWaterConsumptionPerHour_+")',
            '(Value="BaseOxygenConsumptionPerHour_+")',
        ),
        direction="divide", result="nearest", minimum_result=1,
    ),
    SettingSpec(
        "melee_damage", "Combat", "Tool melee damage",
        "Scales melee damage for tools and melee-capable equipment while retaining tier differences.",
        ("Tools/D_ToolDamage.json",), "field", ("Melee_Damage",),
        result="float", minimum_result=0,
        caution=True,
    ),
    SettingSpec(
        "ranged_damage", "Combat", "Projectile damage",
        "Scales ammunition projectile damage while preserving ammo-tier differences.",
        ("Tools/D_AmmoTypes.json",), "field", ("ProjectileDamage",),
        result="float", minimum_result=0,
        caution=True,
    ),
    SettingSpec(
        "reload_speed", "Combat", "Reload speed",
        "Divides firearm and ranged-weapon reload times. Animation timing may limit extreme values.",
        ("Tools/D_FirearmData.json", "Tools/D_RangedWeaponData.json"),
        "field", ("ReloadTime", "WeaponReloadTime"),
        direction="divide", result="float", minimum_result=0.05,
        caution=True,
    ),
)


PRESETS: dict[str, dict[str, float]] = {
    "Vanilla": {},
}


INI_PRESETS: dict[str, dict[str, Any]] = {
    "Vanilla": {
        "groups": {"xpGroup": 1, "stackGroup": 1, "slotGroup": 1, "recipeOutputGroup": 1, "missionCurrencyGroup": 1},
        "growth": 1, "inventorySlots": 1, "movement": 0,
    },
}


def multiplier_text_to_decimal(text: str) -> Decimal:
    cleaned = (
        text.strip().lower()
        .replace("x", "")
        .replace("?", "")
        .replace("??", "")
        .replace("?????", "")
    )
    return Decimal(cleaned)


def parse_multiplier(text: str) -> Decimal:
    try:
        value = multiplier_text_to_decimal(text)
    except Exception as error:
        raise ValueError(f"Invalid multiplier: {text}") from error
    if not value.is_finite() or value <= 0 or value > 100:
        raise ValueError("Multipliers must be greater than 0 and no more than 100")
    return value


def parse_runtime_value(text: str, spec: RuntimeSettingSpec) -> Decimal:
    try:
        value = multiplier_text_to_decimal(text)
    except Exception as error:
        raise ValueError(f"Invalid {spec.label}: {text}") from error
    if not value.is_finite() or value < spec.minimum or value > spec.maximum:
        raise ValueError(f"{spec.label} must be between {spec.minimum} and {spec.maximum}")
    return value


def display_multiplier(value: float | Decimal) -> str:
    number = Decimal(str(value))
    normalized = number.normalize()
    if normalized == normalized.to_integral_value():
        text = str(int(normalized))
    else:
        text = format(normalized, "f").rstrip("0").rstrip(".")
    return f"{text}x"


def multiplier_choices(values: Iterable[str | float | Decimal]) -> tuple[str, ...]:
    return tuple(display_multiplier(value) for value in values)


def is_direct_multiplier(spec: DirectSettingSpec) -> bool:
    return spec.kind in {"row_field_multiplier", "talent_reward_stat_multiplier"}


def range_row_wording(prefix: str, minimum: str, maximum: str) -> str:
    templates = {
        "xpGroup": "Events that normally award {minimum}–{maximum} XP",
        "stackGroup": "Items that normally stack to {minimum}–{maximum}",
        "slotGroup": "Storage that normally has {minimum}–{maximum} slots",
        "recipeOutputGroup": "Recipe outputs that normally produce {minimum}–{maximum} items",
        "missionCurrencyGroup": "Mission payouts normally worth {minimum}–{maximum} currency",
    }
    return templates[prefix].format(minimum=minimum, maximum=maximum)


def parse_direct_value(text: str, spec: DirectSettingSpec) -> Decimal:
    value = multiplier_text_to_decimal(str(text)) if is_direct_multiplier(spec) else Decimal(str(text).strip())
    if not value.is_finite() or value < 0:
        raise ValueError(f"{spec.label} must be a finite number of zero or greater")
    return value


class Configurator(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = max(980, min(1280, screen_w - 80))
        height = max(680, min(860, screen_h - 100))
        self.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 2)}")
        self.minsize(min(980, width), min(680, height))

        self.app_dir = APP_BASE_DIR
        self.state_dir = APP_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.builds_dir = self.state_dir / "builds"
        self.backups_dir = self.state_dir / "backups"
        self.save_backups_dir = self.state_dir / "save_backups"
        self.runtime_dir = self.state_dir / "runtime_mods"
        self.profiles_dir = self.app_dir / "profiles" if IS_BUNDLED_APP else self.app_dir / "config" / "profiles"
        self.app_log = self.state_dir / "configurator.log"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self.setting_vars = {spec.key: tk.StringVar(value=display_multiplier(1)) for spec in SETTINGS}
        self.direct_vars = {
            spec.key: tk.StringVar(value=display_multiplier(spec.default) if is_direct_multiplier(spec) else spec.default)
            for spec in DIRECT_SETTINGS
        }
        self.curve_vars = {spec.key: tk.StringVar(value=display_multiplier(1)) for spec in CURVE_SETTINGS}
        self.runtime_vars = {spec.key: tk.StringVar(value=display_multiplier(spec.default)) for spec in RUNTIME_SETTINGS}
        self.native_group_vars: dict[str, list[tk.StringVar]] = {
            group.key: [tk.StringVar(value=display_multiplier(1)) for _minimum, _maximum in group.ranges]
            for group in NATIVE_GROUPS
        }
        self.profile_var = tk.StringVar(value="Vanilla Defaults")
        self.profile_combo: ttk.Combobox | None = None
        self.mod_name_var = tk.StringVar(value=RUNTIME_MOD_FOLDER)
        self.status_var = tk.StringVar(value="Choose Vanilla Defaults, Premade_Configuration, or a saved/imported profile")
        self.summary_var = tk.StringVar(value="No changes selected")
        self.group_master_vars: dict[str, tk.StringVar] = {}
        self.range_label_vars: dict[str, tk.StringVar] = {}
        self.console_text: tk.Text | None = None
        self.save_backup_listbox: tk.Listbox | None = None
        self.save_backup_entries: list[Path] = []
        self.save_backup_summary_var = tk.StringVar(value="No save backups loaded")
        self.vault_dir = self.state_dir / "transfer_vault"
        self.vault_path = self.vault_dir / "vault.json"
        self.vault_ledger_path = self.vault_dir / "ledger.jsonl"
        self.vault_listbox: tk.Listbox | None = None
        self.vault_source_listbox: tk.Listbox | None = None
        self.vault_target_combo: ttk.Combobox | None = None
        self.vault_summary_var = tk.StringVar(value="Transfer vault not scanned")
        self.vault_sources: list[dict[str, Any]] = []
        self.vault_items: list[dict[str, Any]] = []
        self.vault_targets: list[dict[str, Any]] = []
        self.vault_target_var = tk.StringVar(value="")

        self.build_ui()
        self.refresh_profile_choices()
        self.status_var.set("Vanilla defaults loaded. Choose Premade_Configuration or a saved/imported profile to apply settings.")
        self.update_summary()

    def build_ui(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.configure(background=UI_BG)
        style.configure("App.TFrame", background=UI_BG)
        style.configure("Panel.TFrame", background=UI_PANEL)
        style.configure("Header.TFrame", background=UI_BG)
        style.configure("Title.TLabel", background=UI_BG, foreground=UI_TEXT, font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=UI_BG, foreground=UI_TEAL, font=("Segoe UI", 10))
        style.configure("Hud.TLabel", background=UI_BG, foreground=UI_MUTED, font=("Segoe UI", 9))
        style.configure("CardText.TLabel", background=UI_PANEL, foreground=UI_MUTED, font=("Segoe UI", 9))
        style.configure("CardHead.TLabel", background=UI_PANEL, foreground=UI_TEXT, font=("Segoe UI", 9, "bold"))
        style.configure("Summary.TLabel", background=UI_BG, foreground=UI_TEAL)
        style.configure("Status.TLabel", background=UI_STATUS, foreground=UI_AMBER, relief=tk.FLAT, padding=(8, 4))
        style.configure("Card.TLabelframe", background=UI_PANEL, bordercolor=UI_BORDER, lightcolor=UI_BORDER, darkcolor=UI_BORDER, relief="solid", borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=UI_PANEL, foreground=UI_TEAL, font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background=UI_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=UI_PANEL_ALT, foreground=UI_MUTED, padding=(13, 6), font=("Segoe UI", 9, "bold"))
        style.map(
            "TNotebook.Tab",
            background=[("selected", UI_PANEL)],
            foreground=[("selected", UI_TEAL)],
            padding=[("selected", (18, 10))],
        )
        style.configure("TCombobox", fieldbackground="#0b1518", background=UI_PANEL_ALT, foreground=UI_TEXT, arrowcolor=UI_TEAL, bordercolor=UI_BORDER, lightcolor=UI_BORDER, darkcolor=UI_BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", "#0b1518")], foreground=[("readonly", UI_TEXT)], selectbackground=[("readonly", "#0b1518")], selectforeground=[("readonly", UI_TEXT)])
        style.configure("Profile.TCombobox", fieldbackground=UI_INPUT_BG, background=UI_INPUT_BG, foreground=UI_INPUT_TEXT, arrowcolor=UI_TEAL_DARK, bordercolor=UI_AMBER, lightcolor=UI_AMBER, darkcolor=UI_AMBER)
        style.map("Profile.TCombobox", fieldbackground=[("readonly", UI_INPUT_BG)], foreground=[("readonly", UI_INPUT_TEXT)], selectbackground=[("readonly", UI_INPUT_BG)], selectforeground=[("readonly", UI_INPUT_TEXT)])
        style.configure("TEntry", fieldbackground="#0b1518", foreground=UI_TEXT, bordercolor=UI_BORDER, lightcolor=UI_BORDER, darkcolor=UI_BORDER)
        style.configure("TCheckbutton", background=UI_PANEL, foreground=UI_TEXT)
        style.map("TCheckbutton", background=[("active", UI_PANEL)], foreground=[("active", UI_TEAL)])
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 9), background=UI_AMBER, foreground="#071014", bordercolor=UI_AMBER)
        style.map("Primary.TButton", background=[("active", "#ffc057")], foreground=[("active", "#071014")])
        style.configure("TButton", padding=(10, 6), background=UI_PANEL_ALT, foreground=UI_TEAL, bordercolor=UI_BORDER)
        style.map("TButton", background=[("active", UI_TEAL_DARK)], foreground=[("active", UI_TEXT)])
        style.configure("Soft.TButton", padding=(10, 6), background=UI_PANEL_ALT, foreground=UI_TEAL, bordercolor=UI_BORDER)
        style.map("Soft.TButton", background=[("active", UI_TEAL_DARK)], foreground=[("active", UI_TEXT)])
        self.option_add("*TCombobox*Listbox.background", UI_INPUT_BG)
        self.option_add("*TCombobox*Listbox.foreground", UI_INPUT_TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", UI_TEAL_DARK)
        self.option_add("*TCombobox*Listbox.selectForeground", UI_TEXT)

        header = ttk.Frame(self, padding=(18, 16, 18, 12), style="Header.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(header, text="Icarus Configuration Mod", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Profiles  -  Balance Tuning  -  Runtime Validation",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        actions = ttk.Frame(self, padding=(12, 10, 12, 8), style="App.TFrame")
        actions.pack(fill=tk.X)
        ttk.Label(actions, text="Profile:", style="Hud.TLabel").pack(side=tk.LEFT)
        self.profile_combo = ttk.Combobox(actions, textvariable=self.profile_var, state="readonly", width=30, style="Profile.TCombobox")
        self.profile_combo.pack(side=tk.LEFT, padx=(6, 4))
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_selected_profile())
        ttk.Button(actions, text="Import Profile", command=self.load_profile).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Save Profile", command=self.save_profile).pack(side=tk.RIGHT, padx=(0, 6))

        parity = (
            f"{len(SETTINGS) + len(DIRECT_SETTINGS) + len(CURVE_SETTINGS) + sum(len(group.ranges) for group in NATIVE_GROUPS)} INI controls"
            f" + {len(RUNTIME_SETTINGS)} runtime controls"
        )
        ttk.Label(actions, text=parity, style="Hud.TLabel").pack(side=tk.RIGHT, padx=(0, 18))

        notebook = ttk.Notebook(self)
        self.notebook = notebook
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        categories = ["Gathering", "Crafting", "Inventory", "Survival", "Movement", "Progression", "Rewards", "Combat"]
        for spec in SETTINGS:
            if spec.category == "Player":
                continue
            if spec.category not in categories:
                categories.append(spec.category)
        category_frames: dict[str, ttk.Frame] = {}
        category_rows: dict[str, int] = {}
        category_content: dict[str, ttk.Frame] = {}
        for category in categories:
            outer = ttk.Frame(notebook)
            notebook.add(outer, text=category)
            canvas = tk.Canvas(outer, highlightthickness=0, background=UI_BG)
            scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
            content = ttk.Frame(canvas, padding=10, style="App.TFrame")
            window = canvas.create_window((0, 0), window=content, anchor="nw")
            content.bind("<Configure>", lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            category_frames[category] = outer
            category_content[category] = content
            category_rows[category] = 0

        self.add_save_backup_tab(notebook)
        self.add_transfer_vault_tab(notebook)

        console_outer = ttk.Frame(notebook, padding=10, style="App.TFrame")
        notebook.add(console_outer, text="Console")
        console_actions = ttk.Frame(console_outer, style="App.TFrame")
        console_actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(console_actions, text="Refresh Logs", style="Soft.TButton", command=self.refresh_console).pack(side=tk.LEFT)
        ttk.Button(console_actions, text="Clear App Log", style="Soft.TButton", command=self.clear_app_log).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(console_actions, text="Open Runtime Folder", style="Soft.TButton", command=self.open_runtime_folder).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(console_actions, text="Reset Installed Mod", style="Soft.TButton", command=self.reset_installed_mod).pack(side=tk.LEFT, padx=(6, 0))
        self.console_text = tk.Text(console_outer, height=20, wrap=tk.WORD, font=("Consolas", 9), background="#050a0d", foreground=UI_TEXT, insertbackground=UI_TEAL, selectbackground=UI_TEAL_DARK, relief=tk.FLAT, borderwidth=0)
        console_scroll = ttk.Scrollbar(console_outer, orient=tk.VERTICAL, command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=console_scroll.set)
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        console_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        choices = multiplier_choices(("0.5", "0.75", "1", "1.25", "1.5", "2", "3", "5", "10"))
        for spec in SETTINGS:
            category = "Survival" if spec.category == "Player" else spec.category
            parent = category_content[category]
            row = category_rows[category]
            card = ttk.LabelFrame(parent, text=spec.label + ("  [!]" if spec.caution else ""), style="Card.TLabelframe", padding=10)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(card, text=spec.description, wraplength=720, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(card, textvariable=self.setting_vars[spec.key], values=choices, width=10)
            combo.grid(row=0, column=1, sticky="e", padx=(16, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.update_summary())
            combo.bind("<FocusOut>", lambda _event: self.update_summary())
            card.columnconfigure(0, weight=1)
            parent.columnconfigure(0, weight=1)
            category_rows[category] += 1

        for spec in DIRECT_SETTINGS:
            parent = category_content[spec.category]
            row = category_rows[spec.category]
            card = ttk.LabelFrame(parent, text=spec.label, style="Card.TLabelframe", padding=10)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(card, text=spec.description, wraplength=720, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
            variable = self.direct_vars[spec.key]
            if spec.choices == ("0", "1"):
                ttk.Checkbutton(card, variable=variable, onvalue="1", offvalue="0").grid(row=0, column=1, sticky="e", padx=(16, 0))
            elif spec.choices:
                combo_values = multiplier_choices(spec.choices) if is_direct_multiplier(spec) else spec.choices
                combo = ttk.Combobox(card, textvariable=variable, values=combo_values, width=10)
                combo.grid(row=0, column=1, sticky="e", padx=(16, 0))
                combo.bind("<<ComboboxSelected>>", lambda _event: self.update_summary())
                combo.bind("<FocusOut>", lambda _event: self.update_summary())
            else:
                entry = ttk.Entry(card, textvariable=variable, width=10)
                entry.grid(row=0, column=1, sticky="e", padx=(16, 0))
                entry.bind("<FocusOut>", lambda _event: self.update_summary())
            card.columnconfigure(0, weight=1)
            parent.columnconfigure(0, weight=1)
            category_rows[spec.category] += 1

        for spec in CURVE_SETTINGS:
            parent = category_content[spec.category]
            row = category_rows[spec.category]
            title = spec.label if CURVE_RUNTIME_ENABLED else f"{spec.label} (unsupported)"
            card = ttk.LabelFrame(parent, text=title, style="Card.TLabelframe", padding=10)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(card, text=spec.description, wraplength=720, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
            combo_state = "normal" if CURVE_RUNTIME_ENABLED else "disabled"
            combo = ttk.Combobox(card, textvariable=self.curve_vars[spec.key], values=multiplier_choices(("0.5", "0.75", "1", "1.25", "1.5", "2", "3", "5", "7.5", "10")), width=10, state=combo_state)
            combo.grid(row=0, column=1, sticky="e", padx=(16, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.update_summary())
            combo.bind("<FocusOut>", lambda _event: self.update_summary())
            card.columnconfigure(0, weight=1)
            parent.columnconfigure(0, weight=1)
            category_rows[spec.category] += 1

        for spec in RUNTIME_SETTINGS:
            parent = category_content[spec.category]
            row = category_rows[spec.category]
            card = ttk.LabelFrame(parent, text=spec.label, style="Card.TLabelframe", padding=10)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(card, text=spec.description, wraplength=720, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
            combo = ttk.Combobox(card, textvariable=self.runtime_vars[spec.key], values=multiplier_choices(spec.choices), width=10)
            combo.grid(row=0, column=1, sticky="e", padx=(16, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.update_summary())
            combo.bind("<FocusOut>", lambda _event: self.update_summary())
            card.columnconfigure(0, weight=1)
            parent.columnconfigure(0, weight=1)
            category_rows[spec.category] += 1

        for group in NATIVE_GROUPS:
            self.add_group_card(category_content[group.category], category_rows, group)

        footer = ttk.Frame(self, padding=(12, 0, 12, 8), style="App.TFrame")
        footer.pack(fill=tk.X)
        ttk.Label(footer, textvariable=self.summary_var, style="Summary.TLabel").pack(anchor=tk.W, pady=(0, 6))
        build_row = ttk.Frame(footer, style="App.TFrame")
        build_row.pack(fill=tk.X)
        ttk.Button(build_row, text="Preview All", style="Soft.TButton", command=self.preview).pack(side=tk.LEFT)
        ttk.Button(build_row, text="Apply Configuration", style="Primary.TButton", command=self.apply_configuration).pack(side=tk.RIGHT)
        ttk.Button(build_row, text="Save Unified INI", style="Soft.TButton", command=lambda: self.save_ini(False)).pack(side=tk.RIGHT, padx=(0, 8))
        if self.developer_tools_available():
            ttk.Button(build_row, text="Build DLL Mod Files", style="Soft.TButton", command=self.build_runtime_mod_files).pack(side=tk.RIGHT, padx=(0, 8))
            ttk.Entry(build_row, textvariable=self.mod_name_var, width=32).pack(side=tk.RIGHT, padx=(0, 8))
            ttk.Label(build_row, text="Mod name:", style="Hud.TLabel").pack(side=tk.RIGHT)

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel", anchor=tk.W).pack(
            fill=tk.X, side=tk.BOTTOM
        )
        for variables in self.native_group_vars.values():
            for variable in variables:
                variable.trace_add("write", lambda *_args: self.update_summary())
        for variable in self.direct_vars.values():
            variable.trace_add("write", lambda *_args: self.update_summary())
        for variable in self.curve_vars.values():
            variable.trace_add("write", lambda *_args: self.update_summary())
        for variable in self.runtime_vars.values():
            variable.trace_add("write", lambda *_args: self.update_summary())

    def add_save_backup_tab(self, notebook: ttk.Notebook) -> None:
        outer = ttk.Frame(notebook, padding=10, style="App.TFrame")
        notebook.add(outer, text="Save Backups")
        actions = ttk.Frame(outer, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(actions, text="Create Backup", style="Primary.TButton", command=self.create_manual_save_backup).pack(side=tk.LEFT)
        ttk.Button(actions, text="Restore Selected", style="Soft.TButton", command=self.restore_selected_save_backup).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Refresh", style="Soft.TButton", command=self.refresh_save_backup_list).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Open Backup Folder", style="Soft.TButton", command=self.open_save_backup_folder).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(outer, textvariable=self.save_backup_summary_var, style="Hud.TLabel").pack(anchor=tk.W, pady=(0, 8))

        body = ttk.Frame(outer, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        self.save_backup_listbox = tk.Listbox(
            body,
            height=18,
            background="#050a0d",
            foreground=UI_TEXT,
            selectbackground=UI_TEAL_DARK,
            selectforeground=UI_TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            activestyle="none",
            font=("Consolas", 10),
        )
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.save_backup_listbox.yview)
        self.save_backup_listbox.configure(yscrollcommand=scrollbar.set)
        self.save_backup_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(
            outer,
            text="Backups include Icarus Saved\\PlayerData, Saved\\SaveGames, Saved\\ExtraData, and steam_autocloud.vdf when present. Applying configuration creates an automatic backup first.",
            style="CardText.TLabel",
            wraplength=920,
        ).pack(anchor=tk.W, pady=(8, 0))
        self.refresh_save_backup_list()

    def add_transfer_vault_tab(self, notebook: ttk.Notebook) -> None:
        outer = ttk.Frame(notebook, padding=10, style="App.TFrame")
        notebook.add(outer, text="Transfer Vault")

        actions = ttk.Frame(outer, style="App.TFrame")
        actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(actions, text="Scan Saves", style="Primary.TButton", command=self.refresh_transfer_vault).pack(side=tk.LEFT)
        ttk.Button(actions, text="Move Selected To Vault", style="Soft.TButton", command=self.vault_export_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Restore Vault Item", style="Soft.TButton", command=self.vault_import_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(actions, text="Open Vault Folder", style="Soft.TButton", command=self.open_transfer_vault_folder).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(outer, textvariable=self.vault_summary_var, style="Hud.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(
            outer,
            text="Offline shared stash for all local players. Close Icarus first. JSON inventories can be moved now; live world inventories inside ProspectBlob are detected but not edited until the binary inventory writer is verified.",
            style="CardText.TLabel",
            wraplength=980,
        ).pack(anchor=tk.W, pady=(0, 8))

        selector = ttk.Frame(outer, style="App.TFrame")
        selector.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(selector, text="Restore target:", style="Hud.TLabel").pack(side=tk.LEFT)
        self.vault_target_combo = ttk.Combobox(selector, textvariable=self.vault_target_var, state="readonly", width=72, style="Profile.TCombobox")
        self.vault_target_combo.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        columns = ttk.Frame(outer, style="App.TFrame")
        columns.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(columns, text="Detected Player/World Items", style="Card.TLabelframe", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.vault_source_listbox = tk.Listbox(
            left,
            height=18,
            background="#050a0d",
            foreground=UI_TEXT,
            selectbackground=UI_TEAL_DARK,
            selectforeground=UI_TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            activestyle="none",
            font=("Consolas", 9),
        )
        source_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.vault_source_listbox.yview)
        self.vault_source_listbox.configure(yscrollcommand=source_scroll.set)
        self.vault_source_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        source_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        right = ttk.LabelFrame(columns, text="Shared Transfer Vault", style="Card.TLabelframe", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self.vault_listbox = tk.Listbox(
            right,
            height=18,
            background="#050a0d",
            foreground=UI_TEXT,
            selectbackground=UI_TEAL_DARK,
            selectforeground=UI_TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            activestyle="none",
            font=("Consolas", 9),
        )
        vault_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.vault_listbox.yview)
        self.vault_listbox.configure(yscrollcommand=vault_scroll.set)
        self.vault_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vault_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_transfer_vault()

    def add_group_card(self, parent: ttk.Frame, rows: dict[str, int], group: NativeGroupSpec) -> None:
        row = rows[group.category]
        card = ttk.LabelFrame(parent, text=group.label, style="Card.TLabelframe", padding=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        description = (
            f"{group.description} Ranges are fixed native filters based on the vanilla value in "
            f"{group.file}; only the multiplier is editable."
        )
        ttk.Label(card, text=description, wraplength=680, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        variables = self.native_group_vars[group.key]
        current = [variable.get() for variable in variables]
        master = tk.StringVar(value=(current[0] if len(set(current)) == 1 else "Custom"))
        self.group_master_vars[group.key] = master
        ttk.Label(card, text="Overall multiplier", style="CardText.TLabel").grid(row=0, column=1, padx=(12, 4))
        combo = ttk.Combobox(card, textvariable=master, values=multiplier_choices(("0.5", "0.75", "1", "1.5", "2", "3", "5", "7.5", "10")), width=10)
        combo.grid(row=0, column=2, padx=(4, 6))
        details = ttk.Frame(card, style="Panel.TFrame")
        visible = tk.BooleanVar(value=False)
        toggle = ttk.Button(card, text="Fine tune", width=13)
        toggle.grid(row=0, column=3)

        def apply_master(_event: tk.Event | None = None) -> None:
            if master.get() == "Custom":
                return
            try:
                value = display_multiplier(parse_multiplier(master.get()))
            except Exception:
                return
            for variable in variables:
                variable.set(value)
            self.update_summary()

        combo.bind("<<ComboboxSelected>>", apply_master)
        combo.bind("<FocusOut>", apply_master)

        def toggle_details() -> None:
            visible.set(not visible.get())
            if visible.get():
                details.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
            else:
                details.grid_remove()

        toggle.configure(command=toggle_details)
        ttk.Label(details, text="Fixed vanilla range", style="CardHead.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(details, text="Multiplier", style="CardHead.TLabel").grid(row=0, column=1, sticky="e", pady=(0, 4))
        for index, ((minimum, maximum), variable) in enumerate(zip(group.ranges, variables), start=1):
            key = f"{group.key}{index}"
            wording_var = tk.StringVar(value=range_row_wording(group.key, str(minimum), str(maximum)))
            self.range_label_vars[key] = wording_var
            ttk.Label(details, textvariable=wording_var, wraplength=620, style="CardText.TLabel").grid(row=index, column=0, sticky="w", pady=2)
            entry = ttk.Entry(details, textvariable=variable, width=10)
            entry.grid(row=index, column=1, sticky="e", padx=(8, 0), pady=2)
            entry.bind("<FocusOut>", lambda _e, p=group.key: self.refresh_group_master(p))
        if group.exclude_name_patterns:
            text = "Built-in exclusions: " + ", ".join(group.exclude_name_patterns)
            ttk.Label(details, text=text, wraplength=650, style="CardText.TLabel").grid(row=len(group.ranges) + 1, column=0, columnspan=2, sticky="w", pady=(8, 2))
        details.columnconfigure(0, weight=1)
        details.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        details.grid_remove()
        card.columnconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        rows[group.category] += 1

    def refresh_group_master(self, prefix: str) -> None:
        values = [str(variable.get()) for variable in self.native_group_vars.get(prefix, [])]
        if prefix in self.group_master_vars and values:
            self.group_master_vars[prefix].set(values[0] if len(set(values)) == 1 else "Custom")

    def values(self) -> dict[str, Decimal]:
        return {key: parse_multiplier(variable.get()) for key, variable in self.setting_vars.items()}

    def native_group_values(self) -> dict[str, list[Decimal]]:
        values: dict[str, list[Decimal]] = {}
        for group in NATIVE_GROUPS:
            group_values: list[Decimal] = []
            for variable in self.native_group_vars[group.key]:
                group_values.append(parse_multiplier(variable.get()))
            values[group.key] = group_values
        return values

    def direct_values(self) -> dict[str, Decimal]:
        return {spec.key: parse_direct_value(self.direct_vars[spec.key].get(), spec) for spec in DIRECT_SETTINGS}

    def curve_values(self) -> dict[str, Decimal]:
        if not CURVE_RUNTIME_ENABLED:
            return {spec.key: Decimal("1") for spec in CURVE_SETTINGS}
        return {spec.key: parse_multiplier(self.curve_vars[spec.key].get()) for spec in CURVE_SETTINGS}

    def runtime_values(self) -> dict[str, Decimal]:
        return {spec.key: parse_runtime_value(self.runtime_vars[spec.key].get(), spec) for spec in RUNTIME_SETTINGS}

    def read_user_settings(self) -> dict:
        if not USER_SETTINGS_PATH.is_file():
            return {}
        try:
            return json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def write_user_settings(self, settings: dict) -> None:
        USER_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_SETTINGS_PATH.write_text(json.dumps(settings, indent=4) + "\n", encoding="utf-8")

    def locate_steam_libraries(self) -> list[Path]:
        roots: list[Path] = []
        for steam in (Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")):
            library_file = steam / "steamapps" / "libraryfolders.vdf"
            if not library_file.is_file():
                continue
            roots.append(steam)
            text = library_file.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if '"path"' not in line:
                    continue
                parts = line.split('"')
                if len(parts) >= 4:
                    roots.append(Path(parts[3].replace("\\\\", "\\")))
        return list(dict.fromkeys(roots))

    def normalize_icarus_win64_dir(self, selected: Path) -> Path | None:
        candidates = [
            selected,
            selected / "Binaries" / "Win64",
            selected / "Icarus" / "Binaries" / "Win64",
            selected / "Icarus" / "Icarus" / "Binaries" / "Win64",
            selected / "steamapps" / "common" / "Icarus" / "Icarus" / "Binaries" / "Win64",
        ]
        for candidate in candidates:
            if candidate.is_dir() and candidate.name.casefold() == "win64":
                return candidate.resolve()
        return None

    def prompt_for_icarus_win64_dir(self) -> Path:
        selected = filedialog.askdirectory(
            parent=self,
            title="Select Icarus Win64 or Icarus install folder",
            initialdir=str(Path.home()),
        )
        if not selected:
            raise FileNotFoundError("Icarus Win64 folder was not selected")
        win64_dir = self.normalize_icarus_win64_dir(Path(selected))
        if win64_dir is None:
            raise FileNotFoundError(
                "Selected folder was not an Icarus install. Select the Icarus folder or Icarus\\Binaries\\Win64."
            )
        settings = self.read_user_settings()
        settings["icarus_win64_dir"] = str(win64_dir)
        self.write_user_settings(settings)
        self.log(f"Saved Icarus Win64 folder: {win64_dir}")
        return win64_dir

    def game_win64_dir(self, prompt: bool = False) -> Path:
        configured = os.environ.get("ICARUS_WIN64_DIR")
        saved = self.read_user_settings().get("icarus_win64_dir")
        candidates = []
        if configured:
            candidates.append(Path(configured))
        if saved:
            candidates.append(Path(saved))
        candidates.extend(
            [
                self.app_dir / "Binaries" / "Win64",
                self.app_dir.parent / "Icarus" / "Binaries" / "Win64",
                Path(r"C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Binaries\Win64"),
                Path(r"C:\Program Files\Steam\steamapps\common\Icarus\Icarus\Binaries\Win64"),
            ]
        )
        for library in self.locate_steam_libraries():
            candidates.append(library / "steamapps" / "common" / "Icarus" / "Icarus" / "Binaries" / "Win64")
        detected = next((path.resolve() for path in candidates if path.is_dir()), None)
        if detected is not None:
            return detected
        if prompt:
            return self.prompt_for_icarus_win64_dir()
        return candidates[-2]

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        try:
            self.app_log.parent.mkdir(parents=True, exist_ok=True)
            with self.app_log.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
        except Exception:
            pass

    def read_tail(self, path: Path, max_chars: int = 40000) -> str:
        if not path.is_file():
            return f"(missing) {path}\n"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as error:
            return f"(error reading {path}) {error}\n"
        return text[-max_chars:]

    def running_icarus_processes(self) -> list[str]:
        if os.name != "nt":
            return []
        found: list[str] = []
        for image_name in ("Icarus-Win64-Shipping.exe", "Icarus.exe"):
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except Exception:
                continue
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or "No tasks are running" in line or not line.startswith('"'):
                    continue
                columns = [part.strip().strip('"') for part in line.split('","')]
                if len(columns) >= 2 and columns[0].lower() == image_name.lower():
                    found.append(f"{columns[0]} pid={columns[1]}")
        return found

    def runtime_health_report(self, win64_dir: Path, runtime_mod: Path) -> str:
        lines: list[str] = []
        processes = self.running_icarus_processes()
        if processes:
            lines.append("WARNING: Icarus is currently running.")
            lines.append("UE4SS C++ DLL changes are loaded at game startup; fully close and restart Icarus before testing newly applied runtime settings.")
            lines.append("Running processes: " + ", ".join(processes))
        else:
            lines.append("Icarus is not running. Runtime changes should load on the next launch.")

        config_path = runtime_mod / "runtime_config.json"
        ini_path = runtime_mod / RUNTIME_INI_NAME
        dll_path = runtime_mod / "dlls" / "main.dll"
        ue4ss_log_path = win64_dir / "UE4SS.log"
        newest_runtime_mtime = 0.0
        if config_path.is_file():
            config_mtime = config_path.stat().st_mtime
            newest_runtime_mtime = max(newest_runtime_mtime, config_mtime)
            lines.append(f"Runtime config modified: {datetime.fromtimestamp(config_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        if ini_path.is_file():
            ini_mtime = ini_path.stat().st_mtime
            newest_runtime_mtime = max(newest_runtime_mtime, ini_mtime)
            lines.append(f"Unified INI modified: {datetime.fromtimestamp(ini_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        if dll_path.is_file():
            dll_mtime = dll_path.stat().st_mtime
            newest_runtime_mtime = max(newest_runtime_mtime, dll_mtime)
            lines.append(f"Runtime DLL modified: {datetime.fromtimestamp(dll_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

        ue4ss_log_mtime = ue4ss_log_path.stat().st_mtime if ue4ss_log_path.is_file() else 0.0
        if ue4ss_log_mtime:
            lines.append(f"UE4SS log modified: {datetime.fromtimestamp(ue4ss_log_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

        stale_log = bool(newest_runtime_mtime and ue4ss_log_mtime and ue4ss_log_mtime < newest_runtime_mtime)
        ue4ss_log = self.read_tail(ue4ss_log_path, 20000)
        if "Registered BlueprintUpdateCamera camera tilt hook" in ue4ss_log:
            if stale_log and not processes:
                lines.append("NOTE: UE4SS.log is older than the installed runtime files, so its old BlueprintUpdateCamera hook entry is from a previous session.")
                lines.append("Start Icarus again to verify the fixed runtime loads.")
            else:
                lines.append("WARNING: current UE4SS log shows the old BlueprintUpdateCamera camera hook was loaded in this running session.")
                lines.append("That hook is not part of the installed C++ DLL runtime, but the game must be restarted to unload the old hook.")
        if "Started safe 2000ms air-control refresh loop" in ue4ss_log:
            if stale_log and not processes:
                lines.append("NOTE: UE4SS.log is older than the installed runtime files, so its old 2000ms loop entry is from a previous session.")
            else:
                lines.append("WARNING: current UE4SS log shows the old 2000ms loop was loaded in this running session.")
                lines.append("The installed C++ DLL runtime replaced that Lua loop, but that also requires a game restart.")
        dll_log = self.read_tail(runtime_mod / "runtime_dll.log", 20000)
        if "VALIDATION DllLoaded=true IniRead=true ManifestRead=true" in dll_log:
            lines.append("OK: DLL loaded, read the unified INI, and read the option manifest.")
        elif (runtime_mod / "runtime_dll.log").is_file():
            lines.append("WARNING: DLL log exists but does not show completed INI/manifest validation.")
        else:
            lines.append("WARNING: C++ DLL runtime validation log is missing. Start Icarus after installing the mod.")
        if "VALIDATION ApplyStatus=runtime" in dll_log:
            lines.append("OK: DLL runtime apply validation was written. Check the Runtime DLL log section for applied object counts.")
        elif (runtime_mod / "runtime_dll.log").is_file():
            lines.append("WARNING: DLL log exists but does not show runtime apply validation yet. Enter a prospect/session after restarting Icarus.")
        if "VALIDATION ApplyStatus=tables" in dll_log:
            lines.append("OK: DLL data-table apply validation was written. Check the Runtime DLL log section for matched tables and changed field counts.")
        elif (runtime_mod / "runtime_dll.log").is_file():
            lines.append("WARNING: DLL log exists but does not show data-table apply validation yet. Open a prospect/session so the game loads DataTables.")
        greenlight = re.findall(
            r"VALIDATION GreenLight Phase=(?P<phase>\S+) GreenLight=(?P<green>YES|NO) Active=(?P<active>\d+) Applied=(?P<applied>\d+) Partial=(?P<partial>\d+) Pending=(?P<pending>\d+) Skipped=(?P<skipped>\d+) Unsupported=(?P<unsupported>\d+) MissingFields=(?P<missing>\d+)",
            dll_log,
        )
        settings_summary = re.findall(
            r"VALIDATION SettingsSummary Phase=(?P<phase>\S+) Total=(?P<total>\d+)(?: Active=(?P<active>\d+))? Applied=(?P<applied>\d+)(?: Partial=(?P<partial>\d+))? Pending=(?P<pending>\d+) Skipped=(?P<skipped>\d+) Unsupported=(?P<unsupported>\d+)(?: MissingFields=(?P<missing>\d+))? Inactive=(?P<inactive>\d+)",
            dll_log,
        )
        if greenlight:
            phase, green, active, applied, partial, pending, skipped, unsupported, missing = greenlight[-1]
            level = "OK" if green == "YES" else "WARNING"
            lines.append(
                f"{level}: validator green light at {phase}: {green} "
                f"({active} active, {applied} applied, {partial} partial, {pending} pending, "
                f"{skipped} skipped, {unsupported} unsupported, {missing} missing fields)."
            )
        if settings_summary:
            phase, total, active, applied, partial, pending, skipped, unsupported, missing, inactive = settings_summary[-1]
            active = active or "unknown"
            partial = partial or "0"
            missing = missing or "0"
            lines.append(
                f"OK: per-setting validator wrote {total} statuses at {phase}: "
                f"{active} active, {applied} applied, {partial} partial, {pending} pending, "
                f"{skipped} skipped, {unsupported} unsupported, {missing} missing fields, {inactive} inactive."
            )
            problem_lines = [
                line for line in dll_log.splitlines()
                if line.startswith("SETTING_STATUS ")
                and " Active=true " in line
                and any(token in line for token in (" Result=pending ", " Result=skipped ", " Result=unsupported ", " Result=partial "))
            ]
            for line in problem_lines[-12:]:
                match = re.search(r"Id=(\S+).*?Result=(\S+).*?Reason=(.*)$", line)
                if match:
                    lines.append(f"SETTING WARNING: {match.group(1)} is {match.group(2)} ({match.group(3)})")
        elif (runtime_mod / "runtime_dll.log").is_file():
            lines.append("WARNING: DLL log exists but does not show per-setting validator output yet. Restart Icarus and enter a loaded session.")
        if not dll_path.is_file():
            lines.append("ERROR: DLL-only runtime is missing dlls/main.dll.")
        return "\n".join(lines) + "\n"

    def refresh_console(self) -> None:
        if self.console_text is None:
            return
        win64_dir = self.game_win64_dir()
        mods_root = self.runtime_mods_root(win64_dir)
        runtime_mod = mods_root / RUNTIME_MOD_FOLDER
        sections = [
            ("Configurator log", self.read_tail(self.app_log)),
            ("Runtime health", self.runtime_health_report(win64_dir, runtime_mod)),
            ("UE4SS log", self.read_tail(win64_dir / "UE4SS.log")),
            ("UE4SS mods.txt", self.read_tail(mods_root / "mods.txt", 8000)),
            ("Unified INI", self.read_tail(runtime_mod / RUNTIME_INI_NAME, 12000)),
            ("Runtime config", self.read_tail(runtime_mod / "runtime_config.json", 4000)),
            ("Runtime file log", self.read_tail(runtime_mod / "runtime.log", 12000)),
            ("Runtime DLL log", self.read_tail(runtime_mod / "runtime_dll.log", 20000)),
        ]
        combined = []
        for title, text in sections:
            combined.append(f"===== {title} =====\n{text.rstrip()}\n")
        self.console_text.configure(state=tk.NORMAL)
        self.console_text.delete("1.0", tk.END)
        self.console_text.insert(tk.END, "\n".join(combined))
        self.console_text.see(tk.END)

    def clear_app_log(self) -> None:
        try:
            self.app_log.write_text("", encoding="utf-8")
            self.refresh_console()
            self.status_var.set("Cleared configurator log")
        except Exception as error:
            self.show_error("Clear log failed", error)

    def open_runtime_folder(self) -> None:
        try:
            runtime_mod = self.runtime_mods_root(self.game_win64_dir()) / RUNTIME_MOD_FOLDER
            runtime_mod.mkdir(parents=True, exist_ok=True)
            os.startfile(runtime_mod)
        except Exception as error:
            self.show_error("Open runtime folder failed", error)

    def icarus_saved_dir(self) -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "Icarus" / "Saved"

    def save_backup_components(self) -> tuple[str, ...]:
        return ("PlayerData", "SaveGames", "ExtraData", "steam_autocloud.vdf")

    def safe_reason_slug(self, reason: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", reason.strip()).strip("._")
        return slug or "manual"

    def directory_stats(self, path: Path) -> tuple[int, int]:
        if path.is_file():
            return 1, path.stat().st_size
        count = 0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
                total += item.stat().st_size
        return count, total

    def format_bytes(self, size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{size} B"

    def create_save_backup(self, reason: str = "manual", silent: bool = False) -> Path:
        processes = self.running_icarus_processes()
        if processes:
            raise RuntimeError(
                "Close Icarus before creating or restoring save backups. Running processes: "
                + ", ".join(processes)
            )
        source_root = self.icarus_saved_dir()
        if not source_root.is_dir():
            raise FileNotFoundError(f"Icarus save folder was not found: {source_root}")
        existing_components = [name for name in self.save_backup_components() if (source_root / name).exists()]
        if not existing_components:
            raise FileNotFoundError(f"No supported Icarus save files were found in: {source_root}")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.save_backups_dir / f"{stamp}_{self.safe_reason_slug(reason)}"
        suffix = 2
        while target.exists():
            target = self.save_backups_dir / f"{stamp}_{self.safe_reason_slug(reason)}_{suffix}"
            suffix += 1
        saved_target = target / "Saved"
        saved_target.mkdir(parents=True, exist_ok=False)

        copied: list[str] = []
        file_count = 0
        byte_count = 0
        for name in existing_components:
            source = source_root / name
            destination = saved_target / name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            copied.append(name)
            files, size = self.directory_stats(destination)
            file_count += files
            byte_count += size

        manifest = {
            "schema": 1,
            "created": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
            "source": str(source_root),
            "components": copied,
            "file_count": file_count,
            "total_bytes": byte_count,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")
        self.log(
            f"Created Icarus save backup {target} "
            f"({file_count} files, {self.format_bytes(byte_count)}, components: {', '.join(copied)})"
        )
        self.refresh_save_backup_list()
        if not silent:
            self.status_var.set(f"Created save backup: {target.name}")
            messagebox.showinfo(APP_NAME, f"Created save backup:\n{target}", parent=self)
        return target

    def create_manual_save_backup(self) -> None:
        try:
            self.create_save_backup("manual")
        except Exception as error:
            self.show_error("Save backup failed", error)

    def auto_backup_saves_before_apply(self) -> Path | None:
        try:
            backup = self.create_save_backup("before_apply", silent=True)
            self.status_var.set(f"Created save backup before apply: {backup.name}")
            return backup
        except FileNotFoundError as error:
            self.log(f"WARNING: Save backup skipped before apply: {error}")
            return None

    def save_backup_manifest(self, backup: Path) -> dict[str, Any]:
        manifest_path = backup / "manifest.json"
        if not manifest_path.is_file():
            return {}
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def available_save_backups(self) -> list[Path]:
        if not self.save_backups_dir.is_dir():
            return []
        return sorted(
            [path for path in self.save_backups_dir.iterdir() if path.is_dir() and (path / "Saved").is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def refresh_save_backup_list(self) -> None:
        self.save_backup_entries = self.available_save_backups()
        if self.save_backup_listbox is not None:
            self.save_backup_listbox.delete(0, tk.END)
            for backup in self.save_backup_entries:
                manifest = self.save_backup_manifest(backup)
                count = manifest.get("file_count", "?")
                size = manifest.get("total_bytes")
                size_text = self.format_bytes(size) if isinstance(size, int) else "unknown size"
                created = manifest.get("created", backup.name)
                reason = manifest.get("reason", "")
                self.save_backup_listbox.insert(tk.END, f"{backup.name} | {created} | {reason} | {count} files | {size_text}")
        save_root = self.icarus_saved_dir()
        self.save_backup_summary_var.set(
            f"Save folder: {save_root}    Backup folder: {self.save_backups_dir}    Backups: {len(self.save_backup_entries)}"
        )

    def selected_save_backup(self) -> Path:
        if self.save_backup_listbox is None:
            raise RuntimeError("Save backup list is not available")
        selection = self.save_backup_listbox.curselection()
        if not selection:
            raise RuntimeError("Select a save backup first")
        return self.save_backup_entries[int(selection[0])]

    def remove_existing_save_component(self, path: Path, save_root: Path) -> None:
        resolved_root = save_root.resolve()
        resolved_path = path.resolve()
        if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
            raise RuntimeError(f"Refusing to remove path outside Icarus Saved folder: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def restore_selected_save_backup(self) -> None:
        try:
            backup = self.selected_save_backup()
            processes = self.running_icarus_processes()
            if processes:
                raise RuntimeError(
                    "Close Icarus before restoring save backups. Running processes: "
                    + ", ".join(processes)
                )
            saved_source = backup / "Saved"
            if not saved_source.is_dir():
                raise FileNotFoundError(f"Backup is missing Saved folder: {saved_source}")
            components = [path for path in saved_source.iterdir() if path.name in self.save_backup_components()]
            if not components:
                raise FileNotFoundError(f"Backup has no supported save components: {saved_source}")
            if not messagebox.askyesno(
                APP_NAME,
                "Restore this Icarus save backup?\n\n"
                "The app will create a pre-restore backup first, then replace matching PlayerData/SaveGames/ExtraData files.",
                parent=self,
            ):
                return
            self.create_save_backup("pre_restore", silent=True)
            save_root = self.icarus_saved_dir()
            save_root.mkdir(parents=True, exist_ok=True)
            restored: list[str] = []
            for source in components:
                target = save_root / source.name
                self.remove_existing_save_component(target, save_root)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
                restored.append(source.name)
            self.log(f"Restored Icarus save backup {backup} to {save_root} ({', '.join(restored)})")
            self.status_var.set(f"Restored save backup: {backup.name}")
            self.refresh_save_backup_list()
            messagebox.showinfo(APP_NAME, f"Restored save backup:\n{backup.name}", parent=self)
        except Exception as error:
            self.show_error("Save restore failed", error)

    def open_save_backup_folder(self) -> None:
        try:
            self.save_backups_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(self.save_backups_dir)
        except Exception as error:
            self.show_error("Open save backup folder failed", error)

    def player_data_root(self) -> Path:
        return self.icarus_saved_dir() / "PlayerData"

    def read_json_file(self, path: Path, fallback: Any = None) -> Any:
        if not path.is_file():
            return fallback
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def write_json_file(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")

    def item_row_name(self, item: dict[str, Any]) -> str:
        static = item.get("ItemStaticData", {})
        if isinstance(static, dict):
            row = static.get("RowName")
            if row:
                return str(row)
        return str(item.get("RowName") or item.get("Name") or "UnknownItem")

    def item_stack_value(self, item: dict[str, Any]) -> Any:
        dynamic = item.get("ItemDynamicData", [])
        if isinstance(dynamic, list):
            for entry in dynamic:
                if isinstance(entry, dict) and entry.get("PropertyType") in {"ItemableStack", "Stack", "StackCount"}:
                    return entry.get("Value", 1)
        return 1

    def reset_item_guid(self, item: dict[str, Any]) -> dict[str, Any]:
        cloned = json.loads(json.dumps(item))
        if isinstance(cloned, dict) and "DatabaseGUID" in cloned:
            cloned["DatabaseGUID"] = uuid4().hex.upper()
        return cloned

    def load_vault(self) -> dict[str, Any]:
        if not self.vault_path.is_file():
            return {"schema": 1, "items": []}
        data = self.read_json_file(self.vault_path, {"schema": 1, "items": []})
        if not isinstance(data, dict):
            return {"schema": 1, "items": []}
        data.setdefault("schema", 1)
        data.setdefault("items", [])
        if not isinstance(data["items"], list):
            data["items"] = []
        return data

    def save_vault(self, data: dict[str, Any]) -> None:
        data["updated"] = datetime.now().isoformat(timespec="seconds")
        self.write_json_file(self.vault_path, data)

    def append_vault_ledger(self, event: dict[str, Any]) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        event = {"time": datetime.now().isoformat(timespec="seconds"), **event}
        with self.vault_ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def acquire_vault_lock(self) -> Any:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.vault_dir / "vault.lock"
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise RuntimeError(f"Transfer vault is locked by another operation: {lock_path}") from error
        os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode("utf-8"))
        return fd, lock_path

    def release_vault_lock(self, lock: Any) -> None:
        fd, lock_path = lock
        try:
            os.close(fd)
        finally:
            Path(lock_path).unlink(missing_ok=True)

    def scan_meta_inventory_sources(self, steam_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        target = {
            "label": f"{steam_dir.name} - MetaInventory",
            "steam_id": steam_dir.name,
            "kind": "meta_inventory",
            "path": str(steam_dir / "MetaInventory.json"),
        }
        inventory = self.read_json_file(steam_dir / "MetaInventory.json", {"InventoryID": "MetaInventoryID_Main", "Items": []})
        items = inventory.get("Items", []) if isinstance(inventory, dict) else []
        if isinstance(items, list):
            for index, item in enumerate(items):
                if isinstance(item, dict):
                    sources.append(
                        {
                            "transferable": True,
                            "kind": "meta_inventory",
                            "path": str(steam_dir / "MetaInventory.json"),
                            "steam_id": steam_dir.name,
                            "index": index,
                            "item": item,
                            "label": f"{steam_dir.name} | MetaInventory | {self.item_row_name(item)} x{self.item_stack_value(item)}",
                        }
                    )
        return sources, target

    def scan_loadout_sources(self, steam_dir: Path) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        path = steam_dir / "Loadout" / "Loadouts.json"
        data = self.read_json_file(path, {})
        loadouts = data.get("Loadouts", []) if isinstance(data, dict) else []
        if not isinstance(loadouts, list):
            return sources
        for loadout_index, loadout in enumerate(loadouts):
            if not isinstance(loadout, dict):
                continue
            items = loadout.get("MetaItems", [])
            if not isinstance(items, list):
                continue
            for item_index, item in enumerate(items):
                if isinstance(item, dict):
                    sources.append(
                        {
                            "transferable": True,
                            "kind": "loadout_meta_item",
                            "path": str(path),
                            "steam_id": steam_dir.name,
                            "loadout_index": loadout_index,
                            "index": item_index,
                            "item": item,
                            "label": f"{steam_dir.name} | Loadout {loadout_index} | {self.item_row_name(item)} x{self.item_stack_value(item)}",
                        }
                    )
        return sources

    def prospect_blob_summary(self, prospect_path: Path) -> tuple[bool, int, int]:
        try:
            data = self.read_json_file(prospect_path, {})
            blob = data.get("ProspectBlob", {}).get("BinaryBlob", "") if isinstance(data, dict) else ""
            if not blob:
                return False, 0, 0
            decompressed = zlib.decompress(base64.b64decode(blob))
            item_hits = decompressed.count(b"ItemStaticData\x00")
            inventory_hits = decompressed.count(b"SavedInventories") + decompressed.count(b"InventorySaveData")
            return True, item_hits, inventory_hits
        except Exception:
            return False, 0, 0

    def plausible_unreal_name(self, value: str) -> bool:
        if not value or len(value) > 160:
            return False
        return re.fullmatch(r"[A-Za-z0-9_./:-]+", value) is not None

    def unreal_string_near(self, data: bytes, start: int, max_scan: int = 24) -> str | None:
        for shift in range(max_scan):
            cursor = start + shift
            if cursor + 4 > len(data):
                return None
            length = int.from_bytes(data[cursor:cursor + 4], "little", signed=True)
            if 1 <= length <= 160 and cursor + 4 + length <= len(data):
                raw = data[cursor + 4:cursor + 4 + length]
                if raw.endswith(b"\x00"):
                    try:
                        value = raw[:-1].decode("utf-8")
                    except UnicodeDecodeError:
                        value = ""
                    if self.plausible_unreal_name(value):
                        return value
            if -160 <= length < 0:
                char_count = abs(length)
                byte_count = char_count * 2
                if cursor + 4 + byte_count <= len(data):
                    raw = data[cursor + 4:cursor + 4 + byte_count]
                    try:
                        value = raw.decode("utf-16-le", errors="strict").rstrip("\x00")
                    except UnicodeDecodeError:
                        value = ""
                    if self.plausible_unreal_name(value):
                        return value
        return None

    def unreal_property_string_after(self, data: bytes, property_name_end: int) -> str | None:
        try:
            cursor = property_name_end
            if cursor + 12 > len(data):
                return None
            return self.unreal_string_near(data, cursor)
        except Exception:
            return None

    def unreal_name_property_after_key(self, data: bytes, key: bytes, start: int = 0) -> tuple[str | None, int]:
        key_pos = data.find(key, start)
        if key_pos < 0:
            return None, -1
        prop = b"NameProperty\x00"
        prop_pos = data.find(prop, key_pos, key_pos + 256)
        if prop_pos < 0:
            return None, key_pos
        return self.unreal_property_string_after(data, prop_pos + len(prop)), key_pos

    def nearest_blob_actor_name(self, data: bytes, item_pos: int) -> str:
        search_start = max(0, item_pos - 12000)
        chunk = data[search_start:item_pos]
        marker = b"ObjectFName\x00"
        rel = chunk.rfind(marker)
        if rel < 0:
            return "Unknown saved inventory"
        name, _pos = self.unreal_name_property_after_key(data, marker, search_start + rel)
        return name or "Unknown saved inventory"

    def extract_prospect_blob_items(self, prospect_path: Path) -> list[dict[str, Any]]:
        data = self.read_json_file(prospect_path, {})
        blob = data.get("ProspectBlob", {}).get("BinaryBlob", "") if isinstance(data, dict) else ""
        if not blob:
            return []
        decompressed = zlib.decompress(base64.b64decode(blob))
        items: list[dict[str, Any]] = []
        cursor = 0
        marker = b"ItemStaticData\x00"
        while True:
            item_pos = decompressed.find(marker, cursor)
            if item_pos < 0:
                break
            row_name, _row_pos = self.unreal_name_property_after_key(decompressed, marker, item_pos)
            if row_name and row_name != "None":
                actor_name = self.nearest_blob_actor_name(decompressed, item_pos)
                items.append(
                    {
                        "row_name": row_name,
                        "actor_name": actor_name,
                        "offset": item_pos,
                    }
                )
            cursor = item_pos + len(marker)
        return items

    def scan_prospect_sources(self, steam_dir: Path) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        prospects_dir = steam_dir / "Prospects"
        if not prospects_dir.is_dir():
            return sources
        for prospect_path in sorted(prospects_dir.glob("*.json")):
            if ".backup" in prospect_path.name:
                continue
            data = self.read_json_file(prospect_path, {})
            info = data.get("ProspectInfo", {}) if isinstance(data, dict) else {}
            prospect_id = info.get("ProspectID", prospect_path.stem) if isinstance(info, dict) else prospect_path.stem
            decoded, item_hits, inventory_hits = self.prospect_blob_summary(prospect_path)
            sources.append(
                {
                    "transferable": False,
                    "kind": "prospect_blob",
                    "path": str(prospect_path),
                    "steam_id": steam_dir.name,
                    "label": (
                        f"{steam_dir.name} | Prospect {prospect_id} | live-world inventory blob "
                        f"detected={decoded} itemRows={item_hits} inventoryMarkers={inventory_hits} | decoded view-only"
                    ),
                }
            )
            try:
                blob_items = self.extract_prospect_blob_items(prospect_path)
            except Exception:
                blob_items = []
            for index, item in enumerate(blob_items):
                sources.append(
                    {
                        "transferable": False,
                        "kind": "prospect_blob_item",
                        "path": str(prospect_path),
                        "steam_id": steam_dir.name,
                        "item_index": index,
                        "row_name": item["row_name"],
                        "actor_name": item["actor_name"],
                        "offset": item["offset"],
                        "label": (
                            f"{steam_dir.name} | Prospect {prospect_id} | {item['actor_name']} | "
                            f"{item['row_name']} | blob item offset {item['offset']} | view-only"
                        ),
                    }
                )
            members = info.get("AssociatedMembers", []) if isinstance(info, dict) else []
            if isinstance(members, list):
                for member in members:
                    if isinstance(member, dict):
                        sources.append(
                            {
                                "transferable": False,
                                "kind": "prospect_member",
                                "path": str(prospect_path),
                                "steam_id": str(member.get("UserID", steam_dir.name)),
                                "label": (
                                    f"{prospect_id} | player {member.get('CharacterName', '?')} "
                                    f"({member.get('UserID', '?')}) slot {member.get('ChrSlot', '?')} | member detected"
                                ),
                            }
                        )
        return sources

    def scan_transfer_sources(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        root = self.player_data_root()
        sources: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []
        if not root.is_dir():
            return sources, targets
        for steam_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            meta_sources, target = self.scan_meta_inventory_sources(steam_dir)
            sources.extend(meta_sources)
            targets.append(target)
            sources.extend(self.scan_loadout_sources(steam_dir))
            sources.extend(self.scan_prospect_sources(steam_dir))
        return sources, targets

    def refresh_transfer_vault(self) -> None:
        try:
            self.vault_sources, self.vault_targets = self.scan_transfer_sources()
            self.vault_items = self.load_vault().get("items", [])
            if self.vault_source_listbox is not None:
                self.vault_source_listbox.delete(0, tk.END)
                for source in self.vault_sources:
                    prefix = "MOVE" if source.get("transferable") else "SCAN"
                    self.vault_source_listbox.insert(tk.END, f"{prefix} | {source.get('label', '')}")
            if self.vault_listbox is not None:
                self.vault_listbox.delete(0, tk.END)
                for item in self.vault_items:
                    item_data = item.get("item", {}) if isinstance(item, dict) else {}
                    self.vault_listbox.insert(
                        tk.END,
                        f"{item.get('id', '?')} | {self.item_row_name(item_data)} x{self.item_stack_value(item_data)} | from {item.get('source_label', '')}",
                    )
            target_labels = [target["label"] for target in self.vault_targets]
            if self.vault_target_combo is not None:
                self.vault_target_combo.configure(values=target_labels)
            if target_labels and self.vault_target_var.get() not in target_labels:
                self.vault_target_var.set(target_labels[0])
            transferable = sum(1 for source in self.vault_sources if source.get("transferable"))
            self.vault_summary_var.set(
                f"Players scanned: {len(self.vault_targets)}    Move-ready JSON items: {transferable}    "
                f"Vault items: {len(self.vault_items)}    Vault folder: {self.vault_dir}"
            )
        except Exception as error:
            self.show_error("Transfer vault scan failed", error)

    def selected_vault_source(self) -> dict[str, Any]:
        if self.vault_source_listbox is None:
            raise RuntimeError("Transfer source list is not available")
        selection = self.vault_source_listbox.curselection()
        if not selection:
            raise RuntimeError("Select a source item first")
        source = self.vault_sources[int(selection[0])]
        if not source.get("transferable"):
            raise RuntimeError("That entry is scan-only. Live prospect blob item movement needs the verified binary inventory writer first.")
        return source

    def selected_vault_item(self) -> dict[str, Any]:
        if self.vault_listbox is None:
            raise RuntimeError("Vault item list is not available")
        selection = self.vault_listbox.curselection()
        if not selection:
            raise RuntimeError("Select a vault item first")
        return self.vault_items[int(selection[0])]

    def selected_vault_target(self) -> dict[str, Any]:
        label = self.vault_target_var.get()
        for target in self.vault_targets:
            if target.get("label") == label:
                return target
        raise RuntimeError("Select a restore target first")

    def remove_source_item(self, source: dict[str, Any]) -> dict[str, Any]:
        path = Path(source["path"])
        data = self.read_json_file(path, {})
        if source["kind"] == "meta_inventory":
            items = data.get("Items", [])
            index = int(source["index"])
            if not isinstance(items, list) or index >= len(items):
                raise RuntimeError("Source inventory changed. Rescan before moving.")
            item = items.pop(index)
            self.write_json_file(path, data)
            return item
        if source["kind"] == "loadout_meta_item":
            loadouts = data.get("Loadouts", [])
            loadout_index = int(source["loadout_index"])
            item_index = int(source["index"])
            items = loadouts[loadout_index].get("MetaItems", [])
            if not isinstance(items, list) or item_index >= len(items):
                raise RuntimeError("Source loadout changed. Rescan before moving.")
            item = items.pop(item_index)
            self.write_json_file(path, data)
            return item
        raise RuntimeError(f"Unsupported source kind: {source['kind']}")

    def vault_export_selected(self) -> None:
        lock = None
        try:
            processes = self.running_icarus_processes()
            if processes:
                raise RuntimeError("Close Icarus before moving items into the transfer vault. Running processes: " + ", ".join(processes))
            source = self.selected_vault_source()
            if not messagebox.askyesno(
                APP_NAME,
                "Move this item into the shared transfer vault?\n\n"
                "The app will create a save backup first, remove the item from the source JSON inventory, and write a ledger entry.",
                parent=self,
            ):
                return
            lock = self.acquire_vault_lock()
            self.create_save_backup("pre_vault_export", silent=True)
            item = self.remove_source_item(source)
            vault = self.load_vault()
            vault_item = {
                "id": uuid4().hex,
                "stored": datetime.now().isoformat(timespec="seconds"),
                "source_label": source.get("label", ""),
                "source": {key: value for key, value in source.items() if key != "item"},
                "item": item,
            }
            vault["items"].append(vault_item)
            self.save_vault(vault)
            self.append_vault_ledger({"action": "export", "vault_id": vault_item["id"], "source": source.get("label", ""), "item": self.item_row_name(item)})
            self.status_var.set(f"Moved item to transfer vault: {self.item_row_name(item)}")
            self.refresh_transfer_vault()
        except Exception as error:
            self.show_error("Transfer vault export failed", error)
        finally:
            if lock is not None:
                self.release_vault_lock(lock)

    def add_item_to_target_inventory(self, target: dict[str, Any], item: dict[str, Any]) -> None:
        path = Path(target["path"])
        data = self.read_json_file(path, {"InventoryID": "MetaInventoryID_Main", "Items": []})
        if not isinstance(data, dict):
            raise RuntimeError(f"Target inventory is not a JSON object: {path}")
        data.setdefault("InventoryID", "MetaInventoryID_Main")
        data.setdefault("Items", [])
        if not isinstance(data["Items"], list):
            raise RuntimeError(f"Target inventory Items field is not a list: {path}")
        data["Items"].append(self.reset_item_guid(item))
        self.write_json_file(path, data)
        verify = self.read_json_file(path, {})
        verify_items = verify.get("Items", []) if isinstance(verify, dict) else []
        if not isinstance(verify_items, list) or not verify_items:
            raise RuntimeError("Target inventory verification failed after write")

    def vault_import_selected(self) -> None:
        lock = None
        try:
            processes = self.running_icarus_processes()
            if processes:
                raise RuntimeError("Close Icarus before restoring vault items. Running processes: " + ", ".join(processes))
            vault_item = self.selected_vault_item()
            target = self.selected_vault_target()
            item = vault_item.get("item", {})
            if not isinstance(item, dict):
                raise RuntimeError("Vault item is malformed")
            if not messagebox.askyesno(
                APP_NAME,
                "Restore this vault item to the selected player's MetaInventory?\n\n"
                "The app will create a save backup first, add the item, remove it from the vault, and write a ledger entry.",
                parent=self,
            ):
                return
            lock = self.acquire_vault_lock()
            self.create_save_backup("pre_vault_import", silent=True)
            vault = self.load_vault()
            items = vault.get("items", [])
            vault_id = vault_item.get("id")
            match_index = next((index for index, entry in enumerate(items) if isinstance(entry, dict) and entry.get("id") == vault_id), None)
            if match_index is None:
                raise RuntimeError("Vault item changed. Rescan before restoring.")
            self.add_item_to_target_inventory(target, item)
            items.pop(match_index)
            self.save_vault(vault)
            self.append_vault_ledger({"action": "import", "vault_id": vault_id, "target": target.get("label", ""), "item": self.item_row_name(item)})
            self.status_var.set(f"Restored vault item: {self.item_row_name(item)}")
            self.refresh_transfer_vault()
        except Exception as error:
            self.show_error("Transfer vault import failed", error)
        finally:
            if lock is not None:
                self.release_vault_lock(lock)

    def open_transfer_vault_folder(self) -> None:
        try:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(self.vault_dir)
        except Exception as error:
            self.show_error("Open transfer vault folder failed", error)

    def runtime_mods_root(self, win64_dir: Path) -> Path:
        modern = win64_dir / "ue4ss"
        if modern.is_dir():
            return modern / "Mods"
        return win64_dir / "Mods"

    def decimal_ini_value(self, value: Decimal) -> str:
        normalized = value.normalize()
        if normalized == normalized.to_integral_value():
            return str(int(normalized))
        return format(normalized, "f").rstrip("0").rstrip(".")

    def option_manifest(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "backend": "ue4ss-cpp-dll",
            "tableMultipliers": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "category": spec.category,
                    "files": list(spec.files),
                    "kind": spec.kind,
                    "fields": list(spec.fields),
                    "direction": spec.direction,
                    "result": spec.result,
                    "minimumResult": spec.minimum_result,
                    "positiveOnly": spec.positive_only,
                    "greaterThanOne": spec.greater_than_one,
                    "rowNames": list(spec.row_names),
                    "excludeNameSuffixes": list(spec.exclude_name_suffixes),
                }
                for spec in SETTINGS
            ],
            "nativeGroups": [
                {
                    "key": group.key,
                    "label": group.label,
                    "category": group.category,
                    "file": group.file,
                    "field": group.field,
                    "kind": group.kind,
                    "ranges": [list(pair) for pair in group.ranges],
                    "result": group.result,
                    "minimumResult": group.minimum_result,
                    "excludeNamePatterns": list(group.exclude_name_patterns),
                }
                for group in NATIVE_GROUPS
            ],
            "directSettings": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "category": spec.category,
                    "file": spec.file,
                    "kind": spec.kind,
                    "default": spec.default,
                    "rowName": spec.row_name,
                    "field": spec.field,
                    "currency": spec.currency,
                    "compatIniKey": DIRECT_INI_KEYS.get(spec.key, ""),
                }
                for spec in DIRECT_SETTINGS
            ],
            "growthCurves": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "category": spec.category,
                    "asset": spec.asset,
                    "compatIniKeys": list(CURVE_INI_KEYS[spec.key]),
                    "checks": [list(check) for check in spec.checks],
                }
                for spec in CURVE_SETTINGS
            ],
            "runtimeSettings": [
                {
                    "key": spec.key,
                    "label": spec.label,
                    "category": spec.category,
                    "default": spec.default,
                    "minimum": str(spec.minimum),
                    "maximum": str(spec.maximum),
                    "compatIniKey": RUNTIME_INI_KEYS.get(spec.key, ""),
                }
                for spec in RUNTIME_SETTINGS
            ],
        }

    def write_option_manifest(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.option_manifest(), indent=4) + "\n", encoding="utf-8")
        return target

    def unified_ini_text(self) -> str:
        values = self.values()
        native_values = self.native_group_values()
        direct_values = self.direct_values()
        curve_values = self.curve_values()
        runtime_values = self.runtime_values()
        lines: list[str] = [
            "; Generated by Icarus Balance Configurator.",
            "; This is the single editable source of truth for this profile.",
            "; The UE4SS C++ DLL reads this file. The Python app is only the editor/installer.",
            "",
            "[metadata]",
            f"appVersion = {APP_VERSION}",
            f"modName = {self.safe_mod_name()}",
            "schema = 1",
            "",
            "[table_multipliers]",
            "; One-to-one with the original table multiplier controls.",
        ]
        for spec in SETTINGS:
            lines.append(f"; {spec.label}")
            lines.append(f"{spec.key} = {self.decimal_ini_value(values[spec.key])}")
        lines.extend(["", "[native_groups]", "; One-to-one with the grouped range controls."])
        for group in NATIVE_GROUPS:
            lines.append(f"; {group.label}: {group.file} -> {group.field}")
            for index, ((minimum, maximum), multiplier) in enumerate(zip(group.ranges, native_values[group.key]), start=1):
                lines.append(f"; {group.key}{index}: {minimum}-{maximum}")
                lines.append(f"{group.key}{index} = {self.decimal_ini_value(multiplier)}")
            if group.exclude_name_patterns:
                lines.append(f"{group.key}Excluded = [{','.join(group.exclude_name_patterns)}]")
            lines.append("")
        lines.extend(["[direct_settings]", "; One-to-one with direct table edits and fixed-value controls."])
        for spec in DIRECT_SETTINGS:
            lines.append(f"; {spec.label}")
            lines.append(f"{spec.key} = {self.decimal_ini_value(direct_values[spec.key])}")
            ini_key = DIRECT_INI_KEYS.get(spec.key)
            if ini_key:
                lines.append(f"{ini_key} = {self.decimal_ini_value(direct_values[spec.key])}")
        lines.extend(["", "[growth_curves]", "; One-to-one with cooked growth curve controls."])
        for spec in CURVE_SETTINGS:
            lines.append(f"; {spec.label}")
            lines.append(f"{spec.key} = {self.decimal_ini_value(curve_values[spec.key])}")
            for ini_key in CURVE_INI_KEYS[spec.key]:
                lines.append(f"{ini_key} = {self.decimal_ini_value(curve_values[spec.key])}")
        lines.extend(["", "[runtime]", "; Runtime companion settings."])
        for spec in RUNTIME_SETTINGS:
            lines.append(f"; {spec.label}")
            lines.append(f"{spec.key} = {self.decimal_ini_value(runtime_values[spec.key])}")
            lines.append(f"{RUNTIME_INI_KEYS[spec.key]} = {self.decimal_ini_value(runtime_values[spec.key])}")
        lines.extend(
            [
                "",
                "[debug_validation]",
                "; Opt-in runtime validation harness. Leave disabled for normal play.",
                "; When enabled with forceAllSupported, the DLL forces supported settings to test values,",
                "; captures each default value before mutation, computes expected math, writes, and reads back.",
                "enabled = false",
                "forceAllSupported = false",
                "testMultiplier = 2",
                "directAmount = 100",
                "boolValue = true",
                "includeRiskyArrayEdits = false",
                "logEachMathCheck = false",
            ]
        )
        lines.extend(["", "[notes]", "backend = ue4ss-cpp-dll", "ue4ssRuntime = true", ""])
        return "\n".join(lines)

    def write_unified_ini(self, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.unified_ini_text(), encoding="utf-8")
        return target

    def save_ini(self, silent: bool = False) -> Path | None:
        try:
            initial = f"{self.safe_mod_name()}.ini"
            if silent:
                self.builds_dir.mkdir(parents=True, exist_ok=True)
                target = self.builds_dir / initial
            else:
                self.builds_dir.mkdir(parents=True, exist_ok=True)
                selected = filedialog.asksaveasfilename(
                    parent=self,
                    title="Save unified mod INI",
                    initialdir=self.builds_dir,
                    initialfile=initial,
                    defaultextension=".ini",
                    filetypes=(("INI settings", "*.ini"),),
                )
                if not selected:
                    return None
                target = Path(selected)
            written = self.write_unified_ini(target)
            self.status_var.set(f"Saved unified INI: {written}")
            self.log(f"Saved unified INI {written}")
            if not silent:
                messagebox.showinfo(APP_NAME, f"Saved unified INI:\n{written}", parent=self)
            return written
        except Exception as error:
            self.show_error("Save unified INI failed", error)
            return None

    def apply_preset(self, name: str) -> None:
        preset = PRESETS.get(name, {})
        for spec in SETTINGS:
            self.setting_vars[spec.key].set(display_multiplier(preset.get(spec.key, 1)))
        group_preset = INI_PRESETS.get(name, INI_PRESETS["Vanilla"])["groups"]
        for group in NATIVE_GROUPS:
            value = display_multiplier(group_preset.get(group.key, 1))
            for variable in self.native_group_vars[group.key]:
                variable.set(value)
            self.refresh_group_master(group.key)
        direct_presets = {
            "Vanilla": {},
        }
        selected_direct = direct_presets.get(name, {})
        for spec in DIRECT_SETTINGS:
            value = selected_direct.get(spec.key, spec.default)
            self.direct_vars[spec.key].set(display_multiplier(value) if is_direct_multiplier(spec) else value)
        curve_presets = {
            "Vanilla": {},
        }
        selected_curves = curve_presets.get(name, {})
        for spec in CURVE_SETTINGS:
            self.curve_vars[spec.key].set(display_multiplier(selected_curves.get(spec.key, "1")))
        runtime_presets = {
            "Vanilla": {},
        }
        selected_runtime = runtime_presets.get(name, {})
        for spec in RUNTIME_SETTINGS:
            self.runtime_vars[spec.key].set(display_multiplier(selected_runtime.get(spec.key, spec.default)))
        self.update_summary()

    def update_summary(self) -> None:
        try:
            values = self.values()
            table_active = sum(1 for spec in SETTINGS if values[spec.key] != 1)
            native_active = sum(
                1
                for group_values in self.native_group_values().values()
                for value in group_values
                if value != 1
            )
            direct_active = sum(
                1 for spec in DIRECT_SETTINGS
                if self.direct_values()[spec.key] != Decimal(spec.default)
            )
            curve_active = sum(1 for value in self.curve_values().values() if value != 1)
            runtime_active = sum(
                1 for spec in RUNTIME_SETTINGS
                if self.runtime_values()[spec.key] != Decimal(spec.default)
            )
            self.summary_var.set(
                f"{table_active} table systems - {native_active} native ranges - "
                f"{direct_active} direct native settings - {curve_active} growth curves - "
                f"{runtime_active} runtime controls"
            )
        except ValueError as error:
            self.summary_var.set(str(error))

    def runtime_selected(self) -> bool:
        values = self.runtime_values()
        return any(values[spec.key] != Decimal(spec.default) for spec in RUNTIME_SETTINGS)

    def configuration_selected(self) -> bool:
        return any(value != 1 for value in self.values().values()) or any(
            value != 1
            for group_values in self.native_group_values().values()
            for value in group_values
        ) or any(self.direct_values()[spec.key] != Decimal(spec.default) for spec in DIRECT_SETTINGS) or any(
            value != 1 for value in self.curve_values().values()
        ) or self.runtime_selected()

    def write_runtime_mod_package(self, target_root: Path) -> Path:
        values = self.runtime_values()
        mod_name = RUNTIME_MOD_FOLDER
        mod_dir = target_root / mod_name
        dlls_dir = mod_dir / "dlls"
        dll_candidates = (
            self.app_dir / "main.dll",
            self.app_dir / "tools" / "dll" / "out" / "main.dll",
            self.app_dir / "builds" / RUNTIME_MOD_FOLDER / "dlls" / "main.dll",
        )
        source_dll = next((candidate for candidate in dll_candidates if candidate.is_file()), dll_candidates[0])
        if not source_dll.is_file():
            raise FileNotFoundError(
                "DLL-only package requires a prebuilt UE4SS C++ DLL. "
                "Run tools\\scripts\\Build DLL.bat first."
            )
        if mod_dir.exists():
            shutil.rmtree(mod_dir)
        dlls_dir.mkdir(parents=True, exist_ok=True)
        (mod_dir / "runtime.log").unlink(missing_ok=True)
        (mod_dir / "runtime_dll.log").unlink(missing_ok=True)
        ini_path = self.write_unified_ini(mod_dir / RUNTIME_INI_NAME)
        manifest_path = self.write_option_manifest(mod_dir / "option_manifest.json")
        config = {
            "air_control": float(values["air_control"]),
            "camera_tilt": float(values["camera_tilt"]),
            "ini": ini_path.name,
            "manifest": manifest_path.name,
            "dll": "dlls/main.dll",
        }
        (mod_dir / "runtime_config.json").write_text(json.dumps(config, indent=4) + "\n", encoding="utf-8")
        shutil.copy2(source_dll, dlls_dir / "main.dll")
        (mod_dir / "enabled.txt").write_text("1\n", encoding="utf-8")
        return mod_dir

    def find_ue4ss_zip_asset(self) -> tuple[str, str]:
        request = urllib.request.Request(UE4SS_RELEASES_API, headers={"User-Agent": APP_NAME.replace(" ", "-")})
        with urllib.request.urlopen(request, timeout=30) as response:
            releases = json.loads(response.read().decode("utf-8"))
        for release in releases:
            if release.get("prerelease"):
                continue
            for asset in release.get("assets", []):
                name = str(asset.get("name", ""))
                url = str(asset.get("browser_download_url", ""))
                if name.startswith("UE4SS_") and name.endswith(".zip") and url:
                    return name, url
        raise FileNotFoundError("Could not find a stable UE4SS zip asset on GitHub")

    def ensure_ue4ss_loader(self, win64_dir: Path) -> None:
        modern = win64_dir / "ue4ss"
        if (win64_dir / "dwmapi.dll").is_file() and ((modern / "UE4SS.dll").is_file() or (win64_dir / "UE4SS.dll").is_file()):
            self.log(f"UE4SS loader already present in {win64_dir}")
            return
        asset_name, url = self.find_ue4ss_zip_asset()
        self.log(f"Installing UE4SS loader {asset_name} from {url}")
        tools_dir = self.app_dir / "tools" / "ue4ss"
        tools_dir.mkdir(parents=True, exist_ok=True)
        archive = tools_dir / asset_name
        self.status_var.set(f"Downloading {asset_name}...")
        self.update_idletasks()
        urllib.request.urlretrieve(url, archive)
        extract_dir = tools_dir / asset_name.removesuffix(".zip")
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(extract_dir)

        source_root = extract_dir
        nested = [path for path in extract_dir.iterdir() if path.is_dir()]
        if len(nested) == 1 and not any((extract_dir / name).exists() for name in ("dwmapi.dll", "UE4SS.dll", "ue4ss")):
            source_root = nested[0]

        copied = 0
        for item in source_root.iterdir():
            target = win64_dir / item.name
            if item.is_dir():
                if target.exists():
                    shutil.move(str(target), str(self.backup_existing_runtime_file(target)))
                shutil.copytree(item, target)
                copied += 1
            elif item.is_file():
                if target.exists():
                    shutil.move(str(target), str(self.backup_existing_runtime_file(target)))
                shutil.copy2(item, target)
                copied += 1
        if copied == 0 or not (win64_dir / "dwmapi.dll").is_file():
            raise RuntimeError(f"{asset_name} did not install a usable UE4SS loader")
        archive.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        self.log(f"Installed UE4SS loader to {win64_dir}")

    def ensure_matching_ue4ss_runtime(self, win64_dir: Path) -> None:
        bundled = next((candidate for candidate in BUNDLED_UE4SS_DLLS if candidate.is_file()), None)
        if bundled is None:
            return
        target = win64_dir / "UE4SS.dll"
        if target.is_file() and filecmp.cmp(bundled, target, shallow=False):
            self.log(f"Matching UE4SS runtime already installed in {win64_dir}")
            return
        processes = self.running_icarus_processes()
        if processes:
            raise RuntimeError("Fully close Icarus before replacing UE4SS.dll with the matching DLL runtime")
        if target.exists():
            shutil.move(str(target), str(self.backup_existing_runtime_file(target)))
        shutil.copy2(bundled, target)
        self.log(f"Installed matching UE4SS runtime DLL to {target}")

    def enable_runtime_mod_only(self, mods_root: Path, mod_name: str) -> Path:
        mods_txt = mods_root / "mods.txt"
        existing = mods_txt.read_text(encoding="utf-8", errors="ignore").splitlines() if mods_txt.is_file() else []
        output: list[str] = []
        found_runtime = False
        for entry in existing:
            stripped = entry.strip()
            if not stripped or stripped.startswith(";") or ":" not in stripped:
                output.append(entry)
                continue
            key = stripped.split(":", 1)[0].strip().lstrip("\ufeff")
            if key.casefold() == mod_name.casefold():
                output.append(f"{mod_name} : 1")
                found_runtime = True
            elif key in MOD_FOLDERS_TO_CLEAN:
                continue
            else:
                output.append(entry)
        if not found_runtime:
            output.append(f"{mod_name} : 1")
        mods_txt.parent.mkdir(parents=True, exist_ok=True)
        mods_txt.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
        return mods_txt

    def clean_stale_runtime_mods(self, mods_root: Path) -> None:
        for folder_name in sorted(MOD_FOLDERS_TO_CLEAN):
            target = mods_root / folder_name
            if target.exists():
                shutil.move(str(target), str(self.backup_existing_runtime_file(target)))
                self.log(f"Moved old runtime folder to backup: {target}")

    def reset_installed_mod(self) -> None:
        try:
            if not messagebox.askyesno(
                APP_NAME,
                "Remove installed Configuration_Mod runtime files and clean generated local files?",
                parent=self,
            ):
                return
            for target in (self.backups_dir, self.runtime_dir, self.builds_dir):
                if target.exists():
                    shutil.rmtree(target)
                    self.log(f"Removed local folder: {target}")
            for cache in self.app_dir.rglob("__pycache__"):
                shutil.rmtree(cache, ignore_errors=True)
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            win64_dir = self.game_win64_dir(prompt=True)
            if win64_dir.is_dir():
                mods_roots = [win64_dir / "Mods", win64_dir / "ue4ss" / "Mods"]
                names_to_remove = {RUNTIME_MOD_FOLDER} | UE4SS_BUILTIN_MODS_TO_DISABLE | OLD_RUNTIME_MOD_NAMES
                for root in mods_roots:
                    for name in names_to_remove:
                        target = root / name
                        if target.exists():
                            if target.is_dir():
                                shutil.rmtree(target)
                            else:
                                target.unlink()
                            self.log(f"Removed installed runtime path: {target}")
                    mods_txt = root / "mods.txt"
                    if mods_txt.is_file():
                        lines = mods_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
                        filtered = [
                            line for line in lines
                            if not any(line.strip().casefold().startswith(f"{name.casefold()} :") for name in names_to_remove)
                        ]
                        if filtered:
                            mods_txt.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
                            self.log(f"Cleaned mod load order: {mods_txt}")
                        else:
                            mods_txt.unlink()
                            self.log(f"Removed empty mod load order: {mods_txt}")
                ue4ss_log = win64_dir / "UE4SS.log"
                if ue4ss_log.exists():
                    ue4ss_log.unlink()
                    self.log(f"Removed UE4SS log: {ue4ss_log}")
            self.status_var.set("Reset complete. Runtime mod files were removed where found.")
            self.refresh_console()
            messagebox.showinfo(APP_NAME, "Reset complete.", parent=self)
        except Exception as error:
            self.show_error("Reset failed", error)

    def install_runtime_support(self) -> None:
        try:
            if not self.configuration_selected():
                message = "Vanilla Defaults is selected. Choose Premade_Configuration or a saved/imported profile before installing runtime changes."
                self.status_var.set(message)
                self.log("Install skipped: " + message)
                self.refresh_console()
                messagebox.showinfo(APP_NAME, message, parent=self)
                return
            self.auto_backup_saves_before_apply()
            win64_dir = self.game_win64_dir(prompt=True)
            if not win64_dir.is_dir():
                raise FileNotFoundError(f"Could not find Icarus Win64 folder: {win64_dir}")
            self.ensure_ue4ss_loader(win64_dir)
            self.ensure_matching_ue4ss_runtime(win64_dir)
            ue4ss_log = win64_dir / "UE4SS.log"
            if ue4ss_log.exists():
                shutil.move(str(ue4ss_log), str(self.backup_existing_runtime_file(ue4ss_log)))
                self.log(f"Moved old UE4SS log to backup: {ue4ss_log}")
            mods_root = self.runtime_mods_root(win64_dir)
            self.clean_stale_runtime_mods(mods_root)
            runtime_mod = self.write_runtime_mod_package(mods_root)
            self.enable_runtime_mod_only(mods_root, runtime_mod.name)
            self.log(f"Installed runtime mod {runtime_mod} with {self.runtime_values()}")
            self.status_var.set(f"Installed UE4SS runtime mod files: {runtime_mod}")
            processes = self.running_icarus_processes()
            if processes:
                self.log("WARNING: Icarus is running; restart required before runtime changes can apply: " + ", ".join(processes))
            self.refresh_console()
            restart_note = (
                "\n\nIcarus is currently running. Fully close and restart it before testing these runtime settings."
                if processes
                else "\n\nLaunch Icarus after applying the C++ DLL mod."
            )
            messagebox.showinfo(
                "C++ DLL mod installed",
                f"Installed C++ DLL mod:\n{runtime_mod}{restart_note}",
                parent=self,
            )
        except Exception as error:
            self.show_error("Runtime support install failed", error)

    def build_runtime_mod_files(self) -> None:
        try:
            if not self.developer_tools_available():
                raise RuntimeError("Developer build files are not included in this player release")
            if not self.configuration_selected():
                message = "Vanilla Defaults is selected. Choose Premade_Configuration or a saved/imported profile before building runtime files."
                self.status_var.set(message)
                self.log("Build skipped: " + message)
                self.refresh_console()
                messagebox.showinfo(APP_NAME, message, parent=self)
                return
            subprocess.run(
                [sys.executable, str(self.app_dir / "tools" / "scripts" / "build_dll.py")],
                cwd=str(self.app_dir),
                check=True,
            )
            self.builds_dir.mkdir(parents=True, exist_ok=True)
            runtime_mod = self.write_runtime_mod_package(self.builds_dir)
            self.log(f"Built C++ DLL mod folder {runtime_mod}")
            self.status_var.set(f"Built C++ DLL mod files: {runtime_mod}")
            messagebox.showinfo(APP_NAME, f"Built C++ DLL mod files:\n{runtime_mod}", parent=self)
            self.refresh_console()
        except Exception as error:
            self.show_error("Build C++ DLL mod failed", error)

    def preview(self) -> None:
        try:
            selected = self.configuration_selected()
            lines = []
            for spec in SETTINGS:
                multiplier = self.values()[spec.key]
                if multiplier != 1:
                    lines.append(f"{spec.label}: {display_multiplier(multiplier)} - C++ DLL INI")
            for group in NATIVE_GROUPS:
                for index, multiplier in enumerate(self.native_group_values()[group.key], start=1):
                    if multiplier != 1:
                        minimum, maximum = group.ranges[index - 1]
                        lines.append(
                            f"{group.label} {minimum}-{maximum}: {display_multiplier(multiplier)} - C++ DLL INI"
                        )
            for spec in DIRECT_SETTINGS:
                value = self.direct_values()[spec.key]
                if value != Decimal(spec.default):
                    lines.append(f"{spec.label}: {value} - C++ DLL INI")
            for spec in CURVE_SETTINGS:
                multiplier = self.curve_values()[spec.key]
                if multiplier != 1:
                    lines.append(f"{spec.label}: {display_multiplier(multiplier)} - C++ DLL INI")
            for spec in RUNTIME_SETTINGS:
                multiplier = self.runtime_values()[spec.key]
                if multiplier != Decimal(spec.default):
                    lines.append(f"{spec.label}: {display_multiplier(multiplier)} - live runtime override")
            if selected:
                lines.append("\nOutput: one UE4SS C++ DLL mod folder with one unified INI.")
            messagebox.showinfo("Change preview", "\n".join(lines) if lines else "No changes selected.", parent=self)
            self.status_var.set(f"Preview: {len(lines)} C++ DLL entries")
        except Exception as error:
            self.show_error("Preview failed", error)

    def safe_mod_name(self) -> str:
        name = self.mod_name_var.get().strip()
        if not name or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Mod name may contain only letters, numbers, dots, underscores, and hyphens")
        return name

    def developer_tools_available(self) -> bool:
        return (self.app_dir / "tools" / "scripts" / "build_dll.py").is_file()

    def backup_existing_runtime_file(self, original: Path) -> Path:
        directory = self.backups_dir / "runtime" / datetime.now().strftime("%Y%m%d_%H%M%S")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / original.name

    def apply_configuration(self) -> None:
        self.install_runtime_support()

    def profile_choices(self) -> tuple[str, ...]:
        profiles = sorted(path.stem for path in self.profiles_dir.glob("*.json") if path.is_file())
        return ("Vanilla Defaults",) + tuple(profiles)

    def profile_path_for_choice(self, choice: str) -> Path:
        return self.profiles_dir / f"{choice}.json"

    def refresh_profile_choices(self) -> None:
        choices = self.profile_choices()
        if self.profile_combo is not None:
            self.profile_combo.configure(values=choices)
        if self.profile_var.get() not in choices:
            self.profile_var.set("Vanilla Defaults")

    def profile_library_path(self, source: Path) -> Path:
        name = source.name if source.suffix.lower() == ".json" else f"{source.name}.json"
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        if not safe_name.lower().endswith(".json"):
            safe_name += ".json"
        target = self.profiles_dir / safe_name
        if source.resolve() == target.resolve():
            return target
        stem = target.stem
        suffix = target.suffix
        counter = 2
        while target.exists():
            target = self.profiles_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return target

    def apply_selected_profile(self) -> None:
        selected = self.profile_var.get()
        if selected == "Vanilla Defaults":
            self.apply_preset("Vanilla")
            self.profile_var.set("Vanilla Defaults")
            self.status_var.set("Loaded vanilla defaults")
            return
        path = self.profile_path_for_choice(selected)
        try:
            profile = json.loads(path.read_text(encoding="utf-8-sig"))
            self.apply_profile_data(profile)
            self.profile_var.set(path.stem)
            self.status_var.set(f"Loaded profile {path.stem}")
            self.log(f"Loaded profile {path}")
        except Exception as error:
            self.show_error("Load profile failed", error)

    def save_profile(self) -> None:
        try:
            values = {key: str(value) for key, value in self.values().items()}
            selected = filedialog.asksaveasfilename(
                parent=self, title="Save balance profile", initialdir=self.profiles_dir,
                initialfile=f"{self.safe_mod_name()}.json", defaultextension=".json",
                filetypes=(("Balance profile", "*.json"),),
            )
            if not selected:
                return
            profile = {
                "version": 7,
                "mod_name": self.safe_mod_name(),
                "settings": values,
                "direct_settings": {key: str(value) for key, value in self.direct_values().items()},
                "curve_settings": {key: str(value) for key, value in self.curve_values().items()},
                "runtime_settings": {key: str(value) for key, value in self.runtime_values().items()},
                "native_groups": {
                    key: [str(value) for value in values]
                    for key, values in self.native_group_values().items()
                },
            }
            Path(selected).write_text(
                json.dumps(profile, indent=4) + "\n",
                encoding="utf-8",
            )
            saved = Path(selected)
            library_path = self.profile_library_path(saved)
            if saved.resolve() != library_path.resolve():
                shutil.copy2(saved, library_path)
                self.log(f"Imported saved profile into profile library: {library_path}")
            self.refresh_profile_choices()
            self.profile_var.set(library_path.stem)
            self.status_var.set(f"Saved profile {library_path.stem}")
        except Exception as error:
            self.show_error("Save profile failed", error)

    def apply_profile_data(self, profile: dict[str, Any]) -> None:
        settings = profile.get("settings", {})
        for spec in SETTINGS:
            self.setting_vars[spec.key].set(display_multiplier(settings.get(spec.key, 1)))
        for key, value in profile.get("direct_settings", {}).items():
            if key in self.direct_vars:
                spec = next((candidate for candidate in DIRECT_SETTINGS if candidate.key == key), None)
                self.direct_vars[key].set(display_multiplier(value) if spec and is_direct_multiplier(spec) else str(value))
        for key, value in profile.get("curve_settings", {}).items():
            if key in self.curve_vars:
                self.curve_vars[key].set(display_multiplier(value))
        for key, value in profile.get("runtime_settings", {}).items():
            if key in self.runtime_vars:
                self.runtime_vars[key].set(display_multiplier(value))
        if profile.get("mod_name"):
            self.mod_name_var.set(profile["mod_name"])
        for key, values in profile.get("native_groups", {}).items():
            if key not in self.native_group_vars or not isinstance(values, list):
                continue
            for variable, value in zip(self.native_group_vars[key], values):
                variable.set(display_multiplier(value))
        for prefix in self.group_master_vars:
            self.refresh_group_master(prefix)
        self.update_summary()

    def load_profile(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self, title="Import balance profile", initialdir=self.profiles_dir,
            filetypes=(("Balance profile", "*.json"),),
        )
        if not selected:
            return
        try:
            selected_path = Path(selected)
            profile = json.loads(selected_path.read_text(encoding="utf-8-sig"))
            library_path = self.profile_library_path(selected_path)
            if selected_path.resolve() != library_path.resolve():
                shutil.copy2(selected_path, library_path)
                self.log(f"Imported profile into profile library: {library_path}")
            self.apply_profile_data(profile)
            self.refresh_profile_choices()
            self.profile_var.set(library_path.stem)
            self.status_var.set(f"Imported profile {library_path.stem}")
            self.log(f"Loaded profile {library_path}")
        except Exception as error:
            self.show_error("Load profile failed", error)

    def show_error(self, title: str, error: BaseException) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)
        self.log(f"ERROR: {title}: {error}")
        self.log("".join(traceback.format_exception(type(error), error, error.__traceback__)))
        self.status_var.set(title)
        self.refresh_console()
        messagebox.showerror(title, str(error), parent=self)


def main() -> int:
    try:
        app = Configurator()
        app.mainloop()
        return 0
    except Exception as error:
        print(f"{APP_NAME} failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
