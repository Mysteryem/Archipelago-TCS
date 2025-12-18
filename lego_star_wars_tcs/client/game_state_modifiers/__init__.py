import abc
from typing import Container

from ..common import ClientComponent


class ItemReceiver(ClientComponent):
    @property
    @abc.abstractmethod
    def receivable_ap_ids(self) -> Container[int]:
        ...

    @abc.abstractmethod
    def clear_received_items(self) -> None:
        """Clear all received items, without clearing any settings."""
        ...
