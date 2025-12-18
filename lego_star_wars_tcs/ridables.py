from .constants import CharacterAbility
from .levels import SHORT_NAME_TO_CHAPTER_AREA, BONUS_NAME_TO_BONUS_AREA


class Ridable:
    user_facing_name: str
    character_id: int
    chapter_shortnames: tuple[str, ...]
    bonus_area_names: tuple[str, ...]
    is_in_cantina: bool

    def __init__(self,
                 _internal_name: str,  # Currently unused, but useful for reference.
                 user_facing_name: str,
                 character_id: int,
                 *area_names: str
                 ):
        self.user_facing_name = user_facing_name
        self.character_id = character_id
        chapter_names = []
        bonus_names = []
        unknown_names = []
        for name in area_names:
            if name in SHORT_NAME_TO_CHAPTER_AREA:
                chapter_names.append(name)
            elif name in BONUS_NAME_TO_BONUS_AREA:
                bonus_names.append(name)
            elif name == "cantina":
                self.is_in_cantina = True
            else:
                unknown_names.append(name)
        if unknown_names:
            raise ValueError(f"Unknown area names for ridable {user_facing_name}: {unknown_names}")
        self.chapter_shortnames = tuple(chapter_names)
        self.bonus_area_names = tuple(bonus_names)

    @property
    def location_name(self):
        return f"Ride {self.user_facing_name}"


# There is apparently a resident ATAT in HOTHESCAPE/5-2?
_RIDABLES: tuple[Ridable, ...] = (
    Ridable("STAP2", "STAP", 302, "1-1"),
    Ridable("speeder_land", "Landspeeder", 15, "4-2", "4-3", "New Town", "LEGO City"),
    # This is in the files for New Town, but does not appear to be present.
    Ridable("WookieFlyer", "Wookie Flyer", 222, "LEGO City"),
    # There is also a Dewback out-of-bounds/unloaded in 4-3 MOSEISLEY_B.
    Ridable("Dewback", "Dewback", 137, "4-2", "4-3", "New Town", "LEGO City"),
    # Orange Car.
    # In 4-1, requires destroying Silver Bricks + (Imperial Panel or Bounty Hunter Panel)
    Ridable("MoonCar", "Moon Car", 187, "4-1", "New Town", "LEGO City"),
    Ridable("lifeBoat", "Lifeboat", 310, "New Town"),
    Ridable("fireTruck", "Firetruck", 309, "New Town"),
    Ridable("BasketCannon", "Basketball Cannon", 245, "New Town"),
    Ridable("CloneWalker", "Clone Walker", 18, "3-4", "New Town"),
    # Red Car from Cloud City.
    Ridable("CloudCar", "Cloud Car", 191, "5-6", "New Town", "LEGO City"),
    Ridable("TaunTaun", "Tauntaun", 108, "5-2", "New Town", "LEGO City"),
    # 'Milk Van'.
    # In New Town, requires destroying a house (melee OK)
    # In 4-1, requires protocol droid + jedi + (Bounty Hunter panel or Imperial Panel) (basically the same as the Power
    #   Brick)
    Ridable("TownCar", "Town Car", 189, "4-1", "New Town", "LEGO City"),
    # In 5-4 there is one Tractor used to get the Power Brick, requiring SITH, but there is a later Tractor that only
    # requires JEDI
    Ridable("Tractor", "Tractor", 188, "5-4", "6-4", "New Town", "LEGO City"),
    Ridable("bantha", "Bantha", 106, "4-2", "New Town", "LEGO City"),
    Ridable("ATST", "AT-ST", 164, "4-3", "6-3", "6-4", "LEGO City"),
    Ridable("service_car", "Service Car", 160, "1-5", "1-6", "4-5"),
    Ridable("FlashSpeeder", "Flash Speeder", 271, "1-5"),
    Ridable("GrabberControl", "Crane Control", 135, "4-1", "4-4", "4-5", "5-5", "5-6"),
    Ridable("MosCannon", "Mos Eisley Cannon", 180, "4-3"),
    # Note: Also in the HOTH NEWBONUS, which is not part of the randomizer currently.
    # This is in the files for 6-3, but if it exists, I don't know where it is.
    Ridable("TrooperCannon", "Stormtrooper Cannon", 200, "5-2", "5-5"),
    # This is in the files, but I'm not sure this exists?
    # _Ridable("HeavyRepeatingCannon", "Hoth Heavy Repeating Cannon", 0, "5-2"),
    # The one that is used to launch C-3PO.
    Ridable("SnowMob", "Snowmobile", 203, "5-2"),
    Ridable("Catapult", "Ewok Catapult", 159, "6-4"),
    Ridable("Cannon", "Skiff Cannon", 134, "6-2"),
    Ridable("BigGun", "Big Skiff Cannon", 210, "6-2"),
    # Requires pulling a lever OR destroying barrels and building bricks.
    Ridable("mapcar", "Cantina Car", 303, "cantina"),
    Ridable("speederbike", "Speeder Bike", 30, "6-3"),
    # Apparently there is also one in HOTHESCAPE/5-2?
    Ridable("ATAT", "AT-AT", 47, "6-3"),
)

RIDABLES_BY_NAME = {ridable.user_facing_name: ridable for ridable in _RIDABLES}
del _RIDABLES

# Most ridables can be reached with only the characters that are needed to complete the chapter in Story.
RIDABLES_REQUIREMENTS: dict[str, dict[str, tuple[CharacterAbility, ...]]] = {
    "4-1": {
        # The car is hidden within Silver Bricks.
        "Moon Car": (CharacterAbility.BOUNTY_HUNTER,),
        # The car is at the end of a hallway that needs a Bounty Hunter or Imperial to access.
        # A Protocol Droid Panel must be used to remove a force field, and a Jedi must be used to spawn the plants that
        # spawn the Town Car bricks when destroyed.
        "Town Car": (CharacterAbility.BOUNTY_HUNTER, CharacterAbility.IMPERIAL),
    },
    "LEGO City": {
        # The car is hidden within Silver Bricks.
        "Moon Car": (CharacterAbility.BOUNTY_HUNTER,),
    },
    "New Town": {
        # The car is hidden within Silver Bricks.
        "Moon Car": (CharacterAbility.BOUNTY_HUNTER,),
    }
}


def get_ridable_requirements(chapter_short_name_or_bonus: str, ridable_name: str) -> tuple[CharacterAbility, ...]:
    return RIDABLES_REQUIREMENTS.get(chapter_short_name_or_bonus, {}).get(ridable_name, ())


def _make_lookups() -> tuple[dict[str, list[Ridable]], dict[str, list[Ridable]]]:
    from collections import defaultdict
    chapter_to_ridable = defaultdict(list)
    bonus_to_ridable = defaultdict(list)
    for ridable in RIDABLES_BY_NAME.values():
        for chapter in ridable.chapter_shortnames:
            chapter_to_ridable[chapter].append(ridable)
        for bonus in ridable.bonus_area_names:
            bonus_to_ridable[bonus].append(ridable)
    return dict(chapter_to_ridable), dict(bonus_to_ridable)


CHAPTER_TO_RIDABLES: dict[str, list[Ridable]]
BONUS_TO_RIDABLES: dict[str, list[Ridable]]
CHAPTER_TO_RIDABLES, BONUS_TO_RIDABLES = _make_lookups()
del _make_lookups
