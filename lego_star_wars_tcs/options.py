import itertools
from dataclasses import dataclass
from typing import Mapping, AbstractSet

from Options import (
    PerGameCommonOptions,
    StartInventoryPool,
    Choice,
    Range,
    NamedRange,
    OptionSet,
    DefaultOnToggle,
    Toggle,
    OptionGroup,
)

from .levels import BOSS_UNIQUE_NAME_TO_CHAPTER
from .locations import LEVEL_SHORT_NAMES_SET
from .items import CHARACTERS_AND_VEHICLES_BY_NAME, EXTRAS_BY_NAME


CHAPTER_OPTION_KEYS: Mapping[str, AbstractSet[str]] = {
    "All": LEVEL_SHORT_NAMES_SET,
    "Prequel Trilogy": {chapter for chapter in LEVEL_SHORT_NAMES_SET if chapter[0] in "123"},
    "Original Trilogy": {chapter for chapter in LEVEL_SHORT_NAMES_SET if chapter[0] in "456"},
    **{f"Episode {s}": {chapter for chapter in LEVEL_SHORT_NAMES_SET if chapter[0] == s} for s in "123456"},
    **{chapter: {chapter} for chapter in sorted(LEVEL_SHORT_NAMES_SET)},
}


class ChapterOptionSet(OptionSet):
    valid_keys = list(CHAPTER_OPTION_KEYS.keys())

    @property
    def value_ungrouped(self) -> set[str]:
        """Ungroup all grouped chapters in .value into a single set of individual chapters."""
        return set().union(*(CHAPTER_OPTION_KEYS[key] for key in self.value))


class ChoiceFromStringExtension(Choice):
    """
    Extends Choice to add a method to set the value from a string option name, similar to constructing a new Choice
    instance with Choice.from_text().
    """
    def set_from_string(self, s: str):
        for k, v in self.name_lookup.items():
            if s == v:
                self.value = k
                return
        raise ValueError(f"{s} is not a valid string for {type(self)}. Expected: {sorted(self.name_lookup.values())}")


class MinikitGoalAmount(NamedRange):
    """
    The number of Minikits required to goal.

    If set to zero, Minikits will not be part of the goal, but will still be in the item pool as filler items if Minikit
    locations are enabled.

    If set to non-zero, and Minikit locations are disabled, the Minikit Bundle Size will be forcefully set to 10.

    Each enabled episode chapter shuffles 10 Minikits into the item pool, which may be bundled to reduce the number
    Minikit items in the item pool.

    Setting this option to "use_percentage_option" will use the Minikit Goal Amount Percentage option's value to
    determine how many Minikit's are required to goal.
    """
    display_name = "Goal Minikit Count"
    range_start = 0
    range_end = 360
    special_range_names = {
        "use_percentage_option": -1,
    }
    default = -1


class MinikitGoalAmountPercentage(Range):
    """
    The percentage of Minikits in the item pool that are required to goal.

    10 Minikits are added to the item pool for each enabled episode chapter, which may be bundled to reduce the number
    of individual items.

    This does nothing unless the Minikit Goal Amount option is set to "use_percentage_option" instead of a number.

    The final number of Minikits required to goal is rounded to the nearest integer, but will always be at least 1.
    """
    display_name = "Goal Minikit Percentage"
    range_start = 1
    range_end = 100
    default = 75


class DefeatBossesGoalAmount(Range):
    """
    Choose how many bosses must be defeated to goal.

    If set to zero, bosses will not be part of the goal.

    The Chapter a boss is in must be completed for defeating the boss to count.
    """
    display_name = "Defeat Bosses Goal Amount"
    range_start = 0
    range_end = len(BOSS_UNIQUE_NAME_TO_CHAPTER)


class EnabledBossesCount(Range):
    """
    Choose the number of bosses that will be present in the world.

    This will automatically be set at least as high as the number of bosses required to goal.
    This will automatically be set no higher than the maximum of the number of allowed bosses in allowed Chapters.
    """
    display_name = "Enabled Bosses Count"
    range_start = 0
    range_end = len(BOSS_UNIQUE_NAME_TO_CHAPTER)


