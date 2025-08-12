import asyncio
import traceback
import colorama
import hashlib
import random

import ModuleUpdate
import Utils
from NetUtils import ClientStatus
from worlds._bizhawk.context import AuthStatus

ModuleUpdate.update()


import logging
import typing
from pymem import pymem
from pymem.exception import ProcessNotFound, ProcessError, PymemError, WinAPIError

from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor

from .. import options
from ..constants import GAME_NAME, AP_WORLD_VERSION
from ..items import CHARACTERS_AND_VEHICLES_BY_NAME, AP_NON_VEHICLE_CHARACTER_INDICES
from ..levels import SHORT_NAME_TO_CHAPTER_AREA, CHAPTER_AREAS, ChapterArea
from ..locations import LOCATION_NAME_TO_ID
from .common_addresses import ShopType, CantinaRoom, GameState1, OPENED_MENU_DEPTH_ADDRESS
from .location_checkers.free_play_completion import FreePlayChapterCompletionChecker
from .location_checkers.bonus_level_completion import BonusAreaCompletionChecker
from .location_checkers.true_jedi_and_minikits import TrueJediAndMinikitChecker
from .location_checkers.shop_purchases import PurchasedExtrasChecker, PurchasedCharactersChecker
from .game_state_modifiers.extras import AcquiredExtras
from .game_state_modifiers.characters import AcquiredCharacters
from .game_state_modifiers.generic import AcquiredGeneric
from .game_state_modifiers.goal_manager import GoalManager
from .game_state_modifiers.levels import UnlockedChapterManager
from .game_state_modifiers.minikits import AcquiredMinikits
from .game_state_modifiers.studs import STUDS_AP_ID_TO_VALUE, give_studs
from .game_state_modifiers.text_display import InGameTextDisplay
from .game_state_modifiers.text_replacer import TextReplacer


logger = logging.getLogger("Client")
debug_logger = logging.getLogger("TCS Debug")

# Aliases for clarity in typing.
MemoryAddress = int
MemoryOffset = int
BitMask = int
LocationId = int


PROCESS_NAME = "LEGOStarWarsSaga"

# The STEAM and GOG versions have different memory addresses.
# The client needs to determine which version is being used and adjust the addresses accordingly.
VERSION_CHECK_PATTERN = (b"japanese\x00\x00\x00\x00"
                         b"danish\x00\x00"
                         b"spanish\x00"
                         b"italian\x00"
                         b"german\x00\x00"
                         b"french\x00\x00"
                         b"english\x00"
                         b"Err\\.\\.\\.\x00")
VERSION_CHECK_ADDRESS_GOG = 0x76161c
VERSION_CHECK_ADDRESS_STEAM = 0x761634
VERSION_CHECK_GOG_OFFSET = VERSION_CHECK_ADDRESS_STEAM - VERSION_CHECK_ADDRESS_GOG

# A potential alternative version check
# VERSION_CHECK_PATTERN = b"This program cannot be run in DOS mode"
# VERSION_CHECK_ADDRESS_GOG = 0x40004e
# VERSION_CHECK_ADDRESS_STEAM = None  # Not present in the executable.

MEMORY_OFFSET_STEAM = 0
MEMORY_OFFSET_GOG = 0x20
# Addresses greater than this need to be offset by 0x20 when the GOG version is being used.
# It is possible that the cutoff point is earlier, somewhere between 0x802000 and 0x855000
GOG_MEMORY_OFFSET_START = 0x855000

# class MemoryBlock(NamedTuple):
#     base: int
#     gog_offset: int
#
# memory_blocks = [
#     MemoryBlock(0x761000, -0x18),
#     # Somewhere in between 0x761634 and 0x7fd2c1, an early offset occurs, aligning the two versions.
#     MemoryBlock(0x7FD000, 0x0),
#     MemoryBlock(0x800000, 0x0),
#     MemoryBlock(0x802000, 0x0),
#     # Somewhere in between 0x800944 and 0x855F38, an offset occurs, misaligning the two versions.
#     MemoryBlock(0x855000, 0x20),
#     MemoryBlock(0x86E000, 0x20),
#     MemoryBlock(0x87B000, 0x20),
#     MemoryBlock(0x925000, 0x20),
#     MemoryBlock(0x951000, 0x20),
#     MemoryBlock(0x973000, 0x20),
#     MemoryBlock(0x986000, 0x20),
#     MemoryBlock(0x297C000, 0x20),
# ]


CURRENT_LEVEL_ID = 0x951BA0  # 2 bytes (or more)
# While in the Cantina and in the shop room, all extras that have been received, but not purchased, must be locked,
# otherwise those extras cannot be bought from the shop.
# When entering the Cantina, all purchased extras that have not been received will need to be locked because entering
# the cantina will unlock all extras that have been purchased.
LEVEL_ID_CANTINA = 325

CURRENT_SAVE_SLOT = 0x802014  # byte, 255/-1 for no save file loaded. [0-5] for save file [1-6]

# Unsure what this is, but it changes when moving between rooms in the cantina and appears to persist while in a level,
# so this can be used to both see what room the player is in when they are in the cantina, and to see what Episode they
# are in at a glance (the current Episode can be determined exactly from the current level ID if this turns out to be
# unreliable for checking the current episode)
# 0: Main room with the shop (what we care about)
# 1: Episode 1 room
# 2: Episode 2 room
# 3: Episode 3 room
# 4: Episode 4 room
# 5: Episode 5 room
# 6: Episode 6 room
# 7: Outside junkyard
# 8: Bonuses room
# 9: Bounty Hunter missions room
CANTINA_ROOM_ID = 0x87B460
CANTINA_ROOM_WITH_SHOP = 0

# Appears to be 1 while in the shop, and 0 otherwise. But becomes 0 when playing a cutscene from within the shop.
# SHOP_CHECK2 = 0x880474  # byte
ACTIVE_SHOP_TYPE_ADDRESS = 0x8801AC


# CUSTOM_CHARACTER_1_NAME = 0x86E500  # char[16], null-terminated, so 15 usable characters
# CUSTOM_CHARACTER_2_NAME = 0x86E538  # char[16], null-terminated, so 15 usable characters

# Byte
# 0 = Blue Lightsaber (requires any Jedi unlocked)
# 1 = Green Lightsaber (default) (requires any Jedi unlocked)
# 2 = Red Lightsaber (requires any Sith unlocked)
# 3 = Purple Lighsaber (requires any Jedi unlocked)
# 4 = Red Blaster (always available)
# 5 = Blue Blaster (always available)
# 6 = Pistol (always available)
# 7 = Shiny Pistol (always available)
# 8 = Crossbow (bowcaster) (requires *unknown* unlocked (probably Chewbacca or Wookie))
# 9 = There is no 9
CUSTOM_CHARACTER_1_WEAPON = 0x86E4F0

# These character IDs/indices update when swapping characters in the Cantina, and the game reads these values to
# determine what characters P1 and P2 should spawn into the Cantina as.
# By changing these values and then forcing a hard (reset) load into the Cantina, the client can change the player's
# characters to whatever the client needs.
P1_CANTINA_FREE_PLAY_SELECTION_CHARACTER_ID = 0x802bd8
P2_CANTINA_FREE_PLAY_SELECTION_CHARACTER_ID = 0x802bdc


# # Unverified, but seems to be the case.
# MINIKIT_NAME_LENGTH_BYTES = 8
# # todo: Need to include location IDs somewhere
# # todo: Can objects other than minikits get included in these lists? In which case, we might need to read more memory...
# #   Polly on the Lego TTGames modding discord seemed to have an idea of how minikits were laid out in memory.
# # todo: This dictionary will be long and will want to go in a different module.
# _MINIKIT_ADDRESSES_AND_NAMES: dict[int, dict[bytes, int]] = {
#     # 1-1A
#     0x0: {
#         b"m_pup1": 1,
#         b"m_pup2": 2,
#         b"m_pup3": 3,
#         b"m_pup4": 4,
#         b"m_pup5": 5,
#         b"pup_2": 6,
#     },
#     # 1-1B
#     0x0: {
#         b"m_pup1": 7,
#         b"pup2": 8,
#     },
#     # 1-1C
#     0x0: {
#         b"m_pup1": 9,
#         b"m_pup2": 10,
#     },
#
#     0x0: {
#         b"m_pup2": 11,
#         b"m_pOOP1": 12,
#         b"m_pOOP2": 13,
#         b"m_pOOP3": 14,
#         b"m_pup1": 15,
#     },
#     0x0: {
#         b"m_pup1": 0,  # todo
#     }
# }
#
# def _s8(b: bytes) -> bytes:
#     """Null terminate and pad an 8 byte string"""
#     if len(b) >= 8:
#         raise AssertionError(f"String {b} is too long")
#     return b + b"\x00" * (8 - len(b))
# MINIKIT_ADDRESSES_AND_NAMES: dict[int, dict[bytes, int]] = {k: {_s8(k2): v2 for k2, v2 in v.items()}
#                                                             for k, v in _MINIKIT_ADDRESSES_AND_NAMES.items()}
#
#
# def _read_minikit_locations(process: pymem.Pymem) -> set[int]:
#     s = set()
#     for address, names_to_ap_locations in MINIKIT_ADDRESSES_AND_NAMES.items():
#         # Read the bytes for the number of minikit names that can be at this address (the number of minikits in this
#         # particular sublevel, e.g. Negotiations_A)
#         length = len(names_to_ap_locations)
#         names_bytes = process.read_bytes(address, length * MINIKIT_NAME_LENGTH_BYTES)
#
#         # Find all the names as 8-byte null-terminated strings.
#         # names: set[bytes] = set(struct.unpack("8s" * length, names_bytes))
#         # for name, ap_location in names_to_ap_locations.items():
#         #     if name in names:
#         #         s.add(ap_location)
#
#         # Alternative. todo: Which is faster?
#         # Iterate the names as 8-byte null-terminated strings.
#         for unpacked in struct.unpack("8s" * length, names_bytes):
#             # The names in the mapping are null-terminated and padded to 8 bytes in advance.
#             # todo: Could do this. It's faster to start with, but slower once more minikits have been collected.
#             # if unpacked == b"\x00\x00\x00\x00\x00\x00\x00\x00":
#             #     # No more to read.
#             #     break
#             if unpacked in names_to_ap_locations:
#                 s.add(names_to_ap_locations[unpacked])
#             else:
#                 logger.warning("Unexpected unpacked minikit name %s for sublevel address %s", unpacked, address)
#     return s

