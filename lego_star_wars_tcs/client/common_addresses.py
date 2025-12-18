from enum import IntEnum, IntFlag

from .common import StaticUChar, StaticFloat, StaticUint, StaticBOOL, FloatField, UCharField
from .type_aliases import TCSContext
from ..levels import AREA_ID_TO_CHAPTER_AREA


# There are two pointers here, which are NULL when the player is dropped out.
# The full array of all 8 'player' character pointers, that can be tagged, is found at 0x93d7f0
HUMAN_CONTROLLED_PLAYER_CHARACTER_POINTERS = 0x93d810


class CharacterFlags1(IntFlag):
    PLAYER_CONTROLLED = 0x80

    @classmethod
    def get(cls, ctx: TCSContext, character_address: int):
        return cls(ctx.read_uchar(character_address + 0x1fc, raw=True))


def player_character_entity_iter(ctx: TCSContext):
    for i in range(0, 2):
        character_address = ctx.read_uint(HUMAN_CONTROLLED_PLAYER_CHARACTER_POINTERS + i * 4)
        if character_address != 0:
            yield i + 1, character_address


# CharacterEntity to index: ((int)char_ent - (int)character_entities_0093d524) / 0x10d8 & 0xffff;


CHARACTER_POWER_UP_TIMER = FloatField(0xdec)


# It looks like AREA IDs tend to use 4 bytes, even though they only need 1 byte.
# This first address seems to be part of a larger struct in memory and is not referenced, by address, directly.
CURRENT_AREA_ADDRESS = StaticUChar(0x7fd2c1)
# This second address is referenced directly, so could be a better choice.
# CURRENT_AREA_ADDRESS = StaticUChar(0x803784)

# Technically, this is direct access of the WORLDINFO struct at 0x93d858, accessing field offset 0x12c.
CURRENT_P_AREA_DATA_ADDRESS = StaticUint(0x93d984)
# ID field of P_AREA_DATA.
AREA_DATA_ID = UCharField(0x7c)


CHARACTERS_SHOP_START = 0x86E4A8  # See CHARACTER_SHOP_SLOTS in items.py for the mapping
EXTRAS_SHOP_START = 0x86E4B8

# 0 when a menu is not open, 1 when a menu is open (pause screen, shop, custom character creator, select mode after
# entering a level door). Increases to 2 when opening a submenu in the pause screen.
OPENED_MENU_DEPTH_ADDRESS = 0x800944


# Byte
# 255: Cutscene
# 1: Playing, Indy trailer, loading into Cantina, Title crawl
# 2: In-level 'cutscene' where non-playable characters play an animation and the player has no control
# 6: Bounty Hunter missions select
# 7: In custom character creator
# 8: In Cantina shop
# 9: Minikits display on outside scrapyard
# There is another address at 0x925395
GAME_STATE_ADDRESS = 0x925394


# This is GameState1 because other address have been found that can be used to infer game state, so it is likely that
# there will be a GameState2 in the future.
class GameState1(IntEnum):
    CUTSCENE = 255
    PLAYING_OR_TRAILER_OR_CANTINA_LOAD_OR_CHAPTER_TITLE_CRAWL = 1
    IN_LEVEL_SOFT_CUTSCENE = 2
    UNKNOWN_3 = 3
    UNKNOWN_4 = 4
    UNKNOWN_5 = 5
    IN_BOUNTY_HUNTER_MISSION_SELECT = 6
    IN_CUSTOM_CHARACTER_CREATOR = 7
    IN_CANTINA_SHOP = 8
    IN_JUNKYARD_MINIKITS_DISPLAY = 9

    def is_set(self, ctx: TCSContext) -> bool:
        return ctx.read_uchar(GAME_STATE_ADDRESS) == self.value

    @classmethod
    def is_playing(cls, ctx: TCSContext) -> bool:
        state = ctx.read_uchar(GAME_STATE_ADDRESS)
        return (state == cls.PLAYING_OR_TRAILER_OR_CANTINA_LOAD_OR_CHAPTER_TITLE_CRAWL.value
                or state == cls.IN_LEVEL_SOFT_CUTSCENE.value)


