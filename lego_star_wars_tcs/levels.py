import struct
from collections import Counter
from dataclasses import dataclass, field
from typing import ClassVar

from .constants import (
    CharacterAbility,
    HIGH_JUMP,
    IMPERIAL,
    SHORTIE,
    SITH,
    DROID_OR_FLY,
    BOUNTY_HUNTER,
    ASTROMECH,
    BLASTER,
    VEHICLE_TIE,
    VEHICLE_TOW,
)
from .items import SHOP_SLOT_REQUIREMENT_TO_UNLOCKS


@dataclass(frozen=True)
class ChapterArea:
    """
    Each game level/chapter within an Episode, e.g. 1-4 is represented by an Area, see AREAS.TXT.

    Does not include Character Bonus, Minikit Bonus, or Superstory, though the first two do have their own Areas.
    """
    # Used as a bool or as `value > 0`. The bits other than the first get preserved, so it appears to be safe to store
    # arbitrary data in the remaining 7 bits.
    UNLOCKED_OFFSET: ClassVar[int] = 0

    # Used as a bool or as `value > 0`. The bits other than the first get preserved, so it appears to be safe to store
    # arbitrary data in the remaining 7 bits, which is where the client stores Free Play completion.
    STORY_COMPLETE_OFFSET: ClassVar[int] = 1

    # Used as a bool or as `value > 0`. The bits other than the first get preserved, so it appears to be safe to store
    # arbitrary data in the remaining 7 bits.
    TRUE_JEDI_COMPLETE_OFFSET: ClassVar[int] = 2

    # The 3rd byte also gets set when True Jedi is completed. Having either the second byte or the second byte as
    # nonzero counts for True Jedi being completed.
    # Maybe one of the two bytes is a leftover from having separate True Jedi for Story and Free Play originally, like
    # in some later, non-Star Wars games?
    TRUE_JEDI_COMPLETE_2_OFFSET: ClassVar[int] = 3

    # Used as a bool or as `value > 0`. The bits other than the first get preserved, so it appears to be safe to store
    # arbitrary data in the remaining 7 bits.
    MINIKIT_GOLD_BRICK_OFFSET: ClassVar[int] = 4

    # Setting this to 10 or higher will prevent newly collected minikits from being saved as collected.
    MINIKIT_COUNT_OFFSET: ClassVar[int] = 5

    # Must be exactly `1`
    POWER_BRICK_COLLECTED_OFFSET: ClassVar[int] = 6

    # Used as a bool or as `value > 0`. The bits other than the first get preserved, so it appears to be safe to store
    # arbitrary data in the remaining 7 bits.
    CHALLENGE_COMPLETE_OFFSET: ClassVar[int] = 7

    # Unused, 4-byte float that preserves NaN signal bits and appears to never be written to normally, so can be used to
    # store arbitrary data.
    UNUSED_CHALLENGE_BEST_TIME_OFFSET: ClassVar[int] = 8
    # The default, unused value is 1200 seconds, or 20 minutes, as a single-precision float.
    UNUSED_CHALLENGE_BEST_TIME_VALUE: ClassVar[bytes] = struct.pack("f", 1200.0)

    name: str
    # The episode this Area is in.
    episode: int
    # The number within the episode that this Area is in.
    number_in_episode: int
    # # Level IDs, see the order of the levels defined in LEVELS.TXT.
    # # These are the individual playable 'levels' within a game level, and also include intros, outros and the 'status'
    # # screen at the end of a game level.
    # level_ids: set[int]
    # The address in the in-memory save data that stores most of the Area information.
    address: int
    # The level ID of the 'status' screen used when tallying up collected studs/minikits/etc., either from
    # "Save and Exit to Cantina", or from completing the level.
    status_level_id: int
    area_id: int
    ## The address of each Level in the area with minikits, and the names of the minikits in that Level.
    #minikit_address_to_names: dict[int, set[str]]
    # TODO: Convert this file mostly into a script that writes `print(repr(GAME_LEVEL_AREAS))`
    short_name: str = field(init=False)
    character_requirements: frozenset[str] = field(init=False)
    shop_unlocks: frozenset[str] = field(init=False)
    power_brick_ability_requirements: CharacterAbility = field(init=False)
    power_brick_location_name: str = field(init=False)
    all_minikits_ability_requirements: CharacterAbility = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "short_name", f"{self.episode}-{self.number_in_episode}")

        character_requirements = CHAPTER_AREA_CHARACTER_REQUIREMENTS[self.short_name]
        object.__setattr__(self, "character_requirements", character_requirements)

        shop_unlocks = frozenset([f"Purchase {character}" for character
                                  in SHOP_SLOT_REQUIREMENT_TO_UNLOCKS.get(self.short_name, ())])
        object.__setattr__(self, "shop_unlocks", shop_unlocks)

        power_brick_location_name, power_brick_ability_requirements = POWER_BRICK_REQUIREMENTS[self.short_name]
        power_brick_location_name = f"Purchase {power_brick_location_name} ({self.short_name})"
        object.__setattr__(self, "power_brick_location_name", power_brick_location_name)
        if power_brick_ability_requirements is None:
            power_brick_ability_requirements = CharacterAbility.NONE
        object.__setattr__(self, "power_brick_ability_requirements", power_brick_ability_requirements)

        all_minikits_ability_requirements = ALL_MINIKITS_REQUIREMENTS[self.short_name]
        object.__setattr__(self, "all_minikits_ability_requirements", all_minikits_ability_requirements)