# todo: Add optional gold brick and hint purchase checks (they should go in a different module)
# class PurchasedGoldBricks:
#     pass
# class PurchasedHints:
#     pass

class NoProcessError(RuntimeError):
    pass


# Each EpisodeGameLevelArea has an unused single-precision float that is written to the save file. The client writes
# arbitrary data to these bytes.
# The first normally unused area float bytes are used to store the expected item index.
UNUSED_AREA_DWORD_EXPECTED_IDX = 0
# The next 4 normally unused area float bytes are used to store an MD5 hash of the seed name.
UNUSED_AREA_DWORD_SEED_NAME_HASH_START = UNUSED_AREA_DWORD_EXPECTED_IDX + 1
UNUSED_AREA_DWORD_SEED_NAME_HASH_END = UNUSED_AREA_DWORD_SEED_NAME_HASH_START + 4
UNUSED_AREA_DWORD_SEED_NAME_HASH_AREAS = slice(UNUSED_AREA_DWORD_SEED_NAME_HASH_START,
                                               UNUSED_AREA_DWORD_SEED_NAME_HASH_END)
# The next 16 normally unused area float bytes are used to store the slot name for automatic authentication.
# Slot names are up to 16 UTF-8 characters, and a UTF-8 character can be up to 4 bytes, so the bytes of 16 unused floats
# are used.
UNUSED_AREA_DWORD_SLOT_NAME_START = UNUSED_AREA_DWORD_SEED_NAME_HASH_END
UNUSED_AREA_DWORD_SLOT_NAME_END = UNUSED_AREA_DWORD_SLOT_NAME_START + 16
UNUSED_AREA_DWORD_SLOT_NAME_AREAS = slice(UNUSED_AREA_DWORD_SLOT_NAME_START,
                                          UNUSED_AREA_DWORD_SLOT_NAME_END)

DATA_STORAGE_KEY_SUFFIX = "{team}_{slot}"

COMPLETED_FREE_PLAY_KEY_PREFIX = "tcs_completed_free_play_"
COMPLETED_TRUE_JEDI_KEY_PREFIX = "tcs_completed_true_jedi_"
COMPLETED_10_MINIKITS_KEY_PREFIX = "tcs_completed_10_minikits_"
COMPLETED_BONUSES_KEY_PREFIX = "tcs_completed_bonuses_"
COLLECTED_POWER_BRICKS_KEY_PREFIX = "tcs_collected_power_bricks_"

LEVEL_ID_KEY_PREFIX = "tcs_current_level_id_"
CANTINA_ROOM_KEY_PREFIX = "tcs_cantina_room_"
# By writing whether the minikit goal has been submitted to datastorage, only one player in same-slot co-op needs to
# submit the minikits to the minikit display in the cantina's junkyard.
MINIKIT_GOAL_SUBMITTED_PREFIX = "tcs_minikit_goal_submitted_"


class LegoStarWarsTheCompleteSagaCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: CommonContext):
        super().__init__(ctx)

    def _cmd_debug_message(self):
        """Queue a debug message to be displayed in-game"""
        if isinstance(self.ctx, LegoStarWarsTheCompleteSagaContext):
            if self.ctx.slot:
                import random
                self.ctx.text_display.queue_message(random.choice([
                    "The quick brown fox jumps over the lazy dog!",  # English
                    "Voix ambiguë d'un cœur qui, au zéphyr, préfère les jattes de kiwis.",  # French
                    "Victor jagt zwölf Boxkämpfer quer über den großen Sylter Deich",  # German
                    "Jeżu klątw, spłódź Finom część gry hańb!",  # Polish
                    "В чащах юга жил бы цитрус? Да, но фальшивый экземпляр!",  # Russian
                    # Japanese does not display, despite there being Japanese localization files...
                    "いろはにほへと ちりぬるを わかよたれそ つねならむ うゐのおくやま けふこえて あさきゆめみし ゑひもせす（ん）",  # Japanese
                    "(2)色は匂へど 散りぬるを 我が世誰ぞ 常ならむ 有為の奥山 今日越えて 浅き夢見じ 酔ひもせず（ん）",  # Japanese 2
                ]))