class AllowedBosses(OptionSet):
    """
    Choose bosses that count towards the Defeat Bosses Goal.

    When bosses must be defeated as part of the goal, the Chapters for the bosses in this list will be added to Allowed
    Chapters list if they are not already in Allowed Chapters list.

    allowed_bosses:
      - Darth Maul (1-6) # Darth Maul
      - Zam Wesell (2-1) # Bounty Hunter Pursuit
      - Jango Fett (2-2) # Discovery On Kamino
      - Jango Fett (2-4) # Jedi Battle
      - Count Dooku (2-6) # Count Dooku
      - Count Dooku (3-2) # Chancellor In Peril
      - General Grievous (3-3) # General Grievous
      - Anakin Skywalker (3-6) # Darth Vader
      - Death Star (4-6) # Rebel Attack
      - Darth Vader (5-4) # Dagobah
      - Darth Vader (5-5) # Cloud City Trap
      - Boba Fett (5-6) # Betrayal Over Bespin
      - Rancor (6-1) # Jabba's Palace
      - Boba Fett (6-2) # The Great Pit Of Carkoon
      - Darth Sidious (6-5) # Jedi Destiny
      - Death Star II (6-6) # Into The Death Star
    """
    display_name = "Allowed Bosses"
    valid_keys = list(BOSS_UNIQUE_NAME_TO_CHAPTER.keys())
    default = list(BOSS_UNIQUE_NAME_TO_CHAPTER.keys())


class OnlyUniqueBossesCountTowardsGoal(ChoiceFromStringExtension):
    """
    When enabled, only unique bosses will count towards your goal. Defeating the same boss character in two separate
    Chapters will only count as one boss kill.

    When unique bosses are enabled, the maximum number of bosses that can count towards the goal will be reduced to 12,
    or 11 when Anakin Skywalker counts as the same boss as Darth Vader.
    """
    display_name = "Only Count Unique Bosses"
    option_disabled = 0
    option_enabled = 1
    option_enabled_and_count_anakin_as_vader = 2


class MinikitBundleSize(ChoiceFromStringExtension):
    """
    Minikit items in the item pool are bundled into items individually worth this number of Minikits.

    Low bundle sizes can cause generation times to increase and are more likely to result in generation failing with a
    FillError when generating Lego Star Wars: The Complete Saga on its own, or with other games that can struggle to
    place all items.

    Low bundle sizes also mean fewer filler items in the item pool.
    """
    display_name = "Minikit Bundle Size"
    option_individual = 1
    alias_1 = 1
    option_2 = 2
    option_5 = 5
    option_10 = 10
    default = 5


class EnabledChaptersCount(Range):
    """Choose how many randomly picked chapters from Allowed Chapters should be enabled.

    If there are fewer allowed chapters than the count to enable, all the allowed chapters will be enabled.
    """
    display_name = "Enabled Chapter Count"
    range_start = 1
    range_end = 36
    default = 18


class AllowedChapterTypes(ChoiceFromStringExtension):
    """Specify additional filtering of the allowed chapters that can be enabled.

    - All: No additional filtering, all chapters specified in the Allowed Chapters option are allowed.
    - No Vehicles: No vehicle chapters (1-4, 2-1, 2-5, 3-1, 4-6, 5-1, 5-3, 6-6) will be allowed.
    """
    display_name = "Allowed Chapter Types"
    option_all = 0
    option_no_vehicles = 1
    default = 0


class AllowedChapters(ChapterOptionSet):
    """Choose the chapter levels that are allowed to be picked when randomly choosing which chapters will be enabled.

    Individual chapters can be specified, e.g. "1-1", "5-4".

    Special values:
    - "All": All chapters will be allowed.
    - "Prequel Trilogy": All chapters in episodes 1, 2 and 3 will be allowed.
    - "Original Trilogy": All chapters in episode 4, 5 and 6 will be allowed.
    - "Episode {number}": e.g. "Episode 3" will allow all chapters in Episode 3, so 3-1 through to 3-6.

    Examples:
    # Enable only 1-1 (Negotiations)
    allowed_chapters: ["1-1"]

    # Enable only 1-1 (Negotiations) (alt.)
    allowed_chapters:
      - 1-1

    # Enable all
    allowed_chapters: ["All"]

    # Enable all (alt.)
    allowed_chapters:
      - All

    # Enable only vehicle levels
    allowed_chapters:
      - 1-4
      - 2-2
      - 2-5
      - 3-1
      - 4-6
      - 5-1
      - 5-3
      - 6-6

    # A mix of values
    allowed_chapters:
      - Prequel Trilogy
      - Episode 4
      - 5-2
      - 5-3
      - 6-5
    """
    display_name = "Allowed Chapters"
    default = frozenset({"All"})


