"""Persistencia compartilhada pelo backend AgriShield."""

from .supabase_rest import (
    ErroSupabase,
    cliente_supabase,
    diagnostico_supabase,
    supabase_configurado,
)

__all__ = [
    "ErroSupabase",
    "cliente_supabase",
    "diagnostico_supabase",
    "supabase_configurado",
]
