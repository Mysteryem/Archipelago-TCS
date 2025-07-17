import abc
from typing import Container

from ..common import ClientComponent
from ..type_aliases import TCSContext


class GameStateUpdater(ClientComponent):
    @abc.abstractmethod
    async def update_game_state(self, ctx: TCSContext) -> None: ...


class ItemReceiver(GameStateUpdater):
    @property
    @abc.abstractmethod
    def receivable_ap_ids(self) -> Container[int]:
        ...

    @abc.abstractmethod
    def clear_received_items(self) -> None:
        """Clear all received items, without clearing any settings."""
        ...
