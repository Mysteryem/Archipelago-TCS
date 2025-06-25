import abc
from typing import Container

from ..type_aliases import TCSContext


class GameStateUpdater(abc.ABC):
    @abc.abstractmethod
    async def update_game_state(self, ctx: TCSContext) -> None: ...


class ItemReceiver(GameStateUpdater):
    @property
    @abc.abstractmethod
    def receivable_ap_ids(self) -> Container[int]: ...
