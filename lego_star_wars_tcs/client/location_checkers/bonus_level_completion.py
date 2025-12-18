import logging
from typing import Iterable

from ..type_aliases import MemoryAddress, ApLocationId, TCSContext, AreaId
from ...levels import BONUS_AREAS
from ...locations import LOCATION_NAME_TO_ID


debug_logger = logging.getLogger("TCS Debug")


ALL_STORY_COMPLETION_CHECKS: dict[AreaId, tuple[ApLocationId, MemoryAddress]] = {
    bonus.area_id: (LOCATION_NAME_TO_ID[bonus.completion_location_name], bonus.address + bonus.completion_offset)
    for bonus in BONUS_AREAS
}


class BonusAreaCompletionChecker:
    """
    Check if the player has completed a bonus Area by reading the completion byte of each bonus Area that has not
    already been completed according to the server.
    """
    # Anakin's Flight and A New Hope support Free Play, but the rest are Story mode only, for now, this class only
    # checks for story completion.
    remaining_story_completion_checks: dict[AreaId, tuple[ApLocationId, MemoryAddress]]

    def __init__(self):
        self.remaining_story_completion_checks = ALL_STORY_COMPLETION_CHECKS.copy()

    @staticmethod
    def update_from_datastorage(ctx: TCSContext, area_ids: Iterable[AreaId]):
        debug_logger.info("Updating Bonus Completion area_ids from datastorage: %s", area_ids)
        for area_id in area_ids:
            _ap_id, address = ALL_STORY_COMPLETION_CHECKS[area_id]
            ctx.write_byte(address, 1)

    async def check_completion(self, ctx: TCSContext, new_location_checks: list[int]):
        # As location checks get sent, the remaining bytes check to gets reduced.
        updated_remaining_story_completion_checks = {}
        write_to_datastorage_area_ids: list[AreaId] = []
        for area_id, (ap_id, address) in self.remaining_story_completion_checks.items():
            # Memory reads are assumed to be the slowest part
            if not ctx.is_location_unchecked(ap_id):
                # By skipping the location, it will not be added to the updated dictionary, so will not be checked in
                # the future.
                if ctx.is_location_sendable(ap_id):
                    write_to_datastorage_area_ids.append(area_id)
                    # Tell the goal manager it should update for newly completed bonuses.
                    ctx.goal_manager.tag_for_update("area")
                continue
            # It seems that the value is always `1` for a completed bonus and `0` otherwise. The client checks
            # truthiness in case it is possible that other bits could be set.
            if ctx.read_uchar(address):
                # The bonus has been completed, or viewed in the case of the Indiana Jones trailer.
                new_location_checks.append(ap_id)
            # Even if the location is being sent, it is still added to the updated dictionary in case the client loses
            # connection from the server.
            updated_remaining_story_completion_checks[area_id] = (ap_id, address)
        self.remaining_story_completion_checks = updated_remaining_story_completion_checks
        ctx.update_datastorage_bonuses_completion(write_to_datastorage_area_ids)

