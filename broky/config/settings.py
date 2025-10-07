"""LangChain specific configuration layer."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LangChainSettings(BaseModel):
    """Configuration contract for LangChain agents and tools."""

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGSMITH_API_KEY")

    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    default_vector_limit: int = Field(default=5, alias="VECTOR_SEARCH_LIMIT")
    default_vector_threshold: float = Field(default=0.7, alias="VECTOR_SEARCH_THRESHOLD")

    class Config:
        populate_by_name = True

    @property
    def supabase_api_key(self) -> Optional[str]:
        return self.supabase_service_role_key

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_api_key)


@lru_cache(maxsize=1)
def get_langchain_settings() -> LangChainSettings:
    """Load settings una sola vez para toda la ejecución."""

    load_dotenv()

    env_values = {
        key: value
        for key in (
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "LANGSMITH_API_KEY",
            "SUPABASE_URL",
            "SUPABASE_SERVICE_ROLE_KEY",
            "VECTOR_SEARCH_LIMIT",
            "VECTOR_SEARCH_THRESHOLD",
        )
        if (value := os.getenv(key)) is not None
    }

    return LangChainSettings(**env_values)