class PreferredChapters(ChapterOptionSet):
    """
    When the generator picks which chapters should be enabled, it will pick from these preferred chapters first.

    If a preferred chapter is not allowed to be picked because it is not included in the Allowed Chapters option, it
    will not be picked.

    This option can be used to guarantee that certain chapters are present in a generated world.

    Individual chapters can be specified, e.g. "1-1", "5-4".

    Special values:
    - "Prequel Trilogy": All chapters in episodes 1, 2 and 3 will be preferred.
    - "Original Trilogy": All chapters in episode 4, 5 and 6 will be preferred.
    - "Episode {number}": e.g. "Episode 3" will make all chapters in Episode 3, so 3-1 through to 3-6, be preferred.

    Examples:
    # Prefer 1-1 (Negotiations)
    preferred_chapters: ["1-1"]

    # Prefer 1-1 (Negotiations) (alt.)
    preferred_chapters:
      - 1-1

    # Prefer vehicle levels
    preferred_chapters:
      - 1-4
      - 2-2
      - 2-5
      - 3-1
      - 4-6
      - 5-1
      - 5-3
      - 6-6

    # A mix of values
    preferred_chapters:
      - Prequel Trilogy
      - Episode 4
      - 5-2
      - 5-3
      - 6-5
    """
    display_name = "Preferred Chapters"
    # There is no point to using "All" for Preferred Chapters, so remove it from the valid_keys.
    valid_keys = [key for key in ChapterOptionSet.valid_keys if key != "All"]
    default = frozenset()


class PreferEntireEpisodes(Toggle):
    """
    When enabled, after the generator has picked a chapter to be enabled out of the allowed chapters, it will continue
    picking additional chapters from the same episode until it runs out of allowed chapters in that episode.

    For example, if the generator picks 3-2 as the first enabled chapter, its next picked chapters will be guaranteed to
    be picked from the allowed chapters out of 3-1, 3-3, 3-4, 3-5 and 3-6.

    The Starting Chapter is always the first picked enabled chapter.

    With all chapters allowed to be enabled and an Enabled Chapters Count set to a multiple of 6, this option will
    result in whole episodes being enabled.

    When combined with the Preferred Chapters option, this option can be used to guarantee entire episodes.
    """
    display_name = "Prefer Entire Episodes"


class EnableMinikitLocations(DefaultOnToggle):
    """
    Enable locations for collecting each Minikit in enabled Chapters.

    Minikit locations are progressive within each Chapter (to be changed in the future), so collecting 4 Minikits in any
    order in a Chapter will send the location checks for Minikit 1, Minikit 2, Minikit 3 and Minikit 4, in that Chapter,
    in order.

    All Minikits in a Chapter enter logic at the same time, when it is logically possible to reach all Minikits in that
    Chapter.

    If Minikit locations are not enabled, but the goal requires Minikits, the Minikit Bundle Size will be forcefully set
    to 10.

    When Minikit locations are not enabled, Bonus levels will not consider the 10/10 Minikit Gold Bricks as part of Gold
    Brick logic.
    """
    display_name = "Enable Minikit Locations"


class EnableTrueJediLocations(DefaultOnToggle):
    """
    Enable locations for completing True Jedi in each enabled Chapter.

    When True Jedi locations are not enabled, Bonus levels will not consider True Jedi Gold Bricks as part of Gold Brick
    logic.
    """
    display_name = "Enable True Jedi Locations"


class EnableChapterCompletionCharacterUnlockLocations(DefaultOnToggle):
    """
    Enable locations for unlocking Story mode characters that would normally unlock when completing a Chapter in
    vanilla.

    In vanilla, completing any Chapter with C-3PO as a playable Story mode character would unlock C-3PO. In vanilla,
    this would mean completing either 2-3, 4-1, 5-2 or 6-1 because Chapters within an Episode unlock in order in
    vanilla, but the AP randomizer allows for Chapters to be unlocked out-of-order, so, additionally, completing any of
    4-2, 4-3, 4-4, 4-5, 5-6, 6-2 or 6-4, would also send the Story Character Unlock location for C-3PO.

    The first Chapter completed that would unlock a Story mode character will send the Unlock location for that
    character.

    Because Story mode is skipped in the AP randomizer, these character unlock locations are sent when the Chapters are
    completed in Free Play.

    With all Chapters enabled, this adds 56 locations.
    """
    display_name = "Chapter Completion Character Unlocks"


class EnableBonusLocations(Toggle):
    """
    The Bonuses Door in the Cantina has a number of levels that require Gold Bricks to access. When this option is
    enabled, completing each of these Bonus levels (in Story Mode if they have a Story mode) will be a location to
    check.

    Additionally, watching the Lego Indiana Jones trailer (it can be skipped once started), and purchasing Indiana Jones
    from the shop are added as locations to check.

    Gold Brick logic currently only counts Gold Bricks earned from Chapter completion, True Jedi, 10/10 Minikits in a
    Chapter, and the singular Gold Bricks awarded for completing other Bonus levels.

    Depending on other options, not all Chapters could be enabled, so if there are not enough Gold Bricks logically
    available for a Bonus level to be accessed, that Bonus level will not be included in the multiworld.

    With all Chapters enabled, this adds 8 locations.
    """
    display_name = "Bonuses"