# When enabled, character swapping is enabled, e.g. Free Play/Challenge/Minikit Bonus/Character Bonus/LEGO City/
# New Town.
# This can be forcefully enabled in Story, and potentially other modes, to allow character swapping, though may disable
# some Story-only events that usually get disabled in Free Play, e.g. TC-14 won't spawn if this is enabled before
# Negotiations_A loads.
IS_CHARACTER_SWAPPING_ENABLED = StaticBOOL(0x93b2a4)

# See ChapterDoorGameMode below.
CHAPTER_DOOR_GAME_MODE = StaticUint(0x87951C)


class ChapterDoorGameMode(IntEnum):
    """
    The current game mode when in a chapter door. Note: Entering non-chapter levels does not clear this value.

    The value sticks around while inside a chapter itself, so can be used as an imperfect way to detect what mode the
    player is currently in. Notably, this can give false positives for Bounty Hunter Missions and Superstory.

    Adjusting this value changes the currently selected option in the chapter door's menu.
    """
    STORY = 0
    FREE_PLAY = 1
    CHALLENGE = 2

    def is_set(self, ctx: TCSContext) -> bool:
        return CHAPTER_DOOR_GAME_MODE.get(ctx) == self.value

    def set(self, ctx: TCSContext):
        CHAPTER_DOOR_GAME_MODE.set(ctx, self.value)

    # @classmethod
    # def get(cls, ctx: TCSContext) -> "ChapterDoorGameMode | None":
    #     v = CHAPTER_DOOR_GAME_MODE.get(ctx)
    #     if v in ChapterDoorGameMode:
    #         return cls(v)
    #     else:
    #         return None


CHALLENGE_MODE_ADDRESS = StaticUint(0x856c08)


class ChallengeMode(IntEnum):
    NO_CHALLENGE = 0x0
    CHALLENGE_IN_PROGRESS = 0x1
    CHALLENGE_STOPPED = 0x2
    CHALLENGE_FAILED = 0x3

    def is_set(self, ctx: TCSContext) -> bool:
        return CHALLENGE_MODE_ADDRESS.get(ctx) == self.value


def is_in_chapter_free_play(ctx: TCSContext, area_id: int | None = None) -> bool:
    # The current area ID is often known in advance.
    if area_id is None:
        area_id = CURRENT_AREA_ADDRESS.get(ctx)

    if area_id not in AREA_ID_TO_CHAPTER_AREA:
        # This eliminates Bonuses that have Free Play.
        return False

    if not IS_CHARACTER_SWAPPING_ENABLED.get(ctx):
        # This eliminates Bounty Hunter Missions because they do not allow character swapping (only tagging).
        # This eliminates Superstory because it does not allow character swapping (only tagging).
        return False

    if not ChapterDoorGameMode.FREE_PLAY.is_set(ctx):
        # This eliminates chapters in Challenge mode.
        return False

    return True


class ShopType(IntEnum):
    NONE = 255  # -1 as a `signed char`
    HINTS = 0
    CHARACTERS = 1
    EXTRAS = 2
    ENTER_CODE = 3
    GOLD_BRICKS = 4
    STORY_CLIPS = 5


class CantinaRoom(IntEnum):
    UNKNOWN = -2
    NOT_IN_CANTINA = -1
    SHOP_ROOM = 0
    EPISODE_1 = 1
    EPISODE_2 = 2
    EPISODE_3 = 3
    EPISODE_4 = 4
    EPISODE_5 = 5
    EPISODE_6 = 6
    JUNKYARD = 7
    BONUSES = 8
    BOUNTY_HUNTER_MISSIONS = 9


_CUSTOM_SAVE_FLAGS_1_ADDRESS = 0x86e4e6  # 0x86e506 (GOG)


