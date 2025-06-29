from ..type_aliases import MemoryAddress, ApLocationId, TCSContext
from ...levels import BONUS_AREAS
from ...locations import LOCATION_NAME_TO_ID


ALL_STORY_COMPLETION_CHECKS: dict[MemoryAddress, ApLocationId] = {
    bonus.address + bonus.completion_offset: LOCATION_NAME_TO_ID[bonus.name] for bonus in BONUS_AREAS
}


class BonusAreaCompletionChecker:
    """
    Check if the player has completed a bonus Area by reading the completion byte of each bonus Area that has not
    already been completed according to the server.
    """
    # Anakin's Flight and A New Hope support Free Play, but the rest are Story mode only, for now, this class only
    # checks for story completion.
    remaining_story_completion_checks: dict[MemoryAddress, ApLocationId]

    def __init__(self):
        self.remaining_story_completion_checks = ALL_STORY_COMPLETION_CHECKS.copy()

    async def check_completion(self, ctx: TCSContext, new_location_checks: list[int]):
        # As location checks get sent, the remaining bytes check to gets reduced.
        updated_remaining_story_completion_checks = {}
        for address, ap_id in self.remaining_story_completion_checks.items():
            # Memory reads are assumed to be the slowest part
            if not ctx.is_location_sendable(ap_id):
                # By skipping the location, it will not be added to the updated dictionary, so will not be checked in
                # the future.
                continue
            # It seems that the value is always `1` for a completed bonus and `0` otherwise. The client checks
            # truthiness in case it is possible that other bits could be set.
            if ctx.read_uchar(address):
                # The bonus has been completed, or viewed in the case of the Indiana Jones trailer.
                new_location_checks.append(ap_id)
            # Even if the location is being sent, it is still added to the updated dictionary in case the client loses
            # connection from the server.
            updated_remaining_story_completion_checks[address] = ap_id
        self.remaining_story_completion_checks = updated_remaining_story_completion_checks
