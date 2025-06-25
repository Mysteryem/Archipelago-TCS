import logging
from typing import Mapping


from ..type_aliases import TCSContext
from ...items import GENERIC_BY_NAME


logger = logging.getLogger("Client")


# TODO: We should add to the in-level studs instead, additionally adding to the True Jedi meter. If the player exits
#  without saving, then they will enter the Cantina and receive the Studs there instead, so they cannot abuse exiting
#  without saving re-giving them the studs, which would have otherwise allowed for entering another level and getting
#  the True Jedi progress there.
# Note, this is not the in-level stud count. We don't add to that, because it is not saved.
STUD_COUNT_ADDRESS = 0x86E4DC
MAX_STUD_COUNT = 4_000_000_000


STUDS_AP_ID_TO_VALUE: Mapping[int, int] = {
    # For when additional Stud items are added.
    # GENERIC_BY_NAME["Silver Stud"].code: 10
    # GENERIC_BY_NAME["Gold Stud"].code: 100
    # GENERIC_BY_NAME["Blue Stud"].code: 1000
    GENERIC_BY_NAME["Purple Stud"].code: 10000
}


def give_studs(ctx: TCSContext, ap_item_id: int):
    """
    Grant Studs to the player. Unlike other items, Studs are a consumable resource, so cannot simply be set to the
    number of received studs and instead must use the last/next item index from AP to determine when a Studs item is
    newly received by the current save file.
    """
    studs_to_add = STUDS_AP_ID_TO_VALUE.get(ap_item_id)
    if studs_to_add is None:
        logger.warning("Tried to receive unknown Studs item with item ID %i", ap_item_id)
        return

    # Multiply by the player's current maximum score multiplier.
    studs_to_add *= ctx.acquired_generic.current_score_multiplier

    current_stud_count = ctx.read_uint(STUD_COUNT_ADDRESS)
    new_stud_count = min(current_stud_count + studs_to_add, MAX_STUD_COUNT)
    ctx.write_uint(STUD_COUNT_ADDRESS, new_stud_count)
