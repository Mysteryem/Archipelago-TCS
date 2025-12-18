import logging
from typing import Mapping

from ..events import subscribe_event, OnReceiveSlotDataEvent
from ..type_aliases import TCSContext
from ...items import MINIKITS_BY_COUNT
from . import ItemReceiver

MINIKIT_ITEMS: Mapping[int, int] = {item.code: count for count, item in MINIKITS_BY_COUNT.items()}

logger = logging.getLogger("Client")


class AcquiredMinikits(ItemReceiver):
    receivable_ap_ids = MINIKIT_ITEMS

    minikit_count: int

    def __init__(self):
        self.minikit_count = 0

    @subscribe_event
    def init_from_slot_data(self, _event: OnReceiveSlotDataEvent) -> None:
        self.clear_received_items()

    def clear_received_items(self) -> None:
        self.minikit_count = 0

    def receive_minikit(self, ctx: TCSContext, ap_item_id: int):
        # Minikits
        if ap_item_id in MINIKIT_ITEMS:
            self.minikit_count += MINIKIT_ITEMS[ap_item_id]
            ctx.goal_manager.tag_for_update("minikit")
        else:
            logger.error("Unhandled ap_item_id %s for generic item", ap_item_id)
