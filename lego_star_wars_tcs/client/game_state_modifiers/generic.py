import logging
from typing import Mapping, Sequence, AbstractSet, Any

from ..type_aliases import TCSContext
from ...items import (
    GENERIC_BY_NAME,
    ExtraData,
    EXTRAS_BY_NAME,
    CHARACTERS_AND_VEHICLES_BY_NAME,
    GenericItemData,
)
from . import ItemReceiver

RECEIVABLE_GENERIC_BY_AP_ID: Mapping[int, GenericItemData] = {
    item.code: item for item in GENERIC_BY_NAME.values() if item.code != -1 and not item.name.endswith("Stud")
}
EPISODE_UNLOCKS: Mapping[int, int] = {
    GENERIC_BY_NAME[f"Episode {i} Unlock"].code: i for i in range(1, 6+1)
}
ALL_EPISODES_TOKEN: int = GENERIC_BY_NAME["All Episodes Token"].code
PROGRESSIVE_SCORE_MULTIPLIER: int = GENERIC_BY_NAME["Progressive Score Multiplier"].code
SCORE_MULIPLIER_EXTRAS: Sequence[ExtraData] = (
    EXTRAS_BY_NAME["Score x2"],
    EXTRAS_BY_NAME["Score x4"],
    EXTRAS_BY_NAME["Score x6"],
    EXTRAS_BY_NAME["Score x8"],
    EXTRAS_BY_NAME["Score x10"],
)

BONUS_CHARACTER_REQUIREMENTS: Mapping[int, AbstractSet[int]] = {
    1: {CHARACTERS_AND_VEHICLES_BY_NAME["Anakin's Pod"].character_index},
    2: {CHARACTERS_AND_VEHICLES_BY_NAME["Naboo Starfighter"].character_index},
    3: {CHARACTERS_AND_VEHICLES_BY_NAME["Republic Gunship"].character_index},
    4: {CHARACTERS_AND_VEHICLES_BY_NAME[name].character_index
        for name in ("Darth Vader", "Stormtrooper", "C-3PO")},
}

BONUSES_BASE_ADDRESS = 0x86E4E4

# Goal progress is written into Custom Character 2's name until a better place for this information is found.
CUSTOM_CHARACTER2_NAME_OFFSET = 0x86E524 + 0x14  # string[15]


logger = logging.getLogger("Client")


COMBINED_SCORE_MULTIPLIERS: Sequence[int] = [
    1,
    2,
    2 * 4,  # 8
    2 * 4 * 6,  # 48
    2 * 4 * 6 * 8,  # 384
    2 * 4 * 6 * 8 * 10,  # 3840
]
COMBINED_SCORE_MULTIPLIER_MAX = COMBINED_SCORE_MULTIPLIERS[5]

# todo: This is an idea for the future for slower scaling score multipliers.
#  The score multiplier extras would want to be enabled/disabled automatically as progressive score multiplier items are
#  received.
STEP_SCORE_MULTIPLIERS: Sequence[tuple[tuple[int, ...], int]] = [
    ((), 1),
    ((2,), 2),  # +1
    ((4,), 4),  # +2
    ((6,), 6),  # +2
    ((8,), 8),  # ((2, 4), 8),  # +2
    ((10,), 10),  # +2
    ((2, 6), 12),  # +2
    ((2, 8), 16),  # +4
    ((2, 10), 20),  # +4
    ((4, 6), 24),  # +4
    ((4, 8), 32),  # +8
    ((4, 10), 40),  # +8
    ((6, 8), 48),  # ((2, 4, 6), 48),  # +8
    ((6, 10), 60),  # Suggested to skip  # +12
    ((2, 4, 8), 64),  # +4 (no skip) or +16 (skip)
    ((8, 10), 80),  # ((2, 4, 10), 80),  # +16
    ((2, 6, 8), 96),  # +16
    ((2, 6, 10), 120),  # Suggested cutoff #1 at 16 multipliers with (6, 10) skipped.  # +24
    ((2, 8, 10), 160),  # +40
    ((4, 6, 8), 192),  # +32
    ((4, 6, 10), 240),  # +48
    ((4, 8, 10), 320),  # +80
    ((2, 4, 6, 8), 384),  # +64
    ((6, 8, 10), 480),  # ((2, 4, 6, 10), 480),  # +96
    ((2, 4, 8, 10), 640),  # +160
    ((2, 6, 8, 10), 960),  # +320
    ((4, 6, 8, 10), 1920),  # +960
    ((2, 4, 6, 8, 10), 3840),  # +1920
]


class AcquiredGeneric(ItemReceiver):
    receivable_ap_ids = RECEIVABLE_GENERIC_BY_AP_ID

    received_episode_unlocks: set[int]
    all_episodes_token_counts: int = 0
    progressive_score_count: int = 0

    def __init__(self):
        self.received_episode_unlocks = set()

    def init_from_slot_data(self, slot_data: dict[str, Any]) -> None:
        self.clear_received_items()

    def clear_received_items(self) -> None:
        self.received_episode_unlocks.clear()
        self.all_episodes_token_counts = 0
        self.progressive_score_count = 0

    @property
    def current_score_multiplier(self):
        idx = min(self.progressive_score_count, len(COMBINED_SCORE_MULTIPLIERS) - 1)
        return COMBINED_SCORE_MULTIPLIERS[idx]

    def receive_generic(self, ctx: TCSContext, ap_item_id: int):
        # Progressive Score Multiplier
        if ap_item_id == PROGRESSIVE_SCORE_MULTIPLIER:
            if self.progressive_score_count < len(SCORE_MULIPLIER_EXTRAS):
                ctx.acquired_extras.unlock_extra(SCORE_MULIPLIER_EXTRAS[self.progressive_score_count])
            self.progressive_score_count += 1
        # 'All Episodes' tokens
        elif ap_item_id == ALL_EPISODES_TOKEN:
            self.all_episodes_token_counts += 1
        # Episode Unlocks
        elif ap_item_id in EPISODE_UNLOCKS:
            self.received_episode_unlocks.add(EPISODE_UNLOCKS[ap_item_id])
            ctx.unlocked_chapter_manager.on_character_or_episode_unlocked(ap_item_id)
        else:
            logger.error("Unhandled ap_item_id %s for generic item", ap_item_id)

    async def update_game_state(self, ctx: TCSContext):
        # Bonus level doors unlock as per vanilla, which is having enough Gold Bricks.
        pass
