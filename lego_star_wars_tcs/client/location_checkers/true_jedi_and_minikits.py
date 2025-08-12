from typing import Iterable, Any

from . import ClientComponent
from ..type_aliases import TCSContext
from ...levels import SHORT_NAME_TO_CHAPTER_AREA, AREA_ID_TO_CHAPTER_AREA, ChapterArea
from ...locations import LEVEL_COMMON_LOCATIONS, LOCATION_NAME_TO_ID


ALL_GAME_AREA_SHORTNAMES: tuple[str, ...] = tuple(LEVEL_COMMON_LOCATIONS.keys())
# Suppress PyCharm typing bug.
# PyCharm gets the typing correct when doing `tuple(list(enumerate(data["Minikits"], start=1)))`, which evaluate to the
# same type.
# noinspection PyTypeChecker
ALL_MINIKIT_CHECKS_BY_SHORTNAME: dict[str, list[tuple[int, str]]] = {
    name: tuple(enumerate(data["Minikits"], start=1)) for name, data in LEVEL_COMMON_LOCATIONS.items()
}


# It looks like AREA IDs tend to use 4 bytes, even though they only need 1 byte.
CURRENT_AREA_ADDRESS = 0x7fd2c1
CURRENT_AREA_MINIKIT_COUNT_ADDRESS = 0x951238
# There is a second address, but I don't know what the difference is. This address remains non-zero for longer when
# exiting a level.
# CURRENT_AREA_MINIKIT_COUNT_ADDRESS2 = 0x951230
# The number of minikits found in this current session is also found in this same memory area.
# CURRENT_AREA_CURRENT_SESSION_MINIKIT_COUNT_ADDRESS = 0x951234
# There is an array of found Minikits in the current session. Each element of the array includes the Minikit's internal
# name and the Level ID the Minikit was found in. Minikit names can be shared by multiple Levels within an Area, so the
# Level ID is necessary to differentiate them.
# Each Minikit name is an 8-character null-terminated string.
# Each Level ID is a 2-byte integer (probably)
# There are then 2 unknown bytes
# CURRENT_AREA_CURRENT_SESSION_MINIKIT_ARRAY = 0x955FD0

# Set to 1 when True Jedi is completed, in either Story mode or Free Play, 0 otherwise.
CURRENT_AREA_TRUE_JEDI_COMPLETE_STORY_OR_FREE_PLAY_ADDRESS = 0x87B980
# There is a second byte that only gets set from Free Play.
# Completing True Jedi in either Story or Free Play sets both True Jedi bytes in the save data, so there is not much
# point in only sending in-level True Jedi from Free Play mode, when the player could 'cheat' and do it in Story mode
# instead.
# CURRENT_AREA_TRUE_JEDI_COMPLETE_FREE_PLAY_ONLY_ADDRESS = 0x87B996