class LegoStarWarsTheCompleteSagaContext(CommonContext):
    command_processor = LegoStarWarsTheCompleteSagaCommandProcessor
    game = GAME_NAME
    items_handling = 0b111  # Fully remote

    # Copied from BizHawkClientContext
    server_seed_name: str | None = None
    auth_status: AuthStatus
    password_requested: bool

    disabled_locations: set[int]  # Server state.

    game_process: pymem.Pymem | None = None
    #previous_level_id: int = -1
    current_level_id: int = 0  # Title screen
    current_cantina_room: CantinaRoom = CantinaRoom.UNKNOWN
    # Memory in the GOG version is offset 32 bytes after GOG_MEMORY_OFFSET_START.
    # todo: Memory in the retail version is offset ?? bytes after ??.
    _gog_memory_offset: int = 0
    # In the case of an unrecognised version, an overall memory offset may be set.
    _overall_memory_offset: int = 0
    _cantina_needs_reload_to_fix_characters: bool = False

    # Client state.
    acquired_characters: AcquiredCharacters
    acquired_extras: AcquiredExtras
    acquired_generic: AcquiredGeneric
    acquired_minikits: AcquiredMinikits
    unlocked_chapter_manager: UnlockedChapterManager
    text_display: InGameTextDisplay
    goal_manager: GoalManager
    client_expected_idx: int

    # Location checkers.
    free_play_completion_checker: FreePlayChapterCompletionChecker
    true_jedi_and_minikit_checker: TrueJediAndMinikitChecker
    purchased_extras_checker: PurchasedExtrasChecker
    purchased_characters_checker: PurchasedCharactersChecker
    bonus_area_completion_checker: BonusAreaCompletionChecker

    # Game-state only.
    text_replacer: TextReplacer

    # Customizable client behaviour
    received_item_messages: bool = True
    checked_location_messages: bool = True

    fully_connected: bool
    last_connected_slot: str | None = None
    last_connected_seed_name: str | None = None
    last_loaded_save_file: int | None = None

    def __init__(self, server_address: typing.Optional[str] = None, password: typing.Optional[str] = None) -> None:
        super().__init__(server_address, password)

        # Copied from BizHawkClientContext
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        self.password_requested = False

        self.disabled_locations = set()

        self.acquired_extras = AcquiredExtras()
        self.acquired_characters = AcquiredCharacters()
        self.acquired_generic = AcquiredGeneric()
        self.acquired_minikits = AcquiredMinikits()
        self.goal_manager = GoalManager()

        self.text_display = InGameTextDisplay()

        # It is not ideal to leak `self` in __init__. The TextReplacer methods could be updated to include a TCSContext
        # parameter if needed, instead of leaking `self`. Alternatively, the TextReplacer could be created only when
        # successfully connecting to the game.
        self.text_replacer = TextReplacer(self)

        self.unlocked_chapter_manager = UnlockedChapterManager()
        self.free_play_completion_checker = FreePlayChapterCompletionChecker()
        self.true_jedi_and_minikit_checker = TrueJediAndMinikitChecker()
        self.purchased_extras_checker = PurchasedExtrasChecker()
        self.purchased_characters_checker = PurchasedCharactersChecker()
        self.bonus_area_completion_checker = BonusAreaCompletionChecker()

        self.client_expected_idx = 0

        self.fully_connected = False

    def _get_datastorage_key(self, key_prefix: str):
        return key_prefix + DATA_STORAGE_KEY_SUFFIX.format(team=self.team, slot=self.slot)

    def _is_datastorage_key(self, to_check: str, prefix: str):
        return to_check.startswith(prefix) and to_check == self._get_datastorage_key(prefix)

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)

        if not self.checked_location_messages and not self.received_item_messages:
            return

        if "type" in args and args["type"] == "ItemSend":
            item = args["item"]
            recipient = args["receiving"]

            # Receiving an item from the server
            if self.slot_concerns_self(recipient):
                item_name = self.item_names.lookup_in_game(item.item)
                if self.slot_concerns_self(item.player):
                    # This counts as both a checked location and a received item.
                    if self.checked_location_messages or self.received_item_messages:
                        location_name = self.location_names.lookup_in_game(item.location)
                        message = f"Found {item_name} ({location_name})"
                        self.text_display.queue_message(message)
                else:
                    if self.received_item_messages:
                        finder = self.player_names[item.player]
                        location_name = self.location_names.lookup_in_slot(item.location, item.player)
                        message = f"Received {item_name} from {finder} ({location_name})"
                        self.text_display.queue_message(message)
            # Sending an item to the server.
            elif self.slot_concerns_self(item.player):
                item_name = self.item_names.lookup_in_slot(item.item, recipient)

                if self.slot_concerns_self(recipient):
                    # Should not happen?
                    location_name = self.location_names.lookup_in_game(item.location)
                    message = f"Sent {item_name}...to myself? ({location_name}) Please report this."
                    self.text_display.queue_message(message)
                else:
                    if self.checked_location_messages:
                        owner = self.player_names[recipient]
                        location_name = self.location_names.lookup_in_game(item.location)
                        message = f"Sent {item_name} to {owner} ({location_name})"
                        self.text_display.queue_message(message)

    @staticmethod
    def _validate_version(slot_data: typing.Mapping[str, typing.Any]) -> bool:
        # All versions of the TCS apworld should have written "apworld_version" into slot data, if it is absent then
        # there is an error.
        # Ensure the read data from slot_data is a tuple rather than a list so that the comparisons with
        # AP_WORLD_VERSION work as expected.
        server_apworld_version = tuple(slot_data["apworld_version"])
        if AP_WORLD_VERSION != server_apworld_version:
            # If the major version does not match, the versions are incompatible.
            # If the minor version of the client is less than the server, then the versions are incompatible.
            if AP_WORLD_VERSION[0] != server_apworld_version[0] or AP_WORLD_VERSION[1] < server_apworld_version[1]:
                logger.error("Error: The multiworld was generated with apworld version %s, which is not compatible with"
                             " the client's apworld version %s. Disconnecting.",
                             server_apworld_version, AP_WORLD_VERSION)
                return False
            else:
                # If the minor version of the client is equal, then the patch version needs to be compared.
                if AP_WORLD_VERSION[1] == server_apworld_version[1] and AP_WORLD_VERSION[2] < server_apworld_version[2]:
                    # The client has an older patch version than the server, this should just mean the client is
                    # potentially missing some backwards compatible bug fixes, but the bug fixes are likely forwards
                    # compatible, so the connection will be allowed, but with a warning message.
                    logger.warning("Warning: Connected to a multiworld generated with a different, but probably"
                                   " compatible, apworld version %s. The client apworld version is %s. Updating the"
                                   " client version is recommended to avoid issues. Please update your apworld version"
                                   " before reporting any issues.",
                                   server_apworld_version, AP_WORLD_VERSION)
                else:
                    # The client has matching major version and newer minor+patch version, everything *should* be OK
                    # because the client has only additional backwards compatible features and bug fixes.
                    logger.info("Info: Connected to a multiworld generated with a different, but compatible, apworld"
                                " version %s. The client apworld version is %s.",
                                server_apworld_version, AP_WORLD_VERSION)
        else:
            logger.info("Info: Connected to multiworld generated on the same version as the client")

        return True

    def _validate_seed_name_against_save_data(self, new_seed_name: str) -> tuple[bool, bytes | None]:
        save_data_seed_name_hash = self.read_seed_name_hash()
        server_seed_name_hash = self.hash_seed_name(new_seed_name)
        debug_logger.info("Seed hash from save file is %s", save_data_seed_name_hash)
        debug_logger.info("Seed hash from server is %s", server_seed_name_hash)
        if save_data_seed_name_hash is not None:
            if server_seed_name_hash != save_data_seed_name_hash:
                Utils.async_start(self.disconnect())
                logger.info("Connection aborted: The server's seed does not match the save file's seed.")
                self.last_connected_seed_name = None
                self.last_connected_slot = None
                return False, None
            else:
                return True, None
        return True, server_seed_name_hash

    def _read_slot_data(self, slot_data: dict[str, typing.Any]):
        # The connection to the server is assumed to be OK by this point, so slot_data can now be used to adjust client
        # behaviour.
        received_item_messages = slot_data["received_item_messages"]
        self.received_item_messages = received_item_messages == options.ReceivedItemMessages.option_all

        checked_location_messages = slot_data["checked_location_messages"]
        self.checked_location_messages = checked_location_messages == options.CheckedLocationMessages.option_all

        self.acquired_characters.init_from_slot_data(self, slot_data)
        self.acquired_extras.init_from_slot_data(self, slot_data)
        self.acquired_generic.init_from_slot_data(self, slot_data)
        self.unlocked_chapter_manager.init_from_slot_data(self, slot_data)
        self.acquired_minikits.init_from_slot_data(self, slot_data)
        self.text_display.init_from_slot_data(self, slot_data)

        self.true_jedi_and_minikit_checker.init_from_slot_data(self, slot_data)
        self.free_play_completion_checker.init_from_slot_data(self, slot_data)
        self.goal_manager.init_from_slot_data(self, slot_data)
        self.client_expected_idx = 0

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)

        if cmd == "RoomInfo":
            new_seed_name = args["seed_name"]

            if self.is_in_game():
                ok, _server_seed_hash = self._validate_seed_name_against_save_data(new_seed_name)
                if not ok:
                    return

            if self.last_connected_seed_name is not None and self.last_connected_seed_name != new_seed_name:
                self.on_multiworld_or_slot_changed()
                # The last connected slot is irrelevant if the multiworld itself has changed.
                self.last_connected_slot = None
            self.last_connected_seed_name = new_seed_name
            self.seed_name = new_seed_name
            if self.server_version < (0, 6, 2):
                logger.warning("Lego Star Wars: The Complete Saga works best with servers running AP version 0.6.2 or"
                               " newer. The connected server is running version %s, so some same-slot co-op and tracker"
                               " features will not be available.", self.server_version.as_simple_string())
        elif cmd == "Connected":
            if self.last_connected_seed_name is None:
                # The client should be just about to disconnect from failing to match the server's seed.
                # Disconnect again just in-case.
                Utils.async_start(self.disconnect())
                return

            slot_data = args.get("slot_data")
            if isinstance(slot_data, typing.Mapping):
                if not self._validate_version(slot_data):
                    # _validate_version should have logged the appropriate message to the user.
                    self.last_connected_seed_name = None
                    Utils.async_start(self.disconnect())
                    return
            else:
                logger.error("Error: slot_data missing from Connected message, something is probably broken.")

            # It is assumed that the player must be loaded into a save file or a new game at this point.
            ok, server_seed_hash_to_write = self._validate_seed_name_against_save_data(self.last_connected_seed_name)
            if not ok:
                self.seed_name = None
                self.last_connected_seed_name = None
                return

            if server_seed_hash_to_write is not None:
                self.write_seed_name_hash(self.last_connected_seed_name)

            new_slot = self.auth

            if self.last_connected_slot is not None and self.last_connected_slot != new_slot:
                self.on_multiworld_or_slot_changed()
            if self.read_slot_name() is None:
                self.write_slot_name(new_slot)
                self.ap_first_time_setup()
            self.disabled_locations = set(LOCATION_NAME_TO_ID.values()) - self.server_locations

            self._read_slot_data(slot_data)

            # Setting this to non-None indicates to the game watcher loop to start fully running.
            self.last_connected_slot = self.auth
            self.auth_status = AuthStatus.AUTHENTICATED
            # Get, and subscribe to, updates to Free Play completions
            listen_keys = list(
                map(
                    self._get_datastorage_key,
                    (
                        COMPLETED_FREE_PLAY_KEY_PREFIX,
                        COMPLETED_TRUE_JEDI_KEY_PREFIX,
                        COMPLETED_10_MINIKITS_KEY_PREFIX,
                        COMPLETED_BONUSES_KEY_PREFIX,
                        COLLECTED_POWER_BRICKS_KEY_PREFIX,
                        MINIKIT_GOAL_SUBMITTED_PREFIX,
                    )
                )
            )
            Utils.async_start(self.send_msgs(
                [
                    {
                        "cmd": "Get",
                        "keys": listen_keys
                    },
                    {
                        "cmd": "SetNotify",
                        "keys": listen_keys
                    }
                ]
            ))
        elif cmd == "SetReply":
            key: str = args["key"]
            if self._is_datastorage_key(key, COMPLETED_FREE_PLAY_KEY_PREFIX):
                value = args["value"]
                if value is not None:
                    self.free_play_completion_checker.update_from_datastorage(self, value)
            elif self._is_datastorage_key(key, COMPLETED_TRUE_JEDI_KEY_PREFIX):
                value = args["value"] or ()
                previous_value = args["original_value"] or ()
                new_values = set(value)
                new_values.difference_update(previous_value)
                if new_values:
                    self.true_jedi_and_minikit_checker.update_from_datastorage(
                        self, new_true_jedi_area_ids=new_values)
            elif self._is_datastorage_key(key, COMPLETED_10_MINIKITS_KEY_PREFIX):
                value = args["value"] or ()
                previous_value = args["original_value"] or ()
                new_values = set(value)
                new_values.difference_update(previous_value)
                if new_values:
                    self.true_jedi_and_minikit_checker.update_from_datastorage(
                        self, new_minikits_gold_brick_area_ids=new_values)
            elif self._is_datastorage_key(key, COMPLETED_BONUSES_KEY_PREFIX):
                value = args["value"] or ()
                previous_value = args["original_value"] or ()
                new_values = set(value)
                new_values.difference_update(previous_value)
                if new_values:
                    self.bonus_area_completion_checker.update_from_datastorage(self, new_values)
            elif self._is_datastorage_key(key, COLLECTED_POWER_BRICKS_KEY_PREFIX):
                value = args["value"] or ()
                previous_value = args["original_value"] or ()
                new_values = set(value)
                new_values.difference_update(previous_value)
                if new_values:
                    self.true_jedi_and_minikit_checker.update_from_datastorage(
                        self, new_power_brick_area_ids=new_values)
            elif self._is_datastorage_key(key, MINIKIT_GOAL_SUBMITTED_PREFIX):
                value = args["value"]
                if value:
                    self.goal_manager.complete_minikit_goal_from_datastorage(self)

        elif cmd == "Retrieved":
            keys: dict[str, typing.Any] = args["keys"]
            completed_free_play = keys.get(self._get_datastorage_key(COMPLETED_FREE_PLAY_KEY_PREFIX))
            if completed_free_play:
                self.free_play_completion_checker.update_from_datastorage(self, completed_free_play)
            completed_true_jedi = keys.get(self._get_datastorage_key(COMPLETED_TRUE_JEDI_KEY_PREFIX))
            if completed_true_jedi:
                self.true_jedi_and_minikit_checker.update_from_datastorage(
                    self, new_true_jedi_area_ids=completed_true_jedi)
            completed_10_minikits = keys.get(self._get_datastorage_key(COMPLETED_10_MINIKITS_KEY_PREFIX))
            if completed_10_minikits:
                self.true_jedi_and_minikit_checker.update_from_datastorage(
                    self, new_minikits_gold_brick_area_ids=completed_10_minikits)
            completed_bonuses = keys.get(self._get_datastorage_key(COMPLETED_BONUSES_KEY_PREFIX))
            if completed_bonuses:
                self.bonus_area_completion_checker.update_from_datastorage(self, completed_bonuses)
            collected_power_bricks = keys.get(self._get_datastorage_key(COLLECTED_POWER_BRICKS_KEY_PREFIX))
            if collected_power_bricks:
                self.true_jedi_and_minikit_checker.update_from_datastorage(
                    self, new_power_brick_area_ids=collected_power_bricks)
            completed_minikit_goal = keys.get(self._get_datastorage_key(MINIKIT_GOAL_SUBMITTED_PREFIX))
            if completed_minikit_goal:
                self.goal_manager.complete_minikit_goal_from_datastorage(self)

    def _update_datastorage_area_ids(self, key_prefix: str, area_ids: list[int], log_name: str):
        if self.server_version < (0, 6, 2):
            # Using the "update" operation on list values was only added in AP 0.6.2, so an older server version will
            # disconnect the client.
            return
        if not area_ids:
            return
        debug_logger.info("Sending %s area_ids to datastorage: %s", log_name, area_ids)
        Utils.async_start(self.send_msgs([{
            "cmd": "Set",
            "key": self._get_datastorage_key(key_prefix),
            "default": [],
            "want_reply": False,
            "operations": [{"operation": "update", "value": area_ids}]
        }]))

    def update_datastorage_free_play_completion(self, area_ids: list[int]):
        self._update_datastorage_area_ids(COMPLETED_FREE_PLAY_KEY_PREFIX, area_ids, "Free Play Completion")

    def update_datastorage_true_jedi_completion(self, area_ids: list[int]):
        self._update_datastorage_area_ids(COMPLETED_TRUE_JEDI_KEY_PREFIX, area_ids, "True Jedi Completion")

    def update_datastorage_10_minikits_completion(self, area_ids: list[int]):
        self._update_datastorage_area_ids(COMPLETED_10_MINIKITS_KEY_PREFIX, area_ids, "10/10 Minikits Completion")

    def update_datastorage_bonuses_completion(self, area_ids: list[int]):
        self._update_datastorage_area_ids(COMPLETED_BONUSES_KEY_PREFIX, area_ids, "Bonuses Completion")

    def update_datastorage_power_bricks_collected(self, area_ids: list[int]):
        self._update_datastorage_area_ids(COLLECTED_POWER_BRICKS_KEY_PREFIX, area_ids, "Power Bricks Collected")

    def update_datastorage_minikits_goal_submitted(self):
        debug_logger.info("Sending minikit-goal-submitted to datastorage")
        Utils.async_start(self.send_msgs([{
            "cmd": "Set",
            "key": self._get_datastorage_key(MINIKIT_GOAL_SUBMITTED_PREFIX),
            "default": False,
            "want_reply": False,
            "operations": [{"operation": "replace", "value": True}]
        }]))

    def on_multiworld_or_slot_changed(self):
        # The client is connecting to a different multiworld or slot to before, so reset all persisted client data.
        self.reset_persisted_client_data()

    def is_location_unchecked(self, location_id: int):
        """Return whether a location id exists, but has not been checked."""
        return location_id not in self.checked_locations and location_id not in self.disabled_locations

    def is_location_sendable(self, location_id: int):
        return location_id not in self.disabled_locations

    def run_gui(self):
        from kvui import GameManager

        class LegoStarWarsTheCompleteSagaManager(GameManager):
            if not Utils.is_frozen():
                logging_pairs = [
                    ("Client", "Archipelago"),
                    ("TCS Debug", "Debug"),
                ]
            else:
                logging_pairs = [
                    ("Client", "Archipelago"),
                ]
            base_title = "Archipelago Lego Star Wars: The Complete Saga Client"

        self.ui = LegoStarWarsTheCompleteSagaManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    async def server_auth(self, password_requested: bool = False):
        self.password_requested = password_requested

        if self.game_process is None:
            logger.info("Awaiting connection to game process before authenticating")
            return

        if not self.is_in_game():
            logger.info("Awaiting a save file to be loaded, or a new game to be started, before authenticating")
            return

        if self.auth is None:
            self.auth_status = AuthStatus.NEED_INFO
            await self.set_auth()

            if self.auth is None:
                # If a new game was started, there will be no username stored in the save file, so the user will need to
                # provide it.
                await self.get_username()

        if password_requested and not self.password:
            self.auth_status = AuthStatus.NEED_INFO
            await super().server_auth(password_requested)

        self.tags = set()
        await self.send_connect()
        self.auth_status = AuthStatus.PENDING

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.auth_status = AuthStatus.NOT_AUTHENTICATED
        self.server_seed_name = None
        if not allow_autoreconnect:
            self.reset_persisted_client_data()
            self.last_connected_slot = None
            self.last_connected_seed_name = None
        await super().disconnect(allow_autoreconnect)

    async def set_auth(self) -> None:
        slot_name = self.read_slot_name()
        if slot_name is not None:
            self.auth = slot_name
        else:
            # No slot name has been written to the save file yet, so the player will need to provide it.
            pass

    async def shutdown(self):
        logger.info("Shutting down client")
        await self.unhook_game_process()
        return await super().shutdown()

    def open_game_process(self):
        try:
            process = pymem.Pymem(PROCESS_NAME)
        except ProcessNotFound:
            logger.info(f"{PROCESS_NAME} process not found. Make sure it is running.")
            return False
        except ProcessError as err:
            logger.info(f"Unexpected error connecting to game process: {err}.")
            return False

        # Find the address of a unique pattern to determine offsets.
        found_address = process.pattern_scan_module(VERSION_CHECK_PATTERN, process.process_base)
        if found_address is None:
            logger.info(f"Connected to process but could not determine memory offsets. Supported game versions are"
                        f" Steam and GOG, make sure your LegoStarWarsSaga.exe has not been modified.")
            return False

        if found_address == VERSION_CHECK_ADDRESS_STEAM:
            logger.info("Connected to STEAM version successfully")
            # All memory addresses have been written with the STEAM version in mind.
            self._gog_memory_offset = 0
            self._overall_memory_offset = 0
        elif found_address == VERSION_CHECK_ADDRESS_GOG:
            logger.info("Connected to GOG version successfully")
            # The GOG version is offset after around GOG_MEMORY_OFFSET_START.
            self._gog_memory_offset = MEMORY_OFFSET_GOG
            self._overall_memory_offset = 0
        else:
            # Assume a modified STEAM version that is offset by a fixed amount. todo: Try the 'Steamless' executable.
            memory_offset = found_address - VERSION_CHECK_ADDRESS_STEAM
            logger.warning(f"Connected to an unrecognised game version with memory offset {memory_offset:X}. Assuming"
                           f" the game version is a modified STEAM version. Things could be very broken. Please report"
                           f" this in the Lego Star Wars: The Complete Saga thread in the Archipelago discord server.")
            self._gog_memory_offset = 0
            self._overall_memory_offset = memory_offset

        self.game_process = process
        self.text_replacer = TextReplacer(self)
        return True

    async def unhook_game_process(self):
        if self.game_process is not None:
            try:
                self.text_replacer.on_unhook_game_process()
            except (PymemError, WinAPIError):
                pass
            finally:
                self.text_display = InGameTextDisplay()
                self.game_process.close_process()
                self.game_process = None
                logger.info("Unhooked game process")
        # Create a new TextReplacer so that if the game is restarted without the client being restarted, then the client
        # won't try to read/write to memory that was only applicable to the previous game instance.
        self.text_replacer = TextReplacer(self)

    @property
    def _game_process(self) -> pymem.Pymem:
        process = self.game_process
        if process is None:
            raise NoProcessError("No process to read from")
        else:
            return process

    def _adjust_address(self, address: int) -> int:
        if address >= GOG_MEMORY_OFFSET_START:
            return address + self._gog_memory_offset + self._overall_memory_offset
        else:
            return address + self._overall_memory_offset

    def read_uint(self, address: int, raw=False) -> int:
        return self._game_process.read_uint(address if raw else self._adjust_address(address))

    def read_ushort(self, address: int, raw=False) -> int:
        return self._game_process.read_short(address if raw else self._adjust_address(address))

    def read_bytes(self, address: int, length: int, raw=False) -> bytes:
        return self._game_process.read_bytes(address if raw else self._adjust_address(address), length)

    def read_byte(self, address: int, raw=False) -> bytes:
        return self._game_process.read_bytes(address if raw else self._adjust_address(address), 1)

    def read_uchar(self, address: int, raw=False) -> int:
        return self._game_process.read_uchar(address if raw else self._adjust_address(address))
        #return self._game_process.read_bytes(address if raw else self._adjust_address(address), 1)[0]

    def write_uint(self, address: int, value: int, raw=False) -> None:
        self._game_process.write_uint(address if raw else self._adjust_address(address), value)

    def write_byte(self, address: int, value: int, raw=False) -> None:
        self._game_process.write_uchar(address if raw else self._adjust_address(address), value)

    def write_bytes(self, address: int, value: bytes, length: int, raw=False) -> None:
        self._game_process.write_bytes(address if raw else self._adjust_address(address), value, length)

    def write_float(self, address: int, value: float, raw=False) -> None:
        self._game_process.write_float(address if raw else self._adjust_address(address), value)

    def allocate(self, num_bytes: int) -> MemoryAddress:
        return self._game_process.allocate(num_bytes)

    def free(self, address: MemoryAddress) -> None:
        self._game_process.free(address)

    @staticmethod
    def hash_seed_name(seed_name: str) -> bytes:
        encoded = seed_name.encode("utf-8", errors="replace")
        # 16 bytes
        hashed = hashlib.md5(encoded).digest()
        # The default, unused values in each of the sections of 4 bytes we're writing to is 1200.0f.
        # In the tiny chance that the seed name hashes to the same bytes as these default values
        if hashed == ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE * 4:
            # Pick something else.
            hashed = bytes(range(16))
        return hashed

    def write_seed_name_hash(self, seed_name: str):
        hashed = self.hash_seed_name(seed_name)
        assert len(hashed) == 16

        # The normally unused 4 bytes for the first area are being used to store the expected item index, so start from
        # the second area.
        areas = CHAPTER_AREAS[UNUSED_AREA_DWORD_SEED_NAME_HASH_AREAS]
        parts = [hashed[i * 4:i * 4 + 4] for i in range(4)]
        for part, area in zip(parts, areas, strict=True):
            address = area.address + area.UNUSED_CHALLENGE_BEST_TIME_OFFSET

            if __debug__:
                # Ensure the bytes have not already been written to.
                existing_bytes = self.read_bytes(address, 4)
                assert existing_bytes == ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE, (
                    f"The unused bytes the seed hash is being written to at area {area.short_name} are not their"
                    f" expected value of {ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE!r}, instead found"
                    f" {existing_bytes!r}"
                )

            # Write the bytes for this part of the hashed seed name.
            assert len(part) == 4
            self.write_bytes(address, part, 4)

    def read_seed_name_hash(self) -> bytes | None:
        areas = CHAPTER_AREAS[UNUSED_AREA_DWORD_SEED_NAME_HASH_AREAS]
        hashed = b""
        for area in areas:
            address = area.address + area.UNUSED_CHALLENGE_BEST_TIME_OFFSET
            hashed += self.read_bytes(address, 4)
        if hashed == ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE * 4:
            return None
        else:
            return hashed

    def is_seed_name_hash_set(self) -> bool:
        # There is no more efficient way to check this, without forcing the first 4 bytes of seed hashes to not match
        # the default unused value in the save data, then only the first 4 bytes would need to be checked.
        return self.read_seed_name_hash() is not None

    def write_slot_name(self, name: str) -> None:
        assert len(name) <= 16, "Error: Slot name to write is too long, this should not happen."
        encoded_name = name.encode("utf-8")
        # Each UTF-8 character encodes to no more than 4 bytes.
        assert len(encoded_name) <= 64, "Error: Slot name to write encodes to too many bytes, this should not happen."
        # pad with 0xFF bytes. 0xFF never appears in UTF-8.
        if len(encoded_name) < 64:
            encoded_name += b"\xFF" * (64 - len(encoded_name))
        assert len(encoded_name) == 64
        areas = CHAPTER_AREAS[UNUSED_AREA_DWORD_SLOT_NAME_AREAS]
        parts = [encoded_name[i * 4: i * 4 + 4] for i in range(16)]
        for part, area in zip(parts, areas, strict=True):
            address = area.address + area.UNUSED_CHALLENGE_BEST_TIME_OFFSET

            if __debug__:
                # Ensure the bytes have not already been written to.
                existing_bytes = self.read_bytes(address, 4)
                assert existing_bytes == ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE, (
                    f"The unused bytes the slot name is being written to at area {area.short_name} are not their"
                    f" expected value of {ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE!r}, instead found"
                    f" {existing_bytes!r}"
                )

            # Write the bytes for this part of the encoded name.
            assert len(part) == 4
            self.write_bytes(address, part, 4)
            if b"\xFF" in part:
                # Writing can stop once there are padding bytes in a part that was written.
                break

    def read_slot_name(self) -> str | None:
        """
        Read the slot name from the current save file.

        self.is_in_game() should be checked to have returned True before calling this function.

        :return: The slot name in the current save file, or None if no slot name has been written to the current save
        file.
        """
        areas = CHAPTER_AREAS[UNUSED_AREA_DWORD_SLOT_NAME_AREAS]
        encoded_name = b""
        for area in areas:
            address = area.address + area.UNUSED_CHALLENGE_BEST_TIME_OFFSET
            read_bytes = self.read_bytes(address, 4)
            encoded_name += read_bytes
            if b"\xFF" in read_bytes:
                # Reading can stop once there are padding bytes in a part that was read.
                break
        if encoded_name == ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE * 16:
            # The default value of the unused bytes is fortunately invalid UTF-8, so it is not possible for a slot name
            # to produce the same bytes as the default values.
            return None
        # Strip any \xFF padding and return the decoded string.
        debug_logger.info(f"Read slot_name bytes as {[hex(x)[2:] for x in encoded_name]}")
        return encoded_name.partition(b"\xFF")[0].decode("utf-8")

    def is_slot_name_set(self) -> bool:
        """
        Return whether the current save data has a slot name set.

        More efficient than checking `self.read_slot_name is not None`.
        """
        areas = CHAPTER_AREAS[UNUSED_AREA_DWORD_SLOT_NAME_AREAS]
        # Only the first unused bytes need to be checked.
        area = areas[0]
        address = area.address + area.UNUSED_CHALLENGE_BEST_TIME_OFFSET
        read_bytes = self.read_bytes(address, 4)
        # The default value is not valid UTF-8, so the default value is not possible to be part of a slot name, so
        # if the default value is found, then the slot name has not been set and vice versa.
        return read_bytes != ChapterArea.UNUSED_CHALLENGE_BEST_TIME_VALUE

    def is_connected_to_server(self):
        return self.server is not None and not self.server.socket.closed

    def update_current_level_id(self, new_level_id: int):
        current_level_id = self.current_level_id
        if new_level_id != current_level_id:
            # Update client state.
            self.current_level_id = new_level_id
            # Update the datastorage value in the background.
            Utils.async_start(self.send_msgs([{
                "cmd": "Set",
                "key": self._get_datastorage_key(LEVEL_ID_KEY_PREFIX),
                "want_reply": False,
                "operations": [{"operation": "replace", "value": new_level_id}]
            }]))

    def read_current_level_id(self) -> int:
        """
        Read the current level ID from memory.

        The ID of each level is determined incrementally, by the order of the levels in LEVELS/LEVELS.TXT, where the
        first level (the title screen) has ID 0 and the next level has ID 1 etc.

        :return: The current level ID.
        """
        level_id = self.read_ushort(CURRENT_LEVEL_ID)
        self.update_current_level_id(level_id)
        return level_id

    def update_current_cantina_room(self, new_cantina_room: CantinaRoom) -> None:
        current_cantina_room = self.current_cantina_room
        if new_cantina_room != current_cantina_room:
            # Update client state.
            self.current_cantina_room = new_cantina_room
            # Update the datastorage value in the background.
            Utils.async_start(self.send_msgs([{
                "cmd": "Set",
                "key": self._get_datastorage_key(CANTINA_ROOM_KEY_PREFIX),
                "want_reply": False,
                "operations": [{"operation": "replace", "value": new_cantina_room.value}]
            }]))

    def read_current_cantina_room(self) -> CantinaRoom:
        if not self.read_current_level_id() == LEVEL_ID_CANTINA:
            room = CantinaRoom.NOT_IN_CANTINA
        else:
            current_room_id = self.read_uchar(CANTINA_ROOM_ID)
            if 0 <= current_room_id <= 8:
                room = CantinaRoom(current_room_id)
            else:
                room = CantinaRoom.UNKNOWN
        self.update_current_cantina_room(room)
        return room

    def is_in_game(self) -> bool:
        # There are more than 255 levels, but far fewer than 65536, so assume 2 bytes.
        return ((process := self.game_process) is not None
                and process.read_ushort(self._adjust_address(CURRENT_LEVEL_ID)) != 0)

    def get_current_save_file(self) -> int | None:
        file_number = self.read_uchar(CURRENT_SAVE_SLOT)
        if file_number == 255:
            return None
        else:
            return file_number

    def is_in_shop(self, shop_type: ShopType | None = None) -> bool:
        """Check whether the player is currently in a shop. Does not check for being in-game."""
        return (GameState1.IN_CANTINA_SHOP.is_set(self)
                and self.read_current_level_id() == LEVEL_ID_CANTINA  # Additionally check the player is in the Cantina,
                and self.read_uchar(CANTINA_ROOM_ID) == CantinaRoom.SHOP_ROOM.value  # and in the room with the shops.
                and (shop_type is None or self.read_uchar(ACTIVE_SHOP_TYPE_ADDRESS) == shop_type.value))

    def _load_level(self, level_id: int, reset_door: bool = False, hard_reset: bool = False):
        """

        :param level_id: ID of the level to load
        :param reset_door: Reset the saved door. The saved door controls where the player spawns
        :param hard_reset: Fully reload the level, even when the player is in the level already
        :return:
        """
        if not 0 <= level_id <= 333:
            raise ValueError(f"{level_id} is not a valid level ID")
        if self.is_in_game():
            # Based on BrickBench, with addresses converted to Steam addresses.
            if reset_door:
                self.write_byte(0x9513b8, 0)
            if hard_reset:
                self.write_uint(0x803784, 0xFFFFFFFF)
                self.write_uint(0x93b2ac, 0x20)
            level_data_start_addr = self.read_uint(0x951b78)
            # Each level struct is 0x130 bytes. Level IDs are consecutive according to the order they are defined in
            # LEVELS.TXT.
            target_level_data_addr = level_data_start_addr + 0x130 * level_id
            self.write_uint(0x951b80, target_level_data_addr)
            # Some sort of flag that BrickBench sets. I don't know what this does.
            self.write_uint(0x93d850, 1)

    def reload_cantina(self, hard: bool = False) -> bool:
        if self.is_in_game() and self.read_current_cantina_room() == CantinaRoom.SHOP_ROOM:
            if self.is_in_shop():
                # Reloading the cantina while the shop is open gets the camera stuck in the shop, with seemingly no way
                # to fix.
                return False
            else:
                # The Cantina's level ID is 325
                self._load_level(325, hard_reset=hard)
                return True
        return False

    def ap_first_time_setup(self):
        # Custom Character 1 starts with a lightsaber, but the player might not have Jedi unlocked, meaning that Custom
        # Character 1 should not be allowed to use a lightsaber.
        # Custom Characters always have access to blasters, so give Custom Character 1 a Red Blaster.
        self.write_byte(CUSTOM_CHARACTER_1_WEAPON, 4)

    @staticmethod
    def _get_valid_replacement_characters(unlocked_characters: set[int], needed_count: int) -> list[int]:
        """
        Get 2 valid replacement characters, or a single 'Glup' replacement character if there are no valid replacement
        characters.
        """
        # Prioritise good characters.
        replacements = []
        needed_remaining = needed_count

        # Pick from unlocked characters, except Custom Characters, who are not allowed in the Cantina because that is
        # where they are edited.
        not_allowed = {
            CHARACTERS_AND_VEHICLES_BY_NAME["STRANGER 1"].character_index,
            CHARACTERS_AND_VEHICLES_BY_NAME["STRANGER 2"].character_index,
        }
        allowed_character_indices = unlocked_characters - not_allowed
        allowed_character_indices.intersection_update(AP_NON_VEHICLE_CHARACTER_INDICES)

        to_pick_from = sorted(allowed_character_indices)
        picks = random.sample(to_pick_from, min(needed_remaining, len(to_pick_from)))
        replacements.extend(picks)
        needed_remaining -= len(picks)

        if needed_remaining == 0:
            return replacements
        else:
            # Fill remaining spots with the "Skeleton" "Extra Toggle" character.
            replacements.extend([CHARACTERS_AND_VEHICLES_BY_NAME["Skeleton"].character_index] * needed_remaining)
            return replacements

    def _get_player_character_addr(self, player: int) -> int:
        # Note: The returned address from this function is not static for the current game instance. Whenever P1 swaps
        #  character with P2 (or P3/P4/etc. for Story mode), the value of this pointer changes to point to the other
        #  character.
        # The data at a character address includes things like the character's position vector and rotation.
        if player == 1:
            # There seems to be the same pointer value at +0x20, but Brick Bench uses 0x93d810 (GOG), which is 0x93d7f0
            # (STEAM) used below, so lets use that one.
            # Maybe 0x93d830 can be different in some cases?
            ptr_addr = 0x93d7f0
        elif player == 2:
            ptr_addr = 0x93d7f4
        else:
            raise ValueError(f"Invalid player {player}")
        character_address = self.read_uint(ptr_addr)
        return character_address

    def _get_character_data_address(self, character_address: int) -> int:
        # Each character has a pointer to its character data, which controls how the character looks, what animations it
        # plays, and probably what abilities the character has and other static data that can be referenced by multiple
        # characters with the same character data, e.g. all the regular Battle Droids in 1-1 are separate character
        # instances, but each reference the same Battle Droid character data.
        if character_address == 0:
            # NULL pointer
            return 0
        character_data_address = self.read_uint(character_address + 0x50, raw=True)
        return character_data_address

    def _get_character_id(self, character_data_address) -> int | None:
        if character_data_address == 0:
            return None
        # Character ID is the first 2 bytes
        character_id = self.read_ushort(character_data_address + 0x0, raw=True)
        return character_id

    def _get_player_character_id(self, player: int) -> int | None:
        return self._get_character_id(self._get_character_data_address(self._get_player_character_addr(player)))

    async def reload_cantina_if_invalid_characters(self):
        unlocked_characters = self.acquired_characters.unlocked_characters

        if not unlocked_characters:
            # If connected, there should always be at least 1 character unlocked, even if it is a vehicle character.
            return

        if (
                self.is_in_game()
                and self.read_current_level_id() == LEVEL_ID_CANTINA
                and GameState1.PLAYING_OR_TRAILER_OR_CANTINA_LOAD_OR_CHAPTER_TITLE_CRAWL.is_set(self)
                and self.read_uchar(OPENED_MENU_DEPTH_ADDRESS) == 0
        ):
            if self._cantina_needs_reload_to_fix_characters:
                if self.reload_cantina(hard=True):
                    await asyncio.sleep(1.0)
                    self._cantina_needs_reload_to_fix_characters = False
                return
            # Skeleton is the backup character the client forces when the player does not have at least 2 unlocked
            # non-vehicle characters.
            skeleton_character_index = CHARACTERS_AND_VEHICLES_BY_NAME["Skeleton"].character_index
            needed_replacements = 0
            p1_character_id = self._get_player_character_id(1)
            if (p1_character_id is not None
                    and p1_character_id != skeleton_character_index
                    and p1_character_id not in unlocked_characters):
                needed_replacements += 1
                replace_p1 = True
                debug_logger.info("P1 is character ID %i in the Cantina, which is not unlocked. Picking a replacement"
                                  " character and reloading the Cantina.", p1_character_id)
            else:
                replace_p1 = False
            p2_character_id = self._get_player_character_id(2)
            if (p2_character_id is not None
                    and p2_character_id != skeleton_character_index
                    and p2_character_id not in unlocked_characters):
                needed_replacements += 1
                replace_p2 = True
                debug_logger.info("P2 is character ID %i in the Cantina, which is not unlocked. Picking a replacement"
                                  " character and reloading the Cantina.", p2_character_id)
            else:
                replace_p2 = False
            if needed_replacements == 0:
                # Both characters are unlocked or are already Skeleton, so there is nothing to do.
                return
            replacements = self._get_valid_replacement_characters(unlocked_characters, needed_replacements)
            if replace_p1:
                self.write_uint(P1_CANTINA_FREE_PLAY_SELECTION_CHARACTER_ID, replacements.pop(0))
            if replace_p2:
                self.write_uint(P2_CANTINA_FREE_PLAY_SELECTION_CHARACTER_ID, replacements.pop(0))

            if self.reload_cantina(hard=True):
                await asyncio.sleep(1.0)
            else:
                # If the reload failed (e.g. the player is in the shop or the game is paused), try again.
                self._cantina_needs_reload_to_fix_characters = True

    def set_game_expected_idx(self, idx: int) -> None:
        # The expected idx is stored in the unused 4 bytes at the end of Negotiations' (1-1's) save data.
        negotiations = SHORT_NAME_TO_CHAPTER_AREA["1-1"]
        self.write_uint(negotiations.address + negotiations.UNUSED_CHALLENGE_BEST_TIME_OFFSET, idx)

    def get_game_expected_idx(self) -> int:
        # Retrieve the expected idx from the unused 4 bytes at the end of Negotiations' (1-1's) save data.
        negotiations = SHORT_NAME_TO_CHAPTER_AREA["1-1"]
        expected_idx = self.read_uint(negotiations.address + negotiations.UNUSED_CHALLENGE_BEST_TIME_OFFSET)
        # The default value for new save files is 1200.0f.
        # 1_150_681_088 == struct.unpack("i", struct.pack("f", 1200))
        if expected_idx == 1_150_681_088:
            # Yes, the client will break if you send it this many items, but that should never happen right?
            return 0
        else:
            return expected_idx

    def give_item(self, code: int) -> bool:
        if code in STUDS_AP_ID_TO_VALUE:
            # Studs are directly given to the player as they are received, so it is necessary to check that the player
            # is currently in-game.
            if not self.is_in_game():
                return False
            give_studs(self, code)
        else:
            self.receive_item(code)
        return True

    def receive_item(self, code: int):
        from .. import LegoStarWarsTCSWorld
        item_name = LegoStarWarsTCSWorld.item_id_to_name.get(code, f"Unknown {code}")
        debug_logger.info(f"Receiving item {item_name} from AP")
        if code in self.acquired_generic.receivable_ap_ids:
            self.acquired_generic.receive_generic(self, code)
        elif code in self.acquired_minikits.receivable_ap_ids:
            self.acquired_minikits.receive_minikit(self, code)
        elif code in self.acquired_characters.receivable_ap_ids:
            self.acquired_characters.receive_character(code)
            self.unlocked_chapter_manager.on_character_or_episode_unlocked(code)
        elif code in self.acquired_extras.receivable_ap_ids:
            self.acquired_extras.receive_extra(code)
        elif code in STUDS_AP_ID_TO_VALUE:
            # The client may be resetting its state after a save data rollback or after connecting to an existing seed.
            pass
        else:
            logger.warning(f"Received unknown item with AP ID {code}")

    def reset_persisted_client_data(self, clear_text_display_queue=True):
        """
        Reset all client state.

        Used when deliberately disconnecting from a server.
        """
        self.finished_game = False
        self.locations_checked.clear()
        self.acquired_extras = AcquiredExtras()
        self.acquired_characters = AcquiredCharacters()
        self.acquired_generic = AcquiredGeneric()
        self.acquired_minikits = AcquiredMinikits()

        self.unlocked_chapter_manager = UnlockedChapterManager()
        self.client_expected_idx = 0
        self.current_level_id = 0
        self.current_cantina_room = CantinaRoom.UNKNOWN

        self.free_play_completion_checker = FreePlayChapterCompletionChecker()
        self.true_jedi_and_minikit_checker = TrueJediAndMinikitChecker()
        self.purchased_extras_checker = PurchasedExtrasChecker()
        self.purchased_characters_checker = PurchasedCharactersChecker()
        self.bonus_area_completion_checker = BonusAreaCompletionChecker()

        self.goal_manager = GoalManager()

        if clear_text_display_queue:
            self.text_display.message_queue.clear()

    def reset_client_received_items(self):
        """
        Reset the items that the client thinks it has received.

        Use in cases where the client save data has rolled back.
        """
        self.acquired_extras.clear_received_items()
        self.acquired_characters.clear_received_items()
        self.acquired_generic.clear_received_items()
        self.acquired_minikits.clear_received_items()

        self.client_expected_idx = 0


