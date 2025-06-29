from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, ClassVar, Literal, Iterable

from BaseClasses import Item, ItemClassification
from .constants import (
    CharacterAbility,
    GAME_NAME,
    ASTROMECH,
    BLASTER,
    BOUNTY_HUNTER,
    DROID_OR_FLY,
    HIGH_JUMP,
    IMPERIAL,
    JEDI,
    PROTOCOL_DROID,
    SHORTIE,
    SITH,
    VEHICLE_TIE,
    VEHICLE_TOW,
)

if TYPE_CHECKING:
    from . import LegoStarWarsTCSWorld
else:
    LegoStarWarsTCSWorld = object


ItemType = Literal["Character", "Vehicle", "Extra", "Generic", "Minikit"]


class LegoStarWarsTCSItem(Item):
    game = GAME_NAME
    # Most Progression items collect their abilities into the state through a world.collect() override.
    collect_extras: tuple[str, ...] | None

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int,
                 collect_extras: Iterable[str] | None = None):
        super().__init__(name, classification, code, player)
        self.collect_extras = tuple(collect_extras) if collect_extras is not None else None


@dataclass(frozen=True)
class GenericItemData:
    code: int
    name: str
    item_type: ClassVar[ItemType] = "Generic"


@dataclass(frozen=True)
class MinikitItemData(GenericItemData):
    bundle_size: int
    item_type: ClassVar[ItemType] = "Minikit"


@dataclass(frozen=True)
class GenericCharacterData(GenericItemData):
    character_index: int
    abilities: CharacterAbility = CharacterAbility.NONE
    shop_slot: int = field(init=False)

    def __post_init__(self):
        shop_slot = CHARACTER_TO_SHOP_SLOT.get(self.name, -1)
        object.__setattr__(self, "shop_slot", shop_slot)


@dataclass(frozen=True)
class CharacterData(GenericCharacterData):
    item_type: ClassVar[ItemType] = "Character"


@dataclass(frozen=True)
class VehicleData(GenericCharacterData):
    item_type: ClassVar[ItemType] = "Vehicle"


@dataclass(frozen=True)
class ExtraData(GenericItemData):
    extra_number: int
    level_shortname: str | None
    item_type: ClassVar[ItemType] = "Extra"
    shop_slot_byte: int = field(init=False)
    shop_slot_bit_mask: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "shop_slot_byte", self.extra_number // 8)
        object.__setattr__(self, "shop_slot_bit_mask", 1 << (self.extra_number % 8))