@dataclass(frozen=True)
class BonusArea:
    name: str
    address: int
    completion_offset: int
    """
    The cheat table listing the addresses listed a base address with unknown purpose for the bonus levels, and then an
    offset from that address for the completion byte, so that is why there is an offset separate from the address.
    """
    status_level_id: int
    area_id: int
    item_requirements: Counter[str]
    gold_brick: bool = True


# GameLevelArea short_name to the set of characters needed to unlock that GameLevelArea
# To find characters, grep the LEVELS directory for non-binary files, searching for '" player'. Note that vehicle levels
# typically have an alternate color scheme vehicle for Player 2 which may not be collectable.
CHAPTER_AREA_CHARACTER_REQUIREMENTS: dict[str, frozenset[str]] = {
    k: frozenset(v) for k, v in {
        # "1-1": {
        #     "Obi-Wan Kenobi",
        #     "Qui-Gon Jinn",
        #     "TC-14",
        # },
        "1-1": set(),
        "1-2": {
            # "Obi-Wan Kenobi",
            # "Qui-Gon Jinn",
            "Jar Jar Binks",
        },
        "1-3": {
            # "Obi-Wan Kenobi",
            # "Qui-Gon Jinn",
            "Captain Panaka",
            "Queen Amidala",
        },
        "1-4": {
            "Anakin's Pod",
        },
        "1-5": {
            # "Obi-Wan Kenobi",
            # "Qui-Gon Jinn",
            "Anakin Skywalker (Boy)",
            "Captain Panaka",
            "Padmé (Battle)",
            "R2-D2",
        },
        "1-6": set(),
        # "1-6": {
        #     "Obi-Wan Kenobi",
        #     "Qui-Gon Jinn",
        # },
        "2-1": {
            "Anakin's Speeder",
        },
        "2-2": {
            "Obi-Wan Kenobi (Jedi Master)",
            "R4-P17",
        },
        "2-3": {
            "Anakin Skywalker (Padawan)",
            "C-3PO",
            "Padmé (Geonosis)",
            "R2-D2",
        },
        "2-4": {
            "Anakin Skywalker (Padawan)",
            "Mace Windu",
            "Padmé (Clawed)",
            "Obi-Wan Kenobi (Jedi Master)",
            "R2-D2",
        },
        "2-5": {
            "Republic Gunship",
        },
        "2-6": {
            "Anakin Skywalker (Padawan)",
            "Obi-Wan Kenobi (Jedi Master)",
            "Yoda",
        },
        "3-1": {
            "Anakin's Starfighter",
            "Obi-Wan's Starfighter",
            # These non-vehicle characters are also listed as player characters in the file, but do not get unlocked
            # when completing the chapter in Story mode, so should not be requirements to play the chapter:
            # "Obi-Wan Kenobi (Episode 3)",
            # "Anakin Skywalker (Jedi)",
        },
        "3-2": {
            "Anakin Skywalker (Jedi)",
            "Chancellor Palpatine",
            "Obi-Wan Kenobi (Episode 3)",
            "R2-D2",
        },
        "3-3": {
            "Commander Cody",
            "Obi-Wan Kenobi (Episode 3)",
        },
        "3-4": {
            "Chewbacca",
            "Yoda",
        },
        "3-5": {
            "Obi-Wan Kenobi (Episode 3)",
            "Yoda",
        },
        "3-6": {
            "Anakin Skywalker (Jedi)",
            "Obi-Wan Kenobi (Episode 3)",
        },
        "4-1": {
            "Captain Antilles",
            "C-3PO",
            "Princess Leia",
            "R2-D2",
            "Rebel Friend",
        },
        "4-2": {
            "Ben Kenobi",
            "C-3PO",
            "Luke Skywalker (Tatooine)",
            "R2-D2",
        },
        "4-3": {
            "Ben Kenobi",
            "C-3PO",
            "Chewbacca",
            "Han Solo",
            "Luke Skywalker (Tatooine)",
            "R2-D2",
        },
        "4-4": {
            "Ben Kenobi",
            "C-3PO",
            "Chewbacca",
            "Han Solo (Stormtrooper)",
            "Luke Skywalker (Stormtrooper)",
            "R2-D2",
        },
        "4-5": {
            "C-3PO",
            "Chewbacca",
            "Han Solo",
            "Luke Skywalker (Tatooine)",
            "Princess Leia",
            "R2-D2",
        },
        "4-6": {
            "X-Wing",
            "Y-Wing",
        },
        "5-1": {
            "Snowspeeder",
        },
        "5-2": {
            "C-3PO",
            "Chewbacca",
            "Han Solo (Hoth)",
            "Princess Leia (Hoth)",
        },
        "5-3": {
            "Millennium Falcon",
            "X-Wing",
        },
        "5-4": {
            "Luke Skywalker (Dagobah)",
            "Luke Skywalker (Pilot)",
            "R2-D2",
            "Yoda",
        },
        "5-5": {
            "Luke Skywalker (Bespin)",
            "R2-D2",
        },
        "5-6": {
            "C-3PO",
            "Lando Calrissian",
            "Princess Leia (Bespin)",
            "R2-D2",
            "Chewbacca",
        },
        "6-1": {
            "Chewbacca",
            "C-3PO",
            "Han Solo (Skiff)",
            "Princess Leia (Boushh)",
            "Luke Skywalker (Jedi)",
            "R2-D2",
        },
        "6-2": {
            "Chewbacca",
            "C-3PO",
            "Han Solo (Skiff)",
            "Princess Leia (Slave)",
            "Lando Calrissian (Palace Guard)",
            "Luke Skywalker (Jedi)",
            "R2-D2",
        },
        "6-3": {
            "Luke Skywalker (Endor)",
            "Princess Leia (Endor)",
        },
        "6-4": {
            "Chewbacca",
            "C-3PO",
            "Han Solo (Endor)",
            "Princess Leia (Endor)",
            "R2-D2",
            "Wicket",
        },
        "6-5": {
            "Darth Vader",
            "Luke Skywalker (Jedi)",
        },
        "6-6": {
            "Millennium Falcon",
            "X-Wing",
        }
    }.items()
}