async def give_items(ctx: LegoStarWarsTheCompleteSagaContext):
    if ctx.is_in_game():
        # The player can enter a save file, receive items, and then exit back to the main menu without saving,
        # and then load their save file again, reverting their expected_idx to an older value and undoing any studs that
        # were given.
        # To ensure that given studs take into account the player's score multiplier at the time the studs were given,
        # it is necessary to reset all received items on the client side in this case.
        expected_idx_game = ctx.get_game_expected_idx()
        expected_idx_client = ctx.client_expected_idx

        received_items = ctx.items_received

        # Check if the game rolled back its save data, the client needs to reset its items and catch back up to the
        # game.
        if expected_idx_game < ctx.client_expected_idx:
            debug_logger.info("Resetting client received items due to game save data rollback")
            ctx.reset_client_received_items()
            for idx, item in enumerate(received_items[:expected_idx_game]):
                ctx.receive_item(item.item)
                ctx.client_expected_idx = idx + 1
            assert ctx.client_expected_idx == min(expected_idx_game, len(received_items))
        # Check if the player is resuming a seed where the client is fresh and needs to be caught up to the game.
        elif expected_idx_client < expected_idx_game:
            # The client may not have yet connected to the server and received the items to be able to catch up yet, so
            # don't spam the debug log.
            if len(received_items) > expected_idx_client:
                debug_logger.info("Catching up client to game state. Client expected: %i. Game expected: %i.",
                                  ctx.client_expected_idx, expected_idx_game)
                for idx, item in enumerate(received_items[expected_idx_client:expected_idx_game],
                                           start=expected_idx_client):
                    ctx.receive_item(item.item)
                    ctx.client_expected_idx = idx + 1
                # If `expected_idx_client` is to be used beyond this point, it needs to be updated.
                # expected_idx_client = ctx.client_expected_idx
                assert ctx.client_expected_idx == min(expected_idx_game, len(received_items))

        # Check if there are new items.
        if len(received_items) <= expected_idx_game:
            # There are no new items.
            return

        # Loop through items to give.
        # Give the player all items at an index greater than or equal to the expected index.
        for idx, item in enumerate(received_items[expected_idx_game:], start=expected_idx_game):
            while not ctx.give_item(item.item):
                await asyncio.sleep(0.01)

            # Increment the expected index.
            ctx.set_game_expected_idx(idx + 1)
            ctx.client_expected_idx = idx + 1


