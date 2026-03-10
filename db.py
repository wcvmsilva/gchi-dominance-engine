"""
GCHI Dominance Engine — Supabase Database Client
Provides a cached Supabase client for all pages.
"""

import os
import streamlit as st

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://xoqhxpqsfxpdiwyuvhdd.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    st.secrets.get("SUPABASE_KEY", "") if hasattr(st, "secrets") else ""
)


@st.cache_resource(show_spinner=False)
def get_supabase():
    """Return a cached Supabase client."""
    from supabase import create_client
    if not SUPABASE_KEY:
        st.error("SUPABASE_KEY not configured. Set it in Streamlit secrets or environment.")
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
