import abc

from ..common_addresses import CHARACTERS_SHOP_START, EXTRAS_SHOP_START
from ..type_aliases import MemoryAddress, MemoryOffset, BitMask, ApLocationId, TCSContext
from ...items import CHARACTERS_AND_VEHICLES_BY_NAME, EXTRAS_BY_NAME
from ...locations import LOCATION_NAME_TO_ID


class BasePurchasesChecker(abc.ABC):
    remaining_purchases: dict[MemoryOffset, dict[BitMask, ApLocationId]]

    @property
    @abc.abstractmethod
    def shop_address(self) -> MemoryAddress: ...

    @property
    @abc.abstractmethod
    def shop_offsets_to_ap_location_ids(self) -> dict[MemoryOffset, dict[BitMask, ApLocationId]]: ...

    def __init__(self):
        self.remaining_purchases = {byte_offset: bit_mask_to_ap_id.copy() for byte_offset, bit_mask_to_ap_id
                                    in self.shop_offsets_to_ap_location_ids.items()}
        self.remaining_min_byte = min(self.remaining_purchases.keys())
        self.remaining_max_byte = max(self.remaining_purchases.keys())

    async def check_extra_purchases(self, ctx: TCSContext, new_location_checks: list[int]):
        updated_remaining_purchases: dict[MemoryOffset, dict[BitMask, ApLocationId]] = {}
        for byte_offset, bit_mask_to_ap_id in self.remaining_purchases.items():
            updated_bit_to_ap_id: dict[BitMask, ApLocationId] = {bit: ap_id for bit, ap_id in bit_mask_to_ap_id.items()
                                                                 if ctx.is_location_sendable(ap_id)}
            if updated_bit_to_ap_id:
                updated_remaining_purchases[byte_offset] = updated_bit_to_ap_id

        if updated_remaining_purchases:
            min_byte_offset = min(updated_remaining_purchases.keys())
            max_byte_offset = max(updated_remaining_purchases.keys())
            num_bytes = max_byte_offset - min_byte_offset + 1
            characters_shop_bytes = ctx.read_bytes(self.shop_address + min_byte_offset, num_bytes)

            for byte_offset, bit_mask_to_ap_id in updated_remaining_purchases.items():
                shop_byte = characters_shop_bytes[byte_offset - min_byte_offset]
                for bit_mask, ap_id in bit_mask_to_ap_id.items():
                    if shop_byte & bit_mask:
                        new_location_checks.append(ap_id)
        self.remaining_purchases = updated_remaining_purchases


def _characters_to_shop_address() -> dict[MemoryOffset, dict[BitMask, ApLocationId]]:
    per_byte: dict[MemoryOffset, dict[BitMask, ApLocationId]] = {}
    for character in CHARACTERS_AND_VEHICLES_BY_NAME.values():
        if character.shop_slot == -1:
            # Not present in the shop.
            continue
        if character.code == -1:
            # Not implemented yet.
            continue
        byte_offset = character.shop_slot // 8
        bit_mask = 1 << (character.shop_slot % 8)
        location_name = f"Purchase {character.name}"
        assert location_name in LOCATION_NAME_TO_ID, f"ERROR: {location_name} is not a location name"
        location_id = LOCATION_NAME_TO_ID[location_name]
        per_byte.setdefault(byte_offset, {})[bit_mask] = location_id
    return per_byte


def _extras_to_shop_address() -> dict[MemoryOffset, dict[BitMask, ApLocationId]]:
    """Purchase <extra> shop ID -> AP Location ID"""
    per_byte: dict[MemoryOffset, dict[BitMask, ApLocationId]] = {}
    for extra_data in EXTRAS_BY_NAME.values():
        if extra_data.name == "Adaptive Difficulty":
            # Not present in the shop because it is always unlocked. It is also fortunately found in memory after all
            # the purchasable Extras, so there is no awkward skipping of memory to skip over Adaptive Difficulty.
            continue
        if extra_data.code == -1:
            # Not implemented yet.
            continue
        byte_offset = extra_data.extra_number // 8
        bit_mask = 1 << (extra_data.extra_number % 8)
        if extra_data.level_shortname is not None:
            location_name = f"Purchase {extra_data.name} ({extra_data.level_shortname})"
        else:
            # Not relevant currently because only the Extras unlocked through Power Bricks are implemented as
            # Archipelago items currently.
            location_name = f"Purchase {extra_data.name}"
        assert location_name in LOCATION_NAME_TO_ID, f"ERROR: {location_name} is not a location name"
        location_id = LOCATION_NAME_TO_ID[location_name]
        per_byte.setdefault(byte_offset, {})[bit_mask] = location_id
    return per_byte


class PurchasedCharactersChecker(BasePurchasesChecker):
    shop_offsets_to_ap_location_ids = _characters_to_shop_address()
    shop_address = CHARACTERS_SHOP_START


class PurchasedExtrasChecker(BasePurchasesChecker):
    shop_offsets_to_ap_location_ids = _extras_to_shop_address()
    shop_address = EXTRAS_SHOP_START
