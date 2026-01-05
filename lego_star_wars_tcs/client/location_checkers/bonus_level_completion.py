import logging
from typing import Iterable

from ..common import ClientComponent
from ..events import subscribe_event, OnReceiveSlotDataEvent
from ..type_aliases import MemoryAddress, ApLocationId, TCSContext, AreaId
from ...levels import BONUS_AREAS, BONUS_NAME_TO_BONUS_AREA
from ...locations import LOCATION_NAME_TO_ID


debug_logger = logging.getLogger("TCS Debug")


ALL_STORY_COMPLETION_CHECKS: dict[AreaId, tuple[ApLocationId, MemoryAddress]] = {
    bonus.area_id: (LOCATION_NAME_TO_ID[bonus.completion_location_name], bonus.address + bonus.completion_offset)
    for bonus in BONUS_AREAS
}


class BonusAreaCompletionChecker(ClientComponent):
    """
    Check if the player has completed a bonus Area by reading the completion byte of each bonus Area that has not
    already been completed according to the server.
    """
    # Anakin's Flight and A New Hope support Free Play, but the rest are Story mode only, for now, this class only
    # checks for story completion.
    remaining_story_completion_checks: dict[AreaId, tuple[ApLocationId, MemoryAddress]]
    remaining_bonus_area_completion_locations: dict[AreaId, list[ApLocationId]]

    def __init__(self):
        self.remaining_story_completion_checks = ALL_STORY_COMPLETION_CHECKS.copy()
        self.remaining_bonus_area_completion_locations = {}

    @subscribe_event
    def init_from_slot_data(self, event: OnReceiveSlotDataEvent) -> None:
        if event.generator_version < (1, 3, 0):
            self.remaining_bonus_area_completion_locations = {}
        else:
            bonus_area_completion_locations = {}
            for bonus_name in event.slot_data["enabled_bonuses"]:
                bonus_area = BONUS_NAME_TO_BONUS_AREA[bonus_name]
                loc_ids = [LOCATION_NAME_TO_ID[f"Level Completion - Unlock {character}"]
                           for character in bonus_area.story_characters]
                server_locations = event.context.server_locations
                bonus_area_completion_locations[bonus_area.area_id] = list(filter(server_locations.__contains__, loc_ids))
            self.remaining_bonus_area_completion_locations = bonus_area_completion_locations

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

        updated_remaining_bonus_area_completion_locations = {}
        for area_id, ap_ids in self.remaining_bonus_area_completion_locations.items():
            area_completed_or_disabled = area_id not in updated_remaining_story_completion_checks
            if area_completed_or_disabled:
                # Send the locations to AP, and skip adding the `area_id` key into
                # `updated_remaining_bonus_area_completion_locations`.
                # It does not matter if the locations do not exist, they will get filtered out before being sent to the
                # server.
                new_location_checks.extend(ap_ids)
            else:
                updated_remaining_bonus_area_completion_locations[area_id] = ap_ids

        self.remaining_story_completion_checks = updated_remaining_story_completion_checks
        self.remaining_bonus_area_completion_locations = updated_remaining_bonus_area_completion_locations
        ctx.update_datastorage_bonuses_completion(write_to_datastorage_area_ids)