class EnableAllEpisodesCharacterPurchaseLocations(Toggle):
    """
    Enable the expensive character purchase locations for IG-88, Dengar, 4-LOM, Ben Kenobi (Ghost), Anakin Skywalker
    (Ghost), Yoda (Ghost) and R2-Q5.

    In vanilla, these locations unlock after completing Story mode for every chapter, but the AP randomizer changes
    these shop purchases to unlock according to the All Episodes Character Purchase Requirements option.

    Even when the locations are disabled, the vanilla characters, IG-88, Dengar etc. may still be added to the item
    pool.

    Attempting to purchase the vanilla characters from the shop while the locations are disabled will not unlock the
    vanilla characters.

    This adds 7 locations.
    """
    display_name = "'All Episodes' Character Purchases"


class ChapterUnlockRequirement(ChoiceFromStringExtension):
    """Choose how Chapters within an Episode are unlocked.

    The requirements to access your starting Chapter will be given to you at the start.

    - Story Characters: A Chapter unlocks once its Story mode characters have been unlocked.
    - Chapter Item: A Chapter unlocks after receiving an unlock item specific to that Chapter, e.g.
    "Chapter 2-3 Unlock".
    """
    display_name = "Chapter Unlock Requirements"
    option_story_characters = 0
    option_chapter_item = 1
    # option_random_characters = 2
    # option_open = 3  # Needs the ability to limit characters to only being usable within a specific episode/
    default = 0


class EpisodeUnlockRequirement(ChoiceFromStringExtension):
    """Choose how Episodes are unlocked.

    Note: An Episode door in the Cantina will only unlock when a Chapter within that Episode has been unlocked.

    The Episode of your starting Chapter will always be unlocked from the start.

    - Open: All Episodes will be unlocked from the start.
    - Episode Item: Each Episode will unlock after receiving an unlock item for that Episode, e.g. "Episode 5 Unlock".
    """
    display_name = "Episode Unlock Requirements"
    option_open = 0
    option_episode_item = 1
    default = 0


class AllEpisodesCharacterPurchaseRequirements(ChoiceFromStringExtension):
    """The vanilla unlock requirements for purchasing IG-88, Dengar, 4-LOM, Ben Kenobi (Ghost), Anakin Skywalker
    (Ghost), Yoda (Ghost) and R2-Q5 from the shop, are completing every Story mode chapter. The randomizer changes this
    unlock condition because completing every Story mode chapter is unreasonable in most multiworlds and is impossible
    if not all chapters are enabled.

    - Episodes Unlocked: The shop purchases will unlock when the "Episode # Unlock" item for each Episode with enabled
    Chapters has been received. If the Episode Unlock Requirement is set to Open or there is only 1 enabled Episode,
    this will be forcefully changed to "Episodes Tokens" instead.
    - Episodes Tokens: A number of "All Episodes Token" items will be added to the item pool, equal to the number of
    enabled Episodes. All of these "All Episodes Token" items will need to be received to unlock the characters for
    purchase.
    """
    display_name = "'All Episodes' Character Purchase Unlock Requirements"
    option_episodes_unlocked = 1
    option_episodes_tokens = 2
    default = 2


# Ideally wants Extra Toggle to be randomized, and needs support for per-chapter abilities because different chapters
# have access to different extra characters. I think most of the logic relevant characters are the blaster/grapple ones.
# class ExtraToggleLogic(DefaultOnToggle):
#     """Extra Toggle characters are included in logic"""


