from typing import TYPE_CHECKING

"""
Aliases for clarity in typing.
"""


if TYPE_CHECKING:
    from ..client import LegoStarWarsTheCompleteSagaContext as TCSContext  # type: ignore
else:
    TCSContext = object


# Memory
MemoryAddress = int
MemoryOffset = int
BitMask = int

# Internal TCS IDs
LevelId = int
AreaId = int
CharacterId = int

# Archipelago.
ApLocationId = int
ApItemId = int
