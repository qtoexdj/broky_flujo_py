"""Base helpers que comparten todos los agentes LangChain del proyecto."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

from langchain_core.runnables import Runnable

from broky.core import BrokyContext

logger = logging.getLogger(__name__)


class BrokyAgent(ABC):
    """Interfaz mínima para agentes ejecutados desde LangGraph."""

    def __init__(self, *, runnable: Runnable) -> None:
        self._runnable = runnable

    @abstractmethod
    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        """Transforma el contexto compartido en payload para LangChain."""

    @abstractmethod
    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        """Mapea la respuesta del agent executor de vuelta al contexto."""

    def invoke(self, context: BrokyContext) -> BrokyContext:
        payload = self.build_input(context)
        logger.debug("Ejecutando agente %s con payload=%s", self.__class__.__name__, payload)
        result = self._runnable.invoke(payload)
        return self.handle_output(context, result)
