import abc
from typing import Any

from .type_aliases import TCSContext


class ClientComponent(abc.ABC):
    @abc.abstractmethod
    def init_from_slot_data(self, ctx: TCSContext, slot_data: dict[str, Any]) -> None: ...