IMPORTANT_LEVEL_REQUIREMENT_CHARACTERS: frozenset[str] = frozenset({
    "C-3PO",
    "R2-D2",
    "Chewbacca",
})

POWER_BRICK_REQUIREMENTS: dict[str, tuple[str, CharacterAbility | None]] = {
    # TODO: For future version, it is necessary to determine which Extras need Jedi/Protocol Droids to access.
    "1-1": ("Super Gonk", ASTROMECH),
    "1-2": ("Poo Money", BOUNTY_HUNTER),
    "1-3": ("Walkie Talkie Disable", BOUNTY_HUNTER | SITH),
    "1-4": ("Red Brick Detector", None),
    "1-5": ("Super Slap", None),
    "1-6": ("Force Grapple Leap", IMPERIAL),
    "2-1": ("Stud Magnet", None),
    "2-2": ("Disarm Troopers", IMPERIAL),
    "2-3": ("Character Studs", None),
    "2-4": ("Perfect Deflect", BOUNTY_HUNTER),
    "2-5": ("Exploding Blaster Bolts", None),
    "2-6": ("Force Pull", BOUNTY_HUNTER | SHORTIE),
    "3-1": ("Vehicle Smart Bomb", None),
    "3-2": ("Super Astromech", BOUNTY_HUNTER),
    "3-3": ("Super Jedi Slam", None),
    "3-4": ("Super Thermal Detonator", BOUNTY_HUNTER | SITH),
    "3-5": ("Deflect Bolts", SITH | HIGH_JUMP),
    "3-6": ("Dark Side", ASTROMECH),
    "4-1": ("Super Blasters", None),
    "4-2": ("Fast Force", BOUNTY_HUNTER),
    "4-3": ("Super Lightsabers", None),
    "4-4": ("Tractor Beam", None),
    "4-5": ("Invincibility", None),
    "4-6": ("Score x2", None),
    "5-1": ("Self Destruct", VEHICLE_TIE),
    "5-2": ("Fast Build", SITH),
    "5-3": ("Score x4", None),
    "5-4": ("Regenerate Hearts", SITH),
    "5-5": ("Score x6", BOUNTY_HUNTER | DROID_OR_FLY),
    "5-6": ("Minikit Detector", BOUNTY_HUNTER),
    "6-1": ("Super Zapper", None),
    "6-2": ("Bounty Hunter Rockets", None),
    "6-3": ("Score x8", SHORTIE),
    "6-4": ("Super Ewok Catapult", SHORTIE),
    "6-5": ("Score x10", None),
    "6-6": ("Infinite Torpedos", None),
}

