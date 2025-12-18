import logging
from collections import Counter
from typing import cast, Iterable, Mapping, Any, NoReturn, Callable, ClassVar, TextIO

from BaseClasses import (
    Region,
    ItemClassification,
    CollectionState,
    Location,
    Entrance,
    Tutorial,
    Item,
    MultiWorld,
    LocationProgressType,
)
from Options import OptionError
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import components, Component, launch_subprocess, Type
from worlds.generic.Rules import set_rule, add_rule

from . import constants, regions
from .constants import CharacterAbility, GOLD_BRICK_EVENT_NAME
from .items import (
    ITEM_NAME_TO_ID,
    LegoStarWarsTCSItem,
    ExtraData,
    NonPowerBrickExtraData,
    VehicleData,
    CharacterData,
    GenericCharacterData,
    ITEM_DATA_BY_NAME,
    CHARACTERS_AND_VEHICLES_BY_NAME,
    USEFUL_NON_PROGRESSION_CHARACTERS,
    MINIKITS_BY_COUNT,
    MINIKITS_BY_NAME,
    EXTRAS_BY_NAME,
    SHOP_SLOT_REQUIREMENT_TO_UNLOCKS,
    PURCHASABLE_NON_POWER_BRICK_EXTRAS,
)
from .levels import (
    BonusArea,
    ChapterArea,
    CHAPTER_AREAS,
    BONUS_AREAS,
    EPISODE_TO_CHAPTER_AREAS,
    CHAPTER_AREA_STORY_CHARACTERS,
    ALL_AREA_REQUIREMENT_CHARACTERS,
    VEHICLE_CHAPTER_SHORTNAMES,
    SHORT_NAME_TO_CHAPTER_AREA,
    POWER_BRICK_REQUIREMENTS,
    ALL_MINIKITS_REQUIREMENTS,
    BONUS_NAME_TO_BONUS_AREA,
    BOSS_UNIQUE_NAME_TO_CHAPTER,
    DIFFICULT_OR_IMPOSSIBLE_TRUE_JEDI,
)
from .locations import LOCATION_NAME_TO_ID, LegoStarWarsTCSLocation, LEVEL_SHORT_NAMES_SET, LegoStarWarsTCSShopLocation
from .options import (
    LegoStarWarsTCSOptions,
    StartingChapter,
    AllEpisodesCharacterPurchaseRequirements,
    MinikitGoalAmount,
    OnlyUniqueBossesCountTowardsGoal,
    OPTION_GROUPS,
    GoalChapterLocationsMode,
)
from .option_resolution.common import resolve_options
from .ridables import RIDABLES_REQUIREMENTS
from .item_groups import ITEM_GROUPS
from .location_groups import LOCATION_GROUPS


def launch_client():
    from .client import launch
    launch_subprocess(launch, name="LegoStarWarsTheCompleteSagaClient")


components.append(Component("Lego Star Wars: The Complete Saga Client",
                            func=launch_client,
                            component_type=Type.CLIENT))

# Use deprioritzed on AP 0.6.3+, but still allow generation on older AP versions.
progression_deprioritized_skip_balancing: ItemClassification = getattr(
    ItemClassification,
    "progression_deprioritized_skip_balancing",
    ItemClassification.progression_skip_balancing
)
progression_deprioritized: ItemClassification = getattr(
    ItemClassification,
    "progression_deprioritized",
    ItemClassification.progression
)


class LegoStarWarsTCSWebWorld(WebWorld):
    theme = "partyTime"
    option_groups = OPTION_GROUPS
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide for setting up Lego Star Wars: The Complete Saga to be played in Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Mysteryem"]
    )]


logger = logging.getLogger("Lego Star Wars TCS")