async def game_watcher_check_save_file(ctx: LegoStarWarsTheCompleteSagaContext,
                                       only_just_loaded_into_game: bool) -> bool:
    """
    Check for changes to the current save file.

    If the player loads a different save file, the client data needs to be reset and reloaded onto the new save file.

    Except, this is not necessary if the player has gone from no save file (starting a new game), to creating a save
    file.

    If the player loads a save file for a different multiworld or slot, they need to be disconnected from the current
    multiworld.

    No save file -> save file:    OK
    Save file -> no save file:    Reset client state and reload onto the new game that has yet to save
    Save file -> other save file: Reset client state and disconnect if the other save is for a different
                                  multiworld/slot.
    :param ctx:
    :param only_just_loaded_into_game: Indicates whether the game was previously in the main menu or not connected, but
    has just loaded into a save file or new game.
    :return:
    """
    current_save_file = ctx.get_current_save_file()

    if ctx.last_connected_slot is None and ctx.last_connected_seed_name is None:
        # The player has made no connection to a server, so there is nothing to check against.
        # The player could have started a new game or loaded an existing save file.
        pass
    else:
        # If the player loads a different save file, re-check the multiworld seed and slot name and reset
        # persistent client data if either the seed or slot name differ.
        last_save_file = ctx.last_loaded_save_file
        if (current_save_file != last_save_file
                or (only_just_loaded_into_game and current_save_file is None and last_save_file is None)):
            last_slot_name = ctx.last_connected_slot
            last_seed_name = ctx.last_connected_seed_name

            # The player is allowed to exit to the main menu and start a new game.
            if current_save_file is None:
                if last_slot_name is not None and ctx.read_slot_name() is None:
                    logger.info("Copied the last connected slot name to the new save file.")
                    ctx.write_slot_name(last_slot_name)
                if last_seed_name is not None and ctx.read_seed_name_hash() is None:
                    logger.info("Copied the last connected multiworld seed hash to the new save file.")
                    ctx.write_seed_name_hash(last_seed_name)
                # The save file is new, so run first-time setup.
                ctx.ap_first_time_setup()
            else:
                # The player *could* have another save file with the same seed and slot, which would be
                # unusual, but acceptable.
                # But if the player tries to load into a save file for a different seed/slot, then they need
                # to be disconnected.
                if (last_seed_name is not None
                        and ctx.hash_seed_name(last_seed_name) != ctx.read_seed_name_hash()):
                    if ctx.slot:
                        logger.info("Disconnecting from the server because the newly loaded save file's"
                                    " seed does not match the connected multiworld's seed.")
                    await ctx.disconnect()
                    return False
                elif last_slot_name is not None and last_slot_name != ctx.read_slot_name():
                    if ctx.slot:
                        logger.info("Disconnecting from the server because the newly loaded save file's"
                                    " slot name does not match the connected slot.")
                    await ctx.disconnect()
                    return False
        elif current_save_file is not None and only_just_loaded_into_game:
            # The player can start a new game, progress it before connecting to the server (they shouldn't do this
            # because the client won't be running fully at that point), causing it to save to a save slot. Then the
            # player could connect to the server (writing the seed hash and slot name into the save data), but then
            # return to the main menu, reverting the save data to before the seed hash and slot name were written. If
            # the player then loads the save file again, they can end up connected to the server while not having the
            # slot name and seed name hash written into their save file.
            slot_name = ctx.last_connected_slot
            seed_name = ctx.last_connected_seed_name
            if slot_name is not None and seed_name is not None:
                if not ctx.is_slot_name_set():
                    ctx.write_slot_name(slot_name)
                    logger.info("Restored slot name in save data after save data was rolled back to before it was set")
                if not ctx.is_seed_name_hash_set():
                    ctx.write_seed_name_hash(seed_name)
                    logger.info("Restored seed name hash in save data after save data was rolled back to before it was"
                                " set")
    ctx.last_loaded_save_file = current_save_file
    return True


