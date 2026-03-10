"""
GCHI Dominance Engine — Assembly Builder
Phase 1.2: Build, edit, and validate assemblies with BOM linking,
locked Labor units, Crew Velocity, and Direct Cost summary.
"""

import os
import sys
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import (
    fetch_assemblies,
    fetch_assembly_items,
    fetch_cost_codes,
    fetch_cost_types,
    fetch_crew_velocity,
    fetch_pricing_history,
    fetch_units,
    upsert_assembly,
    upsert_assembly_item,
    delete_assembly_item,
    upsert_pricing,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GCHI Assembly Builder",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS (GCHI Brand)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    :root {
        --gold-dark: #B8860B; --gold-mid: #C9970C; --gold-light: #DAA520;
        --gold-pale: #F5E6A3; --dark-bg: #0F1117; --card-bg: #1A1D26;
        --card-border: #2C2F3E; --text-primary: #FFFFFF;
        --text-secondary: #A0A4B8; --success: #28A745;
        --error: #DC3545; --warning: #FFC107;
    }
    .stApp { background-color: var(--dark-bg); }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F1117 0%, #1A1D26 100%);
        border-right: 1px solid var(--card-border);
    }
    [data-testid="stSidebar"] * { color: var(--text-primary) !important; }
    .gchi-header {
        background: linear-gradient(135deg, var(--gold-dark) 0%, var(--gold-light) 50%, var(--gold-dark) 100%);
        border-radius: 12px; padding: 1.2rem 2rem; margin-bottom: 1.5rem;
    }
    .gchi-header h1 { color: #0F1117 !important; font-size: 1.6rem !important; font-weight: 800 !important; margin: 0 !important; }
    .gchi-header p { color: #1A1D26 !important; font-size: 0.85rem !important; margin: 0 !important; opacity: 0.8; }
    .section-header {
        font-size: 1rem; font-weight: 700; color: var(--gold-light);
        text-transform: uppercase; letter-spacing: 1px;
        border-bottom: 1px solid var(--card-border);
        padding-bottom: 0.5rem; margin: 1.5rem 0 1rem 0;
    }
    .metric-card {
        background: var(--card-bg); border: 1px solid var(--card-border);
        border-radius: 10px; padding: 1.2rem 1.5rem; text-align: center;
    }
    .metric-card .metric-value { font-size: 2rem; font-weight: 800; line-height: 1; }
    .metric-card .metric-label {
        font-size: 0.75rem; color: var(--text-secondary);
        text-transform: uppercase; letter-spacing: 0.8px; margin-top: 0.3rem;
    }
    .metric-card.gold .metric-value { color: var(--gold-light); }
    .metric-card.success .metric-value { color: var(--success); }
    .metric-card.error .metric-value { color: var(--error); }
    .metric-card.warning .metric-value { color: var(--warning); }
    .cost-breakdown {
        background: var(--card-bg); border: 1px solid var(--card-border);
        border-radius: 10px; padding: 1.2rem; margin: 0.5rem 0;
    }
    .cost-breakdown h4 { color: var(--gold-light); margin: 0 0 0.5rem 0; font-size: 0.9rem; }
    .cost-breakdown .line { display: flex; justify-content: space-between; padding: 0.3rem 0; font-size: 0.85rem; }
    .cost-breakdown .line.total { border-top: 1px solid var(--card-border); font-weight: 700; margin-top: 0.5rem; padding-top: 0.5rem; }
    .bom-row { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin: 0.5rem 0; }
    .locked-field { background: rgba(184, 134, 11, 0.1); border: 1px solid var(--gold-dark); border-radius: 6px; padding: 0.5rem 0.8rem; }
    #MainMenu { visibility: hidden; } footer { visibility: hidden; } header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def d(val):
    """Convert to Decimal for precise money math."""
    return Decimal(str(val or 0))


def money(val):
    """Format as USD currency."""
    return f"${d(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def build_cost_code_lookup(codes):
    """Build lookup dicts from cost codes."""
    by_id = {c["id"]: c for c in codes}
    parents = {c["id"]: c for c in codes if c.get("is_parent")}
    children = {c["id"]: c for c in codes if not c.get("is_parent")}
    by_code = {c["code"]: c for c in codes}
    return by_id, parents, children, by_code


def get_latest_price(cost_code_id, pricing_data):
    """Get the most recent unit cost for a cost code."""
    for p in pricing_data:
        if p["cost_code_id"] == cost_code_id:
            return d(p.get("unit_cost", 0))
    return d(0)


def calculate_assembly_cost(items, pricing_data, base_qty, waste_factor):
    """Calculate the full Direct Cost for an assembly.

    Calculation logic per cost type:
    - Materials: qty_per_unit * effective_qty * (1 + item_waste)
    - Labor: qty_per_unit (hrs/sqft) * base_qty (sqft) = total hours (no waste)
    - Equipment: qty_per_unit * effective_qty * (1 + item_waste)
    - Permits/Fees: qty_per_unit * base_qty (no waste — fixed cost per project area)
    """
    effective_qty = d(base_qty) * (d(1) + d(waste_factor))
    base = d(base_qty)
    lines = []
    total_material = d(0)
    total_labor = d(0)
    total_equipment = d(0)
    total_permits = d(0)

    for item in items:
        unit_cost = get_latest_price(item["cost_code_id"], pricing_data)
        qty_per_unit = d(item.get("default_qty_per_unit", 0))
        item_waste = d(item.get("waste_factor", 0))
        cost_type = item.get("cost_type_name", "")

        if cost_type == "Labor":
            # Labor: rate (hrs/sqft) x base area = total hours. No waste on labor.
            calc_qty = qty_per_unit * base
            line_cost = calc_qty * unit_cost
        elif cost_type in ("Permits / Fees", "Permits/Fees", "Permits"):
            # Permits: rate x base area, no waste (fixed cost per project)
            calc_qty = qty_per_unit * base
            line_cost = calc_qty * unit_cost
        else:
            # Materials/Equipment scale with area + global waste + item waste
            calc_qty = qty_per_unit * effective_qty * (d(1) + item_waste)
            line_cost = calc_qty * unit_cost

        line = {
            "cost_code_id": item["cost_code_id"],
            "cost_code": item.get("cost_codes", {}).get("code", "????") if item.get("cost_codes") else "????",
            "name": item.get("cost_codes", {}).get("name", "Unknown") if item.get("cost_codes") else "Unknown",
            "cost_type": cost_type,
            "unit_name": item.get("unit_name", ""),
            "qty_per_unit": float(qty_per_unit),
            "calculated_qty": float(calc_qty.quantize(Decimal("0.01"))),
            "unit_cost": float(unit_cost),
            "line_cost": float(line_cost.quantize(Decimal("0.01"))),
            "waste_factor": float(item_waste),
        }
        lines.append(line)

        if cost_type == "Materials":
            total_material += line_cost
        elif cost_type == "Labor":
            total_labor += line_cost
        elif cost_type in ("Equipment/Rental", "Equipment", "Equipment / Rental"):
            total_equipment += line_cost
        elif cost_type in ("Permits / Fees", "Permits/Fees", "Permits"):
            total_permits += line_cost

    direct_cost = total_material + total_labor + total_equipment + total_permits
    return {
        "lines": lines,
        "total_material": float(total_material.quantize(Decimal("0.01"))),
        "total_labor": float(total_labor.quantize(Decimal("0.01"))),
        "total_equipment": float(total_equipment.quantize(Decimal("0.01"))),
        "total_permits": float(total_permits.quantize(Decimal("0.01"))),
        "direct_cost": float(direct_cost.quantize(Decimal("0.01"))),
        "effective_qty": float(effective_qty.quantize(Decimal("0.01"))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "gchi_logo.png")
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=True)
        else:
            st.markdown("## GCHI")

        st.markdown("---")
        st.markdown('<div class="section-header">Assembly Builder v1.0</div>', unsafe_allow_html=True)
        st.markdown("""
        **Phase 1.2** — Build and validate assemblies with:
        - BOM linked to 4-digit Cost Codes
        - Crew Velocity for Labor hours
        - Waste factors per material
        - Direct Cost calculation
        - Margin analysis (35-40% target)
        """)

        st.markdown("---")
        st.markdown("""
        <div style="background: rgba(184,134,11,0.08); border: 1px solid rgba(184,134,11,0.3);
                    border-radius: 10px; padding: 1rem;">
            <p style="font-size: 0.82rem; margin: 0;"><strong>Wellington Silva</strong></p>
            <p style="font-size: 0.78rem; margin: 0.2rem 0;">Founder & Managing Director</p>
            <p style="font-size: 0.78rem; margin: 0;">GC Home Improvement LLC</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.7rem; color:#555; text-align:center;">'
            'GCHI Dominance Engine v8.4.1<br>Assembly Builder v1.0<br>'
            '&copy; 2026 GC Home Improvement LLC</p>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Page
# ─────────────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    # Header
    st.markdown("""
    <div class="gchi-header">
        <div>
            <h1>Assembly Builder</h1>
            <p>Phase 1.2 — Build, validate, and manage construction assemblies with live Supabase data</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Load data
    try:
        cost_codes = fetch_cost_codes()
        cost_types = fetch_cost_types()
        units = fetch_units()
        assemblies = fetch_assemblies()
        pricing_data = fetch_pricing_history()
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        st.info("Make sure SUPABASE_KEY is set in Streamlit secrets (.streamlit/secrets.toml)")
        st.stop()

    by_id, parents, children, by_code = build_cost_code_lookup(cost_codes)
    ct_map = {ct["id"]: ct["name"] for ct in cost_types}
    unit_map = {u["id"]: u["name"] for u in units}

    # ── Assembly Selector ────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Select Assembly</div>', unsafe_allow_html=True)

    if not assemblies:
        st.warning("No assemblies found in database. Create one below.")
        selected_assembly = None
    else:
        assembly_options = {a["name"]: a for a in assemblies}
        selected_name = st.selectbox(
            "Choose an assembly to view/edit:",
            options=list(assembly_options.keys()),
            index=0,
        )
        selected_assembly = assembly_options[selected_name]

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab_view, tab_edit, tab_new = st.tabs(["View & Calculate", "Edit BOM", "New Assembly"])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1: VIEW & CALCULATE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_view:
        if selected_assembly is None:
            st.info("Select or create an assembly first.")
        else:
            asm = selected_assembly
            items = fetch_assembly_items(asm["id"])

            # Get crew velocity by matching cost_code_ids from assembly items
            item_cc_ids = list(set(it["cost_code_id"] for it in items)) if items else []
            all_crew_vel = fetch_crew_velocity(item_cc_ids if item_cc_ids else None)
            # Filter to active, prefer spring_fall season
            crew_vel = [cv for cv in all_crew_vel if cv.get("is_active")]
            if not crew_vel:
                crew_vel = all_crew_vel

            # Enrich items with cost type and unit names
            for item in items:
                item["cost_type_name"] = ct_map.get(item.get("cost_type_id", ""), "Unknown")
                item["unit_name"] = unit_map.get(item.get("unit_id", ""), "Unknown")

            # ── Assembly Info ────────────────────────────────────────────────
            st.markdown('<div class="section-header">Assembly Details</div>', unsafe_allow_html=True)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f"""
                <div class="metric-card gold">
                    <div class="metric-value">{asm['name'][:20]}</div>
                    <div class="metric-label">Assembly Name</div>
                </div>""", unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="metric-card gold">
                    <div class="metric-value">{asm.get('base_unit_qty', 0)} sq ft</div>
                    <div class="metric-label">Base Area</div>
                </div>""", unsafe_allow_html=True)
            with col3:
                wf = float(asm.get("waste_factor", 0)) * 100
                st.markdown(f"""
                <div class="metric-card warning">
                    <div class="metric-value">{wf:.0f}%</div>
                    <div class="metric-label">Waste Factor</div>
                </div>""", unsafe_allow_html=True)
            with col4:
                st.markdown(f"""
                <div class="metric-card gold">
                    <div class="metric-value">{asm.get('region', 'N/A')}</div>
                    <div class="metric-label">Region</div>
                </div>""", unsafe_allow_html=True)

            # ── Crew Velocity Info ───────────────────────────────────────────
            if crew_vel:
                cv = crew_vel[0]
                output_per_hr = float(cv.get('output_per_hour', 0))
                base_qty = float(asm.get('base_unit_qty', 0))
                crew_size = int(cv.get('crew_size', 2))
                total_h = base_qty / output_per_hr if output_per_hr > 0 else 0
                days = total_h / (crew_size * 8) if crew_size > 0 else 0

                st.markdown('<div class="section-header">Crew Velocity</div>', unsafe_allow_html=True)
                cv_cols = st.columns(4)
                with cv_cols[0]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{crew_size}</div>
                        <div class="metric-label">Crew Size</div>
                    </div>""", unsafe_allow_html=True)
                with cv_cols[1]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{output_per_hr:.2f}</div>
                        <div class="metric-label">Sq Ft / Hour</div>
                    </div>""", unsafe_allow_html=True)
                with cv_cols[2]:
                    st.markdown(f"""
                    <div class="metric-card warning">
                        <div class="metric-value">{total_h:.0f}h</div>
                        <div class="metric-label">Total Labor Hours</div>
                    </div>""", unsafe_allow_html=True)
                with cv_cols[3]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{days:.1f}</div>
                        <div class="metric-label">Work Days</div>
                    </div>""", unsafe_allow_html=True)

            # ── BOM Table ────────────────────────────────────────────────────
            st.markdown('<div class="section-header">Bill of Materials (BOM)</div>', unsafe_allow_html=True)

            if not items:
                st.warning("No line items found for this assembly.")
            else:
                calc = calculate_assembly_cost(
                    items, pricing_data,
                    asm.get("base_unit_qty", 0),
                    asm.get("waste_factor", 0),
                )

                # BOM DataFrame
                bom_data = []
                for line in calc["lines"]:
                    bom_data.append({
                        "Code": line["cost_code"],
                        "Description": line["name"],
                        "Type": line["cost_type"],
                        "Unit": line["unit_name"],
                        "Qty/Unit": line["qty_per_unit"],
                        "Calc Qty": line["calculated_qty"],
                        "Unit Cost": line["unit_cost"],
                        "Waste %": f"{line['waste_factor']*100:.0f}%",
                        "Line Total": money(line["line_cost"]),
                    })

                bom_df = pd.DataFrame(bom_data)
                st.dataframe(bom_df, use_container_width=True, hide_index=True, height=min(400, 50 + len(bom_data) * 38))

                # ── Direct Cost Summary ──────────────────────────────────────
                st.markdown('<div class="section-header">Direct Cost Summary</div>', unsafe_allow_html=True)

                dc = calc["direct_cost"]
                overhead_rate = 0.15
                overhead = dc * overhead_rate
                total_with_oh = dc + overhead

                # Margin analysis
                margins = [
                    {"target": "35%", "rate": 0.35},
                    {"target": "37.5%", "rate": 0.375},
                    {"target": "40%", "rate": 0.40},
                ]

                sum_cols = st.columns(4)
                with sum_cols[0]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{money(calc['total_material'])}</div>
                        <div class="metric-label">Materials</div>
                    </div>""", unsafe_allow_html=True)
                with sum_cols[1]:
                    st.markdown(f"""
                    <div class="metric-card warning">
                        <div class="metric-value">{money(calc['total_labor'])}</div>
                        <div class="metric-label">Labor</div>
                    </div>""", unsafe_allow_html=True)
                with sum_cols[2]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{money(calc['total_equipment'])}</div>
                        <div class="metric-label">Equipment</div>
                    </div>""", unsafe_allow_html=True)
                with sum_cols[3]:
                    st.markdown(f"""
                    <div class="metric-card gold">
                        <div class="metric-value">{money(calc['total_permits'])}</div>
                        <div class="metric-label">Permits/Fees</div>
                    </div>""", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # Cost buildup
                st.markdown(f"""
                <div class="cost-breakdown">
                    <h4>Cost Buildup</h4>
                    <div class="line"><span>Materials</span><span>{money(calc['total_material'])}</span></div>
                    <div class="line"><span>Labor ({crew_vel[0].get('output_per_hour', 0) if crew_vel else 'N/A'} sqft/hr, {sum(l['calculated_qty'] for l in calc['lines'] if l['cost_type']=='Labor'):.0f}h total)</span><span>{money(calc['total_labor'])}</span></div>
                    <div class="line"><span>Equipment</span><span>{money(calc['total_equipment'])}</span></div>
                    <div class="line"><span>Permits & Fees</span><span>{money(calc['total_permits'])}</span></div>
                    <div class="line total"><span>DIRECT COST</span><span>{money(dc)}</span></div>
                    <div class="line"><span>Overhead ({overhead_rate*100:.0f}%)</span><span>{money(overhead)}</span></div>
                    <div class="line total"><span>TOTAL COST (w/ Overhead)</span><span>{money(total_with_oh)}</span></div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # Margin analysis table
                st.markdown('<div class="section-header">Margin Analysis</div>', unsafe_allow_html=True)

                margin_data = []
                for m in margins:
                    if total_with_oh > 0:
                        sell_price = total_with_oh / (1 - m["rate"])
                        gross_profit = sell_price - total_with_oh
                        markup_pct = (sell_price / total_with_oh - 1) * 100
                        base_area = float(asm.get("base_unit_qty", 1)) or 1
                        margin_data.append({
                            "Target Margin": m["target"],
                            "Sell Price": money(sell_price),
                            "Gross Profit": money(gross_profit),
                            "Markup %": f"{markup_pct:.1f}%",
                            "Per Sq Ft": money(sell_price / base_area),
                        })
                    else:
                        margin_data.append({
                            "Target Margin": m["target"],
                            "Sell Price": "$0.00",
                            "Gross Profit": "$0.00",
                            "Markup %": "N/A",
                            "Per Sq Ft": "$0.00",
                        })

                margin_df = pd.DataFrame(margin_data)
                st.dataframe(margin_df, use_container_width=True, hide_index=True)

                # ── Cost Distribution Chart ──────────────────────────────────
                st.markdown('<div class="section-header">Cost Distribution</div>', unsafe_allow_html=True)

                chart_cols = st.columns([1, 1])
                with chart_cols[0]:
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=["Materials", "Labor", "Equipment", "Permits"],
                        values=[calc["total_material"], calc["total_labor"],
                                calc["total_equipment"], calc["total_permits"]],
                        hole=0.5,
                        marker=dict(colors=["#DAA520", "#FFC107", "#B8860B", "#F5E6A3"]),
                        textinfo="label+percent",
                        textfont=dict(color="white"),
                    )])
                    fig_pie.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="white"),
                        showlegend=False,
                        height=350,
                        margin=dict(t=20, b=20, l=20, r=20),
                    )
                    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

                with chart_cols[1]:
                    # Margin waterfall
                    recommended_sell = total_with_oh / (1 - 0.375) if total_with_oh > 0 else 0
                    fig_bar = go.Figure(data=[go.Bar(
                        x=["Materials", "Labor", "Equipment", "Permits", "Overhead", "Profit"],
                        y=[calc["total_material"], calc["total_labor"],
                           calc["total_equipment"], calc["total_permits"],
                           overhead, recommended_sell - total_with_oh],
                        marker_color=["#DAA520", "#FFC107", "#B8860B", "#F5E6A3", "#555", "#28A745"],
                        text=[money(v) for v in [
                            calc["total_material"], calc["total_labor"],
                            calc["total_equipment"], calc["total_permits"],
                            overhead, recommended_sell - total_with_oh
                        ]],
                        textposition="outside",
                        textfont=dict(color="white", size=10),
                    )])
                    fig_bar.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="white"),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        xaxis=dict(showgrid=False),
                        height=350,
                        margin=dict(t=20, b=40, l=20, r=20),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

                # ── Export CSV ───────────────────────────────────────────────
                st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)

                # Build JobTread-ready CSV from assembly
                jt_rows = []
                for line in calc["lines"]:
                    # Find parent cost group for this cost code
                    cc = by_code.get(line["cost_code"])
                    if cc and cc.get("parent_id"):
                        parent = by_id.get(cc["parent_id"], {})
                        cost_group = parent.get("name", "Uncategorized")
                    else:
                        cost_group = cc.get("name", "Uncategorized") if cc else "Uncategorized"

                    jt_rows.append({
                        "Cost Group": cost_group,
                        "Cost Item": line["name"],
                        "Description": f"{asm['name']} - {line['name']}",
                        "Quantity": line["calculated_qty"],
                        "Unit": line["unit_name"],
                        "Unit Cost": line["unit_cost"],
                        "Cost Type": line["cost_type"],
                        "Taxable": "true" if line["cost_type"] == "Materials" else "false",
                    })

                jt_df = pd.DataFrame(jt_rows)
                csv_bytes = jt_df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    label="Download JobTread CSV",
                    data=csv_bytes,
                    file_name=f"GCHI_{asm['name'].replace(' ', '_')}_JobTread.csv",
                    mime="text/csv",
                )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2: EDIT BOM
    # ══════════════════════════════════════════════════════════════════════════
    with tab_edit:
        if selected_assembly is None:
            st.info("Select an assembly first.")
        else:
            asm = selected_assembly
            items = fetch_assembly_items(asm["id"])

            st.markdown(f'<div class="section-header">Edit BOM: {asm["name"]}</div>', unsafe_allow_html=True)

            # Build options for dropdowns
            child_codes = sorted(
                [(c["code"], f'{c["code"]} - {c["name"]}', c["id"]) for c in cost_codes if not c.get("is_parent")],
                key=lambda x: x[0],
            )
            ct_options = [(ct["id"], ct["name"]) for ct in cost_types]
            unit_options = [(u["id"], u["name"]) for u in units]

            # Existing items
            for i, item in enumerate(items):
                cc_info = by_id.get(item["cost_code_id"], {})
                ct_name = ct_map.get(item.get("cost_type_id", ""), "Unknown")
                unit_name = unit_map.get(item.get("unit_id", ""), "Unknown")

                with st.expander(f'{cc_info.get("code", "????")} - {cc_info.get("name", "Unknown")} ({ct_name})', expanded=False):
                    ecol1, ecol2, ecol3 = st.columns(3)
                    with ecol1:
                        new_qty = st.number_input(
                            "Qty per Unit",
                            value=float(item.get("default_qty_per_unit", 0)),
                            min_value=0.0,
                            step=0.01,
                            key=f"qty_{item['id']}",
                        )
                    with ecol2:
                        new_waste = st.number_input(
                            "Waste Factor",
                            value=float(item.get("waste_factor", 0)),
                            min_value=0.0,
                            max_value=1.0,
                            step=0.01,
                            key=f"waste_{item['id']}",
                        )
                    with ecol3:
                        if ct_name == "Labor":
                            st.markdown("""
                            <div class="locked-field">
                                <strong>Unit: Hours (LOCKED)</strong><br>
                                <small>Labor units are locked to Hours per Crew Velocity rules.</small>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.text(f"Unit: {unit_name}")

                    # Price input
                    current_price = float(get_latest_price(item["cost_code_id"], pricing_data))
                    new_price = st.number_input(
                        "Unit Cost ($)",
                        value=current_price,
                        min_value=0.0,
                        step=0.01,
                        key=f"price_{item['id']}",
                    )

                    bcol1, bcol2 = st.columns(2)
                    with bcol1:
                        if st.button("Save Changes", key=f"save_{item['id']}"):
                            upsert_assembly_item({
                                "id": item["id"],
                                "default_qty_per_unit": new_qty,
                                "waste_factor": new_waste,
                            })
                            if new_price != current_price:
                                upsert_pricing({
                                    "cost_code_id": item["cost_code_id"],
                                    "unit_cost": new_price,
                                    "effective_date": str(date.today()),
                                    "source": "manual_edit",
                                    "region": asm.get("region", "charleston_sc"),
                                })
                            st.success("Saved!")
                            st.rerun()
                    with bcol2:
                        if st.button("Delete", key=f"del_{item['id']}", type="secondary"):
                            delete_assembly_item(item["id"])
                            st.warning("Item deleted.")
                            st.rerun()

            # Add new item
            st.markdown('<div class="section-header">Add New Line Item</div>', unsafe_allow_html=True)

            acol1, acol2 = st.columns(2)
            with acol1:
                cc_labels = [f'{c[0]} - {c[1].split(" - ", 1)[1]}' for c in child_codes]
                selected_cc_idx = st.selectbox("Cost Code", options=range(len(cc_labels)), format_func=lambda i: cc_labels[i], key="new_cc")
                selected_cc = child_codes[selected_cc_idx]
            with acol2:
                ct_labels = [ct[1] for ct in ct_options]
                selected_ct_idx = st.selectbox("Cost Type", options=range(len(ct_labels)), format_func=lambda i: ct_labels[i], key="new_ct")
                selected_ct = ct_options[selected_ct_idx]

            acol3, acol4, acol5 = st.columns(3)
            with acol3:
                # Lock unit to Hours if Labor
                if selected_ct[1] == "Labor":
                    hours_unit = next((u for u in unit_options if u[1] == "Hours"), unit_options[0])
                    st.markdown("""
                    <div class="locked-field">
                        <strong>Unit: Hours (LOCKED)</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    selected_unit = hours_unit
                else:
                    unit_labels = [u[1] for u in unit_options]
                    selected_unit_idx = st.selectbox("Unit", options=range(len(unit_labels)), format_func=lambda i: unit_labels[i], key="new_unit")
                    selected_unit = unit_options[selected_unit_idx]
            with acol4:
                new_item_qty = st.number_input("Qty per Unit", value=1.0, min_value=0.0, step=0.01, key="new_qty")
            with acol5:
                new_item_waste = st.number_input("Waste Factor", value=0.0, min_value=0.0, max_value=1.0, step=0.01, key="new_waste")

            new_item_price = st.number_input("Unit Cost ($)", value=0.0, min_value=0.0, step=0.01, key="new_price")

            if st.button("Add Line Item", type="primary"):
                new_id = str(uuid.uuid4())
                max_sort = max([it.get("sort_order", 0) for it in items], default=0) + 1
                upsert_assembly_item({
                    "id": new_id,
                    "assembly_id": asm["id"],
                    "cost_code_id": selected_cc[2],
                    "cost_type_id": selected_ct[0],
                    "unit_id": selected_unit[0],
                    "default_qty_per_unit": new_item_qty,
                    "waste_factor": new_item_waste,
                    "sort_order": max_sort,
                })
                if new_item_price > 0:
                    upsert_pricing({
                        "cost_code_id": selected_cc[2],
                        "unit_cost": new_item_price,
                        "effective_date": str(date.today()),
                        "source": "manual_entry",
                        "region": asm.get("region", "charleston_sc"),
                    })
                st.success(f"Added {selected_cc[1]} to assembly!")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3: NEW ASSEMBLY
    # ══════════════════════════════════════════════════════════════════════════
    with tab_new:
        st.markdown('<div class="section-header">Create New Assembly</div>', unsafe_allow_html=True)

        ncol1, ncol2 = st.columns(2)
        with ncol1:
            new_name = st.text_input("Assembly Name", placeholder="e.g., Standard Deck 10x12 (Wood)")
            new_category = st.selectbox("Category", options=[
                "decking", "roofing", "fencing", "siding", "flooring",
                "painting", "plumbing", "electrical", "foundation",
                "framing", "drywall", "tiling", "cabinetry", "general",
            ])
        with ncol2:
            new_base_qty = st.number_input("Base Unit Qty (sq ft)", value=100.0, min_value=1.0, step=1.0)
            new_waste = st.number_input("Global Waste Factor", value=0.10, min_value=0.0, max_value=0.5, step=0.01)
            new_region = st.selectbox("Region", options=["charleston_sc", "columbia_sc"])

        new_description = st.text_area("Description", placeholder="Describe the assembly scope...")

        if st.button("Create Assembly", type="primary"):
            if not new_name:
                st.error("Assembly name is required.")
            else:
                new_id = str(uuid.uuid4())
                upsert_assembly({
                    "id": new_id,
                    "name": new_name,
                    "category": new_category,
                    "base_unit_qty": new_base_qty,
                    "waste_factor": new_waste,
                    "region": new_region,
                    "description": new_description,
                })
                st.success(f"Assembly '{new_name}' created! Switch to 'Edit BOM' tab to add line items.")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
