"""Entrypoints para construir grafos LangGraph actualizados."""

from typing import Protocol


class GraphBuilder(Protocol):
    """Contrato mínimo para factories que crean StateGraph/RouterGraph."""

    def __call__(self, *args, **kwargs):
        ...