# Purchasable characters and how they are unlocked, in the order they appear in the shop.
# See the order of characters in COLLECTION.TXT that use "buy_in_shop", plus Indiana Jones, who is special.
CHARACTER_SHOP_SLOTS: dict[str, str | None] = {
    "Gonk Droid": None,
    "PK Droid": None,

    # Episode 1
    "Battle Droid": "1-1",
    "Battle Droid (Security)": "1-1",
    "Battle Droid (Commander)": "1-1",
    "Droideka": "1-1",

    "Captain Tarpals": "1-2",
    "Boss Nass": "1-2",

    "Royal Guard": "1-3",
    "Padmé": "1-3",

    "Watto": "1-4",
    "Pit Droid": "1-4",

    # No non-vehicle characters for 1-5

    "Darth Maul": "1-6",

    # Episode 2
    "Zam Wesell": "2-1",
    "Dexter Jettster": "2-1",

    "Clone": "2-2",
    "Lama Su": "2-2",
    "Taun We": "2-2",

    "Geonosian": "2-3",
    "Battle Droid (Geonosis)": "2-3",

    "Super Battle Droid": "2-4",
    "Jango Fett": "2-4",
    "Boba Fett (Boy)": "2-4",
    "Luminara": "2-4",
    "Ki-Adi Mundi": "2-4",
    "Kit Fisto": "2-4",
    "Shaak Ti": "2-4",
    "Aayla Secura": "2-4",
    "Plo Koon": "2-4",

    # No non-vehicle characters for 2-5 or 2-6

    # Episode 3
    # No non-vehicle characters for 3-1

    "Count Dooku": "3-2",
    "Grievous' Bodyguard": "3-2",

    "General Grievous": "3-3",

    "Wookiee": "3-4",
    "Clone (Episode 3)": "3-4",
    "Clone (Episode 3, Pilot)": "3-4",
    "Clone (Episode 3, Swamp)": "3-4",
    "Clone (Episode 3, Walker)": "3-4",

    "Mace Windu (Episode 3)": "3-5",
    "Disguised Clone": "3-5",

    # No non-vehicle characters for 3-6

    # Episode 4
    "Rebel Trooper": "4-1",
    "Stormtrooper": "4-1",
    "Imperial Shuttle Pilot": "4-1",

    "Tusken Raider": "4-2",
    "Jawa": "4-2",

    "Sandtrooper": "4-3",
    "Greedo": "4-3",
    "Imperial Spy": "4-3",

    "Beach Trooper": "4-4",
    "Death Star Trooper": "4-4",
    "TIE Fighter Pilot": "4-4",
    "Imperial Officer": "4-4",
    "Grand Moff Tarkin": "4-4",

    # No non-vehicle characters for 4-5 or 4-6

    # Episode 5
    # No non-vehicle characters for 5-1

    "Han Solo (Hood)": "5-2",
    "Rebel Trooper (Hoth)": "5-2",
    "Rebel Pilot": "5-2",
    "Snowtrooper": "5-2",
    "Luke Skywalker (Hoth)": "5-2",

    # No non-vehicle characters for 5-3, 5-4 or 5-5

    "Lobot": "5-6",
    "Ugnaught": "5-6",
    "Bespin Guard": "5-6",
    "Princess Leia (Prisoner)": "5-6",

    # Episode 6
    "Gamorrean Guard": "6-1",
    "Bib Fortuna": "6-1",
    "Palace Guard": "6-1",
    "Bossk": "6-1",

    "Skiff Guard": "6-2",
    "Boba Fett": "6-2",

    # No non-vehicle characters for 6-3

    "Ewok": "6-4",

    "Imperial Guard": "6-5",
    "The Emperor": "6-5",

    "Admiral Ackbar": "6-6",

    # All Episodes complete
    "IG-88": "ALL_EPISODES",
    "Dengar": "ALL_EPISODES",
    "4-LOM": "ALL_EPISODES",
    "Ben Kenobi (Ghost)": "ALL_EPISODES",
    "Anakin Skywalker (Ghost)": "ALL_EPISODES",
    "Yoda (Ghost)": "ALL_EPISODES",
    "R2-Q5": "ALL_EPISODES",

    # Watch Indiana Jones trailer
    "Indiana Jones": "INDY_TRAILER",

    # Episode 1 Vehicles
    "Sebulba's Pod": "1-4",

    # Episode 2 Vehicles
    "Zam's Airspeeder": "2-1",

    # Episode 3 Vehicles
    "Droid Trifighter": "3-1",
    "Vulture Droid": "3-1",
    "Clone Arcfighter": "3-1",

    # Episode 4 Vehicles
    "TIE Fighter": "4-6",
    "TIE Interceptor": "4-6",
    "TIE Fighter (Darth Vader)": "4-6",

    # Episode 5 Vehicles
    "TIE Bomber": "5-3",
    "Imperial Shuttle": "5-3",
}


def _make_shop_slot_requirement_to_unlocks() -> dict[str | None, frozenset[str]]:
    d: dict[str | None, set[str]] = {}
    for character_name, unlock_requirement in CHARACTER_SHOP_SLOTS.items():
        if unlock_requirement not in d:
            names = set()
            d[unlock_requirement] = names
        else:
            names = d[unlock_requirement]
        names.add(character_name)

    return {k: frozenset(v) for k, v in d.items()}


SHOP_SLOT_REQUIREMENT_TO_UNLOCKS: dict[str | None, frozenset[str]] = _make_shop_slot_requirement_to_unlocks()
del _make_shop_slot_requirement_to_unlocks

CHARACTER_TO_SHOP_SLOT = {name: i for i, name in enumerate(CHARACTER_SHOP_SLOTS.keys())}


_generic = GenericItemData
_char = CharacterData
_vehicle = VehicleData
_extra = ExtraData