class StartingChapter(ChoiceFromStringExtension):
    """
    Choose the starting chapter. The Episode the starting Chapter belongs to will be accessible from the start.

    Known issues:
    - If the starting Chapter belongs to an Episode other than Episode 1, when starting a new save file and connecting
    to the Archipelago server, the starting Episode door will appear locked (red light), but this is only visual.
    - If the starting Chapter belongs to an Episode other than Episode 1, when starting a new save file and connecting
    to the Archipelago server, the Episode 1 door will be open, but it will correctly lock itself upon re-entering the
    main room of the Cantina.
    - Due to the way the logic currently assumes the player has access to a Jedi and a Protocol Droid, if access to the
    chosen starting Chapter does not include a Jedi and Protocol Droid in its requirements, a Jedi character and/or
    TC-14 will be added to the starting inventory.

    Due to the character requirements being shared between some Chapters, some starting Chapters will result in
    additional Chapters being open from the start:

    Starting with 1-1 will also open 1-6.
    Starting with 1-2 will also open 1-6.
    Starting with 1-3 will also open 1-6.
    Starting with 1-5 will also open 1-6.
    Starting with 3-2 will also open 3-6.
    Starting with 4-3 will also open 4-2.
    Starting with 5-3 will also open 6-6 if the Episode Unlock Requirement is set to Open.
    Starting with 6-6 will also open 5-3 if the Episode Unlock Requirement is set to Open.
    """
    display_name = "Starting Chapter"
    # todo: Try setting the attributes for specific levels such that they use 1-1 format rather than 1_1.
    # Variable names cannot use hyphens, so the options for specific levels are set programmatically.
    # option_1-1 = 11
    # option_1-2 = 12
    # etc.
    locals().update({f"option_{episode}-{chapter}": int(f"{episode}{chapter}")
                     for episode, chapter in itertools.product(range(1, 7), range(1, 7))})
    # option_1_1 = 11
    # option_1_2 = 12
    # option_1_3 = 13
    # option_1_4 = 14
    # option_1_5 = 15
    # option_1_6 = 16
    # option_2_1 = 21
    # option_2_2 = 22
    # option_2_3 = 23
    # option_2_4 = 24
    # option_2_5 = 25
    # option_2_6 = 26
    # option_3_1 = 31
    # option_3_2 = 32
    # option_3_3 = 33
    # option_3_4 = 34
    # option_3_5 = 35
    # option_3_6 = 36
    # option_4_1 = 41
    # option_4_2 = 42
    # option_4_3 = 43
    # option_4_4 = 44
    # option_4_5 = 45
    # option_4_6 = 46
    # option_5_1 = 51
    # option_5_2 = 52
    # option_5_3 = 53
    # option_5_4 = 54
    # option_5_5 = 55
    # option_5_6 = 56
    # option_6_1 = 61
    # option_6_2 = 62
    # option_6_3 = 63
    # option_6_4 = 64
    # option_6_5 = 65
    # option_6_6 = 66
    option_random_chapter = -1
    option_random_non_vehicle = -2
    option_random_vehicle = -3
    option_random_episode_1 = 1
    option_random_episode_2 = 2
    option_random_episode_3 = 3
    option_random_episode_4 = 4
    option_random_episode_5 = 5
    option_random_episode_6 = 6
    default = 11


class RandomStartingLevelMaxStartingCharacters(Range):
    """Specify the maximum number of starting characters allowed when picking a random starting level.

    1 Character: 1-4, 2-1, 2-5, 5-1 (all vehicle levels)
    2 Characters: 1-6, 2-2, 3-1 (v), 3-3, 3-4, 3-5, 3-6, 4-6 (v), 5-3 (v), 5-5, 6-3, 6-5, 6-6 (v)
    3 Characters: 1-1, 1-2, 2-6
    4 Characters: 1-3, 2-3, 2-4, 3-2, 4-2, 5-2, 5-4, 5-6
    5 Characters: 4-1
    6 Characters: 1-5, 4-3, 4-4, 4-5, 6-1, 6-4
    7 Characters: 6-2"""
    display_name = "Random Starting Chapter Max Starting Characters",
    range_start = 2
    range_end = 7
    default = 7


class PreferredCharacters(OptionSet):
    """
    Specify characters that the generator should try to always include in the item pool.

    When the number of enabled Chapters is reduced from the maximum, the number of items to add to the item pool is also
    reduced, so not all characters may get added to the item pool.

    The names of all items can be found by starting the Lego Star Wars: The Complete Saga client and entering the
    `/items` command.

    If no vehicle Chapters are enabled, no vehicle characters will be included in the item pool.
    """
    display_name = "Preferred Characters"
    valid_keys = {char.name for char in CHARACTERS_AND_VEHICLES_BY_NAME.values() if char.is_sendable}
    default = frozenset({
        # Highest base movement speed or non-Extra-Toggle characters, lots of glitches.
        "Droideka",
        # Lots of glitches, also a ghost.
        "Yoda (Ghost)",
        # High Jump + Triple jump glitch can get a lot of vertical height.
        # Grevous' Bodyguard can reach similar heights, and has higher movement speed, but has a super-high single jump
        # + slam double jump, so cannot get as much horizontal distance compared to General Grievous.
        "General Grievous",
    })


