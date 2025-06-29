import logging
from typing import Mapping

from ..type_aliases import TCSContext
from ...items import MINIKITS_BY_COUNT
from . import ItemReceiver

MINIKIT_ITEMS: Mapping[int, int] = {item.code: count for count, item in MINIKITS_BY_COUNT.items()}

# Goal progress is written into Custom Character 2's name until a better place for this information is found.
CUSTOM_CHARACTER2_NAME_OFFSET = 0x86E524 + 0x14  # string[15]


logger = logging.getLogger("Client")


class AcquiredMinikits(ItemReceiver):
    receivable_ap_ids = MINIKIT_ITEMS

    minikit_count: int
    goal_minikit_count: int = 999_999_999  # Set by an option and read from slot data.

    def __init__(self):
        self.minikit_count = 0

    def receive_minikit(self, ap_item_id: int):
        # Minikits
        if ap_item_id in MINIKIT_ITEMS:
            self.minikit_count += MINIKIT_ITEMS[ap_item_id]
        else:
            logger.error("Unhandled ap_item_id %s for generic item", ap_item_id)

    def _update_goal_display(self, ctx: TCSContext):
        goal_count = str(self.goal_minikit_count)
        # Display the current count with as many digits as the goal count.
        leading_digits_to_display = len(goal_count)

        # PyCharm does not like the fact that an f-string is being used to format a format string.
        # noinspection PyStringFormat
        current_minikit_count = f"{{:0{leading_digits_to_display}d}}".format(self.minikit_count)

        # There are few available characters. The player is limited to "0-9A-Z -", but the names are capable of
        # displaying more punctuation and lowercase letters. A few characters with ligatures are supported as part of
        # localisation for other languages.
        goal_display_text = f"{current_minikit_count}/{goal_count} GOAL".encode("ascii")
        # The maximum size is 16 bytes, but the string must be null-terminated, so there are 15 usable bytes.
        goal_display_text = goal_display_text[:15] + b"\x00"
        ctx.write_bytes(CUSTOM_CHARACTER2_NAME_OFFSET, goal_display_text, len(goal_display_text))

    async def update_game_state(self, ctx: TCSContext):
        self._update_goal_display(ctx)