async def game_watcher(ctx: LegoStarWarsTheCompleteSagaContext):
    logger.info("Starting connection to game.")
    last_message = ""
    # Used to track if the player was loaded into a save/new game in the previous loop.
    previously_not_in_game = True

    def log_message(msg: str, always_log=False):
        nonlocal last_message
        if always_log or msg != last_message:
            logger.info(msg)
            last_message = msg

    sleep_time = 0.0
    while not ctx.exit_event.is_set():
        if sleep_time > 0.0:
            try:
                await asyncio.wait_for(ctx.watcher_event.wait(), sleep_time)
            except asyncio.TimeoutError:
                pass
            sleep_time = 0.0
        ctx.watcher_event.clear()

        try:
            game_process = ctx.game_process
            if game_process is None:
                previously_not_in_game = True
                if not ctx.open_game_process():
                    log_message("Connection to game failed, attempting again in 5 seconds...", True)
                    sleep_time = 5
                else:
                    # No wait, start processing items/locations/etc. immediately if the client is connected to the
                    # server.
                    pass
            else:
                if not ctx.is_in_game():
                    previously_not_in_game = True
                    # Need to wait for the player to load into a save file.
                    if (ctx.last_loaded_save_file is not None
                            or ctx.last_connected_seed_name is not None
                            or ctx.last_connected_slot is not None):
                        # There is a previously loaded save file or connected seed/slot, so the player has exited to the
                        # main menu.
                        last_connected_slot_name = ctx.last_connected_slot
                        if last_connected_slot_name is not None:
                            log_message(f"Load back into the save file, or a new game, to continue as"
                                        f" {last_connected_slot_name}.")
                        else:
                            log_message("Load back into a save file or a new game to continue.")
                    else:
                        # There is no previously loaded save file or seed/slot, so the player has just started the game.
                        log_message("Load into a save file or start a new game to continue.")
                    sleep_time = 1.0
                    continue

                # The save file check does some extra checks if the player was previously not loaded into a save
                # file/new game, but now is.
                only_just_loaded_into_game = previously_not_in_game
                previously_not_in_game = False

                if not await game_watcher_check_save_file(ctx, only_just_loaded_into_game):
                    # The player changed save file to a save file for a different multiworld or slot.
                    # A message will already have been logged.
                    sleep_time = 1.0
                    continue

                if ctx.last_connected_slot is None or ctx.last_connected_seed_name is None:
                    sleep_time = 1.0
                    if ctx.server is not None and not ctx.server.socket.closed:
                        if ctx.auth_status == AuthStatus.NOT_AUTHENTICATED:
                            await ctx.server_auth(ctx.password_requested)
                        else:
                            # Most likely waiting for the player to enter their slot name.
                            pass
                    else:
                        ctx.auth_status = AuthStatus.NOT_AUTHENTICATED
                        log_message("Connect to a server to continue")
                    continue

                # Even if the client has disconnected from the server, it is still important to run a number of
                # coroutines to allow the player to play while disconnected.
                # todo: Is the `is_in_game()` check here still necessary now that there is an earlier check?
                if ctx.is_in_game():
                    await ctx.text_replacer.update_game_state(ctx)
                    await ctx.free_play_completion_checker.initialize(ctx)
                    await give_items(ctx)

                    # Update game state for received items.
                    await ctx.reload_cantina_if_invalid_characters()
                    await ctx.acquired_characters.update_game_state(ctx)
                    await ctx.acquired_extras.update_game_state(ctx)
                    await ctx.acquired_generic.update_game_state(ctx)
                    await ctx.acquired_minikits.update_game_state(ctx)
                    await ctx.unlocked_chapter_manager.update_game_state(ctx)
                    await ctx.text_display.update_game_state(ctx)

                    # Only queue the message if everything else worked so far.
                    msg = "The client is now fully connected to the game, receiving items and checking locations."
                    if last_message != msg:
                        log_message(msg)
                        slot_name = ctx.read_slot_name()
                        if not ctx.is_connected_to_server():
                            # A previous connection must have been made, but the server connection has been lost
                            # unintentionally (it will attempt to auto-reconnect).
                            # todo: Make these messages display for longer somehow (extra argument to queue_message?).
                            ctx.text_display.queue_message(f"Client running in disconnected mode as {slot_name}")
                            ctx.text_display.queue_message(f"Items and checks will be synced once the server connection"
                                                           f" is reestablished")
                        else:
                            ctx.text_display.queue_message(f"Client running and connected as {slot_name}")

                    # Check for newly cleared locations while connected to a slot on a server.
                    # todo: Some of these don't need to be checked very often because they are persisted in the save
                    #  file.
                    if ctx.slot:
                        new_location_checks: list[int] = []
                        # todo: Free play completion needs to be checked often (need to ensure that players cannot click
                        #  through the status screen faster than we're polling the game to check for free play!)
                        await ctx.free_play_completion_checker.check_completion(ctx, new_location_checks)
                        # todo: True Jedi and Minikit counts (deprecated) in the save data do not need to be checked
                        #  often, but the in-level True Jedi and Minikit counts (deprecated) do need to be check often.
                        await ctx.true_jedi_and_minikit_checker.check_true_jedi_and_minikits(ctx, new_location_checks)
                        # todo: Purchases do not need to be checked often.
                        await ctx.purchased_extras_checker.check_extra_purchases(ctx, new_location_checks)
                        await ctx.purchased_characters_checker.check_extra_purchases(ctx, new_location_checks)
                        # todo: Bonus level completion is read from the save data, so does not need to be read often.
                        await ctx.bonus_area_completion_checker.check_completion(ctx, new_location_checks)

                        # Send newly cleared locations to the server, if there are any.
                        actually_new_location_checks = await ctx.check_locations(new_location_checks)
                        ctx.locations_checked.update(actually_new_location_checks)

                        await ctx.goal_manager.update_game_state(ctx)

                        # Check for goal completion.
                        if not ctx.finished_game:
                            if ctx.goal_manager.is_goal_complete(ctx):
                                await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                                ctx.finished_game = True
                sleep_time = 0.1
        except Exception as e:
            await ctx.unhook_game_process()
            ctx.reset_persisted_client_data()
            if isinstance(e, (PymemError, WinAPIError)):
                msg = "Lost connection to game, attempting re-connection in 5 seconds..."
                debug_logger.error(traceback.format_exc())
            else:
                msg = "Unexpected error occurred, attempting re-connection to game in 5 seconds..."
                logger.error(traceback.format_exc())
            logger.info(msg)
            last_message = msg
            await ctx.disconnect()
            sleep_time = 5
            continue

        # This is reached when there is no game process to connect to, allowing a server connection to be made, without
        # actually connecting to a slot.
        if ctx.server is not None and not ctx.server.socket.closed:
            if ctx.auth_status == AuthStatus.NOT_AUTHENTICATED:
                Utils.async_start(ctx.server_auth(ctx.password_requested))
        else:
            ctx.auth_status = AuthStatus.NOT_AUTHENTICATED


async def main():
    Utils.init_logging("LegoStarWarsTheCompleteSagaClient", exception_logger="ClientException")

    ctx = LegoStarWarsTheCompleteSagaContext()
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    game_watcher_task = asyncio.create_task(game_watcher(ctx), name="LegoStarWarsTheCompleteSagaGameWatcher")

    await ctx.exit_event.wait()
    # Wake the game watcher task, if it is currently sleeping, so it can start shutting down when it sees that the
    # exit_event is set.
    ctx.watcher_event.set()
    ctx.server_address = None

    try:
        await game_watcher_task
    except Exception as e:
        logger.exception(e)
    await ctx.shutdown()


def launch():
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()
