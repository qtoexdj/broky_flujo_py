from __future__ import annotations

import logging
from operator import add
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.services.project_repository import ProjectRepository
from app.services.prospect_repository import ProspectRepository
from app.services.realtor_repository import RealtorRepository
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class InboundState(TypedDict, total=False):
    payload: Dict[str, Any]
    logs: Annotated[List[str], add]
    normalized: Dict[str, Any]
    realtor: Optional[Dict[str, Any]]
    prospect: Optional[Dict[str, Any]]
    prospect_exists: bool
    created_prospect: bool
    properties_interested: List[Dict[str, Any]]
    mentioned_properties: List[Any]
    automation_allowed: bool
    handoff_required: bool
    handoff_reason: Optional[str]


def build_inbound_workflow(settings: Settings):
    client = get_supabase_client(settings)
    if client is None:
        raise RuntimeError("Supabase client no disponible; verifica las credenciales")

    realtor_repo = RealtorRepository(client)
    prospect_repo = ProspectRepository(client)
    project_repo = ProjectRepository(client)

    graph = StateGraph(InboundState)

    def init_payload(state: InboundState) -> InboundState:
        payload = state.get("payload")
        if not payload:
            raise ValueError("El estado inicial debe incluir 'payload'")

        logs = ["payload recibido"]
        return {
            "logs": logs,
            "automation_allowed": True,
            "handoff_required": False,
        }

    def fetch_realtor(state: InboundState) -> InboundState:
        payload = state["payload"]
        metadata = payload.get("metadata") or {}
        channel_id = payload.get("channel_id") or metadata.get("channel_id")
        realtor = None
        if channel_id:
            realtor = realtor_repo.get_by_channel_id(str(channel_id))
            logger.debug("Realtor encontrado para channel_id=%s: %s", channel_id, bool(realtor))
        else:
            logger.warning("Payload sin channel_id")

        normalized = state.get("normalized", {}).copy()
        normalized["realtor"] = realtor
        if realtor:
            if not normalized.get("realtor_id") and realtor.get("id"):
                normalized["realtor_id"] = realtor.get("id")
            normalized["realtor_bot"] = {
                "name": realtor.get("bot_name"),
                "personality": realtor.get("bot_personality"),
                "tone": realtor.get("bot_tone"),
            }
            if (not normalized.get("followup_configuration") and realtor.get("followups_prospects")):
                normalized["followup_configuration"] = realtor.get("followups_prospects")
            if (not normalized.get("notifications_brokers_configurations") and realtor.get("followups_brokers")):
                normalized["notifications_brokers_configurations"] = realtor.get("followups_brokers")
            if not normalized.get("id_vector_project") and normalized.get("realtor_id"):
                slug = str(realtor.get("name") or "").replace(" ", "_")
                safe_uuid = str(normalized["realtor_id"]).replace("-", "_")
                if slug and safe_uuid:
                    normalized["id_vector_project"] = f"vector_projects_{slug}_{safe_uuid}"

        return {
            "realtor": realtor,
            "logs": [f"realtor: {'sí' if realtor else 'no'}"],
            "normalized": normalized,
        }

    def normalize_payload(state: InboundState) -> InboundState:
        payload = state["payload"]
        logger.info("Normalizando payload inbound: %s", payload)
        metadata = payload.get("metadata") or {}

        telephone = (
            payload.get("telephone")
            or metadata.get("telephone")
            or payload.get("from")
        )
        channel_id = payload.get("channel_id") or metadata.get("channel_id")
        chat_id = payload.get("chat_id") or metadata.get("chat_id")
        name = payload.get("name") or metadata.get("name")
        session_id = payload.get("session_id") or metadata.get("session_id")

        normalized = {
            "realtor_id": payload.get("realtor_id") or metadata.get("realtor_id"),
            "telephone": telephone,
            "session_id": session_id,
            "name": name,
            "channel_id": channel_id,
            "chat_id": chat_id,
            "message": payload.get("message"),
            "followup_configuration": payload.get("followup_configuration")
            or metadata.get("followup_configuration")
            or [],
            "notifications_brokers_configurations": payload.get(
                "notifications_brokers_configurations"
            )
            or metadata.get("notifications_brokers_configurations")
            or {},
            "id_vector_project": payload.get("id_vector_project")
            or metadata.get("id_vector_project"),
            "realtor": payload.get("realtor") or metadata.get("realtor"),
        }

        if not normalized.get("session_id"):
            if normalized.get("realtor_id") and telephone:
                normalized["session_id"] = f"{telephone}:{normalized['realtor_id']}"
            elif chat_id:
                normalized["session_id"] = chat_id

        # Si no llega un identificador de vector predefinido, replicamos la
        # convención usada en el flujo original de n8n.
        if not normalized.get("id_vector_project") and normalized.get("realtor_id"):
            realtor_name = (payload.get("realtor") or metadata.get("realtor") or {}).get(
                "name"
            )
            realtor_uuid = normalized["realtor_id"]
            if realtor_name and realtor_uuid:
                slug = str(realtor_name).replace(" ", "_")
                safe_uuid = str(realtor_uuid).replace("-", "_")
                normalized["id_vector_project"] = f"vector_projects_{slug}_{safe_uuid}"

        return {
            "normalized": normalized,
            "logs": ["variables normalizadas"],
        }

    def lookup_prospect(state: InboundState) -> InboundState:
        normalized = state["normalized"]
        realtor_id = normalized.get("realtor_id")
        telephone = normalized.get("telephone")

        logger.info(
            "lookup_prospect con realtor_id=%s telephone=%s | normalized=%s",
            realtor_id,
            telephone,
            normalized,
        )

        if not realtor_id or not telephone:
            logger.warning(
                "No se puede buscar prospecto: faltan realtor_id o telephone (%s, %s)",
                realtor_id,
                telephone,
            )
            return {
                "prospect": None,
                "prospect_exists": False,
                "logs": ["prospecto no buscado"],
            }

        prospect = prospect_repo.find_by_realtor_and_phone(str(realtor_id), str(telephone))
        exists = prospect is not None
        logger.debug(
            "Resultado búsqueda prospecto realtor_id=%s telephone=%s -> %s",
            realtor_id,
            telephone,
            "encontrado" if exists else "no encontrado",
        )

        return {
            "prospect": prospect,
            "prospect_exists": exists,
            "logs": ["prospecto existente" if exists else "prospecto no encontrado"],
        }

    def create_prospect(state: InboundState) -> InboundState:
        normalized = state["normalized"]
        realtor_id = normalized.get("realtor_id")
        telephone = normalized.get("telephone")
        name = normalized.get("name")

        logger.info(
            "create_prospect con datos realtor_id=%s telephone=%s name=%s normalized=%s",
            realtor_id,
            telephone,
            name,
            normalized,
        )

        if not realtor_id or not telephone:
            raise ValueError("No se puede crear prospecto sin realtor_id y telephone")

        prospect = prospect_repo.create(
            realtor_id=str(realtor_id),
            telephone=str(telephone),
            name=name if name else None,
            source="webhook",
        )

        logger.info("Prospecto creado con id %s", prospect.get("id"))

        return {
            "prospect": prospect,
            "created_prospect": True,
            "prospect_exists": True,
            "logs": ["prospecto creado"],
        }

    def hydrate_prospect(state: InboundState) -> InboundState:
        prospect = state.get("prospect")
        if not prospect:
            return {}

        normalized = state["normalized"].copy()
        normalized["prospect_id"] = prospect.get("id")
        normalized["automatization"] = prospect.get("automatization", True)
        normalized["mentioned_properties"] = prospect.get("mentioned_properties", [])
        normalized["stage"] = prospect.get("stage")
        normalized["vendor_id"] = prospect.get("vendor_id")
        normalized["observations"] = prospect.get("observations")
        normalized["calification_variables"] = prospect.get("calification_variables") or {}
        normalized["scheduled_at"] = prospect.get("scheduled_at")
        normalized["created_at"] = prospect.get("created_at")
        normalized["updated_at"] = prospect.get("updated_at")
        normalized["source"] = prospect.get("source")

        return {
            "normalized": normalized,
            "logs": ["datos prospecto listos"],
        }

    def load_properties(state: InboundState) -> InboundState:
        normalized = state.get("normalized", {})
        prospect_id = normalized.get("prospect_id")

        interested: List[Dict[str, Any]] = []
        if prospect_id:
            interested = project_repo.list_interested_projects(str(prospect_id))

        mentioned_list_raw = normalized.get("mentioned_properties") or []
        if isinstance(mentioned_list_raw, list):
            mentioned_list = mentioned_list_raw
        elif mentioned_list_raw:
            mentioned_list = [mentioned_list_raw]
        else:
            mentioned_list = []

        updated_normalized = normalized.copy()
        updated_normalized["properties_interested"] = interested
        updated_normalized["mentioned_properties"] = mentioned_list

        log_parts = [
            f"proyectos de interés: {len(interested)}",
            f"mencionados: {len(mentioned_list)}",
        ]

        return {
            "normalized": updated_normalized,
            "properties_interested": interested,
            "mentioned_properties": mentioned_list,
            "logs": [" | ".join(log_parts)],
        }

    def consolidate_official_data(state: InboundState) -> InboundState:
        normalized = state.get("normalized", {})
        realtor = normalized.get("realtor") or {}
        prospect = state.get("prospect") or {}

        followup_cfg = normalized.get("followup_configuration") or []
        broker_notifications = (
            normalized.get("notifications_brokers_configurations") or {}
        )

        prospect_summary = {
            "id": normalized.get("prospect_id"),
            "stage": normalized.get("stage"),
            "automatization": normalized.get("automatization"),
            "vendor_id": normalized.get("vendor_id"),
            "name": normalized.get("name"),
            "telephone": normalized.get("telephone"),
            "observations": normalized.get("observations"),
            "calification_variables": normalized.get("calification_variables") or {},
            "mentioned_properties": normalized.get("mentioned_properties") or [],
            "properties_interested": normalized.get("properties_interested", []),
            "scheduled_at": normalized.get("scheduled_at"),
            "created_at": normalized.get("created_at"),
            "updated_at": normalized.get("updated_at"),
            "source": normalized.get("source"),
        }

        data = {
            "session_id": normalized.get("session_id"),
            "realtor_id": normalized.get("realtor_id"),
            "realtor": realtor,
            "realtor_bot": normalized.get("realtor_bot"),
            "realtor_followups": {
                "prospects": realtor.get("followups_prospects"),
                "brokers": realtor.get("followups_brokers"),
            },
            "token_whapi": realtor.get("token_whapi"),
            "realtor_location": realtor.get("location"),
            "realtor_description": realtor.get("description"),
            "prospect_id": normalized.get("prospect_id"),
            "telephone": normalized.get("telephone"),
            "name": normalized.get("name"),
            "channel_id": normalized.get("channel_id"),
            "chat_id": normalized.get("chat_id"),
            "message": normalized.get("message"),
            "followup_configuration": followup_cfg,
            "notifications_brokers_configurations": broker_notifications,
            "id_vector_project": normalized.get("id_vector_project"),
            "properties_interested": normalized.get("properties_interested", []),
            "mentioned_properties": normalized.get("mentioned_properties", []),
            "stage": normalized.get("stage"),
            "prospect": prospect_summary,
            "raw_prospect": prospect,
        }

        return {
            "official_data": data,
            "logs": ["datos oficiales consolidados"],
        }

    def apply_opt_out(state: InboundState) -> InboundState:
        normalized = state.get("normalized", {})
        message = normalized.get("message")
        if isinstance(message, str) and message.strip() == "0":
            return {
                "automation_allowed": False,
                "handoff_required": True,
                "handoff_reason": "opt_out",
                "logs": ["opt-out detectado (mensaje '0')"],
            }
        return {"logs": ["mensaje permitido (sin opt-out)"]}

    def apply_automation_flag(state: InboundState) -> InboundState:
        normalized = state.get("normalized", {})
        automatization = normalized.get("automatization", True)
        if not automatization:
            return {
                "automation_allowed": False,
                "handoff_required": True,
                "handoff_reason": state.get("handoff_reason") or "automatizacion_desactivada",
                "logs": ["automatización desactivada para el prospecto"],
            }
        return {"logs": ["automatización habilitada"]}

    def prospect_exists_cond(state: InboundState) -> bool:
        return bool(state.get("prospect_exists"))

    graph.add_node("init", init_payload)
    graph.add_node("normalize", normalize_payload)
    graph.add_node("realtor", fetch_realtor)
    graph.add_node("lookup_prospect", lookup_prospect)
    graph.add_node("create_prospect", create_prospect)
    graph.add_node("hydrate_prospect", hydrate_prospect)
    graph.add_node("load_properties", load_properties)
    graph.add_node("consolidate_official", consolidate_official_data)
    graph.add_node("apply_opt_out", apply_opt_out)
    graph.add_node("apply_automation", apply_automation_flag)

    graph.set_entry_point("init")
    graph.add_edge("init", "normalize")
    graph.add_edge("normalize", "realtor")
    graph.add_edge("realtor", "lookup_prospect")

    graph.add_conditional_edges(
        "lookup_prospect",
        prospect_exists_cond,
        {
            True: "hydrate_prospect",
            False: "create_prospect",
        },
    )

    graph.add_edge("create_prospect", "hydrate_prospect")
    graph.add_edge("hydrate_prospect", "load_properties")
    graph.add_edge("load_properties", "consolidate_official")
    graph.add_edge("consolidate_official", "apply_opt_out")
    graph.add_edge("apply_opt_out", "apply_automation")
    graph.add_edge("apply_automation", END)

    return graph.compile()