ALL_MINIKITS_REQUIREMENTS: dict[str, CharacterAbility] = {
    "1-1": HIGH_JUMP | ASTROMECH | DROID_OR_FLY | SHORTIE,
    "1-2": SHORTIE,
    "1-3": SITH | HIGH_JUMP | DROID_OR_FLY | BOUNTY_HUNTER | SHORTIE,
    "1-4": VEHICLE_TIE,
    "1-5": SITH | BOUNTY_HUNTER | HIGH_JUMP,
    "1-6": SITH | HIGH_JUMP | BLASTER | BOUNTY_HUNTER | IMPERIAL,
    "2-1": VEHICLE_TIE,
    "2-2": SITH | HIGH_JUMP | BLASTER | BOUNTY_HUNTER | SHORTIE,
    "2-3": HIGH_JUMP | IMPERIAL | SHORTIE,
    "2-4": HIGH_JUMP,
    "2-5": VEHICLE_TIE,
    "2-6": HIGH_JUMP | BLASTER | ASTROMECH,
    "3-1": CharacterAbility.NONE,
    "3-2": HIGH_JUMP | BLASTER | SHORTIE,
    "3-3": DROID_OR_FLY | BOUNTY_HUNTER,
    "3-4": SITH | HIGH_JUMP,
    "3-5": SITH | HIGH_JUMP | BLASTER | DROID_OR_FLY | BOUNTY_HUNTER | IMPERIAL,
    "3-6": DROID_OR_FLY,
    "4-1": SITH | BOUNTY_HUNTER | IMPERIAL,
    "4-2": SITH | SHORTIE,
    "4-3": SITH | HIGH_JUMP | BOUNTY_HUNTER | SHORTIE,
    "4-4": SITH | BOUNTY_HUNTER | IMPERIAL,
    "4-5": SITH | BOUNTY_HUNTER | IMPERIAL | SHORTIE,
    "4-6": VEHICLE_TOW | VEHICLE_TIE,
    "5-1": VEHICLE_TIE,
    "5-2": SITH | DROID_OR_FLY | ASTROMECH | BOUNTY_HUNTER,
    "5-3": VEHICLE_TOW | VEHICLE_TIE,
    "5-4": SITH | BOUNTY_HUNTER,
    "5-5": SITH | BOUNTY_HUNTER | IMPERIAL | SHORTIE,
    "5-6": SITH | BOUNTY_HUNTER,
    "6-1": SITH | BOUNTY_HUNTER | IMPERIAL | SHORTIE,
    "6-2": SITH | DROID_OR_FLY | SHORTIE,
    "6-3": SITH | HIGH_JUMP | BOUNTY_HUNTER | IMPERIAL | SHORTIE,
    "6-4": BOUNTY_HUNTER,
    "6-5": HIGH_JUMP | BLASTER | BOUNTY_HUNTER | SHORTIE,
    "6-6": VEHICLE_TIE,
}

