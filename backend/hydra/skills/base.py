from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseHydraSkill(ABC):
    @property
    @abstractmethod
    def skill_identifier(self) -> str:
        pass

    @abstractmethod
    async def execute(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        pass
