import abc

from ..common import ClientComponent
from ..type_aliases import TCSContext


class LocationChecker(ClientComponent):
    @abc.abstractmethod
    async def check_completion(self, ctx: TCSContext, new_location_checks: list[int]): ...