# TODO: Record Level IDs, these would mostly be there to help make map switching in the tracker easier, and would
#  serve as a record of data that might be useful for others.
CHAPTER_AREAS = [
    # area -1/255 = Cantina
    ChapterArea("Negotiations", 1, 1, 0x86E0F4, 7, 0),
    ChapterArea("Invasion of Naboo", 1, 2, 0x86E100, 15, 1),
    ChapterArea("Escape From Naboo", 1, 3, 0x86E10C, 24, 2),
    ChapterArea("Mos Espa Pod Race", 1, 4, 0x86E118, 37, 3),
    # area 4 = Bonus: Pod Race (Original)
    ChapterArea("Retake Theed Palace", 1, 5, 0x86E130, 48, 5),
    ChapterArea("Darth Maul", 1, 6, 0x86E13C, 55, 6),
    # area 7 = EP1 Ending
    # area 8 = EP1 Character Bonus
    # area 9 = EP1 Minikit Bonus. Episode Bonus doors show the Minikit Bonus Area ID rather than Character Bonus Area ID
    ChapterArea("Bounty Hunter Pursuit", 2, 1, 0x86E16C, 68, 10),
    ChapterArea("Discovery On Kamino", 2, 2, 0x86E178, 78, 11),
    ChapterArea("Droid Factory", 2, 3, 0x86E184, 88, 12),
    ChapterArea("Jedi Battle", 2, 4, 0x86E190, 92, 13),
    ChapterArea("Gunship Cavalry", 2, 5, 0x86E19C, 95, 14),
    # area 15 = Bonus: Gunship Cavalry (Original)
    ChapterArea("Count Dooku", 2, 6, 0x86E1B4, 103, 16),
    ChapterArea("Battle Over Coruscant", 3, 1, 0x86E1E4, 111, 20),
    ChapterArea("Chancellor In Peril", 3, 2, 0x86E1F0, 121, 21),
    ChapterArea("General Grievous", 3, 3, 0x86E1FC, 123, 22),
    ChapterArea("Defense Of Kashyyyk", 3, 4, 0x86E208, 128, 23),
    ChapterArea("Ruin Of The Jedi", 3, 5, 0x86E214, 134, 24),
    ChapterArea("Darth Vader", 3, 6, 0x86E220, 139, 25),
    # area 26 = EP3 Ending
    # area 27 = EP3 Character Bonus
    # area 28 = EP3 Minikit Bonus
    # area 29 = Bonus: A New Hope
    ChapterArea("Secret Plans", 4, 1, 0x86E25C, 159, 30),
    ChapterArea("Through The Jundland Wastes", 4, 2, 0x86E268, 167, 31),
    ChapterArea("Mos Eisley Spaceport", 4, 3, 0x86E274, 177, 32),
    ChapterArea("Rescue The Princess", 4, 4, 0x86E280, 185, 33),
    ChapterArea("Death Star Escape", 4, 5, 0x86E28C, 192, 34),
    ChapterArea("Rebel Attack", 4, 6, 0x86E298, 203, 35),
    # area 36 = EP4 Ending
    # area 37 = EP4 Character Bonus
    # area 38 = EP4 Minikit Bonus
    ChapterArea("Hoth Battle", 5, 1, 0x86E2C8, 219, 39),
    ChapterArea("Escape From Echo Base", 5, 2, 0x86E2D4, 228, 40),
    ChapterArea("Falcon Flight", 5, 3, 0x86E2E0, 236, 41),
    ChapterArea("Dagobah", 5, 4, 0x86E2EC, 244, 42),
    ChapterArea("Cloud City Trap", 5, 5, 0x86E2F8, 257, 43),  # 5-5 levels are after 5-6 levels for some reason.
    ChapterArea("Betrayal Over Bespin", 5, 6, 0x86E304, 251, 44),
    # area 45 = EP5 Ending
    # area 46 = EP5 Character Bonus
    # area 47 = EP5 Minikit Bonus
    ChapterArea("Jabba's Palace", 6, 1, 0x86E334, 271, 48),
    ChapterArea("The Great Pit Of Carkoon", 6, 2, 0x86E340, 277, 49),
    ChapterArea("Speeder Showdown", 6, 3, 0x86E34C, 279, 50),
    ChapterArea("The Battle Of Endor", 6, 4, 0x86E358, 286, 51),
    ChapterArea("Jedi Destiny", 6, 5, 0x86E364, 301, 52),
    ChapterArea("Into The Death Star", 6, 6, 0x86E370, 297, 53),
    # area 54 = EP6 Ending
    # area 55 = EP6 Character Bonus
    # area 56 = EP6 Minikit Bonus
    # area 57 = Bonus: New Town
    # area 58 = Bonus: Anakin's Flight
    # area 59 = Bonus: Lego City
    # area 60 = Two Player Arcade
    # area 66 = Cantina
    # area 67 = Bonus: Trailers door
]


