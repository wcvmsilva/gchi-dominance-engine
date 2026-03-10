"""
GCHI Dominance Engine — Supabase Database Client
Provides a cached Supabase client for all pages.
"""

import os
import streamlit as st

# Default Supabase URL (public, safe to hardcode)
_DEFAULT_URL = "https://xoqhxpqsfxpdiwyuvhdd.supabase.co"


def _get_secret(key: str, default: str = "") -> str:
    """
    Retrieve a secret from multiple sources in priority order:
    1. Environment variable (e.g., SUPABASE_KEY)
    2. Streamlit secrets flat format (e.g., secrets["SUPABASE_KEY"])
    3. Streamlit secrets nested format (e.g., secrets["supabase"]["key"])
    """
    # 1. Environment variable
    val = os.environ.get(key, "")
    if val:
        return val

    # 2. Streamlit secrets (flat format)
    try:
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass

    # 3. Streamlit secrets (nested under [supabase] section)
    try:
        supabase_section = st.secrets.get("supabase", {})
        if isinstance(supabase_section, dict):
            # Map SUPABASE_KEY -> key, SUPABASE_URL -> url
            short_key = key.replace("SUPABASE_", "").lower()
            val = supabase_section.get(short_key, "")
            if val:
                return str(val)
    except Exception:
        pass

    # 4. Try accessing as attribute (Streamlit AttrDict)
    try:
        val = getattr(st.secrets, key, "")
        if val:
            return str(val)
    except Exception:
        pass

    return default


SUPABASE_URL = _get_secret("SUPABASE_URL", _DEFAULT_URL)
SUPABASE_KEY = _get_secret("SUPABASE_KEY", "")


@st.cache_resource(show_spinner=False)
def get_supabase():
    """Return a cached Supabase client."""
    from supabase import create_client
    if not SUPABASE_KEY:
        st.error(
            "SUPABASE_KEY not configured. "
            "Set it in Streamlit Cloud > App Settings > Secrets using this format:\n\n"
            "```toml\n"
            'SUPABASE_URL = "https://xoqhxpqsfxpdiwyuvhdd.supabase.co"\n'
            'SUPABASE_KEY = "your-anon-key-here"\n'
            "```"
        )
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_cost_codes():
    """Fetch all cost codes with parent info, cached per session."""
    sb = get_supabase()
    resp = sb.table("cost_codes").select("*").order("code").execute()
    return resp.data or []


def fetch_assemblies():
    """Fetch all assemblies."""
    sb = get_supabase()
    resp = sb.table("assemblies").select("*").order("name").execute()
    return resp.data or []


def fetch_assembly_items(assembly_id: str):
    """Fetch line items for a specific assembly."""
    sb = get_supabase()
    resp = (
        sb.table("assembly_items")
        .select("*, cost_codes(code, name, is_parent, parent_id)")
        .eq("assembly_id", assembly_id)
        .order("sort_order")
        .execute()
    )
    return resp.data or []


def fetch_cost_types():
    """Fetch all cost types."""
    sb = get_supabase()
    resp = sb.table("cost_types").select("*").execute()
    return resp.data or []


def fetch_units():
    """Fetch all units."""
    sb = get_supabase()
    resp = sb.table("units").select("*").execute()
    return resp.data or []


def fetch_crew_velocity(cost_code_ids: list = None):
    """Fetch crew velocity records, optionally filtered by cost_code_ids."""
    sb = get_supabase()
    q = sb.table("crew_velocity").select("*, cost_codes(code, name)")
    if cost_code_ids:
        q = q.in_("cost_code_id", cost_code_ids)
    resp = q.execute()
    return resp.data or []


def fetch_pricing_history(cost_code_id: str = None):
    """Fetch pricing history, optionally filtered by cost code."""
    sb = get_supabase()
    q = sb.table("cost_code_pricing_history").select("*").order("effective_date", desc=True)
    if cost_code_id:
        q = q.eq("cost_code_id", cost_code_id)
    resp = q.execute()
    return resp.data or []


def upsert_assembly(data: dict):
    """Create or update an assembly."""
    sb = get_supabase()
    resp = sb.table("assemblies").upsert(data).execute()
    return resp.data


def upsert_assembly_item(data: dict):
    """Create or update an assembly line item."""
    sb = get_supabase()
    resp = sb.table("assembly_items").upsert(data).execute()
    return resp.data


def delete_assembly_item(item_id: str):
    """Delete an assembly line item."""
    sb = get_supabase()
    resp = sb.table("assembly_items").delete().eq("id", item_id).execute()
    return resp.data


def upsert_pricing(data: dict):
    """Create or update a pricing history record."""
    sb = get_supabase()
    resp = sb.table("cost_code_pricing_history").upsert(data).execute()
    return resp.data
