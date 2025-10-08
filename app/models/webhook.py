from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppMessage(BaseModel):
    id: Optional[str] = None
    from_me: Optional[bool] = None
    type: Optional[str] = None
    chat_id: Optional[str] = None
    timestamp: Optional[int] = None
    source: Optional[str] = None
    text: Optional[Dict[str, Any]] = None
    from_: Optional[str] = Field(default=None, alias="from")
    from_name: Optional[str] = None


class WhatsAppEnvelope(BaseModel):
    messages: Optional[list[WhatsAppMessage]] = None
    event: Optional[Dict[str, Any]] = None
    channel_id: Optional[str] = None


class WebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_user: str = Field(alias="from", description="Identificador del remitente")
    message: str = Field(description="Texto plano recibido desde WhatsApp")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadatos opcionales enviados por WhatsApp"
    )
    realtor_id: Optional[str] = Field(
        default=None,
        description="Identificador del asesor para filtrar proyectos en Supabase",
    )
    channel_id: Optional[str] = Field(default=None, description="Identificador de canal entrante")
    chat_id: Optional[str] = Field(default=None, description="ID de chat WhatsApp")
    session_id: Optional[str] = Field(default=None, description="ID de sesión de conversación")
    telephone: Optional[str] = Field(default=None, description="Teléfono normalizado del contacto")
    name: Optional[str] = Field(default=None, description="Nombre del remitente")


class WebhookResponse(BaseModel):
    reply: str
    user_id: str
