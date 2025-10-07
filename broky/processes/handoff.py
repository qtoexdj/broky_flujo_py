"""Processes that handle human handoff and user opt-out."""

from __future__ import annotations

from typing import Dict


def process_contact_request(metadata: Dict[str, any]) -> str:
    reply = "He contactado a un asesor humano para que te apoye. Te escribirán en breve."
    metadata["handoff_required"] = True
    metadata["handoff_reason"] = "contacto_humano"
    return reply


def process_user_opt_out(metadata: Dict[str, any]) -> str:
    reply = "Entiendo, detendré los mensajes automáticos. Si necesitas algo más, estaré atento."
    metadata["handoff_required"] = True
    metadata["handoff_reason"] = "desinteres"
    metadata["automation_allowed"] = False
    return reply
