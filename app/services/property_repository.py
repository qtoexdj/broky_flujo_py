from __future__ import annotations

import logging
from typing import Any, Dict, List

from supabase import Client

logger = logging.getLogger(__name__)


class PropertyRepository:
    """Helpers to fetch properties associated to a prospect."""

    def __init__(
        self,
        client: Client,
        *,
        rpc_name: str = "get_properties_for_prospect",
    ) -> None:
        self._client = client
        self._rpc_name = rpc_name

    def list_by_prospect(self, prospect_id: str) -> List[Dict[str, Any]]:
        """Return property records linked to the given prospect.

        The repository first attempts to call an RPC (default
        `get_properties_for_prospect`). If the RPC is not present or fails,
        an empty list is returned so the upstream flow can continue.
        """

        try:
            response = self._client.rpc(
                self._rpc_name, {"prospect_id": prospect_id}
            ).execute()
        except Exception:  # pragma: no cover - log but avoid crashing the flow
            logger.warning(
                "No se pudo ejecutar el RPC %s para prospecto %s",
                self._rpc_name,
                prospect_id,
                exc_info=True,
            )
            return []

        data = getattr(response, "data", None)
        if isinstance(data, list):
            return data

        if data is None:
            return []

        logger.debug(
            "Respuesta inesperada del RPC %s para prospecto %s: %s",
            self._rpc_name,
            prospect_id,
            data,
        )
        return []