class PreferredExtras(OptionSet):
    """
    Specify Extras that the generator should try to always include in the item pool.

    When the number of enabled Chapters is reduced from the maximum, the number of items to add to the item pool is also
    reduced, so not all Extras may get added to the item pool.

    The names of all items can be found by starting the Lego Star Wars: The Complete Saga client and entering the
    `/items` command.

    Score Multipliers that are logically required, due to the Most Expensive Purchase With No Score Multiplier option,
    will always be included in the item pool.

    When Progressive Score Multiplier items are enabled (always enabled currently), preferring "Score x{number}" to be
    included in the item pool will try to ensure there are enough Progressive Score Multiplier items to unlock that
    score multiplier.
    """
    display_name = "Preferred Extras"
    valid_keys = {
        # Progressive Score Multiplier is an AP-specific item, and this option does not support specifying multiple of
        # an item, so the individual "Score x{number}" Extras are included as valid keys instead.
        *(extra.name for extra in EXTRAS_BY_NAME.values() if extra.is_sendable
          and extra.name != "Progressive Score Multiplier"),
        "Score x2",
        "Score x4",
        "Score x6",
        "Score x8",
        "Score x10",
    }
    default = frozenset({
        # Out-of-logic access:
        # Out-of-logic SITH access
        "Dark Side",
        # Out-of-logic BOUNTY_HUNTER access (silver bricks only)
        "Exploding Blaster Bolts",
        # Out-of-logic BLASTER access (grapple only)
        "Force Grapple Leap",
        # Out-of-logic BOUNTY_HUNTER access (silver bricks only)
        "Self Destruct",
        # Out-of-logic BOUNTY_HUNTER access (silver bricks only)
        "Super Ewok Catapult",

        # Speed up playing:
        # Useful for survivability/True Jedi, especially in vehicle chapters, and a few places where hostile NPCs can be
        # used to activate buttons.
        "Deflect Bolts",
        # Useful for survivability/True Jedi and a few places where NPCs can be used to activate buttons
        "Disarm Troopers",
        # Useful for speeding up playing through chapters
        "Fast Force",
        # Useful for speeding up playing through chapters
        "Fast Build",
        # Useful for speeding up playing through chapters
        "Infinite Torpedos",
        # Useful for survivability/True Jedi and a few places where hostile NPCs can be used to activate buttons.
        "Invincibility",
        # All score multipliers are useful for speeding up Studs farming and getting True Jedi
        "Score x2",
        "Score x4",
        "Score x6",
        "Score x8",
        "Score x10",
        # Useful for speeding up playing through chapters and getting True Jedi
        "Stud Magnet",
    })


class StartWithDetectors(DefaultOnToggle):
    """Start with the Minikit Detector and Power Brick Detector unlocked.

    When these Extras are enabled, the locations of Minikits and Power Bricks in the current level are shown with
    arrows."""
    display_name = "Start With Detector Extras"


class FillerReserveCharacters(DefaultOnToggle):
    """
    When enabled, reserve space in the item pool for at least as many Characters as enabled locations that would
    normally unlock Characters in vanilla.

    When disabled, the only reserved space in the item pool for Characters will be the Characters needed to reach all
    locations. Additional Characters will only get added to the item pool through the Filler Weight: Characters option.
    """
    display_name = "Filler Reserve: Characters"


class FillerReserveExtras(DefaultOnToggle):
    """
    When enabled, reserve space in the item pool for at least as many Extras as enabled locations that would normally
    unlock Extras in vanilla.

    When disabled, the only reserved space in the item pool for Extras will be the Extras needed to reach all locations.
    Additional Extras will only get added to the item pool through the Filler Weight: Extras option.
    """
    display_name = "Filler Reserve: Extras"


class FillerWeightCharacters(Range):
    """
    This option controls the weight of characters when choosing which items to fill out the rest of the space in the
    item pool. A higher weight in comparison to the other Filler Weight options results in more characters in the item
    pool, compared to other items used to fill out the rest of the item pool.

    The generator tries to fill the item pool with as many Characters and Extras as would be unlocked, in vanilla, by
    all the enabled locations.

    Archipelago locations that don't have a corresponding vanilla item, and Minikits being bundled, results in some free
    space in the item pool for any kind of item.
    """
    # Many characters are just reskins of another character, and the generator already guarantees that the item pool
    # contains enough characters to reach every location. There are also often many character unlocks for each chapter
    # completed.
    display_name = "Filler Weight: Characters"
    range_start = 0
    range_end = 100
    default = 40


class FillerWeightExtras(Range):
    """
    This option controls the weight of Extras when choosing which items to fill out the rest of the space in the
    item pool. A higher weight in comparison to the other Filler Weight options results in more Extras in the item
    pool, compared to other items used to fill out the rest of the item pool.

    The generator tries to fill the item pool with as many Characters and Extras as would be unlocked, in vanilla, by
    all the enabled locations.

    Archipelago locations that don't have a corresponding vanilla item, and Minikits being bundled, results in some free
    space in the item pool for any kind of item.
    """
    # There is only one Extra reserved in the item pool per chapter and Extras tend to have unique effects, so the
    # default weight is higher.
    display_name = "Filler Weight: Extras"
    range_start = 0
    range_end = 100
    default = 30


