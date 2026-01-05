from .levels import SHORT_NAME_TO_CHAPTER_AREA, BONUS_NAME_TO_BONUS_AREA
from .locations import LOCATION_NAME_TO_ID


LOCATION_ID_TO_NAME = {v: k for k, v in LOCATION_NAME_TO_ID.items()}
assert len(LOCATION_ID_TO_NAME) == len(LOCATION_NAME_TO_ID)


def _locations_from_indices(start_inclusive: int, end_inclusive: int) -> set[str]:
    return {LOCATION_ID_TO_NAME[i] for i in range(start_inclusive, end_inclusive + 1)}


LOCATION_GROUPS: dict[str, set[str]] = {
    "Purchases": {name for name in LOCATION_NAME_TO_ID.keys() if name.startswith("Purchase")},
    "True Jedi": _locations_from_indices(110, 145),
    "Chapter Completions": _locations_from_indices(506, 541),
    "Bonuses": _locations_from_indices(547, 554),
    "Bonus Levels": _locations_from_indices(547, 552),
    "Chapter Completion Character Unlocks": _locations_from_indices(566, 621),
    "Minikits": _locations_from_indices(146, 505),
    **{
        f"{shortname} ({area.name})": {
            area.power_brick_location_name,
            f"{shortname} Completion",
            *[f"{shortname} Minikit {i}" for i in range(1, 11)],
            *area.character_shop_unlocks.keys(),
        } for shortname, area in SHORT_NAME_TO_CHAPTER_AREA.items()
    },
    # Chapter Completion Character Unlocks can often be accessed from multiple Chapters, so are put in separate location
    # groups.
    **{
        f"Level Completion Character Unlocks - {shortname}": {
            f"Level Completion - Unlock {char}" for char in area.character_requirements
        } for shortname, area in SHORT_NAME_TO_CHAPTER_AREA.items()
    },
    **{
        f"Level Completion Character Unlocks - {bonus_name}": {
            f"Level Completion - Unlock {char}" for char in area.story_characters
        } for bonus_name, area in BONUS_NAME_TO_BONUS_AREA.items() if area.story_characters
    },
    **{
        f"Minikits - {shortname}": {
            f"{shortname} Minikit {i}" for i in range(1, 11)
        } for shortname, area in SHORT_NAME_TO_CHAPTER_AREA.items()
    },
    **{
        f"Purchases - {shortname}": {*area.character_shop_unlocks.keys(), area.power_brick_location_name}
        for shortname, area in SHORT_NAME_TO_CHAPTER_AREA.items()
    },
    **{
        f"Character Purchases - {shortname}": set(area.character_shop_unlocks.keys())
        for shortname, area in SHORT_NAME_TO_CHAPTER_AREA.items() if area.character_shop_unlocks
    },
    "Ridesanity": _locations_from_indices(622, 648),
}
