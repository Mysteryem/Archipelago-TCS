import logging

from ...levels import CHAPTER_AREAS, ChapterArea
from ...locations import LOCATION_NAME_TO_ID, LEVEL_COMMON_LOCATIONS
from ..type_aliases import ApLocationId, LevelId, TCSContext


debug_logger = logging.getLogger("TCS Debug")


# The most stable byte I could find to determine the difference between the 'status' screen when using "Save and Exit
# Cantina" and when completing a chapter, in Free Play. What this byte controls is unknown.
# Seems to always be 0x8 when using "Save and Quit", and 0x0 when completing a chapter. Can be 0x8 when playing
# through a normal chapter with control of a character.
STATUS_LEVEL_TYPE_ADDRESS = 0x87A6D9
# STATUS_LEVEL_TYPE_SAVE_AND_EXIT = 0x8
STATUS_LEVEL_TYPE_LEVEL_COMPLETION = 0x0


CURRENT_GAME_MODE_ADDRESS = 0x87951C
"""Byte that stores the current game mode."""

# CURRENT_GAME_MODE_STORY = 0
CURRENT_GAME_MODE_FREE_PLAY = 1
# Per-chapter Challenge mode as well as per-episode character bonus and Superstory.
# TODO: What do vehicle bonuses and separate bonus levels count as? Separate bonus levels can have both Story and Free
#  Play modes (Anakin's Flight), but can also be only Free Play (New Town).
# CURRENT_GAME_MODE_CHALLENGE_BONUS = 2


STATUS_LEVEL_ID_TO_AP_ID: dict[LevelId, ApLocationId] = {
    area.status_level_id: LOCATION_NAME_TO_ID[LEVEL_COMMON_LOCATIONS[area.short_name]["Completion"]]
    for area in CHAPTER_AREAS
}
STATUS_LEVEL_ID_TO_AREA: dict[LevelId, ChapterArea] = {
    area.status_level_id: area for area in CHAPTER_AREAS
}
AP_ID_TO_AREA: dict[ApLocationId, ChapterArea] = {
    ap_id: STATUS_LEVEL_ID_TO_AREA[level_id] for level_id, ap_id in STATUS_LEVEL_ID_TO_AP_ID.items()
}


def is_in_free_play(ctx: TCSContext) -> bool:
    """
    Return whether the player is currently in Free Play.

    The result is undefined if the player is not currently in a chapter Area.
    """
    return ctx.read_uchar(CURRENT_GAME_MODE_ADDRESS) == CURRENT_GAME_MODE_FREE_PLAY


def is_status_level_completion(ctx: TCSContext) -> bool:
    """
    Return whether the current status Level is being shown as part of chapter completion.

    The status Level for each chapter Area is used when tallying up Studs/Minikits etc. when returning to the
    Cantina, both for chapter completion and for 'Save and Exit'.

    The result is undefined if the player is not currently in a status Level.
    """
    return ctx.read_uchar(STATUS_LEVEL_TYPE_ADDRESS) == STATUS_LEVEL_TYPE_LEVEL_COMPLETION


# TODO: How quickly can a player reasonably skip through the chapter completion screen? Do we need to check for chapter
#  completion with a higher frequency than how often the game watcher is checking?
class FreePlayChapterCompletionChecker:
    """
    Check if the player has completed a free play chapter by looking for the ending screen that tallies up new
    studs/minikits.

    There appears to be no persistent storage in the game's memory or save data for whether a chapter has been completed
    in Free Play, so the client must poll the game state and track completions itself in the case of disconnecting from
    the server.
    """

    sent_locations: set[ApLocationId]
    completed_free_play: set[ChapterArea]
    initial_setup_complete: bool

    def __init__(self):
        self.sent_locations = set()
        self.completed_free_play = set()
        self.initial_setup_complete = False

    def read_completed_free_play_from_save_data(self, ctx: TCSContext):
        for area in CHAPTER_AREAS:
            unlocked_byte = ctx.read_uchar(area.address + area.UNLOCKED_OFFSET)
            if unlocked_byte == 0b11:
                self.completed_free_play.add(area)
                debug_logger.info("Read from save file that %s has been completed in Free Play", area.short_name)
                self.sent_locations.add(STATUS_LEVEL_ID_TO_AP_ID[area.status_level_id])

    async def initialize(self, ctx: TCSContext):
        if not self.initial_setup_complete:
            self.read_completed_free_play_from_save_data(ctx)
            self.initial_setup_complete = True

    async def check_completion(self, ctx: TCSContext, new_location_checks: list[ApLocationId]):

        # Level ID should be checked first because STATUS_LEVEL_TYPE_ADDRESS can be STATUS_LEVEL_TYPE_LEVEL_COMPLETION
        # during normal gameplay, so it would be possible for STATUS_LEVEL_TYPE_ADDRESS to match and then the player
        # does 'Save and Exit', changing the Level ID to a 'status' level and accidentally sending a location check.
        current_level_id = ctx.read_current_level_id()
        completion_location_id = STATUS_LEVEL_ID_TO_AP_ID.get(current_level_id)
        if (completion_location_id is not None
                and completion_location_id in ctx.missing_locations
                and is_in_free_play(ctx)
                and is_status_level_completion(ctx)):
            self.sent_locations.add(completion_location_id)
            area = STATUS_LEVEL_ID_TO_AREA[current_level_id]
            self.completed_free_play.add(area)
            ctx.write_byte(area.address + area.UNLOCKED_OFFSET, 0b11)

        # Not required because only the intersection of ctx.missing_locations will be sent to the server, but removing
        # checked locations (server state) here helps with debugging by reducing self.sent_locations to only new checks.
        self.sent_locations.difference_update(ctx.checked_locations)

        # Locations to send to the server will be filtered to only those in ctx.missing_locations, so include everything
        # up to this point in-case one was missed in a disconnect.
        new_location_checks.extend(self.sent_locations)
