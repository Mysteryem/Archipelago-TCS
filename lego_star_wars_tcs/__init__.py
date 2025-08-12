import logging
import re
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

from . import constants
from .constants import CharacterAbility, GOLD_BRICK_EVENT_NAME
from .items import (
    ITEM_NAME_TO_ID,
    LegoStarWarsTCSItem,
    ExtraData,
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
)
from .levels import (
    BonusArea,
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
)
from .locations import LOCATION_NAME_TO_ID, LegoStarWarsTCSLocation, LEVEL_SHORT_NAMES_SET
from .options import (
    LegoStarWarsTCSOptions,
    StartingChapter,
    AllEpisodesCharacterPurchaseRequirements,
    MinikitGoalAmount,
    OnlyUniqueBossesCountTowardsGoal,
    OPTION_GROUPS,
)
from .item_groups import ITEM_GROUPS
from .location_groups import LOCATION_GROUPS


def launch_client():
    from .client import launch
    launch_subprocess(launch, name="LegoStarWarsTheCompleteSagaClient")


components.append(Component("Lego Star Wars: The Complete Saga Client",
                            func=launch_client,
                            component_type=Type.CLIENT))


class LegoStarWarsTCSWebWorld(WebWorld):
    theme = "partyTime"
    option_groups = OPTION_GROUPS
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide for setting up Lego Star Wars: The Complete Saga to be played in Archipelago.",
        "English",
        "lsw_tcs_en.md",
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
    enabled_episodes: set[int]
    enabled_bonuses: set[str]
    enabled_bosses: set[str]

    starting_chapter: str = "1-1"
    starting_episode: int = 1
    minikit_bundle_name: str = ""
    enabled_chapter_count: int = -1
    available_minikits: int = -1
    minikit_bundle_count: int = -1
    goal_minikit_count: int = -1
    goal_minikit_bundle_count: int = -1
    goal_boss_count: int = -1
    gold_brick_event_count: int = 0
    character_unlock_location_count: int = 0
    required_score_multiplier_count: int = 0  # set in create_regions

    def __init__(self, multiworld, player: int):
        super().__init__(multiworld, player)
        self.enabled_chapters = set()
        self.enabled_episodes = set()
        self.enabled_bonuses = set()
        self.character_chapter_access_counts = Counter()

    def _log_info(self, message: str, *args) -> None:
        logger.info("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def _log_warning(self, message: str, *args) -> None:
        logger.warning("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def _log_error(self, message: str, *args) -> None:
        logger.error("Lego Star Wars TCS (%s): " + message, self.player_name, *args)

    def _raise_error(self, ex_type: Callable[[str], Exception], message: str, *args) -> NoReturn:
        raise ex_type(("Lego Star Wars TCS (%s): " + message) % (self.player_name, *args))

    def _option_error(self, message: str, *args) -> NoReturn:
        self._raise_error(OptionError, message, *args)

    def _generate_early_pick_unique_enabled_bosses(self,
                                                   required_unique_boss_count: int,
                                                   allowed_boss_chapters: set[str],
                                                   tentative_enabled_chapters: list[str],
                                                   short_name_to_boss_character: dict[str, str]) -> set[str]:
        # Find the currently picked boss chapters and their indices. These will be updated in-place.
        picked_boss_indices: list[int] = [i for i, chapter in enumerate(tentative_enabled_chapters)
                                          if chapter in allowed_boss_chapters]
        picked_boss_chapters: set[str] = {tentative_enabled_chapters[i] for i in picked_boss_indices}
        # Additionally find the indices for each boss character in the currently picked boss chapters.
        picked_boss_characters_to_indices: dict[str, list[int]] = {}
        for i in picked_boss_indices:
            boss_chapter = tentative_enabled_chapters[i]
            boss_character = short_name_to_boss_character[boss_chapter]
            picked_boss_characters_to_indices.setdefault(boss_character, []).append(i)

        required_boss_chapter_count = self.options.enabled_bosses_count.value

        def need_more_unique_bosses() -> bool:
            return len(picked_boss_characters_to_indices) < required_unique_boss_count

        def need_more_boss_chapters() -> bool:
            return len(picked_boss_chapters) < required_boss_chapter_count

        if need_more_unique_bosses() or need_more_boss_chapters():
            # There are too few unique bosses or boss chapters present, more need to be enabled.
            # Replace the latest picked chapters.
            # If more unique bosses are needed, replace chapters that are not unique bosses, with chapters that have new
            # unique bosses.
            # If no more unique bosses are needed, but more boss chapters are needed, replace chapters that are not
            # bosses with new unique bosses, or duplicate bosses.
            # Deterministically shuffle for deterministic randomness in pick order.
            unpicked_boss_chapters = sorted(allowed_boss_chapters.difference(tentative_enabled_chapters))
            self.random.shuffle(unpicked_boss_chapters)

            def replace_chapter_at(i: int, boss_chapter_replacement: str):
                # Replace the chapter at index `i`.
                replaced_chapter = tentative_enabled_chapters[i]
                tentative_enabled_chapters[i] = boss_chapter_replacement

                # Add the replacement boss chapter to the set of enabled boss chapters.
                assert boss_chapter_replacement not in picked_boss_chapters
                picked_boss_chapters.add(boss_chapter_replacement)

                # Remove the replacement boss chapter from the chapters that have not been picked.
                unpicked_boss_chapters.remove(replacement_boss_chapter)

                # Add the index to the chapter indices of the boss of the replacement chapter.
                boss_character_replacement = short_name_to_boss_character[boss_chapter_replacement]
                boss_character_indices = picked_boss_characters_to_indices.setdefault(boss_character_replacement, [])
                assert i not in boss_character_indices
                boss_character_indices.append(i)

                if replaced_chapter in short_name_to_boss_character:
                    # The replaced chapter was a boss, so update the sets of enabled boss chapters and unpicked boss
                    # chapters.
                    picked_boss_chapters.remove(replaced_chapter)
                    assert replaced_chapter not in unpicked_boss_chapters
                    unpicked_boss_chapters.append(replaced_chapter)

                    # Remove the index from the chapter indices of the boss of the replaced chapter.
                    replaced_boss_character = short_name_to_boss_character[replaced_chapter]
                    boss_characters_indices = picked_boss_characters_to_indices[replaced_boss_character]
                    boss_characters_indices.remove(i)
                else:
                    # The replaced chapter was not a boss, but has been replaced by a boss, so add the current index to
                    # the picked indices.
                    picked_boss_indices.append(i)

            # Find unique bosses to pick from. The order of this dict is deterministically random because it is created
            # based on the order of `unpicked_boss_chapters`.
            unpicked_boss_characters_to_pick_from: dict[str, list[str]] = {}
            for boss_chapter in unpicked_boss_chapters:
                boss_character = short_name_to_boss_character[boss_chapter]
                assert boss_character is not None
                if boss_character not in picked_boss_characters_to_indices:
                    unpicked_boss_characters_to_pick_from.setdefault(
                        boss_character, []).append(boss_chapter)
            assert ((len(unpicked_boss_characters_to_pick_from) + len(picked_boss_characters_to_indices))
                    >= required_unique_boss_count), (
                "There are fewer unique bosses available than the number of required unique bosses."
                " This should not happen.")
            assert (len(unpicked_boss_chapters) + len(picked_boss_chapters)) >= required_boss_chapter_count, (
                "There are fewer boss chapters available than the number of required boss chapters."
                " This should not happen.")
            # Replace the latest picked chapters that are not unique bosses or not bosses depending on what is needed
            # most.
            reversed_indices = reversed(range(len(tentative_enabled_chapters)))
            for i in reversed_indices:
                chapter_to_replace = tentative_enabled_chapters[i]
                chapter_at_index_is_a_boss = chapter_to_replace in short_name_to_boss_character
                boss_character_to_replace = short_name_to_boss_character.get(chapter_to_replace, None)
                chapter_at_index_is_a_duplicated_boss = (
                        boss_character_to_replace is not None
                        and len(picked_boss_characters_to_indices[boss_character_to_replace]) > 1
                )

                if self.options.prefer_entire_episodes:
                    # Try to replace chapters with boss chapters from the same episode where possible when the option to
                    # prefer entire episodes is enabled.
                    preferred_episode_number_str = chapter_to_replace[0]
                else:
                    preferred_episode_number_str = None

                # Replace the removed chapter with a unique boss.
                replacement_boss_chapter: str
                replacement_boss_character: str
                if need_more_unique_bosses():
                    if chapter_at_index_is_a_boss and not chapter_at_index_is_a_duplicated_boss:
                        # The chapter at `i` is already a unique boss, so replacing the chapter cannot increase the
                        # number of unique bosses.
                        continue
                    # Iterate through all remaining enabled unique bosses to try to find one in the same episode.
                    for replacement_boss_character, boss_chapters in (
                            unpicked_boss_characters_to_pick_from.items()
                    ):
                        for replacement_boss_chapter in boss_chapters:
                            if (preferred_episode_number_str is None
                                    or replacement_boss_chapter[0] == preferred_episode_number_str):
                                # Suitable replacement found, so break the inner loop.
                                break
                        else:
                            # No break, so no suitable replacement found.
                            continue
                        # Suitable replacement found, so break.
                        break
                    else:
                        # No unique boss in the same episode was found, so pick the first boss in the dict to replace
                        # it.
                        it = iter(unpicked_boss_characters_to_pick_from.items())
                        replacement_boss_character, boss_chapters = next(it)
                        replacement_boss_chapter = boss_chapters[0]
                    # Remove the replacement boss character from the dict of extra, unique boss characters to pick from.
                    # There could be additional chapters that feature this boss, but now that the boss has been picked,
                    # those additional chapters would no longer feature a unique boss.
                    del unpicked_boss_characters_to_pick_from[replacement_boss_character]
                else:
                    if chapter_at_index_is_a_boss:
                        # The chapter at `i` is already a boss chapter, so replacing the chapter cannot increase the
                        # number of bosses.
                        continue
                    for replacement_boss_chapter in unpicked_boss_chapters:
                        if (preferred_episode_number_str is None
                                or replacement_boss_chapter[0] == preferred_episode_number_str):
                            # Suitable replacement found, so break.
                            break
                    else:
                        # No suitable replacement found, so pick the first boss chapter.
                        replacement_boss_chapter = unpicked_boss_chapters[0]

                # Replace the existing chapter with the replacement boss chapter, and update each of the containers for
                # this replacement.
                replace_chapter_at(i, replacement_boss_chapter)

                if not need_more_unique_bosses() and not need_more_boss_chapters():
                    # All needed replacements have been made.
                    break
        assert not need_more_unique_bosses()
        assert not need_more_boss_chapters()

        if len(picked_boss_chapters) > required_boss_chapter_count:
            # There are too many bosses enabled, so disable some bosses while ensuring that we don't go
            # under `required_unique_boss_count`
            remaining_unique_picks = list(picked_boss_characters_to_indices.values())
            # Pick unique bosses in the order they were initially picked.
            enabled_boss_indices = {indices.pop(0) for indices
                                    in remaining_unique_picks[:required_unique_boss_count]}
            extra_boss_chapters_needed = required_boss_chapter_count - len(enabled_boss_indices)
            # Pick extra boss chapters in the order they were initially picked.
            remaining_chapter_picks = [i for i in picked_boss_indices if i not in enabled_boss_indices]
            assert len(remaining_chapter_picks) >= extra_boss_chapters_needed
            enabled_boss_indices.update(remaining_chapter_picks[:extra_boss_chapters_needed])
            picked_boss_chapters = {tentative_enabled_chapters[i] for i in enabled_boss_indices}

        assert len(picked_boss_chapters) == required_boss_chapter_count
        return picked_boss_chapters

    def _generate_early_pick_enabled_bosses(self,
                                            allowed_boss_chapters: set[str],
                                            tentative_enabled_chapters: list[str]) -> set[str]:
        picked_bosses: set[str]
        picked_boss_indices: list[int] = [i for i, chapter in enumerate(tentative_enabled_chapters)
                                          if chapter in allowed_boss_chapters]

        missing_boss_chapter_count = self.options.enabled_bosses_count - len(picked_boss_indices)
        if missing_boss_chapter_count == 0:
            # The exact required number of bosses are present, so no changes are needed.
            picked_bosses = {tentative_enabled_chapters[i] for i in picked_boss_indices}
        elif missing_boss_chapter_count < 0:
            # Too many bosses are present, so pick only as many as needed.
            # If the starting chapter is a boss, always un-pick it first because starting with a boss level
            # is less interesting, especially if there is only one required boss.
            if picked_boss_indices[0] == 0:
                picked_boss_indices = picked_boss_indices[1:]
            chosen_boss_indices = self.random.sample(picked_boss_indices, k=self.options.enabled_bosses_count.value)
            picked_bosses = {tentative_enabled_chapters[i] for i in chosen_boss_indices}
        else:
            # There are too few bosses, so replace the latest picked chapters, that are not bosses, with
            # chapters that have bosses.
            extra_bosses_to_pick_from = sorted(allowed_boss_chapters.difference(tentative_enabled_chapters))
            self.random.shuffle(extra_bosses_to_pick_from)
            picked_bosses = {tentative_enabled_chapters[i] for i in picked_boss_indices}
            # Remove the latest picked chapters that are not bosses.
            picked_boss_indices_set = set(picked_boss_indices)
            reversed_indices = reversed(range(len(tentative_enabled_chapters)))
            replaced_chapters = []

            assert len(extra_bosses_to_pick_from) >= missing_boss_chapter_count, (
                "The number of extra bosses to pick from was less than the missing boss count")
            for i in reversed_indices:
                if i not in picked_boss_indices_set:
                    # The chapter is not a boss, so replace it.
                    chapter_to_replace = tentative_enabled_chapters[i]
                    # Replace the removed chapter with a boss in the same episode if possible.
                    preferred_episode_number_str = chapter_to_replace[0]
                    for j, boss in enumerate(reversed(extra_bosses_to_pick_from), start=1):
                        if boss[0] == preferred_episode_number_str:
                            del extra_bosses_to_pick_from[-j]
                            picked_bosses.add(boss)
                            tentative_enabled_chapters[i] = boss
                            break
                    else:
                        # No suitable boss was found. Pick the last one in the list to replace it.
                        boss = extra_bosses_to_pick_from.pop()
                        tentative_enabled_chapters[i] = boss
                        picked_bosses.add(boss)
                    replaced_chapters.append(chapter_to_replace)
                    if len(replaced_chapters) == missing_boss_chapter_count:
                        # All needed replacements have been made.
                        break
            assert len(replaced_chapters) == missing_boss_chapter_count, (
                "The number of replaced chapters did not match the missing boss count")
        return picked_bosses

    def generate_early(self) -> None:
        # Universal Tracker support.
        if passthrough := getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game):
            # Options directly from slot data.
            self.options.minikit_goal_amount.value = passthrough["minikit_goal_amount"]
            self.options.minikit_bundle_size.value = passthrough["minikit_bundle_size"]
            self.options.episode_unlock_requirement.value = passthrough["episode_unlock_requirement"]
            self.options.all_episodes_character_purchase_requirements.value = (
                passthrough["all_episodes_character_purchase_requirements"])
            self.options.most_expensive_purchase_with_no_multiplier.value = (
                passthrough["most_expensive_purchase_with_no_multiplier"])
            self.options.enable_bonus_locations.value = passthrough["enable_bonus_locations"]
            self.options.enable_story_character_unlock_locations.value = (
                passthrough["enable_story_character_unlock_locations"])
            self.options.enable_all_episodes_purchases.value = passthrough["enable_all_episodes_purchases"]
            self.options.defeat_bosses_goal_amount.value = passthrough["defeat_bosses_goal_amount"]
            self.options.only_unique_bosses_count.value = passthrough["only_unique_bosses_count"]
            self.options.defeat_bosses_goal_amount.value = passthrough["defeat_bosses_goal_amount"]
            self.options.enable_minikit_locations.value = passthrough["enable_minikit_locations"]
            self.options.enable_true_jedi_locations.value = passthrough["enable_true_jedi_locations"]

            # Attributes normally derived from options during generate_early.
            self.enabled_chapters = set(passthrough["enabled_chapters"])
            self.enabled_chapter_count = len(self.enabled_chapters)
            self.enabled_episodes = set(passthrough["enabled_episodes"])
            # The enabled bonuses are set depending on the number of Gold Bricks available
            # self.enabled_bonuses = set(passthrough["enabled_bonuses"])
            self.starting_chapter = passthrough["starting_chapter"]
            self.starting_episode = passthrough["starting_episode"]
            # Derived Minikit attributes.
            self.available_minikits = self.enabled_chapter_count * 10
            bundle_size = self.options.minikit_bundle_size.value
            self.minikit_bundle_name = MINIKITS_BY_COUNT[bundle_size].name
            self.minikit_bundle_count = (self.available_minikits // bundle_size
                                         + (self.available_minikits % bundle_size != 0))
            self.enabled_bosses = set(passthrough["enabled_bosses"])

            # Override options with their derived/rolled values.
            # Override the enable_chapter count to match the number that are enabled.
            self.options.enabled_chapters_count.value = len(self.enabled_chapters)
            # Unrandomize the starting chapter choice with the starting chapter that was actually picked.
            self.options.starting_chapter.set_from_string(self.starting_chapter)
            # Override the allowed chapters with all the chapters that rolled as enabled.
            self.options.allowed_chapters.value = set(self.enabled_chapters)
            # Act as if there was no filtering of allowed chapter types.
            self.options.allowed_chapter_types.set_from_string("all")

        # Normal options parsing.
        else:
            options = self.options

            bosses_required_for_goal = options.defeat_bosses_goal_amount > 0
            # -1 uses the percentage option, which is always greater than zero.
            minikits_required_for_goal = options.minikit_goal_amount != 0

            # Check that at least one goal is enabled.
            # -1 for minikit goal uses a percentage option that is never 0.
            if not bosses_required_for_goal and not minikits_required_for_goal:
                self._option_error("At least one goal must be enabled.")

            # Determine all available chapters to pick from.
            allowed_chapters: set[str] = options.allowed_chapters.value_ungrouped

            allowed_boss_chapters: set[str]
            if bosses_required_for_goal:
                # Update allowed chapters with allowed bosses.
                allowed_boss_chapters = {BOSS_UNIQUE_NAME_TO_CHAPTER[unique_boss].short_name
                                         for unique_boss in options.allowed_bosses.value}
                allowed_chapters.update(allowed_boss_chapters)
            else:
                allowed_boss_chapters = set()

            # Remove vehicle chapters if vehicle chapters are not allowed.
            if options.allowed_chapter_types == "no_vehicles":
                allowed_chapters.difference_update(VEHICLE_CHAPTER_SHORTNAMES)
                allowed_boss_chapters.difference_update(VEHICLE_CHAPTER_SHORTNAMES)

            # Determine starting chapters to pick from.
            starting_chapters: set[str]
            starting_chapter_option = self.options.starting_chapter
            if starting_chapter_option == StartingChapter.option_random_chapter:
                starting_chapters = allowed_chapters.copy()
            elif starting_chapter_option == StartingChapter.option_random_non_vehicle:
                starting_chapters = set(LEVEL_SHORT_NAMES_SET).difference(VEHICLE_CHAPTER_SHORTNAMES)
            elif starting_chapter_option == StartingChapter.option_random_vehicle:
                if options.allowed_chapter_types == "no_vehicles":
                    self._option_error("'random_vehicle' starting Chapter cannot be used when Allowed Chapter Types is"
                                       " set to 'no_vehicles'.")
                starting_chapters = set(VEHICLE_CHAPTER_SHORTNAMES)
            elif match := re.fullmatch(r"random_episode_([1-6])", starting_chapter_option.current_key):
                episode = int(match.group(1))
                starting_chapters = {chapter.short_name for chapter in EPISODE_TO_CHAPTER_AREAS[episode]}
            else:
                starting_chapter = starting_chapter_option.current_key
                assert starting_chapter in LEVEL_SHORT_NAMES_SET
                starting_chapters = {starting_chapter}
                # If a singular starting chapter was chosen, but not in the allowed chapters set, forcefully add it.
                # This should give a better generation experience to players intending to run fully random yamls.
                if starting_chapter not in allowed_chapters:
                    self._log_warning("The individually chosen starting chapter '%s' was not in the set of allowed"
                                      " chapters %s. '%s' has been forcefully allowed to prevent generation failure.",
                                      starting_chapter,
                                      sorted(allowed_chapters),
                                      starting_chapter)
                    allowed_chapters.add(starting_chapter)
                    # Add the forced starting chapter to allowed_bosses if it was an allowed boss originally.
                    if bosses_required_for_goal:
                        unique_boss_name = SHORT_NAME_TO_CHAPTER_AREA[starting_chapter].unique_boss_name
                        if unique_boss_name in options.allowed_bosses.value:
                            allowed_boss_chapters.add(starting_chapter)
            # Filter to only the chapters that are allowed to be enabled.
            allowed_starting_chapters = allowed_chapters.intersection(starting_chapters)
            if not allowed_starting_chapters:
                self._option_error("None of the chosen possible starting chapters were chosen to be possible to be"
                                   " enabled."
                                   " At least one starting chapter must be allowed to be enabled."
                                   "\nPossible starting chapters:"
                                   "\n\t%s (%s)"
                                   "\nAllowed chapters:"
                                   "\n\t%s (allowed chapters) + %s (allowed boss chapters) (%s)",
                                   starting_chapter_option.current_key,
                                   sorted(starting_chapters),
                                   sorted(options.allowed_chapters.value),
                                   sorted(allowed_boss_chapters),
                                   sorted(allowed_chapters))

            assert len(allowed_chapters) >= 1

            if bosses_required_for_goal and not allowed_boss_chapters:
                self._option_error("Defeating bosses is required for the goal, but no boss chapters were allowed to be"
                                   " enabled.")

            # Adjust the count of enabled chapters and warn if it was higher than the number of allowed chapters.
            if options.enabled_chapters_count > len(allowed_chapters):
                self._log_warning("Enabled chapter count (%i) was set higher than the number of allowed chapters (%i),"
                                  " it has been reduced to the number of allowed chapters (%i).",
                                  options.enabled_chapters_count.value,
                                  len(allowed_chapters),
                                  len(allowed_chapters))
                options.enabled_chapters_count.value = len(allowed_chapters)

            # If the Minikits goal is enabled, but Minikit locations are disabled, force Minikit bundle size to 10
            # -1 is the "use_percentage" value, which is always non-zero
            if (options.minikit_goal_amount != 0
                    and not options.enable_minikit_locations
                    and options.minikit_bundle_size != 10):
                self._log_warning("The Minikits goal is enabled, but Minikit locations are disabled, so the Minikit"
                                  " Bundle size has been forcefully set to 10, otherwise there would not be enough"
                                  " locations to place all the Minikits")
                options.minikit_bundle_size.value = 10

            # Determine unique allowed boss characters.
            maximum_boss_chapters = len(allowed_boss_chapters)
            unique_allowed_boss_characters: set[str] = set()
            unique_bosses_only = options.only_unique_bosses_count != OnlyUniqueBossesCountTowardsGoal.option_disabled
            unique_bosses_anakin_as_darth_vader = (
                    options.only_unique_bosses_count
                    == OnlyUniqueBossesCountTowardsGoal.option_enabled_and_count_anakin_as_vader
            )
            if unique_bosses_only:
                short_name_to_boss_character: dict[str, str] = {}
                for chapter in allowed_boss_chapters:
                    boss_character = SHORT_NAME_TO_CHAPTER_AREA[chapter].boss
                    if unique_bosses_anakin_as_darth_vader and boss_character == "Anakin Skywalker":
                        boss_character = "Darth Vader"
                    assert boss_character is not None
                    unique_allowed_boss_characters.add(boss_character)
                    short_name_to_boss_character[chapter] = boss_character
                maximum_unique_boss_characters = len(unique_allowed_boss_characters)
                # The number of unique allowed boss characters is always less than or equal to the number of allowed
                # boss chapters because there can be chapters that have the same boss character.
                assert maximum_unique_boss_characters <= maximum_boss_chapters
            else:
                maximum_unique_boss_characters = -1
                short_name_to_boss_character = {}

            # If the starting chapter cannot be a boss chapter, then the maximum possible number of bosses is 1 fewer.
            starting_chapter_cannot_be_a_boss = allowed_starting_chapters.isdisjoint(allowed_boss_chapters)
            if starting_chapter_cannot_be_a_boss:
                maximum_boss_chapters = min(options.enabled_chapters_count.value - 1, maximum_boss_chapters)
            else:
                maximum_boss_chapters = min(options.enabled_chapters_count.value, maximum_boss_chapters)

            # Update the maximum unique bosses count.
            maximum_unique_boss_characters = min(maximum_unique_boss_characters, maximum_boss_chapters)

            if unique_bosses_only:
                maximum_bosses_for_goal = maximum_unique_boss_characters
            else:
                maximum_bosses_for_goal = maximum_boss_chapters

            # Reduce boss goal count if it is too high. Error in the case of the boss goal not being possible to keep
            # enabled.
            if options.defeat_bosses_goal_amount > maximum_bosses_for_goal:
                if maximum_boss_chapters == 0:
                    assert options.enabled_chapters_count.value == 1
                    self._option_error("Only one Chapter is enabled, but none of the allowed starting chapters were"
                                       " also an allowed boss, and the goal requires defeating bosses.")
                else:
                    self._log_warning("The number of bosses to defeat as part of the goal was %i, but the maximum"
                                      " number of bosses that were allowed to be enabled was %i. The number of bosses"
                                      " to defeat as part of the goal has been reduced to %i.",
                                      options.defeat_bosses_goal_amount.value,
                                      maximum_bosses_for_goal,
                                      maximum_bosses_for_goal)
                    options.defeat_bosses_goal_amount.value = maximum_bosses_for_goal

            # The bosses goal amount should not change beyond this point.
            goal_boss_count = options.defeat_bosses_goal_amount.value

            # Warn and increase the enabled bosses count if it is lower than the goal amount.
            if options.enabled_bosses_count < options.defeat_bosses_goal_amount:
                self._log_warning("The number of enabled bosses was %i, but the number of bosses to defeat as part of"
                                  " the goal was %i. The number of enabled bosses has been increased to %i.",
                                  options.enabled_bosses_count.value,
                                  options.defeat_bosses_goal_amount.value,
                                  options.defeat_bosses_goal_amount.value)
                options.enabled_bosses_count.value = options.defeat_bosses_goal_amount.value

            # Warn and decrease the enabled bosses count if it is higher than the maximum bosses count.
            if options.enabled_bosses_count > maximum_boss_chapters:
                self._log_warning("The number of enabled bosses was %i, but the maximum number of bosses that were"
                                  " allowed to be enabled was %i. The number of enabled bosses has been reduced to %i.",
                                  options.enabled_bosses_count.value,
                                  maximum_boss_chapters,
                                  maximum_boss_chapters)
                options.enabled_bosses_count.value = maximum_boss_chapters

            # If every chapter is a boss chapter, then the starting chapter must also be a boss chapter.
            if options.enabled_bosses_count == options.enabled_chapters_count:
                assert not starting_chapter_cannot_be_a_boss
                allowed_starting_chapters.intersection_update(allowed_boss_chapters)

            # Pick the starting chapter.
            self.starting_chapter = self.random.choice(sorted(allowed_starting_chapters))
            self.starting_episode = SHORT_NAME_TO_CHAPTER_AREA[self.starting_chapter].episode

            # Pick enabled chapters and therefore enabled episodes.
            # Sort once to ensure deterministic generation.
            non_starting_allowed_chapters = sorted(allowed_chapters - {self.starting_chapter})
            self.random.shuffle(non_starting_allowed_chapters)
            # Determine preferred chapters and then sort again to put any preferred chapters first.
            preferred_chapters = self.options.preferred_chapters.value_ungrouped
            if preferred_chapters:
                non_starting_allowed_chapters.sort(key=lambda chapter: -1 if chapter in preferred_chapters else 0)
            # If enabled, sort the allowed chapters into the order of the first occurrence of each episode.
            if self.options.prefer_entire_episodes:
                # The starting chapter is considered the first picked chapter.
                initial_pick_order = [self.starting_chapter, *non_starting_allowed_chapters]
                seen_episodes = 0
                episode_pick_order: dict[str, int] = {}
                for chapter in initial_pick_order:
                    episode_str = chapter[0]
                    if episode_str in episode_pick_order:
                        continue
                    episode_pick_order[episode_str] = seen_episodes
                    seen_episodes += 1
                non_starting_allowed_chapters.sort(key=lambda s: episode_pick_order[s[0]])
            # Ensure there are enough bosses enabled and randomly disable any extra bosses if there are too many.
            tentative_enabled_chapters = [
                self.starting_chapter,
                *non_starting_allowed_chapters[:options.enabled_chapters_count.value - 1],
            ]
            if bosses_required_for_goal:
                if unique_bosses_only:
                    # The number of bosses is counted by the number of unique boss characters.
                    enabled_bosses = self._generate_early_pick_unique_enabled_bosses(
                        goal_boss_count, allowed_boss_chapters, tentative_enabled_chapters,
                        short_name_to_boss_character)
                    enabled_unique_bosses = {short_name_to_boss_character[chapter] for chapter in enabled_bosses}
                    assert len(enabled_unique_bosses) >= goal_boss_count
                else:
                    # Each boss counts separately, even if some bosses use the same boss character.
                    enabled_bosses = self._generate_early_pick_enabled_bosses(
                        allowed_boss_chapters, tentative_enabled_chapters)
                assert len(enabled_bosses) == self.options.enabled_bosses_count.value
                self.enabled_bosses = enabled_bosses
            else:
                self.enabled_bosses = set()

            # Finally set the enabled chapters.
            self.enabled_chapters = set(tentative_enabled_chapters)
            self.enabled_episodes = {SHORT_NAME_TO_CHAPTER_AREA[s].episode for s in self.enabled_chapters}
            self.enabled_chapter_count = len(self.enabled_chapters)
            if self.options.all_episodes_character_purchase_requirements == "episodes_unlocked":
                # Only warn if the 'All Episodes' character shop purchases are enabled.
                warn = self.options.enable_all_episodes_purchases.value
                if self.options.episode_unlock_requirement == "open":
                    if warn:
                        self._log_warning("'All Episodes' character shop unlocks were set to require 'Episodes Tokens' "
                                          " instead of 'Episodes Unlocked' because Episode unlock requirements were"
                                          " set to 'Open'")
                    tokens = AllEpisodesCharacterPurchaseRequirements.option_episodes_tokens
                    option = self.options.all_episodes_character_purchase_requirements
                    option.value = tokens
                elif len(self.enabled_episodes) == 1:
                    if warn:
                        self._log_warning("'All Episodes' character shop unlocks were set to require 'Episodes Tokens'"
                                          " from 'Episodes Unlocked' because there is only 1 Episode enabled.")
                    tokens = AllEpisodesCharacterPurchaseRequirements.option_episodes_tokens
                    option = self.options.all_episodes_character_purchase_requirements
                    option.value = tokens

            # Minikit options.
            bundle_size = self.options.minikit_bundle_size.value
            self.minikit_bundle_name = MINIKITS_BY_COUNT[bundle_size].name
            # todo?: Set self.available_minikits = 0 when self.options.minikit_goal_amount.value == 0 to remove minikits
            #  from the item pool?
            if self.options.minikit_goal_amount != 0 or self.options.enable_minikit_locations:
                self.available_minikits = self.enabled_chapter_count * 10  # 10 Minikits per chapter.
                self.minikit_bundle_count = (self.available_minikits // bundle_size
                                             + (self.available_minikits % bundle_size != 0))
            else:
                self.available_minikits = 0
                self.minikit_bundle_count = 0

            # Adjust Minikit options.
            if self.options.minikit_goal_amount.value > self.available_minikits:
                self._log_warning("The number of minikits required to goal (%i) was higher than the number of available"
                                  " minikits (%i). The number of minikits required to goal has been reduced to the"
                                  " number of available minikits (%i).",
                                  self.options.minikit_goal_amount.value,
                                  self.available_minikits,
                                  self.available_minikits)
                self.options.minikit_goal_amount.value = self.available_minikits

            # Sanity check Filler Weights options.
            if (self.options.filler_weight_characters
                    + self.options.filler_weight_extras
                    + self.options.filler_weight_junk == 0):
                self._option_error("At least one Filler Weight option must be set greater than zero")

        # Calculate goal_minikit_count when set to a percentage of the available minikits.
        if self.options.minikit_goal_amount == MinikitGoalAmount.special_range_names["use_percentage_option"]:
            self.goal_minikit_count = max(1, round(
                self.available_minikits * self.options.minikit_goal_amount_percentage / 100))
        else:
            self.goal_minikit_count = self.options.minikit_goal_amount.value

        # Only whole bundles are counted for logic, so any partial bundles require an extra whole bundle to goal.
        self.goal_minikit_bundle_count = (self.goal_minikit_count // bundle_size
                                          + (self.goal_minikit_count % bundle_size != 0))

        self.prog_useful_level_access_threshold_count = int(
            self.PROG_USEFUL_LEVEL_ACCESS_THRESHOLD_PERCENT * self.enabled_chapter_count)

        if self.options.enable_story_character_unlock_locations:
            # There are often multiple Chapters that can send each Story character unlock location, so enable path
            # display in spoilers with paths enabled.
            self.topology_present = True

        # Debug check to help with comparing passthrough values
        # for k, v in vars(self).items():
        #     print(f"{k}: {v}")
        #
        # if not passthrough:
        #     self.multiworld.re_gen_passthrough = {self.game: self.fill_slot_data()}
        #     # Recursive call, but with passthrough this time.
        #     self.generate_early()
        # else:
        #     # No recursive call the second time around.
        #     return

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
            elif name in ALL_AREA_REQUIREMENT_CHARACTERS:
                classification = ItemClassification.progression
            elif abilities & constants.RARE_AND_USEFUL_ABILITIES:
                # These abilities are typically much less common, so the characters should never be given skip_balancing
                # classification.
                classification = ItemClassification.progression
            elif abilities:
                if self.options.filler_reserve_characters:
                    # Characters with only very common abilities are not worth spending time moving in progression
                    # balancing because there is usually such a large number of them in the item pool.
                    classification = ItemClassification.progression_skip_balancing
                else:
                    # Assume that there won't be many characters in the pool, so don't skip progression balancing.
                    # It is possible for there to still be many characters in the item pool if the filler weight for
                    # characters is high, however, for simplicity, it is assumed that there won't be many characters.
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
                    classification = ItemClassification.progression_skip_balancing
                else:
                    classification = ItemClassification.filler
            elif name == "Progressive Score Multiplier":
                # todo: Vary between progression and progression_skip_balancing depending on what percentage of
                #  locations need them. Make them Useful if none are needed.
                # Generic item that grants Score multiplier Extras, which are used in logic for purchases from the shop.
                classification = ItemClassification.progression
            elif name == "All Episodes Token":
                # Very few location checks.
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
        return "Purple Stud"

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
        # todo: Reserve spaces in the item pool for vehicles and non-vehicles separately, based on how many locations
        #  unlock characters of the each type.
        vehicle_chapters_enabled = not VEHICLE_CHAPTER_SHORTNAMES.isdisjoint(self.enabled_chapters)
        possible_pool_character_items = {name: char for name, char in CHARACTERS_AND_VEHICLES_BY_NAME.items()
                                         if char.is_sendable and (vehicle_chapters_enabled
                                                                  or char.item_type != "Vehicle")}
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
        for name in CHAPTER_AREA_STORY_CHARACTERS[self.starting_chapter]:
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

        effective_item_classifications, effective_item_collect_extras = (
            self._get_effective_item_data(starting_abilities)
        )
        self.starting_character_abilities = starting_abilities

        # Determine what abilities must be supplied by the item pool for all locations to be reachable with all items in
        # the item pool.
        required_character_abilities_in_pool = CharacterAbility.NONE
        for shortname in self.enabled_chapters:
            power_brick_abilities = POWER_BRICK_REQUIREMENTS[shortname][1]
            if power_brick_abilities is not None:
                if isinstance(power_brick_abilities, tuple):
                    # Pick any one of the required abilities at random.
                    required_character_abilities_in_pool |= self.random.choice(power_brick_abilities)
                else:
                    required_character_abilities_in_pool |= power_brick_abilities
            required_character_abilities_in_pool |= ALL_MINIKITS_REQUIREMENTS[shortname]
        for bonus_name in self.enabled_bonuses:
            area = BONUS_NAME_TO_BONUS_AREA[bonus_name]
            required_character_abilities_in_pool |= area.ability_requirements
        # Remove counts <= 0.
        level_access_character_counts = +self.character_chapter_access_counts
        for name in level_access_character_counts.keys():
            required_character_abilities_in_pool &= ~CHARACTERS_AND_VEHICLES_BY_NAME[name].abilities
        required_character_abilities_in_pool &= ~starting_abilities

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

        if self.options.start_with_detectors:
            detectors = {"Minikit Detector", "Power Brick Detector"}
            assert detectors <= set(EXTRAS_BY_NAME.keys())
            non_required_extras = [name for name, extra in EXTRAS_BY_NAME.items()
                                   if extra.is_sendable and name not in detectors]
            for detector in sorted(detectors):
                self.push_precollected(self.create_item(detector))
        else:
            non_required_extras = [name for name, extra in EXTRAS_BY_NAME.items() if extra.is_sendable]

        required_score_multipliers = self.required_score_multiplier_count
        non_required_score_multipliers = 5 - required_score_multipliers
        assert 0 <= required_score_multipliers <= 5
        pool_required_extras = ["Progressive Score Multiplier"] * required_score_multipliers
        non_required_extras.extend(["Progressive Score Multiplier"] * non_required_score_multipliers)

        required_characters_count = len(pool_required_characters)
        required_extras_count = len(pool_required_extras)

        # Try to add as many characters to the pool as this.
        reserved_character_location_count: int
        free_character_location_count: int
        if self.options.filler_reserve_characters:
            reserved_character_location_count = self.character_unlock_location_count
            free_character_location_count = 0
        else:
            reserved_character_location_count = min(required_characters_count, self.character_unlock_location_count)
            free_character_location_count = self.character_unlock_location_count - reserved_character_location_count

        # Try to create as many Extras as this.
        reserved_power_brick_location_count: int
        free_extra_location_count: int
        if self.options.filler_reserve_extras:
            reserved_power_brick_location_count = self.enabled_chapter_count
            free_extra_location_count = 0
        else:
            reserved_power_brick_location_count = min(required_extras_count, self.enabled_chapter_count)
            free_extra_location_count = self.enabled_chapter_count - reserved_power_brick_location_count

        # As many minikit bundles as this will always be created. This may be fewer than is required to goal, but
        # reducing the total bundle count can make a seed longer, so all minikit bundles should be considered to be
        # required.
        required_minikit_location_count = self.minikit_bundle_count

        # The vanilla rewards for these are Gold Bricks, which are events, so these are effectively free locations for
        # any kind of item when enabled.
        if self.options.enable_true_jedi_locations:
            true_jedi_location_count = self.enabled_chapter_count
        else:
            true_jedi_location_count = 0
        completion_location_count = self.enabled_chapter_count + len(self.enabled_bonuses)
        if self.options.enable_minikit_locations:
            free_minikit_location_count = self.enabled_chapter_count * 10 - required_minikit_location_count
        else:
            if self.options.minikit_goal_amount != 0:
                assert self.options.minikit_bundle_size == 10
                assert self.minikit_bundle_name == "10 Minikits"
                assert self.minikit_bundle_count == self.enabled_chapter_count
                # Consume the free Chapter Completion locations to fit the Minikits.
                completion_location_count -= self.enabled_chapter_count
                free_minikit_location_count = 0
            else:
                assert required_minikit_location_count == 0
                free_minikit_location_count = 0

        free_location_count = (
                completion_location_count
                + true_jedi_location_count
                + free_minikit_location_count
                + free_character_location_count
                + free_extra_location_count
        )

        assert free_location_count >= 0, "initial free_location_count should always be >= 0"

        episode_related_items = []
        # A few free locations may need to be used for episode unlock items and/or episode tokens.
        if self.options.episode_unlock_requirement == "episode_item":
            for i in self.enabled_episodes:
                if i != self.starting_episode:
                    episode_related_items.append(f"Episode {i} Unlock")
        if self.options.all_episodes_character_purchase_requirements == "episodes_tokens":
            for _ in range(len(self.enabled_episodes)):
                episode_related_items.append("All Episodes Token")

        free_location_count -= len(episode_related_items)

        if free_location_count < 0:
            needed = -free_location_count
            # Subtract from reserved, but not required, counts.
            ok_to_replace_character_count = max(0, reserved_character_location_count - required_characters_count)
            ok_to_replace_extras_count = max(0, reserved_power_brick_location_count - required_extras_count)
            total_replaceable = ok_to_replace_character_count + ok_to_replace_extras_count
            if needed > total_replaceable:
                self._option_error("There are not enough locations to fit all required items. Enabled")
            character_percentage = ok_to_replace_character_count / total_replaceable
            character_subtract = min(needed, round(character_percentage * needed))
            extra_subtract = needed - character_subtract
            reserved_character_location_count -= character_subtract
            reserved_power_brick_location_count -= extra_subtract
            free_location_count = 0

        assert free_location_count >= 0, "free_location_count must always be >= 0"

        unfilled_locations = self.multiworld.get_unfilled_locations(self.player)
        num_to_fill = len(self.multiworld.get_unfilled_locations(self.player))

        assert num_to_fill == (
                reserved_character_location_count
                + reserved_power_brick_location_count
                + required_minikit_location_count
                + free_location_count
                + len(episode_related_items)
        )

        required_extras_count = len(pool_required_extras)
        required_excludable_count = sum(loc.progress_type == LocationProgressType.EXCLUDED for loc in unfilled_locations)

        if free_location_count < required_excludable_count:
            # This shouldn't really happen unless basically the entire world is excluded and/or barely any locations
            # are enabled.
            needed = required_excludable_count - free_location_count
            # Find how many character/extra locations can be used for filler placement without issue.
            ok_to_replace_character_count = max(0, reserved_character_location_count - required_characters_count)
            ok_to_replace_extras_count = max(0, reserved_power_brick_location_count - required_extras_count)
            total_replaceable = ok_to_replace_extras_count + ok_to_replace_extras_count
            if needed > total_replaceable:
                # There are too many non-excludable items for the number of excluded locations.
                # Give up.
                # If this is too common of an issue, it would be possible to add some of the required characters/extras
                # to start inventory instead of erroring here.
                non_excluded_count = num_to_fill - required_excludable_count
                required_count = required_extras_count + required_characters_count + required_minikit_location_count
                self._option_error("There are too few non-excluded locations to fit all required progression items."
                                   " There are %i non-excluded locations, but there are %i required items.",
                                   non_excluded_count,
                                   required_count)
            character_percentage = ok_to_replace_character_count / total_replaceable
            character_subtract = min(needed, round(character_percentage * needed))
            extra_subtract = needed - character_subtract
            reserved_character_location_count -= character_subtract
            reserved_power_brick_location_count -= extra_subtract
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
        for name in episode_related_items:
            add_to_pool(create_item(name))
        num_to_fill -= len(episode_related_items)

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
                self._log_warning("There were not enough locations to add all required characters to the item pool,"
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
        if reserved_power_brick_location_count < required_extras_count:
            to_subtract = required_extras_count - reserved_power_brick_location_count
            if free_location_count < to_subtract:
                start_inventory_required_extras_count = to_subtract - free_location_count
                self._log_warning("There were not enough locations to add all required Extras to the item pool,"
                                  " some of them have been added to starting inventory")
                free_location_count = 0
            else:
                free_location_count -= to_subtract
                start_inventory_required_extras_count = 0
            reserved_power_brick_location_count = 0
        else:
            reserved_power_brick_location_count -= required_extras_count
            start_inventory_required_extras_count = 0

        self.random.shuffle(pool_required_extras)
        pool_required_extras = pool_required_extras[start_inventory_required_extras_count:]
        start_required_extras = pool_required_extras[:start_inventory_required_extras_count]
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

        picked_extras = non_required_extras[:reserved_power_brick_location_count]
        leftover_extras = non_required_extras[reserved_power_brick_location_count:]
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

        def create_excludable_junk_items(count: int):
            # Only Purple Studs currently.
            # names = self.random.choices(
            #     ["Purple Stud", "Power Up", "Upgrade Studs"],
            #     [100, 5, 5],
            #     k=count)
            # return [create_item(name) for name in names]
            return [create_item("Purple Stud") for _ in range(count)]

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

        self.multiworld.itempool.extend(item_pool)

    def create_region(self, name: str) -> Region:
        r = Region(name, self.player, self.multiworld)
        self.multiworld.regions.append(r)
        return r

    def create_regions(self) -> None:
        # Create the origin region.
        cantina = self.create_region(self.origin_region_name)

        # Double check that the minikit counts is as expected.
        available_minikits_check = 0

        # All regions that connect to story character unlock regions.
        story_character_unlock_regions: dict[str, list[Region]] = {}

        for episode_number in range(1, 7):
            if episode_number not in self.enabled_episodes:
                continue
            episode_room = self.create_region(f"Episode {episode_number} Room")
            cantina.connect(episode_room, f"Episode {episode_number} Door")

            episode_chapters = EPISODE_TO_CHAPTER_AREAS[episode_number]
            for chapter_number, chapter in enumerate(episode_chapters, start=1):
                if chapter.short_name not in self.enabled_chapters:
                    continue
                # Update the count of how many chapters this character blocks access to.
                self.character_chapter_access_counts.update(chapter.character_requirements)
                chapter_region = self.create_region(chapter.name)

                entrance_name = f"Episode {episode_number} Room, Chapter {chapter_number} Door"
                episode_room.connect(chapter_region, entrance_name)

                # Completion.
                completion_name = f"{chapter.short_name} Completion"
                completion_loc = LegoStarWarsTCSLocation(self.player, completion_name,
                                                         self.location_name_to_id[completion_name], chapter_region)
                chapter_region.locations.append(completion_loc)
                if self.options.enable_bonus_locations:
                    # Completion Gold Brick event.
                    completion_gold_brick = LegoStarWarsTCSLocation(self.player, f"{completion_name} - Gold Brick",
                                                                    None, chapter_region)
                    completion_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                    self.gold_brick_event_count += 1
                    chapter_region.locations.append(completion_gold_brick)

                # True Jedi.
                if self.options.enable_true_jedi_locations:
                    true_jedi_name = f"{chapter.short_name} True Jedi"
                    true_jedi_loc = LegoStarWarsTCSLocation(self.player, true_jedi_name,
                                                            self.location_name_to_id[true_jedi_name], chapter_region)
                    chapter_region.locations.append(true_jedi_loc)
                    if self.options.enable_bonus_locations:
                        # True Jedi Gold Brick event.
                        true_jedi_gold_brick = LegoStarWarsTCSLocation(self.player, f"{true_jedi_name} - Gold Brick",
                                                                       None, chapter_region)
                        true_jedi_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                        self.gold_brick_event_count += 1
                        chapter_region.locations.append(true_jedi_gold_brick)

                # Power Brick.
                power_brick_location_name = chapter.power_brick_location_name
                power_brick_location = LegoStarWarsTCSLocation(self.player, power_brick_location_name,
                                                               self.location_name_to_id[power_brick_location_name],
                                                               chapter_region)
                chapter_region.locations.append(power_brick_location)
                self.required_score_multiplier_count = max(
                    self.required_score_multiplier_count,
                    self._get_score_multiplier_requirement(chapter.power_brick_studs_cost))

                # Character Purchases in the shop.
                # Character purchases unlocked upon completing the chapter (normally in Story mode).
                for shop_unlock, studs_cost in chapter.character_shop_unlocks.items():
                    shop_location = LegoStarWarsTCSLocation(self.player, shop_unlock,
                                                            self.location_name_to_id[shop_unlock], chapter_region)
                    chapter_region.locations.append(shop_location)
                    self.required_score_multiplier_count = max(
                        self.required_score_multiplier_count,
                        self._get_score_multiplier_requirement(studs_cost))
                self.character_unlock_location_count += len(chapter.character_shop_unlocks)

                # Minikits.
                if self.options.enable_minikit_locations:
                    chapter_minikits = self.create_region(f"{chapter.name} Minikits")
                    chapter_region.connect(chapter_minikits, f"{chapter.name} - Collect All Minikits")
                    for i in range(1, 11):
                        loc_name = f"{chapter.short_name} Minikit {i}"
                        location = LegoStarWarsTCSLocation(self.player, loc_name, self.location_name_to_id[loc_name],
                                                           chapter_minikits)
                        chapter_minikits.locations.append(location)
                        available_minikits_check += 1
                    if self.options.enable_bonus_locations:
                        # All Minikits Gold Brick.
                        all_minikits_gold_brick = LegoStarWarsTCSLocation(
                            self.player, f"{chapter_minikits.name} - Gold Brick", None, chapter_minikits)
                        all_minikits_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                        self.gold_brick_event_count += 1
                        chapter_minikits.locations.append(all_minikits_gold_brick)
                elif self.options.minikit_goal_amount != 0:
                    # If Minikit locations are disabled, but the goal requires Minikits, the Chapter Completion location
                    # is instead treated as if it was the vanilla location for a 10 Minikits bundle.
                    available_minikits_check += 10

                if self.options.enable_story_character_unlock_locations:
                    # Story Character unlocks.
                    for character in sorted(CHAPTER_AREA_STORY_CHARACTERS[chapter.short_name]):
                        story_character_unlock_regions.setdefault(character, []).append(chapter_region)

                # Boss.
                if chapter.short_name in self.enabled_bosses:
                    loc_name = f"{chapter.short_name} Defeat {chapter.boss}"
                    boss_event_location = LegoStarWarsTCSLocation(self.player, loc_name, None, chapter_region)
                    if self.options.only_unique_bosses_count:
                        boss_event_item = self.create_event(chapter.boss_character_defeated_event_item_name)
                    else:
                        boss_event_item = self.create_event("Boss Defeated")
                    boss_event_location.place_locked_item(boss_event_item)
                    chapter_region.locations.append(boss_event_location)

        for character, parent_regions in story_character_unlock_regions.items():
            character_region = self.create_region(f"Unlock {character}")
            loc_name = f"Chapter Completion - Unlock {character}"
            character_location = LegoStarWarsTCSLocation(
                self.player, loc_name, self.location_name_to_id[loc_name], character_region
            )
            character_region.locations.append(character_location)
            for parent_region in parent_regions:
                parent_region.connect(character_region)

        self.character_unlock_location_count += len(story_character_unlock_regions)

        # Available minikit count is calculated in generate_early.
        if self.available_minikits != available_minikits_check:
            self._raise_error(AssertionError,
                              "Available minikits in create_regions did not match."
                              " %i from generate_early and %i from create_regions",
                              self.available_minikits,
                              available_minikits_check)

        if self.options.enable_bonus_locations:
            # Bonuses.
            bonuses = self.create_region("Bonuses")
            cantina.connect(bonuses, "Bonuses Door")
            gold_brick_costs: dict[int, list[BonusArea]] = {}
            for area in BONUS_AREAS:
                gold_brick_costs.setdefault(area.gold_bricks_required, []).append(area)

            previous_gold_brick_region = bonuses
            for gold_brick_cost, areas in sorted(gold_brick_costs.items(), key=lambda t: t[0]):
                if gold_brick_cost == 0:
                    region = bonuses
                elif gold_brick_cost > self.gold_brick_event_count:
                    # There are not enough Gold Brick events available to enable any more bonuses.
                    break
                else:
                    region = self.create_region(f"{gold_brick_cost} Gold Bricks Collected")
                    player = self.player
                    previous_gold_brick_region.connect(
                        region, f"Collect {gold_brick_cost} Gold Bricks",
                        lambda state, cost_=gold_brick_cost, item_=GOLD_BRICK_EVENT_NAME: (
                            state.has(item_, player, cost_)))
                    previous_gold_brick_region = region

                for area in areas:
                    location = LegoStarWarsTCSLocation(
                        self.player, area.name, self.location_name_to_id[area.name], region)
                    region.locations.append(location)
                    self.enabled_bonuses.add(area.name)
                    # todo: Item requirements have been removed for now because it is not currently possible to lock
                    #  access to the bonus levels.
                    for item in area.item_requirements:
                        if item in CHARACTERS_AND_VEHICLES_BY_NAME:
                            self.character_chapter_access_counts[item] += 1
                    if not area.gold_brick:
                        continue
                    gold_brick_location = LegoStarWarsTCSLocation(
                        self.player, f"{area.name} - Gold Brick", None, region)
                    gold_brick_location.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                    self.gold_brick_event_count += 1
                    region.locations.append(gold_brick_location)

            # Indiana Jones shop purchase. Unlocks in the shop after watching the Lego Indiana Jones trailer.
            purchase_indy_name = "Purchase Indiana Jones"
            purchase_indy = LegoStarWarsTCSLocation(self.player, purchase_indy_name,
                                                    self.location_name_to_id[purchase_indy_name], bonuses)
            bonuses.locations.append(purchase_indy)
            self.character_unlock_location_count += 1

        # 'All Episodes' character purchases.
        if self.options.enable_all_episodes_purchases:
            all_episodes = self.create_region("All Episodes Unlocked")
            cantina.connect(all_episodes, "Unlock All Episodes")
            all_episodes_purchases = SHOP_SLOT_REQUIREMENT_TO_UNLOCKS["ALL_EPISODES"]
            for character_name in all_episodes_purchases.keys():
                purchase = f"Purchase {character_name}"
                location = LegoStarWarsTCSLocation(self.player, purchase, self.location_name_to_id[purchase],
                                                   all_episodes)
                all_episodes.locations.append(location)
                purchase_cost = CHARACTERS_AND_VEHICLES_BY_NAME[character_name].purchase_cost
                self.required_score_multiplier_count = max(self.required_score_multiplier_count,
                                                           self._get_score_multiplier_requirement(purchase_cost))
            self.character_unlock_location_count += len(all_episodes_purchases)

        # Starting character purchases.
        starting_purchases = [
            "Purchase Gonk Droid",
            "Purchase PK Droid",
        ]
        for purchase in starting_purchases:
            location = LegoStarWarsTCSLocation(self.player, purchase, self.location_name_to_id[purchase], cantina)
            cantina.locations.append(location)
        self.character_unlock_location_count += len(starting_purchases)

        # Victory event
        victory = LegoStarWarsTCSLocation(self.player, "Goal", parent=cantina)
        victory.place_locked_item(self.create_event("Victory"))
        cantina.locations.append(victory)

        # For debugging.
        # from Utils import visualize_regions
        # visualize_regions(cantina, "LegoStarWarsTheCompleteSaga_Regions.puml", show_entrance_names=True)

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
                set_rule(spot, lambda state, items_=tuple(singular_names), p=self.player: state.has_all(items_, p))
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
                self._raise_error(AssertionError, "Unreachable: Unexpected episode unlock requirement %s",
                                  self.options.episode_unlock_requirement)

            # Set chapter requirements.
            episode_chapters = EPISODE_TO_CHAPTER_AREAS[episode_number]
            for chapter_number, chapter in enumerate(episode_chapters, start=1):
                if chapter.short_name not in self.enabled_chapters:
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

                entrance_abilities = CharacterAbility.NONE
                for character_name in required_character_names:
                    generic_character = CHARACTERS_AND_VEHICLES_BY_NAME[character_name]
                    entrance_abilities |= generic_character.abilities

                def set_chapter_spot_abilities_rule(spot: Location | Entrance, *abilities: CharacterAbility):
                    # Remove any requirements already satisfied by the chapter entrance before setting the rule.
                    self.set_any_abilities_rule(spot, *[ability & ~entrance_abilities for ability in abilities])

                # Set Power Brick logic
                power_brick = self.get_location(chapter.power_brick_location_name)
                set_chapter_spot_abilities_rule(power_brick, *chapter.power_brick_ability_requirements)
                self._add_score_multiplier_rule(power_brick, chapter.power_brick_studs_cost)

                # Set Minikits logic
                if self.options.enable_minikit_locations:
                    all_minikits_entrance = self.get_entrance(f"{chapter.name} - Collect All Minikits")
                    set_chapter_spot_abilities_rule(all_minikits_entrance, chapter.all_minikits_ability_requirements)

                # Set Character Purchase logic
                for shop_unlock, studs_cost in chapter.character_shop_unlocks.items():
                    purchase_location = self.get_location(shop_unlock)
                    self._add_score_multiplier_rule(purchase_location, studs_cost)

        # Bonus levels.
        gold_brick_requirements: set[int] = set()
        for area in BONUS_AREAS:
            if area.name not in self.enabled_bonuses:
                continue
            # Gold brick requirements are set on entrances, so do not need to be set on the locations themselves.
            gold_brick_requirements.add(area.gold_bricks_required)
            completion = self.get_location(area.name)
            if area.ability_requirements:
                self.set_abilities_rule(completion, area.ability_requirements)
            if area.item_requirements:
                add_rule(completion, lambda state, items_=area.item_requirements: state.has_all(items_, player))
            if area.gold_brick:
                gold_brick = self.get_location(f"{area.name} - Gold Brick")
                set_rule(gold_brick, completion.access_rule)
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
                         lambda state, c=len(self.enabled_episodes), p=player: state.has("All Episodes Token", p, c))
            for character_name, studs_cost in SHOP_SLOT_REQUIREMENT_TO_UNLOCKS["ALL_EPISODES"].items():
                purchase_location = self.get_location(f"Purchase {character_name}")
                self._add_score_multiplier_rule(purchase_location, studs_cost)

        # Victory.
        victory = self.get_location("Goal")
        if self.goal_minikit_count > 0:
            add_rule(victory, lambda state: state.has(self.minikit_bundle_name, player, self.goal_minikit_bundle_count))
        goal_boss_count = self.options.defeat_bosses_goal_amount.value
        if goal_boss_count > 0:
            if self.options.only_unique_bosses_count:
                boss_items = sorted({SHORT_NAME_TO_CHAPTER_AREA[chapter].boss_character_defeated_event_item_name
                                     for chapter in self.enabled_bosses})
                assert goal_boss_count <= len(boss_items)
                add_rule(
                    victory, (
                        lambda state, i_=tuple(boss_items), p_=player, c_=goal_boss_count:
                        state.has_from_list_unique(i_, p_, c_)
                    )
                )
            else:
                add_rule(victory, lambda state, p_=player, c_=goal_boss_count: state.has("Boss Defeated", p_, c_))

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", player)

    @classmethod
    def stage_fill_hook(cls,
                        multiworld: MultiWorld,
                        progitempool: list[Item],
                        usefulitempool: list[Item],
                        filleritempool: list[Item],
                        fill_locations: list[Location],
                        ) -> None:
        game_player_ids = set(multiworld.get_game_players(cls.game))
        game_minimal_player_ids = {player for player in game_player_ids
                                   if multiworld.worlds[player].options.accessibility == "minimal"}

        def sort_func(item: Item):
            if item.player in game_player_ids and item.name in MINIKITS_BY_NAME:
                if item.player in game_minimal_player_ids:
                    # For minimal players, place Minikits first. This helps prevent fill from dumping logically relevant
                    # items into unreachable locations and reducing the number of reachable locations to fewer than the
                    # number of items remaining to be placed.
                    #
                    # Placing only the non-required Minikits first or slightly more than the number of non-required
                    # Minikits first was also tried, but placing all Minikits first seems to give fill the best chance
                    # of succeeding.
                    #
                    # Forcing Minikits first has the unfortunately sideeffect of priority fill picking Minikits first,
                    # but that will just have to be put up with in order to generate well. Maybe a small buffer of
                    # non-Minikit items could be placed first so that the items in the buffer end up on priority
                    # locations.
                    return 1
                else:
                    # For non-minimal players, place Minikits last. The helps prevent fill from filling most/all
                    # reachable locations with the Minikit macguffins that are only required for the goal.
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
                state.prog_items[self.player].update(item.collect_extras)
            return True
        return False

    def remove(self, state: CollectionState, item: LegoStarWarsTCSItem) -> bool:
        changed = super().remove(state, item)
        if changed:
            extras = item.collect_extras
            if extras is not None:
                state.prog_items[self.player].subtract(item.collect_extras)
            return True
        return False

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "apworld_version": constants.AP_WORLD_VERSION,
            "enabled_chapters": sorted(self.enabled_chapters),
            "enabled_episodes": sorted(self.enabled_episodes),
            "enabled_bonuses": sorted(self.enabled_bonuses),
            "starting_chapter": self.starting_chapter,
            "starting_episode": self.starting_episode,
            "minikit_goal_amount": self.goal_minikit_count,
            "enabled_bosses": self.enabled_bosses,
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
            )
        }

    def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
        super().write_spoiler_header(spoiler_handle)

        spoiler_handle.write(f"Apworld version: {constants.AP_WORLD_VERSION}\n")

        spoiler_handle.write(f"Starting Chapter: {self.starting_chapter}\n")

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