class FillerWeightJunk(Range):
    """
    This option controls the weight of Studs, Power Ups and other junk filler Archipelago items when choosing which
    items to fill out the rest of the space in the item pool. A higher weight in comparison to the other Filler Weight
    options results in more Studs and other filler Archipelago items in the item pool, compared to other items used to
    fill out the rest of the item pool.

    Purple Stud is currently the only junk filler Archipelago item that is implemented, but more will likely be added in
    the future.

    The generator tries to fill the item pool with as many Characters and Extras as would be unlocked, in vanilla, by
    all the enabled locations.

    Archipelago locations that don't have a corresponding vanilla item, and Minikits being bundled, results in some free
    space in the item pool for any kind of item.
    """
    display_name = "Filler Weight: Junk"
    range_start = 0
    range_end = 100
    default = 30


class MostExpensivePurchaseWithNoScoreMultiplier(NamedRange):
    """
    The most expensive individual purchase the player can be expected to make without any score multipliers, *in
    thousands of Studs*.

    For example, an option value of 100 means that purchases up to 100,000 studs in price can be expected to be
    purchased without any score multipliers.

    The logical requirements for expensive purchases will scale with this value. For example, if a purchase of up to
    100,000 Studs is expected with no score multipliers, then a purchase of 100,001 up to 200,000 Studs is expected with
    a score multiplier of 2x.

    "Score x2" costs 1.25 million studs (1250 * 1000) in vanilla, so, for a more vanilla experience with potentially
    more farming for Studs, set this option to 1250.

    The most expensive purchase is "Score x10", which costs 20 million studs (20000 * 1000). Setting this options to
    20000 means that all purchases are logically expected without score multipliers.
    """
    display_name = "Most Expensive Purchase Without Score Multipliers"
    default = 100
    # Max purchase cost is 20_000_000
    # 5 * 1000 * 3840 = 19_200_000 -> 5 is too low
    # 6 * 1000 * 3840 = 23_040_000 -> 6 is the minimum allowed
    range_start = 6
    range_end = 20000
    special_range_names = {
        "minimum_(6000_studs)": 6,
        "10000_studs": 10,
        "25000_studs": 25,
        "50000_studs": 50,
        "75000_studs": 75,
        "default_(100000_studs)": 100,
        "250000_studs": 250,
        "500000_studs": 500,
        "750000_studs": 750,
        "1_million_studs": 1000,
        "vanilla_(1.25_million_studs)": 1250,
        "2.5_million_studs": 2500,
        "5_million_studs": 5000,
        "7.5_million_studs": 7500,
        "10_million_studs": 10000,
        "no_score_multipliers_expected": 20000,
    }


class ReceivedItemMessages(ChoiceFromStringExtension):
    """
    Determines whether an in-game notification is displayed when receiving an item.

    Note: Dying while a message is displayed results in losing studs as normal, but the lost studs do not drop, so
    cannot be recovered.
    Note: Collecting studs while a message is displayed plays the audio for collecting Blue/Purple studs, but this has
    no effect on the received value of the studs collected.

    - All: Every item shows a message
    - None: All items are received silently.
    """
    display_name = "Received Item Messages"
    default = 0
    option_all = 0
    option_none = 1
    # option_progression = 2  # Not Yet Implemented


class CheckedLocationMessages(ChoiceFromStringExtension):
    """
    Determines whether an in-game notification is displayed when checking a location.

    Note: Dying while a message is displayed results in losing studs as normal, but the lost studs do not drop, so
    cannot be recovered.
    Note: Collecting studs while a message is displayed plays the audio for collecting Blue/Purple studs, but this has
    no effect on the received value of the studs collected.

    - All: Every checked location shows a message
    - None: No checked locations show a message
    """
    display_name = "Checked Location Messages"
    default = 0
    option_all = 0
    option_none = 1


class LogicDifficulty(ChoiceFromStringExtension):
    # todo: Maybe just remove Extras (other than score multipliers) logic from None difficulty?
    """
    - None:
      - Tries to match developer intended strategies.
      - Includes some combat logic for avoidable/ignorable enemies.
      - Extras (except Score Multipliers for expensive purchases) are not included in logic.
    - Normal:
      - No glitches expected.
      - Players that have played most of the vanilla game should be able to play with this difficulty.
      - Expects more platforming that probably wasn't developer intended, but it generally quite obvious and simple.
      - Logic starts expecting the use of Extras:
        - Self Destruct, Exploding Blaster Bolts, and Super Ewok Catapult can be expected for destroying Silver Brick
        objects.
        - Force Grapple Leap can be expected to use Grapple points.
        - Dark Side can be expected to use Sith Force. There are a few, rare cases where P1 and P2 are expected to use
        Sith Force simultaneously. The CPU co-op partner will only use Sith Force with Sith characters, so these cases
        can require a small amount of controlling both characters simultaneously if the only access to Sith Force is
        through Dark Side.
      - (incomplete, most levels will use None difficulty logic)
    - Moderate:
      - Simpler glitches expected.
      - Players that play the AP randomizer often should be able to perform all tricks in this difficulty efficiency,
      after some practice and/or learning.
      - Slam triple jumps included in logic.
      - Expects more platforming off of terrain
      - (incomplete, most levels will use None difficulty logic)
    - Hard:
      - More difficult jumps and tricks.
      - (incomplete, most levels will use None difficulty logic)
    """
    # - Expert: Includes out-of-bounds clips and 1P2C that is more than just holding down a single button for P2.
    # Comparable to Glitched logic in ViolaGuy's TCS randomizer.
    # - Super Expert: Super Jumps, DV3 Skip, CCT door clip and more. Comparable to Super Glitched logic in ViolaGuy's
    # standalone TCS randomizer.
    option_none = 0
    option_normal = 1
    option_moderate = 2
    option_hard = 3
    # option_expert = 4
    # option_super_expert = 5