ITEM_DATA: list[GenericItemData] = [
    MinikitItemData(1, "5 Minikits", 5),
    _char(2, "Jar Jar Binks", 99, abilities=HIGH_JUMP),
    _char(3, "Queen Amidala", 80, abilities=BLASTER),
    _char(4, "Captain Panaka", 98, abilities=BLASTER),
    _char(5, "Padmé (Battle)", 77, abilities=BLASTER),
    _char(6, "R2-D2", 8, abilities=ASTROMECH | DROID_OR_FLY),
    _char(7, "Anakin Skywalker (Boy)", 93, abilities=SHORTIE),
    _char(8, "Obi-Wan Kenobi (Jedi Master)", 75, abilities=JEDI),
    _char(9, "R4-P17", 66, abilities=ASTROMECH | DROID_OR_FLY),
    _char(10, "Anakin Skywalker (Padawan)", 97, abilities=JEDI),
    _char(11, "Padmé (Geonosis)", 79, abilities=BLASTER),
    _char(12, "C-3PO", 12, abilities=PROTOCOL_DROID),
    _char(13, "Mace Windu", 62, abilities=JEDI),
    _char(14, "Padmé (Clawed)", 78, abilities=BLASTER),
    _char(15, "Yoda", 10, abilities=JEDI),
    _char(16, "Obi-Wan Kenobi (Episode 3)", 74, abilities=JEDI),
    _char(17, "Anakin Skywalker (Jedi)", 96, abilities=JEDI),
    _char(18, "Chancellor Palpatine", 73),
    _char(19, "Commander Cody", 89, abilities=BLASTER | IMPERIAL),
    _char(20, "Chewbacca", 16, abilities=BLASTER),
    _char(21, "Princess Leia", 23, abilities=BLASTER),
    _char(22, "Captain Antilles", 207, abilities=BLASTER),
    _char(23, "Rebel Friend", 190, abilities=BLASTER),
    _char(24, "Luke Skywalker (Tatooine)", 28, abilities=BLASTER),
    _char(25, "Ben Kenobi", 56, abilities=JEDI),
    _char(26, "Han Solo", 33, abilities=BLASTER),
    _char(27, "Luke Skywalker (Stormtrooper)", 29, abilities=BLASTER),
    _char(28, "Han Solo (Stormtrooper)", 34, abilities=BLASTER),
    _char(29, "Han Solo (Hoth)", 143, abilities=BLASTER),
    _char(30, "Princess Leia (Hoth)", 24, abilities=BLASTER),
    _char(31, "Luke Skywalker (Pilot)", 156, abilities=BLASTER),  # Ability missing from manual
    _char(32, "Luke Skywalker (Dagobah)", 157, abilities=JEDI),  # Ability missing from manual
    _char(33, "Luke Skywalker (Bespin)", 25, abilities=JEDI),  # Ability missing from manual
    _char(34, "Princess Leia (Boushh)", 129, abilities=BLASTER),
    _char(35, "Luke Skywalker (Jedi)", 27, abilities=JEDI),
    _char(36, "Han Solo (Skiff)", 141, abilities=BLASTER),
    _char(37, "Lando Calrissian (Palace Guard)", 201, abilities=BLASTER),
    _char(38, "Princess Leia (Slave)", 161, abilities=BLASTER),
    _char(39, "Luke Skywalker (Endor)", 26, abilities=JEDI),
    _char(40, "Princess Leia (Endor)", 162, abilities=BLASTER),
    _char(41, "Han Solo (Endor)", 206, abilities=BLASTER),
    _char(42, "Wicket", 223, abilities=SHORTIE),
    _char(43, "Darth Vader", 40, abilities=IMPERIAL | JEDI | SITH),
    _char(44, "Lando Calrissian", 35, abilities=BLASTER),
    _char(45, "Princess Leia (Bespin)", 57, abilities=BLASTER),
    _char(46, "Gonk Droid", 17),
    _char(47, "PK Droid", 100),
    _char(48, "Battle Droid", 67, abilities=BLASTER),  # ! Cannot grapple !
    _char(49, "Battle Droid (Security)", 70, abilities=BLASTER),  # ! Cannot grapple !
    _char(50, "Battle Droid (Commander)", 68, abilities=BLASTER),  # ! Cannot grapple !
    _char(51, "Droideka", 65, abilities=BLASTER),  # ! Cannot grapple !
    _char(52, "Captain Tarpals", 276, abilities=BLASTER),
    _char(53, "Boss Nass", 254),
    _char(54, "Royal Guard", 101, abilities=BLASTER),
    _char(55, "Watto", 269),
    _char(56, "Pit Droid", 268),
    _char(57, "Darth Maul", 61, abilities=JEDI | SITH),
    _char(58, "Zam Wesell", 2, abilities=BOUNTY_HUNTER | BLASTER),  # There is a second, incorrect Zam Wesell at 305
    _char(59, "Dexter Jettster", 304),
    _char(60, "Clone", 86, abilities=IMPERIAL | BLASTER),
    _char(61, "Lama Su", 280),
    _char(62, "Taun We", 281),
    _char(63, "Geonosian", 95, abilities=BLASTER),  # ? Can these grapple ?
    _char(64, "Battle Droid (Geonosis)", 69, abilities=BLASTER),  # ! Cannot grapple !
    _char(65, "Super Battle Droid", 81, abilities=BLASTER),  # ? Can these grapple ?
    _char(66, "Jango Fett", 59, abilities=BOUNTY_HUNTER | BLASTER | DROID_OR_FLY),
    _char(67, "Boba Fett (Boy)", 94, abilities=SHORTIE),
    _char(68, "Luminara", 84, abilities=JEDI),
    _char(69, "Ki-Adi Mundi", 82, abilities=JEDI),
    _char(70, "Kit Fisto", 83, abilities=JEDI),
    _char(71, "Shaak Ti", 85, abilities=JEDI),
    _char(72, "Aayla Secura", 315, abilities=JEDI),
    _char(73, "Plo Koon", 316, abilities=JEDI),
    _char(74, "Count Dooku", 103, abilities=JEDI | SITH),
    _char(75, "Grievous' Bodyguard", 64, abilities=HIGH_JUMP),
    _char(76, "General Grievous", 60, abilities=HIGH_JUMP),
    _char(77, "Wookiee", 72, abilities=BLASTER),
    _char(78, "Clone (Episode 3)", 87, abilities=IMPERIAL | BLASTER),
    _char(79, "Clone (Episode 3, Pilot)", 88, abilities=IMPERIAL | BLASTER),
    _char(80, "Clone (Episode 3, Swamp)", 90, abilities=IMPERIAL | BLASTER),
    _char(81, "Clone (Episode 3, Walker)", 91, abilities=IMPERIAL | BLASTER),
    _char(82, "Mace Windu (Episode 3)", 63, abilities=JEDI),
    _char(83, "Disguised Clone", 92, abilities=IMPERIAL | BLASTER),
    _char(84, "Rebel Trooper", 13, abilities=BLASTER),
    _char(85, "Stormtrooper", 20, abilities=IMPERIAL | BLASTER),
    _char(86, "Imperial Shuttle Pilot", 53, abilities=IMPERIAL | BLASTER),
    _char(87, "Tusken Raider", 9, abilities=BLASTER),
    _char(88, "Jawa", 22, abilities=SHORTIE),  # Note: Cannot grapple
    _char(89, "Sandtrooper", 51, abilities=IMPERIAL | BLASTER),
    _char(90, "Greedo", 171, abilities=BOUNTY_HUNTER | BLASTER),
    _char(91, "Imperial Spy", 172, abilities=IMPERIAL),
    _char(92, "Beach Trooper", 48, abilities=IMPERIAL | BLASTER),
    _char(93, "Death Star Trooper", 49, abilities=IMPERIAL | BLASTER),
    _char(94, "TIE Fighter Pilot", 50, abilities=IMPERIAL | BLASTER),
    _char(95, "Imperial Officer", 14, abilities=IMPERIAL | BLASTER),
    _char(96, "Grand Moff Tarkin", 131, abilities=IMPERIAL | BLASTER),
    _char(97, "Han Solo (Hood)", 142, abilities=BLASTER),
    _char(98, "Rebel Trooper (Hoth)", 107, abilities=BLASTER),
    _char(99, "Rebel Pilot", 58, abilities=BLASTER),
    _char(100, "Snowtrooper", 45, abilities=IMPERIAL | BLASTER),
    _char(101, "Lobot", 192),
    _char(102, "Ugnaught", 158, abilities=SHORTIE),
    _char(103, "Bespin Guard", 193, abilities=BLASTER),
    _char(104, "Gamorrean Guard", 102),
    _char(105, "Bib Fortuna", 185),
    _char(106, "Palace Guard", 196, abilities=BLASTER),
    _char(107, "Bossk", 212, abilities=BOUNTY_HUNTER | BLASTER),
    _char(108, "Skiff Guard", 186, abilities=BLASTER),
    _char(109, "Boba Fett", 7, abilities=BOUNTY_HUNTER | BLASTER | DROID_OR_FLY),
    _char(110, "Ewok", 199, abilities=SHORTIE | BLASTER),  # ! Cannot blast most targets !
    _char(111, "Imperial Guard", 194, abilities=IMPERIAL | BLASTER),  # ! No blaster !
    _char(112, "The Emperor", 6, abilities=JEDI | SITH | IMPERIAL),
    _char(113, "Admiral Ackbar", 211, abilities=BLASTER),
    _char(114, "IG-88", 197, abilities=BOUNTY_HUNTER | BLASTER | ASTROMECH | PROTOCOL_DROID | DROID_OR_FLY),
    _char(115, "Dengar", 213, abilities=BOUNTY_HUNTER | BLASTER),
    _char(116, "4-LOM", 225, abilities=BOUNTY_HUNTER | BLASTER | ASTROMECH | PROTOCOL_DROID | DROID_OR_FLY),
    _char(117, "Ben Kenobi (Ghost)", 195, abilities=JEDI),
    _char(118, "Yoda (Ghost)", 227, abilities=JEDI),
    _char(119, "R2-Q5", 314, abilities=ASTROMECH | DROID_OR_FLY),
    _char(120, "Padmé", 76, abilities=BLASTER),
    _char(121, "Luke Skywalker (Hoth)", 204, abilities=BLASTER),  # Ability missing from manual
    _extra(122, "Super Gonk", 0x8, "1-1"),
    _extra(123, "Poo Money", 0x9, "1-2"),  # "Fertilizer" in manual
    _extra(124, "Walkie Talkie Disable", 0xA, "1-3"),
    _extra(125, "Red Brick Detector", 0xB, "1-4"),
    _extra(126, "Super Slap", 0xC, "1-5"),
    _extra(127, "Force Grapple Leap", 0xD, "1-6"),
    _extra(128, "Stud Magnet", 0xE, "2-1"),
    _extra(129, "Disarm Troopers", 0xF, "2-2"),
    _extra(130, "Character Studs", 0x10, "2-3"),
    _extra(131, "Perfect Deflect", 0x11, "2-4"),
    _extra(132, "Exploding Blaster Bolts", 0x12, "2-5"),
    _extra(133, "Force Pull", 0x13, "2-6"),
    _extra(134, "Vehicle Smart Bomb", 0x14, "3-1"),
    _extra(135, "Super Astromech", 0x15, "3-2"),
    _extra(136, "Super Jedi Slam", 0x16, "3-3"),
    _extra(137, "Super Thermal Detonator", 0x17, "3-4"),
    _extra(138, "Deflect Bolts", 0x18, "3-5"),
    _extra(139, "Dark Side", 0x19, "3-6"),
    _extra(140, "Super Blasters", 0x1A, "4-1"),
    _extra(141, "Fast Force", 0x1B, "4-2"),
    _extra(142, "Super Lightsabers", 0x1C, "4-3"),
    _extra(143, "Tractor Beam", 0x1D, "4-4"),
    _extra(144, "Invincibility", 0x1E, "4-5"),
    _generic(145, "Progressive Score Multiplier"),
    _extra(-1, "Score x2", 0x1F, "4-6"),
    _extra(146, "Self Destruct", 0x20, "5-1"),
    _extra(147, "Fast Build", 0x21, "5-2"),
    _extra(-1, "Score x4", 0x22, "5-3"),
    _extra(148, "Regenerate Hearts", 0x23, "5-4"),
    _extra(149, "Minikit Detector", 0x24, "5-6"),
    _extra(-1, "Score x6", 0x25, "5-5"),
    _extra(150, "Super Zapper", 0x26, "6-1"),
    _extra(151, "Bounty Hunter Rockets", 0x27, "6-2"),
    _extra(-1, "Score x8", 0x28, "6-3"),
    _extra(152, "Super Ewok Catapult", 0x29, "6-4"),
    _extra(153, "Infinite Torpedos", 0x2A, "6-6"),
    _extra(-1, "Score x10", 0x2B, "6-5"),
    _generic(154, "Progressive Bonus Level"),
    _generic(155, "Restart Level Trap"),
    _generic(-1, "Episode 1 Unlock"),
    _generic(156, "Episode 2 Unlock"),
    _generic(157, "Episode 3 Unlock"),
    _generic(158, "Episode 4 Unlock"),
    _generic(159, "Episode 5 Unlock"),
    _generic(160, "Episode 6 Unlock"),
    _char(161, "Anakin Skywalker (Ghost)", 226, abilities=JEDI),
    _char(162, "Indiana Jones", 317, abilities=BLASTER),
    _char(163, "Princess Leia (Prisoner)", 205, abilities=BLASTER),
    _vehicle(164, "Anakin's Pod", 259),
    _vehicle(165, "Naboo Starfighter", 272, abilities=VEHICLE_TOW),
    _vehicle(166, "Republic Gunship", 285, abilities=VEHICLE_TOW),
    _vehicle(167, "Anakin's Starfighter", 221),
    _vehicle(168, "Obi-Wan's Starfighter", 291),
    _vehicle(169, "X-Wing", 36),
    _vehicle(170, "Y-Wing", 39),
    _vehicle(171, "Millennium Falcon", 38),
    _vehicle(172, "TIE Interceptor", 128, abilities=VEHICLE_TIE),
    _vehicle(173, "Snowspeeder", 32, abilities=VEHICLE_TOW),
    _vehicle(174, "Anakin's Speeder", 3),
    _generic(175, "Purple Stud"),
    # NEW. Items below here did not exist in the manual.
    # TODO: Redo all the item IDs to make more sense. Either internal order in chars.txt, or in character grid order.
    _char(-1, "Qui-Gon Jinn", 104, abilities=JEDI),
    _char(-1, "Obi-Wan Kenobi", 1, abilities=JEDI),
    _char(-1, "TC-14", 71, abilities=PROTOCOL_DROID),
    _extra(-1, "Extra Toggle", 0x0, None),
    _extra(-1, "Fertilizer", 0x1, None),
    _extra(-1, "Disguise", 0x2, None),
    _extra(-1, "Daisy Chains", 0x3, None),
    _extra(-1, "Chewbacca Carrying C-3PO", 0x4, None),
    _extra(-1, "Tow Death Star", 0x5, None),
    _extra(-1, "Silhouettes", 0x6, None),
    _extra(-1, "Beep Beep", 0x7, None),
    _extra(-1, "Adaptive Difficulty", 0x2C, None),  # Effectively a difficulty setting, so not randomized.
    # Custom characters can only use unlocked character equipment, besides some blasters.
    # todo: Does this include lightsabers if there are no Jedi unlocked?
    _char(-1, "Custom Character 1", 168, abilities=BLASTER),
    _char(-1, "Custom Character 2", 169, abilities=BLASTER),
    _vehicle(190, "Sebulba's Pod", 261),
    _vehicle(191, "Zam's Airspeeder", 277),
    _vehicle(192, "Droid Trifighter", 292),
    _vehicle(193, "Vulture Droid", 293),
    _vehicle(194, "Clone Arcfighter", 295),
    _vehicle(195, "TIE Fighter", 37, abilities=VEHICLE_TIE),
    _vehicle(196, "TIE Fighter (Darth Vader)", 182, abilities=VEHICLE_TIE),
    _vehicle(197, "TIE Bomber", 209, abilities=VEHICLE_TIE),
    _vehicle(198, "Imperial Shuttle", 198, abilities=VEHICLE_TIE),
    MinikitItemData(199, "Minikit", 1),
    MinikitItemData(200, "2 Minikits", 2),
    MinikitItemData(201, "10 Minikits", 10),
]