class CustomSaveFlags1(IntFlag):
    """
    There are two unused bytes in the save data after the byte that stores whether the Indiana Jones trailer has been
    watched.
    BYTE1_AFTER_INDIANA_JONES_TRAILER = 0x86e506
    BYTE2_AFTER_INDIANA_JONES_TRAILER = 0x86e507

    The client uses these two bytes for storing up to 16 flags.
    """
    MINIKIT_GOAL_COMPLETE = 0x1
    DEATH_LINK_ENABLED = 0x2
    FIELD_3 = 0x4  # Could be DEFEAT_BOSSES_GOAL_COMPLETE to reduce memory reading once the goal is complete.
    FIELD_4 = 0x8
    FIELD_5 = 0x10
    FIELD_6 = 0x20
    FIELD_7 = 0x40
    FIELD_8 = 0x80
    FIELD_9 = 0x100
    FIELD_10 = 0x200
    FIELD_11 = 0x400
    FIELD_12 = 0x800
    FIELD_13 = 0x1000
    FIELD_14 = 0x2000
    FIELD_15 = 0x4000
    FIELD_16 = 0x8000

    def is_set(self, ctx: TCSContext) -> bool:
        # noinspection PyTypeChecker
        v: int = self.value
        if v <= 0xFF:
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS
        else:
            v = v >> 8
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS + 1

        return (ctx.read_uchar(addr) & v) != 0

    def set(self, ctx: TCSContext):
        # noinspection PyTypeChecker
        v: int = self.value
        if v <= 0xFF:
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS
        else:
            v = v >> 8
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS + 1

        b = ctx.read_uchar(addr)
        if not (b & v):
            ctx.write_byte(_CUSTOM_SAVE_FLAGS_1_ADDRESS, b | v)

    def unset(self, ctx: TCSContext):
        # noinspection PyTypeChecker
        v: int = self.value
        if v <= 0xFF:
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS
        else:
            v = v >> 8
            addr = _CUSTOM_SAVE_FLAGS_1_ADDRESS + 1

        b = ctx.read_uchar(addr)
        if b & v:
            ctx.write_byte(_CUSTOM_SAVE_FLAGS_1_ADDRESS, b & ~v)

# Other potential unused sava-data bytes
# Some (most?) (all?) bonus levels have enough space reserved for all the Minikits/True Jedi/Power Brick bytes, which
# they don't use.
# The Extras shop uses 6 bytes, but appears to have 16 bytes allocated.
# The Hints shop uses 2 bytes, but appears to have 12 bytes allocated.
# The Characters shop uses 13 bytes, but appears to have 16 bytes allocated.


# -- Game state addresses.

# This value is slightly unstable and occasionally changes to 0 while playing. It is also set to 2 in Mos Espa Pod Race
# for some reason.
# Importantly, this value is *not* 0 when watching a Story cutscene, and is instead 1.
PAUSED_OR_STATUS_WHEN_0_ADDRESS = 0x9737D8
# This address is usually -1/255 while playing or paused, 1 while tabbed out and 0 while both paused and tabbed out.
# It is a more unstable than the previous value, while playing, however.
# Notably, if window focus is forced by setting 0x827610 to 1, thus allowing the game to run in the background, then
# this still correctly identifies whether the game is frozen.
TABBED_OUT_WHEN_1_ADDRESS = 0x9868C4

# 0 when playing, 1 when in a cutscene, same-level door transition, Indy trailer and title crawl.
# Rarely unstable and seen as -1 briefly while playing
IS_PLAYING_WHEN_0_ADDRESS = 0x297C0AC

# Set to > 0.0 during a screen wipe/transition. In-game hints only display when this is 0.0.
SCREEN_TRANSITION_TIMER_ADDRESS = StaticFloat(0x950780)


def is_actively_playing(ctx: TCSContext):
    """
    Return True if the player is actively playing the game.

    Returns False in cases like having a menu open, having the game paused, or having the game tabbed out.
    """
    return (
            # Handles pause and status screens.
            ctx.read_uchar(PAUSED_OR_STATUS_WHEN_0_ADDRESS) != 0
            # Handles tabbing out.
            and ctx.read_uchar(TABBED_OUT_WHEN_1_ADDRESS) != 1
            # Handles pause menu and other menus.
            and ctx.read_uchar(OPENED_MENU_DEPTH_ADDRESS) == 0
            # Handles same-level screen transitions.
            and ctx.read_uchar(IS_PLAYING_WHEN_0_ADDRESS) == 0
            # Handles screen/level transitions. Unlike most timer-like floats, this one actually gets set to 0.0.
            and SCREEN_TRANSITION_TIMER_ADDRESS.get(ctx) == 0.0
            and GameState1.is_playing(ctx)
    )
