import abc

from ..type_aliases import TCSContext


class LocationChecker(abc.ABC):
    @abc.abstractmethod
    async def check_completion(self, ctx: TCSContext, new_location_checks: list[int]): ...