USEFUL_NON_PROGRESSION_CHARACTERS: set[str] = {
    # There is currently no Ghost logic for bypassing gas and other hazards, so give the Ghosts at least Useful
    # classification.
    "Ben Kenobi (Ghost)",
    "Anakin Skywalker (Ghost)",
    "Yoda (Ghost)",
    # There is currently no glitch logic for the glitchy mess that is Yoda, so ensure Yoda is never excluded by making
    # him Useful.
    "Yoda",
    # The fastest character.
    "Droideka",
}

ITEM_DATA_BY_NAME: dict[str, GenericItemData] = {data.name: data for data in ITEM_DATA}
ITEM_DATA_BY_ID: dict[int, GenericItemData] = {data.code: data for data in ITEM_DATA if data.code != -1}
EXTRAS_BY_NAME: dict[str, ExtraData] = {data.name: data for data in ITEM_DATA if isinstance(data, ExtraData)}
CHARACTERS_AND_VEHICLES_BY_NAME: dict[str, GenericCharacterData] = {data.name: data for data in ITEM_DATA
                                                                    if isinstance(data, GenericCharacterData)}
GENERIC_BY_NAME: dict[str, GenericItemData] = {data.name: data for data in ITEM_DATA if data.item_type == "Generic"}
MINIKITS_BY_NAME: dict[str, MinikitItemData] = {data.name: data for data in ITEM_DATA
                                                if isinstance(data, MinikitItemData)}

ITEM_NAME_TO_ID: dict[str, int] = {name: item.code for name, item in ITEM_DATA_BY_NAME.items() if item.code != -1}

MINIKITS_BY_COUNT: dict[int, GenericItemData] = {bundle.bundle_size: bundle for bundle in MINIKITS_BY_NAME.values()}