class LegoStarWarsTCSWorld(World):
    """Lego Star Wars: The Complete Saga"""

    game = constants.GAME_NAME
    web = LegoStarWarsTCSWebWorld()
    options: LegoStarWarsTCSOptions
    options_dataclass = LegoStarWarsTCSOptions

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    origin_region_name = "Cantina"

    # Requires Universal Tracker 0.2.12 or newer because the game name contains a colon.
    ut_can_gen_without_yaml = True  # Used by Universal Tracker to allow generation without player yaml.

    PROG_USEFUL_LEVEL_ACCESS_THRESHOLD_PERCENT: ClassVar[float] = 1/6
    prog_useful_level_access_threshold_count: int = 6
    character_chapter_access_counts: Counter[str]

    starting_character_abilities: CharacterAbility = CharacterAbility.NONE

    effective_character_ability_names: dict[str, tuple[str, ...]]
    effective_character_abilities: dict[str, CharacterAbility]
    effective_item_classifications: dict[str, ItemClassification]
    effective_item_collect_extras: dict[str, list[str] | None]

    enabled_chapters: set[str]
    enabled_chapters_with_locations: set[str]  # Includes the Goal Chapter when it has locations.
    enabled_non_goal_chapters: set[str]
    enabled_episodes: set[int]
    enabled_bonuses: set[str]
    enabled_bosses: set[str]
    short_name_to_boss_character: dict[str, str]
    goal_chapter: str | None

    starting_chapter: ChapterArea = SHORT_NAME_TO_CHAPTER_AREA["1-1"]
    minikit_bundle_name: str = ""
    available_minikits: int = -1
    minikit_bundle_count: int = -1
    goal_minikit_count: int = -1
    goal_minikit_bundle_count: int = -1
    goal_boss_count: int = -1
    goal_area_completion_count: int = 0
    gold_brick_event_count: int = 0
    # Used in generation to check that created Gold Bricks match the number expected to be created from options.
    expected_gold_brick_event_count: int = -1
    character_unlock_location_count: int = 0
    goal_excluded_character_unlock_location_count: int = 0

    ridesanity_spots: dict[str, list[tuple[Location | Entrance, tuple[CharacterAbility, ...]]]]
    ridesanity_location_count: int = 0

    def __init__(self, multiworld, player: int):
        super().__init__(multiworld, player)
        self.enabled_chapters = set()
        self.enabled_chapters_with_locations = set()
        self.enabled_non_goal_chapters = set()
        self.enabled_episodes = set()
        self.enabled_bonuses = set()
        self.character_chapter_access_counts = Counter()
        self.short_name_to_boss_character = {}
        self.ridesanity_spots = {}

    def log_info(self, message: str, *args) -> None:
        logger.info("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def log_warning(self, message: str, *args) -> None:
        logger.warning("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def log_error(self, message: str, *args) -> None:
        logger.error("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def raise_error(self, ex_type: Callable[[str], Exception], message: str, *args) -> NoReturn:
        raise ex_type(("Lego Star Wars TCS (%s): " + message) % (self.player_name, *args))

    def option_error(self, message: str, *args) -> NoReturn:
        self.raise_error(OptionError, message, *args)

    def _is_universal_tracker(self) -> bool:
        """Return whether the current generation is being done with Universal Tracker rather than a real generation."""
        # The `generation_is_fake` attribute is added by Universal Tracker to allow detection of generation with
        # Universal Tracker rather than real generation.
        return hasattr(self.multiworld, "generation_is_fake")

    @property
    def starting_episode(self) -> int:
        return self.starting_chapter.episode

    def generate_early(self) -> None:
        resolve_options(self)

    def evaluate_effective_item(self,
                                name: str,
                                effective_character_abilities_lookup: dict[str, CharacterAbility] | None = None,
                                effective_character_ability_names_lookup: dict[str, tuple[str, ...]] | None = None):
        classification = ItemClassification.filler
        collect_extras: Iterable[str] = ()

        item_data = ITEM_DATA_BY_NAME[name]
        if item_data.code < 1:
            raise RuntimeError(f"Error: Item '{name}' cannot be created")
        assert item_data.code != -1
        if isinstance(item_data, ExtraData):
            if isinstance(item_data, NonPowerBrickExtraData):
                # Only Extra Toggle is useful out of these Extras due to the high movement speed Mouse Droid and a few
                # logic breaks in Blaster/Imperial logic.
                if name == "Extra Toggle":
                    classification = ItemClassification.useful
            else:
                # Many Power Brick Extras provide cheat-like abilities to the player, or allow breaking logic (to be
                # included in logic in the future), so should be given Useful classification.
                classification = ItemClassification.useful
        elif isinstance(item_data, GenericCharacterData):
            if effective_character_abilities_lookup is not None:
                abilities = effective_character_abilities_lookup[name]
            else:
                abilities = item_data.abilities & ~self.starting_character_abilities

            if effective_character_ability_names_lookup is not None:
                collect_extras = effective_character_ability_names_lookup[name]
            else:
                collect_extras = cast(list[str], [ability.name for ability in abilities])

            if name in self.character_chapter_access_counts:
                if self.character_chapter_access_counts[name] >= self.prog_useful_level_access_threshold_count:
                    # Characters that block access to a large number of chapters get progression + useful
                    # classification. This is functionally identical to progression classification, but some
                    # games/clients may specially highlight progression + useful items.
                    classification = ItemClassification.progression | ItemClassification.useful
                else:
                    classification = ItemClassification.progression
            elif abilities & constants.RARE_AND_USEFUL_ABILITIES:
                # These abilities are typically much less common, so the characters should never be given skip_balancing
                # classification.
                classification = ItemClassification.progression
            elif abilities:
                # Characters, with only abilities where there are many other characters in the item pool providing those
                # abilities, are given deprioritized and skip_balancing classifications towards the end of create_items.
                classification = ItemClassification.progression
            elif name in USEFUL_NON_PROGRESSION_CHARACTERS:
                # Force ghosts, glitchy characters and fast characters.
                classification = ItemClassification.useful

            if name == "Admiral Ackbar":
                # There is no trap functionality, this trap classification is a joke.
                # Maybe once/if the world switches to modding, receiving this item could play the iconic "It's a trap!"
                # line.
                classification |= ItemClassification.trap
        else:
            if name in MINIKITS_BY_NAME:
                # A goal macguffin.
                if self.goal_minikit_count > 0:
                    if self.options.accessibility == "minimal" or self.minikit_bundle_count > 10:
                        # Minikits are sorted first for minimal players in stage_pre_fill to reduce generation failures,
                        # so should always be deprioritized for minimal players.
                        classification = progression_deprioritized_skip_balancing
                    else:
                        # If there are only very few bundles, e.g. the bundles are 10 minikits at a time and there are
                        # not many in the pool, then don't use deprioritized classification.
                        classification = ItemClassification.progression_skip_balancing
                else:
                    classification = ItemClassification.filler
            elif name == "Progressive Score Multiplier":
                # todo: Vary between progression and progression_skip_balancing depending on what percentage of
                #  locations need them. Make them Useful if none are needed.
                # Generic item that grants Score multiplier Extras, which are used in logic for purchases from the shop.
                classification = ItemClassification.progression
            elif name == "Episode Completion Token":
                # Very few location checks and typically late into a seed.
                classification = ItemClassification.progression_skip_balancing
            elif name == "Kyber Brick":
                # Kyber Bricks are only logically relevant to the Kyber Bricks goal and do not unlock any locations, so
                # should skip progression balancing.
                classification = ItemClassification.progression_skip_balancing
            elif name.startswith("Episode ") and name.endswith(" Unlock"):
                classification = ItemClassification.progression | ItemClassification.useful

        return classification, collect_extras if collect_extras else None

    def _get_effective_item_data(self,
                                 starting_abilities: CharacterAbility,
                                 ) -> tuple[dict[str, ItemClassification], dict[str, Iterable[str] | None]]:
        """
        Pre-calculate the effective character abilities and classification of each item to speed up the creation
        of items with multiple copies.
        """
        effective_character_abilities: dict[str, CharacterAbility] = {}
        effective_character_ability_names: dict[str, tuple[str, ...]] = {}

        effective_ability_cache: dict[CharacterAbility, tuple[str, ...]] = {}
        for name, char in CHARACTERS_AND_VEHICLES_BY_NAME.items():
            # Remove abilities provided by the starting characters from other characters, potentially changing the
            # classification of other characters if all their abilities are covered by the starting characters.
            # This improves generation performance by reducing the number of extra collects when a character item is
            # collected.
            effective_abilities: CharacterAbility = char.abilities & ~starting_abilities
            effective_character_abilities[name] = effective_abilities
            if effective_abilities in effective_ability_cache:
                effective_character_ability_names[name] = effective_ability_cache[effective_abilities]
            else:
                effective_ability_names = tuple(cast(list[str], [ability.name for ability in effective_abilities]))
                effective_ability_cache[effective_abilities] = effective_ability_names
                effective_character_ability_names[name] = effective_ability_names

        effective_item_classifications: dict[str, ItemClassification] = {}
        effective_item_collect_extras: dict[str, Iterable[str] | None] = {}
        for item in self.item_name_to_id:
            classification, collect_extras = self.evaluate_effective_item(item,
                                                                          effective_character_abilities,
                                                                          effective_character_ability_names)
            effective_item_classifications[item] = classification
            effective_item_collect_extras[item] = collect_extras
        return effective_item_classifications, effective_item_collect_extras

    def get_filler_item_name(self) -> str:
        junk_weights: dict[str, int] = self.options.junk_weights.value
        return self.random.choices(tuple(junk_weights), tuple(junk_weights.values()))[0]

    def create_item(self, name: str) -> LegoStarWarsTCSItem:
        code = self.item_name_to_id[name]
        classification, collect_extras = self.evaluate_effective_item(name)

        return LegoStarWarsTCSItem(name, classification, code, self.player, collect_extras)

    def _create_item_ex(self,
                        name: str,
                        classification_lookup: dict[str, ItemClassification],
                        collect_extras_lookup: dict[str, Iterable[str] | None]):
        code = self.item_name_to_id[name]
        classification = classification_lookup[name]
        collect_extras = collect_extras_lookup[name]

        return LegoStarWarsTCSItem(name, classification, code, self.player, collect_extras)

    def create_event(self, name: str) -> LegoStarWarsTCSItem:
        return LegoStarWarsTCSItem(name, ItemClassification.progression, None, self.player)

    def create_items(self) -> None:
        # Determine how many chapter worth's of locations are enabled.
        goal_chapter_locations_excluded = (
                self.goal_chapter
                and self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_excluded
        )

        if self.goal_chapter:
            if self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_removed:
                chapters_with_locations = self.enabled_chapters - {self.goal_chapter}
                chapters_with_non_excluded_locations = self.enabled_non_goal_chapters
            elif self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_excluded:
                chapters_with_locations = self.enabled_chapters
                chapters_with_non_excluded_locations = self.enabled_non_goal_chapters
            else:
                assert self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_normal
                chapters_with_locations = self.enabled_chapters
                chapters_with_non_excluded_locations = self.enabled_chapters
        else:
            chapters_with_locations = self.enabled_chapters
            chapters_with_non_excluded_locations = self.enabled_chapters

        # todo: Reserve spaces in the item pool for vehicles and non-vehicles separately, based on how many locations
        #  unlock characters of the each type.
        vehicle_chapters_enabled = not VEHICLE_CHAPTER_SHORTNAMES.isdisjoint(self.enabled_chapters)

        possible_pool_character_items = {name: char for name, char in CHARACTERS_AND_VEHICLES_BY_NAME.items()
                                         if char.is_sendable and (vehicle_chapters_enabled
                                                                  or char.item_type != "Vehicle")}
        if self.goal_chapter and self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_removed:
            # Vehicle chapters could be disabled for normal chapters, but the goal chapter could be a vehicle chapter,
            # so the vehicles required for the goal chapter need to be forced into the item pool.
            for name in CHAPTER_AREA_STORY_CHARACTERS[self.goal_chapter]:
                if name not in possible_pool_character_items:
                    possible_pool_character_items[name] = CHARACTERS_AND_VEHICLES_BY_NAME[name]

        # If Gunship Cavalry (Original), Pod Race (Original) and Anakin's Flight get updated to require Vehicles again,
        # then Republic Gunship, Anakin's Pod and Naboo Starfighter would be required items to included in the pool.
        # if not vehicle_chapters_enabled:
        #     if "Anakin's Flight" in self.enabled_bonuses:
        #         vehicle = CHARACTERS_AND_VEHICLES_BY_NAME["Naboo Starfighter"]
        #         possible_pool_character_items[vehicle.name] = vehicle
        #     if "Gunship Cavalry (Original)" in self.enabled_bonuses:
        #         vehicle = CHARACTERS_AND_VEHICLES_BY_NAME["Republic Gunship"]
        #         possible_pool_character_items[vehicle.name] = vehicle
        #     if "Mos Espa Pod Race (Original)" in self.enabled_bonuses:
        #         vehicle = CHARACTERS_AND_VEHICLES_BY_NAME["Anakin's Pod"]
        #         possible_pool_character_items[vehicle.name] = vehicle

        # Add characters necessary to unlock the starting chapter into starting inventory.
        for name in CHAPTER_AREA_STORY_CHARACTERS[self.starting_chapter.short_name]:
            self.push_precollected(self.create_item(name))
            del possible_pool_character_items[name]
        if self.options.episode_unlock_requirement == "episode_item":
            self.push_precollected(self.create_item(f"Episode {self.starting_episode} Unlock"))

        # Gather the abilities of all items in starting inventory, so that they can be removed from other created items,
        # improving generation performance.
        initial_starting_items = cast(list[LegoStarWarsTCSItem], self.multiworld.precollected_items[self.player])
        starting_collect_extras = {s for item in initial_starting_items if item.collect_extras
                                   for s in item.collect_extras}
        starting_abilities = CharacterAbility.NONE
        # The Enum class supports __getitem__ for getting members by name, but __contains__ checks whether an Enum
        # instance belongs to that Enum class, so checking if a string is a member name needs to use __members__ or
        # try-except KeyError.
        ability_members = CharacterAbility.__members__
        for collect_extra in starting_collect_extras:
            if collect_extra in ability_members:
                starting_abilities |= CharacterAbility[collect_extra]

        # todo: In the future, it will be necessary to ensure the player has at least 1 (maybe better to be 2) starting
        #  non-vehicle characters when starting with a non-vehicle level, and at least 1 (maybe better to be 2) starting
        #  vehicles when starting with a vehicle level.

        # todo: Logic currently assumes the player always has Protocol Droid access, so it is necessary to start with a
        #  Protocol Droid access character.
        if CharacterAbility.PROTOCOL_DROID not in starting_abilities:
            # Pick whichever character out of TC-14 and C-3PO is required for the least chapters, which is basically
            # always TC-14 because TC-14 is only required for 1-1. The other characters with Protocol Droid access are
            # 4-LOM and IG-88, which both have a bunch of extra abilities that it is better for the player to not start
            # with.
            tc14_count = self.character_chapter_access_counts.get("TC-14", 0)
            c3po_count = self.character_chapter_access_counts.get("C-3PO", 0)
            if tc14_count < c3po_count:
                to_start_with = "TC-14"
            elif c3po_count < tc14_count:
                to_start_with = "C-3PO"
            else:
                to_start_with = self.random.choice(("TC-14", "C-3PO"))
            self.push_precollected(self.create_item(to_start_with))
            starting_abilities |= CharacterAbility.PROTOCOL_DROID
            del possible_pool_character_items[to_start_with]

        # todo: Logic currently assumes the player always has a Jedi, so it is necessary to start with a Jedi character.
        if CharacterAbility.JEDI not in starting_abilities:
            # Pick a Jedi that is not a requirement to access a chapter.
            choices: list[CharacterData] = []
            for char in CHARACTERS_AND_VEHICLES_BY_NAME.values():
                if not char.is_sendable:
                    # The character is not an AP item.
                    continue
                if CharacterAbility.JEDI not in char.abilities:
                    # The character is not a Jedi.
                    continue
                assert isinstance(char, CharacterData), "Vehicles cannot be Jedi"
                if CharacterAbility.SITH in char.abilities:
                    # Skip Sith because they are rarer.
                    continue
                # todo: In the future, chapters may be locked by chapter unlock items rather than characters, so, when
                #  the option for chapter unlock items is enabled, these characters should not be skipped.
                if char.name in ALL_AREA_REQUIREMENT_CHARACTERS:
                    # Skip characters used to unlock chapters.
                    continue
                choices.append(char)
            starting_jedi = self.random.choice(choices)
            starting_abilities |= starting_jedi.abilities
            self.push_precollected(self.create_item(starting_jedi.name))
            del possible_pool_character_items[starting_jedi.name]

        # Determine what abilities must be supplied by the item pool for all locations to be reachable with all items in
        # the item pool.
        required_character_abilities_in_pool = CharacterAbility.NONE
        optional_character_abilities = CharacterAbility.NONE
        for shortname in chapters_with_locations:
            power_brick_abilities = POWER_BRICK_REQUIREMENTS[shortname][1]
            if power_brick_abilities is not None:
                if isinstance(power_brick_abilities, tuple):
                    at_least_one_already_required = False
                    for abilities in power_brick_abilities:
                        if abilities in required_character_abilities_in_pool:
                            at_least_one_already_required = True
                        # Mark the abilities as optional. They will be included in logic, but won't necessarily be
                        # guaranteed to be provided by the item pool.
                        optional_character_abilities |= abilities

                    if not at_least_one_already_required:
                        # Pick any one of the abilities to be required to be provided by the item pool.
                        picked = self.random.choice(power_brick_abilities)
                        required_character_abilities_in_pool |= picked
                else:
                    required_character_abilities_in_pool |= power_brick_abilities
            if self.options.enable_minikit_locations.value:
                required_character_abilities_in_pool |= ALL_MINIKITS_REQUIREMENTS[shortname]
        for bonus_name in self.enabled_bonuses:
            area = BONUS_NAME_TO_BONUS_AREA[bonus_name]
            required_character_abilities_in_pool |= area.completion_ability_requirements
        for _area_name, ridable_spots in self.ridesanity_spots.items():
            for _spot, any_ridable_ability_requirements in ridable_spots:
                if any_ridable_ability_requirements:
                    if len(any_ridable_ability_requirements) == 1:
                        required_character_abilities_in_pool |= any_ridable_ability_requirements[0]
                    else:
                        at_least_one_already_required = False
                        for ridable_ability_requirements in any_ridable_ability_requirements:
                            if ridable_ability_requirements in required_character_abilities_in_pool:
                                at_least_one_already_required = True
                            # Mark the abilities as optional. They will be included in logic, but won't necessarily be
                            # guaranteed to be provided by the item pool.
                            optional_character_abilities |= ridable_ability_requirements

                        if not at_least_one_already_required:
                            # Pick any one of the abilities to be required to be provided by the item pool.
                            picked = self.random.choice(any_ridable_ability_requirements)
                            required_character_abilities_in_pool |= picked
        # Remove counts <= 0.
        level_access_character_counts = +self.character_chapter_access_counts
        for name in level_access_character_counts.keys():
            abilities_provided_by_level_access = CHARACTERS_AND_VEHICLES_BY_NAME[name].abilities
            # Characters with these abilities do not need to be explicitly added to the item pool because these
            # abilities are provided by a character that is required to unlock a chapter.
            required_character_abilities_in_pool &= ~abilities_provided_by_level_access
            optional_character_abilities |= abilities_provided_by_level_access
        required_character_abilities_in_pool &= ~starting_abilities
        optional_character_abilities &= ~starting_abilities

        # If an ability is not relevant to logic at all, then it is undesirable for that ability to be in collects, and
        # any characters with only irrelevant abilities should lose their progression classification.
        # In larger worlds, it is unlikely for there to be any logically irrelevant abilities.
        logically_irrelevant_abilities = ~(required_character_abilities_in_pool | optional_character_abilities)

        effective_item_classifications, effective_item_collect_extras = (
            self._get_effective_item_data(logically_irrelevant_abilities)
        )
        # These abilities are provided by the starting characters, so these abilities can be stripped from other
        # characters, improving logic performance.
        self.starting_character_abilities = starting_abilities

        remaining_abilities_to_fulfil = required_character_abilities_in_pool

        pool_required_characters = []
        for name in level_access_character_counts.keys():
            if name not in possible_pool_character_items:
                continue
            char = CHARACTERS_AND_VEHICLES_BY_NAME[name]
            remaining_abilities_to_fulfil &= ~char.abilities
            pool_required_characters.append(char)
            del possible_pool_character_items[name]

        possible_pool_character_names = list(possible_pool_character_items.values())
        self.random.shuffle(possible_pool_character_names)
        # Sort preferred characters first so that they are picked in preference.
        preferred_characters = self.options.preferred_characters.value
        if preferred_characters:
            possible_pool_character_names.sort(key=lambda char: -1 if char.name in preferred_characters else 0)

        for character in possible_pool_character_names:
            if remaining_abilities_to_fulfil & character.abilities:
                pool_required_characters.append(character)
                remaining_abilities_to_fulfil &= ~character.abilities
                del possible_pool_character_items[character.name]
        non_required_characters = list(possible_pool_character_items.values())

        # Start with all sendable Extras as possible to add to the item pool.
        possible_pool_extras = {name: extra for name, extra in EXTRAS_BY_NAME.items() if extra.is_sendable}

        if not self.options.enable_starting_extras_locations:
            # The starting Extra purchases are vanilla, so don't include their Extras in the pool.
            for extra in PURCHASABLE_NON_POWER_BRICK_EXTRAS:
                del possible_pool_extras[extra.name]

        if self.options.start_with_detectors:
            detectors = {"Minikit Detector", "Power Brick Detector"}
            assert detectors <= set(possible_pool_extras.keys())
            # The detector Extras are being given to the player at the start, so don't include their Extras in the pool.
            for extra_name in detectors:
                del possible_pool_extras[extra_name]
            for detector in sorted(detectors):
                self.push_precollected(self.create_item(detector))

        non_required_extras = list(possible_pool_extras.keys())

        max_studs_purchase = max(loc.studs_cost for loc in self.get_locations()
                                 if isinstance(loc, LegoStarWarsTCSShopLocation))

        required_score_multipliers = self._get_score_multiplier_requirement(max_studs_purchase)
        # Increase required_score_multipliers to at least 1 if there are any enabled chapters with difficult or
        # potentially impossible True Jedi.
        if (required_score_multipliers < 1
                and self.options.enable_true_jedi_locations
                and not self.options.easier_true_jedi
                and not DIFFICULT_OR_IMPOSSIBLE_TRUE_JEDI.isdisjoint(self.enabled_chapters_with_locations)):
            required_score_multipliers = 1

        non_required_score_multipliers = 5 - required_score_multipliers
        assert 0 <= required_score_multipliers <= 5
        pool_required_extras = ["Progressive Score Multiplier"] * required_score_multipliers
        non_required_extras.extend(["Progressive Score Multiplier"] * non_required_score_multipliers)

        required_characters_count = len(pool_required_characters)
        required_extras_count = len(pool_required_extras)

        non_excluded_character_unlock_location_count = (
                self.character_unlock_location_count - self.goal_excluded_character_unlock_location_count
        )

        # Try to add as many characters to the pool as this.
        reserved_character_location_count: int
        free_character_location_count: int
        if self.options.filler_reserve_characters:
            reserved_character_location_count = non_excluded_character_unlock_location_count
            free_character_location_count = 0
        else:
            reserved_character_location_count = min(required_characters_count,
                                                    non_excluded_character_unlock_location_count)
            free_character_location_count = (non_excluded_character_unlock_location_count
                                             - reserved_character_location_count)
        # Any goal excluded character unlock locations do not contribute Characters to the item pool (unless those
        # characters happen to be Filler classification). Enough Filler items for Excluded locations is checked and
        # satisfied later, so these locations are effectively free locations.
        free_character_location_count += self.goal_excluded_character_unlock_location_count

        # Try to create as many Extras as this.
        reserved_extras_location_count = len(chapters_with_non_excluded_locations)
        if self.options.enable_starting_extras_locations:
            reserved_extras_location_count += len(PURCHASABLE_NON_POWER_BRICK_EXTRAS)

        free_extra_location_count: int
        if self.options.filler_reserve_extras:
            # All the locations from Extras are reserved for putting Extra items into the item pool.
            free_extra_location_count = 0
        else:
            # Reserve only as many locations for Extras as the number of Extras that are required to be in the item
            # pool.
            starting_reserved_count = reserved_extras_location_count
            reserved_extras_location_count = min(required_extras_count, starting_reserved_count)
            free_extra_location_count = starting_reserved_count - reserved_extras_location_count
        if goal_chapter_locations_excluded:
            # The Extra location of the Goal Chapter is excluded, and does not contribute an Extra to the item pool.
            free_extra_location_count += 1

        # As many minikit bundles as this will always be created. This may be fewer than is required to goal, but
        # reducing the total bundle count can make a seed longer, so all minikit bundles should be considered to be
        # required.
        required_minikit_location_count = self.minikit_bundle_count

        # The vanilla rewards for these are Gold Bricks, which are events, so these are effectively free locations for
        # any kind of item when enabled.
        if self.options.enable_true_jedi_locations:
            true_jedi_location_count = len(chapters_with_non_excluded_locations)

            if goal_chapter_locations_excluded:
                # True Jedi locations are already free locations for any kind of item.
                true_jedi_location_count += 1
        else:
            true_jedi_location_count = 0

        completion_location_count = len(chapters_with_non_excluded_locations) + len(self.enabled_bonuses)
        if goal_chapter_locations_excluded:
            # The location is excluded, but still counted as a free location.
            completion_location_count += 1

        if self.options.enable_minikit_locations:
            free_minikit_location_count = len(chapters_with_non_excluded_locations) * 10 - required_minikit_location_count
            if goal_chapter_locations_excluded:
                # The locations are excluded, but still count as free locations.
                free_minikit_location_count += 10
        else:
            if self.options.minikit_goal_amount != 0:
                assert self.options.minikit_bundle_size == 10
                assert self.minikit_bundle_name == "10 Minikits"
                assert self.minikit_bundle_count == len(self.enabled_non_goal_chapters)
                # Consume the free Chapter Completion locations to fit the Minikits.
                completion_location_count -= self.minikit_bundle_count
                free_minikit_location_count = 0
            else:
                assert required_minikit_location_count == 0
                free_minikit_location_count = 0
        # There are no corresponding items for ridesanity locations, so they are free locations for any item.
        free_ridesanity_location_count = self.ridesanity_location_count

        free_location_count = (
                completion_location_count
                + true_jedi_location_count
                + free_minikit_location_count
                + free_character_location_count
                + free_extra_location_count
                + free_ridesanity_location_count
        )

        assert free_location_count >= 0, "initial free_location_count should always be >= 0"

        extra_required_items = []
        # A few free locations may need to be used for episode unlock items and/or episode tokens.
        if self.options.episode_unlock_requirement == "episode_item":
            for i in self.enabled_episodes:
                if i != self.starting_episode:
                    extra_required_items.append(f"Episode {i} Unlock")
        if self.options.all_episodes_character_purchase_requirements == "episodes_tokens":
            # One token is added to the item pool for every episode's worth of (6) chapters that are enabled.
            tokens_in_pool = max(1, round(len(self.enabled_episodes) / 6))
            start_inventory_tokens = 6 - tokens_in_pool
            assert 5 >= start_inventory_tokens >= 0
            for _ in range(tokens_in_pool):
                extra_required_items.append("Episode Completion Token")
            for _ in range(start_inventory_tokens):
                self.push_precollected(self.create_item("Episode Completion Token"))
        # 7 free locations may need to be used for Kyber Bricks.
        if self.options.goal_requires_kyber_bricks:
            extra_required_items.extend(("Kyber Brick",) * 7)

        free_location_count -= len(extra_required_items)

        unfilled_locations = self.multiworld.get_unfilled_locations(self.player)
        num_to_fill = len(self.multiworld.get_unfilled_locations(self.player))

        if free_location_count < 0:
            # There are not enough non-excluded locations for all required progression items.
            # Attempt to reduce reserved items until there is enough space.
            needed = -free_location_count
            # Subtract from reserved, but not required, counts.
            ok_to_replace_character_count = max(0, reserved_character_location_count - required_characters_count)
            ok_to_replace_extras_count = max(0, reserved_extras_location_count - required_extras_count)
            total_replaceable = ok_to_replace_character_count + ok_to_replace_extras_count
            if needed > total_replaceable:
                if self.options.goal_requires_kyber_bricks:
                    # The Kyber Bricks goal adds 7 items that have no corresponding vanilla locations.
                    self.option_error("There are not enough locations to fit all required items. Enable additional"
                                      " locations, increase the Minikit Bundle Size, or disable the Kyber Bricks goal"
                                      " to free up more locations. There were %i more required progression items than"
                                      " non-excluded locations.",
                                      needed - total_replaceable)
                else:
                    self.option_error("There are not enough locations to fit all required items. Enable additional"
                                      " locations or increase the Minikit Bundle Size to free up more locations. There"
                                      " were %i more required progression items than locations.",
                                      needed - total_replaceable)
            character_percentage = ok_to_replace_character_count / total_replaceable
            character_subtract = min(needed, round(character_percentage * needed))
            extra_subtract = needed - character_subtract
            reserved_character_location_count -= character_subtract
            reserved_extras_location_count -= extra_subtract
            free_location_count = 0

        assert free_location_count >= 0, "free_location_count must always be >= 0"

        expected_num_to_fill = (
                reserved_character_location_count
                + reserved_extras_location_count
                + required_minikit_location_count
                + free_location_count
                + len(extra_required_items)
        )

        assert num_to_fill == expected_num_to_fill, \
            f"Expected {expected_num_to_fill} locations to fill, but got {num_to_fill}"

        required_extras_count = len(pool_required_extras)
        required_excludable_count = (
                sum(loc.progress_type == LocationProgressType.EXCLUDED for loc in unfilled_locations)
        )

        # fixme: Some reserved characters can be Filler classification, which would be fine being placed on excluded
        #  locations, so this check is currently overly strict because it assumes that reserved characters will be
        #  Useful or Progression.
        if free_location_count < required_excludable_count:
            # This shouldn't really happen unless basically the entire world is excluded and/or barely any locations
            # are enabled.
            needed = required_excludable_count - free_location_count
            # Find how many character/extra locations can be used for filler placement without issue.
            ok_to_replace_character_count = max(0, reserved_character_location_count - required_characters_count)
            ok_to_replace_extras_count = max(0, reserved_extras_location_count - required_extras_count)
            total_replaceable = ok_to_replace_character_count + ok_to_replace_extras_count
            if needed > total_replaceable:
                # There are too many non-excludable items for the number of excluded locations.
                # Give up.
                # If this is too common of an issue, it would be possible to add some of the required characters/extras
                # to start inventory instead of erroring here.
                non_excluded_count = num_to_fill - required_excludable_count
                required_count = (
                        required_extras_count
                        + required_characters_count
                        + required_minikit_location_count
                        + len(extra_required_items)
                )
                self.option_error("There are too few non-excluded locations to fit all required progression items."
                                  " There are %i locations, %i of which are not excluded, but there are %i required"
                                  " items that cannot be placed on excluded locations.",
                                  num_to_fill, non_excluded_count, required_count)
            character_percentage = ok_to_replace_character_count / total_replaceable
            character_subtract = min(needed, round(character_percentage * needed))
            extra_subtract = needed - character_subtract
            reserved_character_location_count -= character_subtract
            reserved_extras_location_count -= extra_subtract
            free_location_count = 0
        else:
            free_location_count -= required_excludable_count

        item_pool: list[LegoStarWarsTCSItem] = []

        created_item_names: set[str] = set()

        def create_item(item_name: str) -> LegoStarWarsTCSItem:
            return self._create_item_ex(item_name, effective_item_classifications, effective_item_collect_extras)

        def add_to_pool(item: LegoStarWarsTCSItem):
            item_pool.append(item)
            created_item_names.add(item.name)

        # Create Episode related items.
        for name in extra_required_items:
            add_to_pool(create_item(name))
        num_to_fill -= len(extra_required_items)

        # Create required characters.
        start_inventory_required_characters_count: int
        if reserved_character_location_count < required_characters_count:
            # If there are not enough reserved character unlock locations for the required characters, subtract from the
            # free location count.
            to_subtract = required_characters_count - reserved_character_location_count
            if free_location_count < to_subtract:
                # If there are not enough free locations, some of the required characters will have to be added to start
                # inventory.
                start_inventory_required_characters_count = to_subtract - free_location_count
                self.log_warning("There were not enough locations to add all required characters to the item pool,"
                                 " some of them have been added to starting inventory")
                free_location_count = 0
            else:
                free_location_count -= to_subtract
                start_inventory_required_characters_count = 0
            reserved_character_location_count = 0
        else:
            reserved_character_location_count -= required_characters_count
            start_inventory_required_characters_count = 0

        self.random.shuffle(pool_required_characters)
        pool_required_chars = pool_required_characters[start_inventory_required_characters_count:]
        start_required_chars = pool_required_characters[:start_inventory_required_characters_count]
        for character in pool_required_chars:
            add_to_pool(create_item(character.name))
        num_to_fill -= len(pool_required_chars)
        assert num_to_fill >= 0
        for character in start_required_chars:
            self.push_precollected(create_item(character.name))

        # Create required extras.
        start_inventory_required_extras_count: int
        if reserved_extras_location_count < required_extras_count:
            to_subtract = required_extras_count - reserved_extras_location_count
            if free_location_count < to_subtract:
                start_inventory_required_extras_count = to_subtract - free_location_count
                self.log_warning("There were not enough locations to add all required Extras to the item pool,"
                                 " some of them have been added to starting inventory")
                free_location_count = 0
            else:
                free_location_count -= to_subtract
                start_inventory_required_extras_count = 0
            reserved_extras_location_count = 0
        else:
            reserved_extras_location_count -= required_extras_count
            start_inventory_required_extras_count = 0

        self.random.shuffle(pool_required_extras)
        start_required_extras = pool_required_extras[:start_inventory_required_extras_count]
        pool_required_extras = pool_required_extras[start_inventory_required_extras_count:]
        for extra_name in pool_required_extras:
            add_to_pool(create_item(extra_name))
        num_to_fill -= len(pool_required_extras)
        assert num_to_fill >= 0
        for extra_name in start_required_extras:
            self.push_precollected(create_item(extra_name))

        # Create required minikits.
        for _ in range(self.minikit_bundle_count):
            add_to_pool(create_item(self.minikit_bundle_name))
        num_to_fill -= self.minikit_bundle_count
        assert num_to_fill >= 0

        # Create as many non-required characters as there are reserved character locations.
        self.random.shuffle(non_required_characters)
        # Sort preferred characters first so that they are picked in preference.
        if preferred_characters:
            non_required_characters.sort(key=lambda char: -1 if char.name in preferred_characters else 0)
        picked_chars = non_required_characters[:reserved_character_location_count]
        leftover_chars = non_required_characters[reserved_character_location_count:]
        for char in picked_chars:
            item = create_item(char.name)
            add_to_pool(item)
            if required_excludable_count > 0 and item.excludable:
                required_excludable_count -= 1
        num_to_fill -= len(picked_chars)
        assert num_to_fill >= 0

        # Create as many non-required extras as there are reserved power brick locations.
        self.random.shuffle(non_required_extras)
        # Sort preferred Extras first so that they are picked in preference.
        preferred_extras = self.options.preferred_extras.value
        if preferred_extras:
            # todo: Once Progressive Score Multipliers can be disabled, this if-condition also needs to check that
            #  Progressive Score Multipliers are enabled.
            # Swap out Progressive Score Multiplier with individual Score multipliers so that only the preferred
            if non_required_score_multipliers:
                score_multipliers = [
                    "Score x10",
                    "Score x8",
                    "Score x6",
                    "Score x4",
                    "Score x2",
                ]
                # Find the highest preferred Score multiplier and ensure the lower multipliers are also preferred.
                for i, multiplier in enumerate(score_multipliers[:-1]):
                    if multiplier in preferred_extras:
                        preferred_extras.update(score_multipliers[i + 1:])
                        break
                score_multipliers_set = set(score_multipliers)

                # Replace "Progressive Score Multiplier" with individual multipliers.
                progressive_replacements = score_multipliers[:non_required_score_multipliers]
                self.random.shuffle(progressive_replacements)

                non_required_extras = [progressive_replacements.pop() if e == "Progressive Score Multiplier" else e
                                       for e in non_required_extras]
                # Sort preferred extras to the front so that they get picked first.
                non_required_extras.sort(key=lambda extra: -1 if extra in preferred_extras else 0)
                # Replace individual multipliers with "Progressive Score Multiplier".
                non_required_extras = ["Progressive Score Multiplier" if e in score_multipliers_set else e
                                       for e in non_required_extras]
            else:
                # Sort preferred extras to the front so that they get picked first.
                non_required_extras.sort(key=lambda extra: -1 if extra in preferred_extras else 0)

        picked_extras = non_required_extras[:reserved_extras_location_count]
        leftover_extras = non_required_extras[reserved_extras_location_count:]
        for extra in picked_extras:
            item = create_item(extra)
            add_to_pool(item)
            if required_excludable_count > 0 and item.excludable:
                required_excludable_count -= 1
        num_to_fill -= len(picked_extras)
        assert num_to_fill >= 0

        # Determine items to fill out the rest of the item pool according to the weights in the options.
        leftover_choices: list[list[LegoStarWarsTCSItem]] = []
        leftover_weights: list[int] = []

        leftover_character_items = list(map(create_item, (char.name for char in leftover_chars)))
        character_weight = self.options.filler_weight_characters.value
        if character_weight and leftover_character_items:
            leftover_choices.append(leftover_character_items)
            leftover_weights.append(character_weight)

        leftover_extra_items = list(map(create_item, leftover_extras))
        extras_weight = self.options.filler_weight_extras.value
        if extras_weight and leftover_extra_items:
            leftover_choices.append(leftover_extra_items)
            leftover_weights.append(extras_weight)

        junk_names_and_weights = self.options.junk_weights.value
        junk_names = tuple(junk_names_and_weights.keys())
        junk_weights = tuple(junk_names_and_weights.values())

        def create_excludable_junk_items(count: int):
            names = self.random.choices(junk_names, junk_weights, k=count)
            return [create_item(name) for name in names]

        junk_weight = self.options.filler_weight_junk.value
        if junk_weight:
            leftover_junk = create_excludable_junk_items(num_to_fill)
            leftover_choices.append(leftover_junk)
            leftover_weights.append(junk_weight)

        all_leftover_items: Iterable[LegoStarWarsTCSItem]
        if not leftover_choices:
            # While there is always at least one nonzero weight, it's possible to have run out of Extras or Characters.
            all_leftover_items = []
        elif len(leftover_choices) == 1:
            all_leftover_items = leftover_choices[0]
        else:
            weighted_leftover_items: list[LegoStarWarsTCSItem] = []
            needed_excludable = required_excludable_count
            # Items will be popped from the ends rather than taken from the start, so reverse the lists.
            for item_list in leftover_choices:
                item_list.reverse()
            while (len(weighted_leftover_items) < num_to_fill or needed_excludable > 0) and leftover_choices:
                picked_list = self.random.choices(leftover_choices, leftover_weights, k=1)[0]
                item = picked_list.pop()
                if needed_excludable > 0 and item.excludable:
                    needed_excludable -= 1
                weighted_leftover_items.append(item)
                if not picked_list:
                    # The picked list is now empty, so update leftover_choices
                    next_leftover_choices: list[list[LegoStarWarsTCSItem]] = []
                    next_leftover_weights: list[int] = []
                    for item_list, weight in zip(leftover_choices, leftover_weights):
                        if item_list:
                            next_leftover_choices.append(item_list)
                            next_leftover_weights.append(weight)

                    leftover_choices = next_leftover_choices
                    leftover_weights = next_leftover_weights

                    if len(leftover_choices) == 1:
                        # There is only one list left, so append all elements from it.
                        remaining_list = next_leftover_choices[0]
                        weighted_leftover_items.extend(reversed(remaining_list))
                        remaining_list.clear()
                        break

            all_leftover_items = weighted_leftover_items

        # Split the all_leftover_items into separate lists for required excludable items and other leftover items.
        excludable_leftover_items = []
        leftover_items = []
        for item in all_leftover_items:
            if required_excludable_count > 0 and item.excludable:
                excludable_leftover_items.append(item)
                required_excludable_count -= 1
            else:
                leftover_items.append(item)
        if len(excludable_leftover_items) < required_excludable_count:
            excludable_leftover_items.extend(create_excludable_junk_items(required_excludable_count))
        # Required excludable items must be picked first.
        leftover_items = excludable_leftover_items + leftover_items
        if len(leftover_items) < num_to_fill:
            leftover_items.extend(create_excludable_junk_items(num_to_fill - len(leftover_items)))
        else:
            leftover_items = leftover_items[:num_to_fill]
        assert len(leftover_items) == num_to_fill

        for item in leftover_items:
            add_to_pool(item)

        assert len(item_pool) == len(unfilled_locations)

        # todo: In the future, individual characters may be relevant to logic, e.g. Droideka, which should never be
        #  given deprioritized + skip_balancing.
        # Give deprioritized + skip_balancing to characters with only common abilities, and that do not give access to
        # levels.
        non_level_access_character_items: list[LegoStarWarsTCSItem] = []
        non_deprioritize_ability_counts: Counter[str] = Counter()
        for item in item_pool:
            if item.advancement and item.name in CHARACTERS_AND_VEHICLES_BY_NAME:
                if progression_deprioritized_skip_balancing in item.classification:
                    # Don't count abilities from characters that are already deprioritized + skip_balancing.
                    continue
                extra_collects = item.collect_extras
                if extra_collects is not None:
                    non_deprioritize_ability_counts.update(extra_collects)
                if level_access_character_counts[item.name] == 0:
                    assert extra_collects is not None, ("No extra collects should mean the character item is not"
                                                        " progression currently if the character does not unlock"
                                                        " levels")
                    non_level_access_character_items.append(item)
        self.random.shuffle(non_level_access_character_items)
        for item in non_level_access_character_items:
            extra_collects = item.collect_extras
            for extra_collect in extra_collects:
                # 3 is a magic number and could be changed if other values produce nicer results.
                if non_deprioritize_ability_counts[extra_collect] <= 3:
                    # One of the abilities is uncommon.
                    break
            else:
                # None of the abilities were uncommon, so add the deprioritize and skip balancing classifications.
                item.classification |= progression_deprioritized_skip_balancing
                # Reduce the remaining ability counts from non-deprioritized characters
                non_deprioritize_ability_counts.subtract(extra_collects)

        self.multiworld.itempool.extend(item_pool)

        if self._is_universal_tracker():
            # Universal Tracker deletes the items added to precollected_items by create_items, instead later creating
            # all items with create_item(), but starting characters need to be created before
            # self.starting_character_abilities is set to `starting_abilities` otherwise the starting characters will
            # lose all their abilities. To work around this, Universal Tracker is made to pretend that the starting
            # characters had no abilities, so no abilities will be stripped from any characters created later on with
            # create_item().
            self.starting_character_abilities = CharacterAbility.NONE

    def create_region(self, name: str) -> Region:
        r = Region(name, self.player, self.multiworld)
        self.multiworld.regions.append(r)
        return r

    def create_regions(self) -> None:
        regions.create_regions(self)
        # Check that the number of Gold Brick events created matched what was expected from the calculation in
        # generate_early.
        assert self.gold_brick_event_count == self.expected_gold_brick_event_count, \
            "Created Gold Bricks did not match expected Gold Bricks, something is wrong."

    def add_location(self, name: str, region: Region) -> LegoStarWarsTCSLocation:
        location = LegoStarWarsTCSLocation(self.player, name, self.location_name_to_id[name], region)
        region.locations.append(location)
        return location

    def add_shop_location(self, name: str, region: Region, purchase_cost: int) -> LegoStarWarsTCSLocation:
        location = LegoStarWarsTCSShopLocation(self.player, name, self.location_name_to_id[name], region, purchase_cost)
        region.locations.append(location)
        return location

    def add_event_pair(self, location_name: str, region: Region, item_name: str = "", hide_in_spoiler: bool = True
                       ) -> LegoStarWarsTCSLocation:
        if not item_name:
            item_name = location_name
        location = LegoStarWarsTCSLocation(self.player, location_name, None, region)
        # Showing in the spoiler is only useful if the event is randomized in some way.
        # This does no affect whether events are shown in a spoiler playthrough.
        location.show_in_spoiler = not hide_in_spoiler
        item = self.create_event(item_name)
        location.place_locked_item(item)
        region.locations.append(location)
        return location

    def add_gold_brick_event(self, location_name: str, region: Region) -> LegoStarWarsTCSLocation:
        self.gold_brick_event_count += 1
        return self.add_event_pair(location_name, region, GOLD_BRICK_EVENT_NAME)

    def set_abilities_rule(self, spot: Location | Entrance, abilities: CharacterAbility):
        player = self.player
        ability_names = cast(list[str], [ability.name for ability in abilities])
        if len(ability_names) == 0:
            set_rule(spot, Location.access_rule if isinstance(spot, Location) else Entrance.access_rule)
        elif len(ability_names) == 1:
            ability_name = ability_names[0]
            set_rule(spot, lambda state: state.has(ability_name, player))
        else:
            set_rule(spot, lambda state: state.has_all(ability_names, player))

    def set_any_abilities_rule(self, spot: Location | Entrance, *any_abilities: CharacterAbility):
        for any_ability in any_abilities:
            if not any_ability:
                # No requirements overrides any other ability requirements
                self.set_abilities_rule(spot, any_ability)
                return
        if not any_abilities:
            self.set_abilities_rule(spot, CharacterAbility.NONE)
            return
        any_abilities_set = set(any_abilities)
        if len(any_abilities_set) == 1:
            self.set_abilities_rule(spot, next(iter(any_abilities_set)))
        else:
            sorted_abilities = sorted(any_abilities_set, key=lambda a: (a.bit_count(), a.value))
            ability_names = [cast(list[str], [a.name for a in any_ability]) for any_ability in sorted_abilities]
            if all(len(names) == 1 for names in ability_names):
                # Optimize for all abilities being only a single flag each.
                singular_names = {names[0] for names in ability_names}
                set_rule(spot, lambda state, items_=tuple(singular_names), p=self.player: state.has_any(items_, p))
            else:
                def rule(state: CollectionState):
                    for names in ability_names:
                        if state.has_all(names, self.player):
                            return True
                    return False
                set_rule(spot, rule)

    def _get_score_multiplier_requirement(self, studs_cost: int):
        max_no_multiplier_cost = self.options.most_expensive_purchase_with_no_multiplier.value * 1000
        count: int
        if studs_cost <= max_no_multiplier_cost:
            count = 0
        elif studs_cost <= max_no_multiplier_cost * 2:
            count = 1  # x2
        elif studs_cost <= max_no_multiplier_cost * 8:
            count = 2  # x2 x4 = x8
        elif studs_cost <= max_no_multiplier_cost * 48:
            count = 3  # x2 x4 x6 = x48
        elif studs_cost <= max_no_multiplier_cost * 384:
            count = 4  # x2 x4 x6 x8 = x384
        elif studs_cost <= max_no_multiplier_cost * 3840:
            count = 5  # x2 x4 x6 x8 x10 = x3840
        else:
            # The minimum value of the option range guarantee that x3840 is enough to purchase everything.
            raise AssertionError(f"Studs cost {studs_cost} is too large. This is an error with the apworld.")

        return count

    def _add_score_multiplier_rule(self, spot: Location, studs_cost: int):
        count = self._get_score_multiplier_requirement(studs_cost)
        if count > 0:
            add_rule(spot, lambda state, p=self.player, c=count: state.has("Progressive Score Multiplier", p, c))

    def set_rules(self) -> None:
        player = self.player

        created_chapters = self.enabled_chapters

        # Episodes.
        for episode_number in range(1, 7):
            if episode_number not in self.enabled_episodes:
                continue
            episode_entrance = self.get_entrance(f"Episode {episode_number} Door")
            if self.options.episode_unlock_requirement == "episode_item":
                item = f"Episode {episode_number} Unlock"
                set_rule(episode_entrance, lambda state, item_=item: state.has(item_, player))
            elif self.options.episode_unlock_requirement == "open":
                pass
            else:
                self.raise_error(AssertionError, "Unreachable: Unexpected episode unlock requirement %s",
                                 self.options.episode_unlock_requirement)

            # Set chapter requirements.
            episode_chapters = EPISODE_TO_CHAPTER_AREAS[episode_number]
            for chapter_number, chapter in enumerate(episode_chapters, start=1):
                assert chapter.episode == episode_number
                assert chapter.number_in_episode == chapter_number
                if chapter.short_name not in created_chapters:
                    continue
                entrance = self.get_entrance(f"Episode {episode_number} Room, Chapter {chapter_number} Door")

                required_character_names = CHAPTER_AREA_STORY_CHARACTERS[chapter.short_name]
                if required_character_names:
                    if len(required_character_names) == 1:
                        item = next(iter(required_character_names))
                        set_rule(entrance, lambda state, item_=item: state.has(item_, player))
                    else:
                        items = tuple(sorted(required_character_names))
                        set_rule(entrance, lambda state, items_=items: state.has_all(items_, player))

                if (chapter.short_name == self.goal_chapter
                        and self.options.goal_chapter_locations_mode == GoalChapterLocationsMode.option_removed):
                    # There are no locations, so there is no logic.
                    continue

                entrance_abilities = CharacterAbility.NONE
                for character_name in required_character_names:
                    generic_character = CHARACTERS_AND_VEHICLES_BY_NAME[character_name]
                    entrance_abilities |= generic_character.abilities

                def set_chapter_spot_abilities_rule(spot: Location | Entrance, *abilities: CharacterAbility):
                    # Remove any requirements already satisfied by the chapter entrance before setting the rule.
                    self.set_any_abilities_rule(spot, *[ability & ~entrance_abilities for ability in abilities])

                # Set Power Brick logic. Score multiplier requirements are added later.
                power_brick = self.get_location(chapter.power_brick_location_name)
                set_chapter_spot_abilities_rule(power_brick, *chapter.power_brick_ability_requirements)

                # Set Minikits logic
                if self.options.enable_minikit_locations:
                    all_minikits_entrance = self.get_entrance(f"{chapter.name} - Collect All Minikits")
                    set_chapter_spot_abilities_rule(all_minikits_entrance, chapter.all_minikits_ability_requirements)

                # Set True Jedi logic
                if self.options.enable_true_jedi_locations and not self.options.easier_true_jedi:
                    if chapter.short_name in DIFFICULT_OR_IMPOSSIBLE_TRUE_JEDI:
                        true_jedi = self.get_location(f"{chapter.short_name} True Jedi")
                        set_rule(true_jedi, lambda state: state.has("Progressive Score Multiplier", player))

                # Ridesanity.
                for spot, ability_requirements in self.ridesanity_spots.get(chapter.short_name, ()):
                    set_chapter_spot_abilities_rule(spot, *ability_requirements)

        # Bonus levels.
        gold_brick_requirements: set[int] = set()
        for area in BONUS_AREAS:
            if area.name not in self.enabled_bonuses:
                continue
            # Gold brick requirements are set on entrances, so do not need to be set on the locations themselves.
            gold_brick_requirements.add(area.gold_bricks_required)
            completion = self.get_location(area.completion_location_name)
            if area.completion_ability_requirements:
                self.set_abilities_rule(completion, area.completion_ability_requirements)
            if area.item_requirements:
                add_rule(completion, lambda state, items_=area.item_requirements: state.has_all(items_, player))
            if area.gold_brick:
                gold_brick = self.get_location(f"{area.name} - Gold Brick")
                set_rule(gold_brick, completion.access_rule)
            # Ridesanity.
            for spot, ability_requirements in self.ridesanity_spots.get(area.name, ()):
                self.set_any_abilities_rule(spot, *ability_requirements)
        # Locations with 0 Gold Bricks required are added to the base Bonuses region.
        gold_brick_requirements.discard(0)

        for gold_brick_count in gold_brick_requirements:
            entrance = self.get_entrance(f"Collect {gold_brick_count} Gold Bricks")
            set_rule(
                entrance,
                lambda state, item_=GOLD_BRICK_EVENT_NAME, count_=gold_brick_count: state.has(item_, player, count_))

        # 'All Episodes' character unlocks.
        if self.options.enable_all_episodes_purchases:
            entrance = self.get_entrance("Unlock All Episodes")
            if self.options.all_episodes_character_purchase_requirements == "episodes_unlocked":
                entrance_unlocks = tuple([f"Episode {i} Unlock" for i in range(1, 7) if i in self.enabled_episodes])
                set_rule(entrance, lambda state, items_=entrance_unlocks, p=player: state.has_all(items_, p))
            elif self.options.all_episodes_character_purchase_requirements == "episodes_tokens":
                set_rule(entrance,
                         lambda state, p=player: state.has("Episode Completion Token", p, 6))

        # Cantina Ridesanity.
        # todo: Currently there are no rules because the player is always forced to start with a Jedi, but there will be
        #  rules in the future because (most) droids cannot ride things.
        for spot, ability_requirements in self.ridesanity_spots.get("cantina", ()):
            self.set_any_abilities_rule(spot, *ability_requirements)

        # Add Score Multiplier requirements to shop purchase locations.
        for loc in self.get_locations():
            if isinstance(loc, LegoStarWarsTCSShopLocation):
                self._add_score_multiplier_rule(loc, loc.studs_cost)

        # Victory.
        victory: Location | Entrance
        if self.goal_chapter:
            # When the goal chapter is enabled, the other goal requirements have to be completed before the goal chapter
            # can be accessed.
            goal_chapter = SHORT_NAME_TO_CHAPTER_AREA[self.goal_chapter]
            victory = self.get_entrance(
                f"Episode {goal_chapter.episode} Room, Chapter {goal_chapter.number_in_episode} Door")
        else:
            victory = self.get_location("Goal")
        # Minikits goal.
        if self.goal_minikit_count > 0:
            add_rule(victory, lambda state: state.has(self.minikit_bundle_name, player, self.goal_minikit_bundle_count))
        # Bosses goal.
        goal_boss_count = self.options.defeat_bosses_goal_amount.value
        if goal_boss_count > 0:
            if self.options.only_unique_bosses_count:
                bosses = {self.short_name_to_boss_character[chapter] for chapter in self.enabled_bosses}
                boss_items = sorted(f"{boss} Defeated" for boss in bosses)
                assert goal_boss_count <= len(boss_items)
                add_rule(
                    victory, (
                        lambda state, i_=tuple(boss_items), p_=player, c_=goal_boss_count:
                        state.has_from_list_unique(i_, p_, c_)
                    )
                )
            else:
                add_rule(victory, lambda state, p_=player, c_=goal_boss_count: state.has("Boss Defeated", p_, c_))
        # Area completion goal.
        goal_area_completions = self.goal_area_completion_count
        if goal_area_completions > 0:
            # "Level" here is as a user-facing term, with the meaning of "Area" internally.
            add_rule(victory, lambda state, p_=player, c_=goal_area_completions: state.has("Level Completion", p_, c_))
        # Kyber Bricks goal.
        if self.options.goal_requires_kyber_bricks:
            add_rule(victory, lambda state, p_=player: state.has("Kyber Brick", p_, 7))

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", player)

    @classmethod
    def stage_fill_hook(cls,
                        multiworld: MultiWorld,
                        progitempool: list[Item],
                        usefulitempool: list[Item],
                        filleritempool: list[Item],
                        fill_locations: list[Location],
                        ) -> None:
        game_players = multiworld.get_game_players(cls.game)
        # Get all player IDs that have progression classification minikits.
        minikit_player_ids = {player for player in game_players if multiworld.worlds[player].goal_minikit_count > 0}
        # Get the player IDs of those that are using minimal accessibility.
        minikit_minimal_player_ids = {player for player in game_players
                                      if multiworld.worlds[player].options.accessibility == "minimal"}

        def sort_func(item: Item):
            if item.player in minikit_player_ids and item.name in MINIKITS_BY_NAME:
                if item.player in minikit_minimal_player_ids:
                    # For minimal players, place goal macguffins first. This helps prevent fill from dumping logically
                    # relevant items into unreachable locations and reducing the number of reachable locations to fewer
                    # than the number of items remaining to be placed.
                    #
                    # Placing only the non-required goal macguffins first or slightly more than the number of
                    # non-required goal macguffins first was also tried, but placing all goal macguffins first seems to
                    # give fill the best chance of succeeding.
                    #
                    # All sizes of minikit bundles, are given the *deprioritized* classification for minimal players,
                    # which avoids them being placed on priority locations, which would otherwise occur due to them
                    # being sorted to be placed first.
                    return 1
                else:
                    # For non-minimal players, place goal macguffins last. The helps prevent fill from filling most/all
                    # reachable locations with the goal macguffins that are only required for the goal.
                    return -1
            else:
                # Python sorting is stable, so this will leave everything else in its original order.
                return 0

        progitempool.sort(key=sort_func)

    def collect(self, state: CollectionState, item: LegoStarWarsTCSItem) -> bool:
        changed = super().collect(state, item)
        if changed:
            extras = item.collect_extras
            if extras is not None:
                state.prog_items[self.player].update(extras)
            return True
        return False

    def remove(self, state: CollectionState, item: LegoStarWarsTCSItem) -> bool:
        changed = super().remove(state, item)
        if changed:
            extras = item.collect_extras
            if extras is not None:
                state.prog_items[self.player].subtract(extras)
            return True
        return False

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            # todo: A number of the slot data keys here could be inferred from what locations exist in the multiworld.
            "apworld_version": constants.AP_WORLD_VERSION,
            "enabled_chapters": sorted(self.enabled_chapters),
            "enabled_episodes": sorted(self.enabled_episodes),
            "enabled_bonuses": sorted(self.enabled_bonuses),
            "starting_chapter": self.starting_chapter.short_name,
            "starting_episode": self.starting_episode,
            "minikit_goal_amount": self.goal_minikit_count,
            "enabled_bosses": self.enabled_bosses,
            "goal_area_completion_count": self.goal_area_completion_count,
            "goal_chapter": self.goal_chapter,
            **self.options.as_dict(
                "received_item_messages",
                "checked_location_messages",
                "minikit_bundle_size",
                "episode_unlock_requirement",
                "all_episodes_character_purchase_requirements",
                "most_expensive_purchase_with_no_multiplier",
                "enable_bonus_locations",
                "enable_story_character_unlock_locations",
                "enable_all_episodes_purchases",
                "defeat_bosses_goal_amount",
                "only_unique_bosses_count",
                "defeat_bosses_goal_amount",
                "enable_minikit_locations",
                "enable_true_jedi_locations",
                "death_link",
                "death_link_amnesty",
                "vehicle_death_link_amnesty",
                "easier_true_jedi",
                "uncap_original_trilogy_high_jump",
                "scale_true_jedi_with_score_multipliers",
                "goal_requires_kyber_bricks",
                "goal_chapter_locations_mode",
                "minikit_goal_completion_method",
                "kyber_brick_goal_completion_method",
                "death_link_studs_loss",
                "death_link_studs_loss_scaling",
                "ridesanity",
                "enable_starting_extras_locations",
            )
        }

    @classmethod
    def stage_write_spoiler_header(cls, multiworld: MultiWorld, spoiler_handle: TextIO):
        spoiler_handle.write(f"Generated with {cls.game} Apworld version {constants.AP_WORLD_VERSION}\n")

    def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
        super().write_spoiler_header(spoiler_handle)

        spoiler_handle.write(f"Starting Chapter: {self.starting_chapter.short_name}\n")

        enabled_episodes = sorted(self.enabled_episodes)
        spoiler_handle.write(f"Enabled Episodes: {enabled_episodes}\n")

        enabled_chapters = sorted(self.enabled_chapters)
        spoiler_handle.write(f"Enabled Chapters: {enabled_chapters}\n")

        enabled_bonuses = sorted(self.enabled_bonuses)
        spoiler_handle.write(f"Enabled Bonuses: {enabled_bonuses}\n")

        enabled_bosses = sorted(self.enabled_bosses)
        spoiler_handle.write(f"Enabled Bosses: {enabled_bosses}\n")

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any] | None:
        slot_data_version = tuple(slot_data["apworld_version"])
        if slot_data_version != constants.AP_WORLD_VERSION:
            raise RuntimeError(f"LSW TCS version error: The version of the apworld used to generate this world"
                               f" ({slot_data_version}) does not match the version of your installed apworld"
                               f" ({constants.AP_WORLD_VERSION}).")
        return slot_data