@dataclass
class LegoStarWarsTCSOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool

    # Goals.
    minikit_goal_amount: MinikitGoalAmount
    minikit_goal_amount_percentage: MinikitGoalAmountPercentage
    minikit_bundle_size: MinikitBundleSize

    defeat_bosses_goal_amount: DefeatBossesGoalAmount
    enabled_bosses_count: EnabledBossesCount
    allowed_bosses: AllowedBosses
    only_unique_bosses_count: OnlyUniqueBossesCountTowardsGoal

    # Enabled/Available locations.
    # Chapters.
    enabled_chapters_count: EnabledChaptersCount
    allowed_chapters: AllowedChapters
    allowed_chapter_types: AllowedChapterTypes
    starting_chapter: StartingChapter
    preferred_chapters: PreferredChapters
    prefer_entire_episodes: PreferEntireEpisodes
    enable_story_character_unlock_locations: EnableChapterCompletionCharacterUnlockLocations
    enable_bonus_locations: EnableBonusLocations
    enable_all_episodes_purchases: EnableAllEpisodesCharacterPurchaseLocations
    enable_minikit_locations: EnableMinikitLocations
    enable_true_jedi_locations: EnableTrueJediLocations

    # Logic.
    # logic_difficulty: LogicDifficulty
    episode_unlock_requirement: EpisodeUnlockRequirement
    # todo: Requires logic rewrite
    # chapter_unlock_requirement: ChapterUnlockRequirement
    most_expensive_purchase_with_no_multiplier: MostExpensivePurchaseWithNoScoreMultiplier
    all_episodes_character_purchase_requirements: AllEpisodesCharacterPurchaseRequirements

    # Items.
    preferred_characters: PreferredCharacters
    preferred_extras: PreferredExtras
    start_with_detectors: StartWithDetectors
    filler_reserve_characters: FillerReserveCharacters
    filler_reserve_extras: FillerReserveExtras
    filler_weight_characters: FillerWeightCharacters
    filler_weight_extras: FillerWeightExtras
    filler_weight_junk: FillerWeightJunk

    # Client behaviour.
    received_item_messages: ReceivedItemMessages
    checked_location_messages: CheckedLocationMessages
    # Future options, not implemented yet.
    # random_starting_level_max_starting_characters: RandomStartingLevelMaxStartingCharacters


OPTION_GROUPS: list[OptionGroup] = [
    OptionGroup("Minikit Goal Options", [
        MinikitGoalAmount,
        MinikitGoalAmountPercentage,
    ]),
    OptionGroup("Bosses Goal Options", [
        DefeatBossesGoalAmount,
        EnabledBossesCount,
        AllowedBosses,
        OnlyUniqueBossesCountTowardsGoal,
    ]),
    OptionGroup("Chapter Options", [
        EnabledChaptersCount,
        AllowedChapters,
        AllowedChapterTypes,
        StartingChapter,
        PreferredChapters,
        PreferEntireEpisodes,
    ]),
    OptionGroup("Location Options", [
        EnableMinikitLocations,
        EnableTrueJediLocations,
        EnableChapterCompletionCharacterUnlockLocations,
        EnableBonusLocations,
        EnableAllEpisodesCharacterPurchaseLocations,
    ]),
    OptionGroup("Logic Options", [
        EpisodeUnlockRequirement,
        MostExpensivePurchaseWithNoScoreMultiplier,
        AllEpisodesCharacterPurchaseRequirements,
    ]),
    OptionGroup("Item Options", [
        MinikitBundleSize,
        StartWithDetectors,
        PreferredCharacters,
        PreferredExtras,
        FillerReserveCharacters,
        FillerReserveExtras,
        FillerWeightCharacters,
        FillerWeightExtras,
        FillerWeightJunk,
    ]),
    OptionGroup("Client Options", [
        ReceivedItemMessages,
        CheckedLocationMessages,
    ])
]