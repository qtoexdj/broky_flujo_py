import os
from functools import lru_cache
from typing import Dict, Optional

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError


class Settings(BaseModel):
    """Application configuration sourced from environment variables."""

    model_config = ConfigDict(populate_by_name=True)

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_embeddings_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDINGS_MODEL"
    )
    temperature: float = Field(default=0.2, alias="OPENAI_TEMPERATURE")
    system_prompt: str = Field(
        default=(
            "Eres un asistente cordial que ayuda a responder mensajes "
            "sencillos de WhatsApp con respuestas breves y útiles."
        ),
        alias="SYSTEM_PROMPT",
    )

    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    vector_table_name: str = Field(default="vector_projects", alias="VECTOR_TABLE_NAME")
    vector_match_count: int = Field(default=5, alias="VECTOR_MATCH_COUNT")

    vector_service_url: Optional[AnyHttpUrl] = Field(
        default=None, alias="VECTOR_SERVICE_URL"
    )
    vector_search_limit: int = Field(default=5, alias="VECTOR_SEARCH_LIMIT")
    vector_search_threshold: float = Field(default=0.7, alias="VECTOR_SEARCH_THRESHOLD")
    vector_service_timeout: float = Field(default=1.2, alias="VECTOR_SERVICE_TIMEOUT")
    rag_failure_reply: str = Field(
        default=(
            "Estamos consultando la información con un asesor. Te responderemos en breve."
        ),
        alias="RAG_FAILURE_REPLY",
    )

    rag_system_prompt: str = Field(
        default=(
            "Eres un asistente inmobiliario profesional. Usa únicamente el contexto "
            "proporcionado para responder. Si la información no es suficiente, indica "
            "claramente que no puedes responder. Incluye detalles concretos como "
            "precios, ubicaciones, tipologías y estados cuando estén disponibles."
        ),
        alias="RAG_SYSTEM_PROMPT",
    )
    rag_prompt_path: str = Field(
        default="docs/prompts/rag_subagent_prompt.md",
        alias="RAG_PROMPT_PATH",
    )

    master_agent_prompt_path: str = Field(
        default="docs/master_agent_prompt.md", alias="MASTER_AGENT_PROMPT_PATH"
    )

    whapi_base_url: Optional[AnyHttpUrl] = Field(
        default="https://gate.whapi.cloud",
        alias="WHAPI_BASE_URL",
    )
    whapi_timeout: float = Field(default=5.0, alias="WHAPI_TIMEOUT")
    public_base_url: Optional[AnyHttpUrl] = Field(default=None, alias="PUBLIC_BASE_URL")

    @property
    def supabase_api_key(self) -> Optional[str]:
        return self.supabase_service_role_key or self.supabase_anon_key

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_api_key)

    @property
    def vector_service_configured(self) -> bool:
        return self.vector_service_url is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once and reuse them across the app."""

    load_dotenv()

    env_values: Dict[str, str] = {}
    for field in Settings.model_fields.values():
        if field.alias:
            value = os.getenv(field.alias)
            if value is not None:
                env_values[field.alias] = value

    try:
        return Settings(**env_values)
    except ValidationError as exc:  # pragma: no cover - defensive failure path
        missing_keys = [
            field.alias
            for field in Settings.model_fields.values()
            if field.is_required() and not env_values.get(field.alias)
        ]
        hint = (
            "Faltan variables de entorno requeridas: " + ", ".join(missing_keys)
            if missing_keys
            else "Configuración inválida, revisa tu archivo .env"
        )
        raise RuntimeError(hint) from exc
