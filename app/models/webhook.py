from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class WebhookResponse(BaseModel):
    reply: str
    user_id: str
