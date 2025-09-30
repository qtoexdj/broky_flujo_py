from typing import Optional

from supabase import Client, create_client

from app.core.config import Settings

_supabase_client: Optional[Client] = None


def get_supabase_client(settings: Settings) -> Optional[Client]:
    """Instantiate the Supabase client if credentials are available."""

    global _supabase_client

    if not settings.supabase_configured:
        return None

    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_api_key)

    return _supabase_client
