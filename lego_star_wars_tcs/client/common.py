import abc
from typing import Any


class ClientComponent(abc.ABC):
    @abc.abstractmethod
    def init_from_slot_data(self, slot_data: dict[str, Any]) -> None: ...
