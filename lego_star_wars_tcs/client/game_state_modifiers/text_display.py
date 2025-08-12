import logging
from collections import deque
from time import perf_counter_ns
from typing import Any

from . import GameStateUpdater
from ..common_addresses import OPENED_MENU_DEPTH_ADDRESS, GameState1
from ..type_aliases import TCSContext
from .text_replacer import TextId


debug_logger = logging.getLogger("TCS Debug")

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


class InGameTextDisplay(GameStateUpdater):
    next_allowed_message_time: int = -1
    next_allowed_clean_time: int = -1
    # If the last write to memory was a custom message.
    memory_dirty: bool = False

    message_queue: deque[str]

    def __init__(self):
        self.message_queue = deque()

    def init_from_slot_data(self, ctx: TCSContext, slot_data: dict[str, Any]) -> None:
        pass

    def queue_message(self, message: str):
        self.message_queue.append(message)

    def priority_message(self, message: str):
        self.message_queue.appendleft(message)

    # A custom minimum duration of more than 4 seconds is irrelevant currently because the message fades out by that
    # point.
    def _display_message(self, ctx: TCSContext, message: str,
                         next_message_delay_ns: int = WAIT_BETWEEN_MESSAGES_NS,
                         display_duration_s: float = 4.0):
        # Write the message into the allocated memory for message strings.
        debug_logger.info("Text Display: Displaying in-game message '%s'", message)
        ctx.text_replacer.write_custom_string(TextId.DOUBLE_SCORE_ZONE, message)
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
            # The TCSContext's TextReplacer will restore all replaced texts back to their vanilla text.
            self.memory_dirty = False

    async def update_game_state(self, ctx: TCSContext) -> None:
        now = perf_counter_ns()
        if now < self.next_allowed_message_time:
            return

        if not self.message_queue:
            if self.memory_dirty and now > self.next_allowed_clean_time:
                debug_logger.info("Text Display: Clearing dirty memory")
                ctx.text_replacer.write_vanilla_string(TextId.DOUBLE_SCORE_ZONE)
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
                    and GameState1.is_playing(ctx)
            ):
                self._display_message(ctx, self.message_queue.popleft())
