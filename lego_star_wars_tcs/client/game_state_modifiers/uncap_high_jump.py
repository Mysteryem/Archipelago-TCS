from ..common import ClientComponent, StaticFloat
from ..events import subscribe_event, OnAreaChangeEvent, OnReceiveSlotDataEvent
from ..type_aliases import TCSContext


HIGH_JUMP_CAP = StaticFloat(0x802d94)


class UncapHighJump(ClientComponent):
    uncap_high_jump: bool = False

    def adjust_high_jump_cap(self, ctx: TCSContext):
        if self.uncap_high_jump:
            HIGH_JUMP_CAP.set(ctx, 1.14)

    @subscribe_event
    def on_receive_slot_data(self, event: OnReceiveSlotDataEvent):
        if event.generator_version < (1, 2, 0):
            # The option did not exist in older versions.
            self.uncap_high_jump = False
        else:
            self.uncap_high_jump = bool(event.slot_data["uncap_original_trilogy_high_jump"])
        self.adjust_high_jump_cap(event.context)

    @subscribe_event
    def on_area_change(self, event: OnAreaChangeEvent):
        self.adjust_high_jump_cap(event.context)