class TrueJediAndMinikitChecker(ClientComponent):
    """
    Check if the player has completed True Jedi for each level and check how many Minikit canisters the player has
    collected in each level.

    It is possible to check the number of Minikit canisters the player has collected in the current level they are in,
    so that Minikit checks send in realtime, but the intention is to make each Minikit a separate check with separate
    logic, which will require a rewrite anyway, so only updating collected Minikits by reading the in-memory save file
    data is good enough before the rewrite.

    Realtime checks are better for if there are receivable items, in the future, that affect the player while in a
    level. Realtime checks are also better for the case of another player in the multiworld waiting for a Minikit check
    to resume playing because the TCS player currently has to choose between either exiting the level early to send the
    check, but then having to replay the level for additional checks, or taking longer to send the check by only sending
    the check once the level has been completed.
    """
    # Sequence and Mapping are used because they hint that the types are immutable.
    remaining_true_jedi_check_shortnames: set[str]
    remaining_minikit_checks_by_shortname: dict[str, list[tuple[int, str]]]
    remaining_minikit_gold_bricks_by_area_id: set[int]
    remaining_power_bricks_by_area_id: set[int]

    def __init__(self):
        # Set to empty collections for safety.
        self.remaining_true_jedi_check_shortnames = set()
        self.remaining_minikit_checks_by_shortname = {}
        self.remaining_minikit_gold_bricks_by_area_id = set()
        self.remaining_power_bricks_by_area_id = set()

    def init_from_slot_data(self, ctx: TCSContext, slot_data: dict[str, Any]) -> None:
        enabled_shortnames = set(slot_data["enabled_chapters"])
        self.remaining_true_jedi_check_shortnames = enabled_shortnames.copy()
        self.remaining_minikit_checks_by_shortname = {shortname: ALL_MINIKIT_CHECKS_BY_SHORTNAME[shortname]
                                                      for shortname in enabled_shortnames}
        self.remaining_minikit_gold_bricks_by_area_id = {
            SHORT_NAME_TO_CHAPTER_AREA[shortname].area_id for shortname in enabled_shortnames
        }
        self.remaining_power_bricks_by_area_id = {
            SHORT_NAME_TO_CHAPTER_AREA[shortname].area_id for shortname in enabled_shortnames
        }

    async def check_true_jedi_and_minikits(self, ctx: TCSContext, new_location_checks: list[int]):
        current_area_id = ctx.read_uchar(CURRENT_AREA_ADDRESS)
        true_jedi_datastorage_area_ids_to_update = []
        if current_area_id in AREA_ID_TO_CHAPTER_AREA:
            current_area = AREA_ID_TO_CHAPTER_AREA[current_area_id]
            self._check_minikits_from_current_area(current_area, ctx, new_location_checks)
            if self._check_true_jedi_from_current_area(current_area, ctx, new_location_checks):
                true_jedi_datastorage_area_ids_to_update.append(current_area_id)

        new_true_jedi_from_sava_data = self._check_true_jedi_power_bricks_and_minikits_from_save_data(
            ctx, new_location_checks)
        true_jedi_datastorage_area_ids_to_update.extend(new_true_jedi_from_sava_data)
        ctx.update_datastorage_true_jedi_completion(true_jedi_datastorage_area_ids_to_update)

    def _check_true_jedi_from_current_area(self,
                                           current_area: ChapterArea,
                                           ctx: TCSContext,
                                           new_location_checks: list[int]
                                           ) -> bool:
        shortname = current_area.short_name
        if shortname not in self.remaining_true_jedi_check_shortnames:
            return False

        location_name = LEVEL_COMMON_LOCATIONS[shortname]["True Jedi"]
        location_id = LOCATION_NAME_TO_ID[location_name]
        if ctx.is_location_sendable(location_id):
            current_area_true_jedi_complete = ctx.read_uint(
                CURRENT_AREA_TRUE_JEDI_COMPLETE_STORY_OR_FREE_PLAY_ADDRESS)
            if current_area_true_jedi_complete:
                self.remaining_true_jedi_check_shortnames.remove(shortname)
                # The location may already be checked due to a !collect, however, already checked locations get
                # filtered out automatically.
                new_location_checks.append(location_id)
                return True
            # The True Jedi is still incomplete, so the client will need to continue polling until the True Jedi is
            # completed in-game. It is important to keep polling even when the location has been checked due to a
            # !collect because completing True Jedi gives a Gold Brick, which should only be given to the player when
            # True Jedi has actually been completed.
            # When True Jedi has actually been completed, it will update datastorage, telling other TCS clients
            # connected to the same slot that they should award the True Jedi Gold Brick. This is important for
            # supporting same-slot co-op.
            return False
        else:
            # The location is not sendable, so the client can forget about polling for this True Jedi location from now
            # on.
            # Note that this means that True Jedi completion does not sync in same-slot co-op when True Jedi locations
            # are disabled.
            self.remaining_true_jedi_check_shortnames.remove(shortname)
            return False

    def _check_minikits_from_current_area(self,
                                          current_area: ChapterArea,
                                          ctx: TCSContext,
                                          new_location_checks: list[int]):
        shortname = current_area.short_name
        if shortname not in self.remaining_minikit_checks_by_shortname:
            return

        remaining_minikits = self.remaining_minikit_checks_by_shortname[shortname]

        not_checked_minikit_checks: list[int] = []
        updated_remaining_minikits: list[tuple[int, str]] = []
        for count, location_name in remaining_minikits:
            location_id = LOCATION_NAME_TO_ID[location_name]
            if ctx.is_location_unchecked(location_id):
                not_checked_minikit_checks.append(location_id)
                updated_remaining_minikits.append((count, location_name))
        if updated_remaining_minikits:
            self.remaining_minikit_checks_by_shortname[shortname] = updated_remaining_minikits

            minikit_count = ctx.read_uchar(CURRENT_AREA_MINIKIT_COUNT_ADDRESS)
            zipped = zip(updated_remaining_minikits, not_checked_minikit_checks, strict=True)
            for (count, _name), location_id in zipped:
                if minikit_count >= count:
                    new_location_checks.append(location_id)
        else:
            del self.remaining_minikit_checks_by_shortname[shortname]

    @staticmethod
    def update_from_datastorage(ctx: TCSContext,
                                new_true_jedi_area_ids: Iterable[int] = (),
                                new_minikits_gold_brick_area_ids: Iterable[int] = (),
                                new_power_brick_area_ids: Iterable[int] = ()):
        # todo: Replace the magic numbers used to get addresses, or at least move them to ChapterArea.
        for area_id in new_true_jedi_area_ids:
            area = AREA_ID_TO_CHAPTER_AREA[area_id]
            true_jedi_address = area.address + 3
            ctx.write_byte(true_jedi_address, 1)
        for area_id in new_minikits_gold_brick_area_ids:
            area = AREA_ID_TO_CHAPTER_AREA[area_id]
            gold_brick_address = area.address + 4
            ctx.write_byte(gold_brick_address, 1)
        for area_id in new_power_brick_area_ids:
            area = AREA_ID_TO_CHAPTER_AREA[area_id]
            power_brick_address = area.address + 6
            ctx.write_byte(power_brick_address, 1)

    def _check_true_jedi_power_bricks_and_minikits_from_save_data(self, ctx: TCSContext, new_location_checks: list[int]
                                                                  ) -> list[int]:
        # todo: More smartly read only as many bytes as necessary. So only 1 byte when either the True Jedi is complete
        #  or all Minikits have been collected.
        # todo: Use a NamedTuple instead of tuple[int, int, int, int]
        cached_bytes: dict[str, tuple[int, int, int, int]] = {}

        def get_bytes_for_short_name(short_name: str):
            if short_name in cached_bytes:
                return cached_bytes[short_name]
            else:
                # True Jedi seems to be at the 4th byte (maybe it is the 3rd because they both get activated?), 10/10
                # Minikits Gold Brick is at the 5th byte, and Minikit count is at the 6th byte. To reduce memory reads,
                # all are retrieved simultaneously.
                #
                read_bytes = ctx.read_bytes(SHORT_NAME_TO_CHAPTER_AREA[short_name].address + 3, 4)
                true_jedi_byte = read_bytes[0]
                minikit_gold_brick = read_bytes[1]
                minikit_count_byte = read_bytes[2]
                power_brick_byte = read_bytes[3]
                new_bytes = (true_jedi_byte, minikit_gold_brick, minikit_count_byte, power_brick_byte)
                cached_bytes[short_name] = new_bytes
                return new_bytes

        checked_true_jedi_area_ids = []
        # A copy has to be iterated so that elements can be removed while iterating.
        for shortname in tuple(self.remaining_true_jedi_check_shortnames):
            location_name = LEVEL_COMMON_LOCATIONS[shortname]["True Jedi"]
            location_id = LOCATION_NAME_TO_ID[location_name]
            if not ctx.is_location_unchecked(location_id):
                self.remaining_true_jedi_check_shortnames.remove(shortname)
                area_id = SHORT_NAME_TO_CHAPTER_AREA[shortname].area_id
                if ctx.is_location_sendable(location_id):
                    checked_true_jedi_area_ids.append(area_id)
                continue
            true_jedi = get_bytes_for_short_name(shortname)[0]
            if true_jedi:
                new_location_checks.append(location_id)

        updated_remaining_minikit_checks_by_shortname: dict[str, list[tuple[int, str]]] = {}
        for shortname, remaining_minikits in self.remaining_minikit_checks_by_shortname.items():
            not_checked_minikit_checks: list[int] = []
            updated_remaining_minikits: list[tuple[int, str]] = []
            for count, location_name in remaining_minikits:
                location_id = LOCATION_NAME_TO_ID[location_name]
                if ctx.is_location_unchecked(location_id):
                    not_checked_minikit_checks.append(location_id)
                    updated_remaining_minikits.append((count, location_name))
            if updated_remaining_minikits:
                updated_remaining_minikit_checks_by_shortname[shortname] = updated_remaining_minikits

                minikit_count = get_bytes_for_short_name(shortname)[2]
                zipped = zip(updated_remaining_minikits, not_checked_minikit_checks, strict=True)
                for (count, _name), location_id in zipped:
                    if minikit_count >= count:
                        new_location_checks.append(location_id)
        self.remaining_minikit_checks_by_shortname = updated_remaining_minikit_checks_by_shortname

        # There are no locations tied to getting the Gold Brick for collecting all Minikits in a Chapter, but the Gold
        # Bricks are written to datastorage to sync Gold Bricks in same-slot co-op, and so that the PopTracker pack can
        # determine how many, and which Gold Bricks have been acquired.
        newly_completed_10_minikits_gold_bricks_area_ids: list[int] = []
        updated_remaining_minikit_gold_bricks_by_area_id: set[int] = set()
        for area_id in self.remaining_minikit_gold_bricks_by_area_id:
            shortname = AREA_ID_TO_CHAPTER_AREA[area_id].short_name
            gold_brick = get_bytes_for_short_name(shortname)[1]
            if gold_brick:
                newly_completed_10_minikits_gold_bricks_area_ids.append(area_id)
            else:
                updated_remaining_minikit_gold_bricks_by_area_id.add(area_id)
        ctx.update_datastorage_10_minikits_completion(newly_completed_10_minikits_gold_bricks_area_ids)
        self.remaining_minikit_gold_bricks_by_area_id = updated_remaining_minikit_gold_bricks_by_area_id

        newly_completed_power_brick_area_ids: list[int] = []
        updated_remaining_power_bricks_by_area_id: set[int] = set()
        for area_id in self.remaining_power_bricks_by_area_id:
            shortname = AREA_ID_TO_CHAPTER_AREA[area_id].short_name
            power_brick = get_bytes_for_short_name(shortname)[3]
            if power_brick:
                newly_completed_power_brick_area_ids.append(area_id)
            else:
                updated_remaining_power_bricks_by_area_id.add(area_id)
        ctx.update_datastorage_power_bricks_collected(newly_completed_power_brick_area_ids)
        self.remaining_power_bricks_by_area_id = updated_remaining_power_bricks_by_area_id

        return checked_true_jedi_area_ids
