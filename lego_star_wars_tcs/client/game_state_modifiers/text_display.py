import logging
import re
import struct
from collections import deque
from time import perf_counter_ns
from typing import Any

from . import GameStateUpdater
from ..common_addresses import OPENED_MENU_DEPTH_ADDRESS
from ..type_aliases import TCSContext


logger = logging.getLogger("Client")
debug_logger = logging.getLogger("TCS Debug")

# char***
LOCALIZED_TEXT_ARRAY_POINTER = 0x926C20
DOUBLE_SCORE_ZONE_TEXT_ID = 87

# This is the number of bytes allocated for displaying messages.
MAX_MESSAGE_LENGTH = 1024

# Float value in seconds. The text will begin to fade out towards the end.
# Note that values higher than 1.0 will flash more rapidly the higher the value.
DOUBLE_SCORE_ZONE_TIMER_ADDRESS = 0x925040

WAIT_BETWEEN_MESSAGES_SECONDS = 2
WAIT_BETWEEN_MESSAGES_NS = WAIT_BETWEEN_MESSAGES_SECONDS * 1_000_000_000

# -- Game state addresses.

# This value is slightly unstable and occasionally changes to 0 while playing. It is also set to 2 in Mos Espa Pod Race
# for some reason.
# Importantly, this value is *not* 0 when watching a Story cutscene, and is instead 1.
PAUSED_OR_STATUS_WHEN_0_ADDRESS = 0x9737D8
# This address is usually -1/255 while playing or paused, 1 while tabbed out and 0 while both paused and tabbed out.
# It is a more unstable than the previous value, while playing, however.
TABBED_OUT_WHEN_1_ADDRESS = 0x9868C4

# 0 when playing, 1 when in a cutscene, same-level door transition, Indy trailer and title crawl.
# Rarely unstable and seen as -1 briefly while playing
IS_PLAYING_WHEN_0_ADDRESS = 0x297C0AC

# 255: Cutscene
# 1: Playing, Indy trailer, loading into Cantina, Title crawl
# 2: In-level 'cutscene' where non-playable characters play an animation and the player has no control
# 6: Bounty Hunter missions select
# 7: In custom character creator
# 8: In Cantina shop
# 9: Minikits display on outside scrapyard
# There is another address at 0x925395
GAME_STATE_ADDRESS = 0x925394


class InGameTextDisplay(GameStateUpdater):
    double_score_zone_string_address: int = -1
    vanilla_pointer: int
    vanilla_bytes: bytes = b""
    initialized: bool = False
    next_allowed_message_time: int = -1
    next_allowed_clean_time: int = -1
    # If the last write to memory was a custom message.
    memory_dirty: bool = False
    messages_enabled: bool = False

    message_queue: deque[str]

    def __init__(self):
        self.message_queue = deque()

    def init_from_slot_data(self, slot_data: dict[str, Any]) -> None:
        pass

    def _initialize(self, ctx: TCSContext):
        self.initialized = True
        process = ctx.game_process
        assert process is not None
        # char*** or the char** of the first string in the array.
        array_address = ctx.read_uint(LOCALIZED_TEXT_ARRAY_POINTER)
        # char**, the address of the pointer to the "Double Score Zone!" text.
        double_score_zone_pointer_address = array_address + DOUBLE_SCORE_ZONE_TEXT_ID * 4  # 4 bytes per pointer.

        # char*, the address of the first character in the vanilla "Double Score Zone!" text.
        self.vanilla_pointer = ctx.read_uint(double_score_zone_pointer_address, raw=True)
        self.vanilla_bytes = ctx.read_bytes(self.vanilla_pointer, 200, raw=True).partition(b"\x00")[0] + b"\x00"

        self.double_score_zone_string_address = process.allocate(MAX_MESSAGE_LENGTH)

        # Replace the game's pointer to the "Double Score Zone!" text with a pointer to the start of the newly
        # allocated memory.
        ctx.write_uint(double_score_zone_pointer_address, self.double_score_zone_string_address, raw=True)

        debug_logger.info("Text Display: Vanilla Double Score Zone! string:")
        debug_logger.info(self.vanilla_bytes.replace(b"\x00", b"NULL\n").decode("utf-8", errors="replace"))
        self.messages_enabled = True

    def queue_message(self, message: str):
        if self.messages_enabled:
            self.message_queue.append(message)

    def write_bytes_to_double_score_zone(self, ctx: TCSContext, string: bytes):
        ctx.write_bytes(self.double_score_zone_string_address, string, len(string), raw=True)

    # A custom minimum duration of more than 4 seconds is irrelevant currently because the message fades out by that
    # point.
    def _display_message(self, ctx: TCSContext, message: str,
                         next_message_delay_ns: int = WAIT_BETWEEN_MESSAGES_NS,
                         display_duration_s: float = 4.0):
        # Write the message into the allocated memory for message strings.
        debug_logger.info("Text Display: Displaying in-game message '%s'", message)
        encoded = message.encode("utf-8", errors="replace")
        # Limit the maximum size and ensure there is a null terminator.
        encoded = encoded[:MAX_MESSAGE_LENGTH - 1] + b"\x00"
        self.write_bytes_to_double_score_zone(ctx, encoded)
        self.memory_dirty = True

        # Set the timer.
        ctx.write_float(DOUBLE_SCORE_ZONE_TIMER_ADDRESS, display_duration_s)

        # Update for the next time that a new message can be displayed.
        now = perf_counter_ns()
        self.next_allowed_message_time = now + next_message_delay_ns
        self.next_allowed_clean_time = max(now + int((display_duration_s + 1) * 1_000_000_000),
                                           self.next_allowed_message_time)

    def on_unhook_game_process(self, ctx: TCSContext) -> None:
        self.message_queue.clear()
        if self.memory_dirty:
            self.write_bytes_to_double_score_zone(ctx, self.vanilla_bytes)
            self.memory_dirty = False

    async def update_game_state(self, ctx: TCSContext) -> None:
        if not self.initialized:
            self._initialize(ctx)
        now = perf_counter_ns()
        if now < self.next_allowed_message_time:
            return

        if not self.message_queue:
            if self.memory_dirty and now > self.next_allowed_clean_time:
                debug_logger.info("Text Display: Clearing dirty memory")
                self.write_bytes_to_double_score_zone(ctx, self.vanilla_bytes)
                self.memory_dirty = False
        else:
            # Don't display a new message if the game is paused, in a cutscene, in a status screen, or tabbed out.
            if (
                    # Handles pause and status screens.
                    ctx.read_uchar(PAUSED_OR_STATUS_WHEN_0_ADDRESS) != 0
                    # Handles tabbing out.
                    and ctx.read_uchar(TABBED_OUT_WHEN_1_ADDRESS) != 1
                    # Handles pause menu and other menus.
                    and ctx.read_uchar(OPENED_MENU_DEPTH_ADDRESS) == 0
                    # Handles same-level screen transitions.
                    and ctx.read_uchar(IS_PLAYING_WHEN_0_ADDRESS) == 0
                    and 1 <= ctx.read_uchar(GAME_STATE_ADDRESS) <= 2
            ):
                self._display_message(ctx, self.message_queue.popleft())