# todo: Need to consider the Gold Brick shop eventually. Also Bounty Hunter missions.
BONUS_AREAS = [
    BonusArea("Mos Espa Pod Race (Original)", 0x86E124, 0x1, 35, 4, Counter({
        "Anakin's Pod": 1,
        "Progressive Bonus Level": 1,
        "Gold Brick": 10,
    })),
    # There are a number of test levels in LEVELS.TXT that seem to not be counted, so the level IDs for Anakin's Flight
    # do not match what is expected:
    # Intro = 327
    # A = 328
    # B = 329
    # C = 330
    # Outro1 = 331
    # Outro2 = 332
    # Status = 333
    BonusArea("Anakin's Flight", 0x86E3AC, 0x1, 333, 58, Counter({
        "Naboo Starfighter": 1,
        "Progressive Bonus Level": 2,
        "Gold Brick": 30,
    })),
    BonusArea("Gunship Cavalry (Original)", 0x86E1A8, 0x1, 98, 15, Counter({
        "Republic Gunship": 1,
        "Progressive Bonus Level": 3,
        "Gold Brick": 10,
    })),
    BonusArea("A New Hope (Bonus Level)", 0x86E3B8, 0x8, 150, 29, Counter({
        "Darth Vader": 1,
        "Stormtrooper": 1,
        "C-3PO": 1,
        "Progressive Bonus Level": 4,
        "Gold Brick": 20,
    })),
    BonusArea("LEGO City", 0x86E3B8, 0x1, 311, 59, Counter({
        "Progressive Bonus Level": 5,
        "Gold Brick": 10,
    })),
    BonusArea("New Town", 0x86E3A0, 0x1, 309, 57, Counter({
        "Progressive Bonus Level": 6,
        "Gold Brick": 50,
    })),
    # The bonus level was never completed, so there is just the trailer to watch (which can be skipped immediately).
    # No gold brick for watching the trailer, but it does unlock the shop slot for purchasing Indiana Jones in vanilla
    # todo: Add the Purchase Indiana Jones location.
    # It looks like the unfinished Indiana Jones level would have been Area 67, though this is inaccessible.
    BonusArea("Indiana Jones: Trailer", 0x86E4E5, 0x0, -1, 67, Counter({
        "Progressive Bonus Level": 1,
    }), gold_brick=False)
]

# todo: Rewrite this to be cleaner, probably by splitting the BonusGameLevelArea requirements into characters and other
#  items.
BONUS_AREA_REQUIREMENT_CHARACTERS = [
    [item for item in area.item_requirements.keys() if item not in ("Progressive Bonus Level", "Gold Brick")]
    for area in BONUS_AREAS
]

ALL_AREA_REQUIREMENT_CHARACTERS: frozenset[str] = frozenset().union(
    *CHAPTER_AREA_CHARACTER_REQUIREMENTS.values(),
    *BONUS_AREA_REQUIREMENT_CHARACTERS
)

SHORT_NAME_TO_CHAPTER_AREA = {area.short_name: area for area in CHAPTER_AREAS}
EPISODE_TO_CHAPTER_AREAS = {i + 1: CHAPTER_AREAS[i * 6:(i + 1) * 6] for i in range(6)}
AREA_ID_TO_CHAPTER_AREA = {area.area_id: area for area in CHAPTER_AREAS}
STATUS_LEVEL_IDS = (
        {area.status_level_id for area in CHAPTER_AREAS} | {area.status_level_id for area in BONUS_AREAS
                                                            if area.status_level_id != -1}
)
