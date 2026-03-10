"""
GCHI Dominance Engine — Streamlit Interface
GC Home Improvement LLC | v8.4
Author: Manus AI

Main application file. Provides a professional, intuitive interface for
validating and preparing JobTread-ready CSV proposals.
"""

import io
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure the app can find validator.py regardless of working directory
sys.path.insert(0, os.path.dirname(__file__))
from validator import GCHIValidator, ValidationResult

# ─────────────────────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GCHI Dominance Engine",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — GCHI Brand Identity
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Root Variables ── */
    :root {
        --gold-dark:   #B8860B;
        --gold-mid:    #C9970C;
        --gold-light:  #DAA520;
        --gold-pale:   #F5E6A3;
        --dark-bg:     #0F1117;
        --card-bg:     #1A1D26;
        --card-border: #2C2F3E;
        --text-primary: #FFFFFF;
        --text-secondary: #A0A4B8;
        --success:     #28A745;
        --error:       #DC3545;
        --warning:     #FFC107;
    }

    /* ── Global ── */
    .stApp { background-color: var(--dark-bg); }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F1117 0%, #1A1D26 100%);
        border-right: 1px solid var(--card-border);
    }
    [data-testid="stSidebar"] * { color: var(--text-primary) !important; }

    /* ── Header Banner ── */
    .gchi-header {
        background: linear-gradient(135deg, var(--gold-dark) 0%, var(--gold-light) 50%, var(--gold-dark) 100%);
        border-radius: 12px;
        padding: 1.2rem 2rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .gchi-header h1 {
        color: #0F1117 !important;
        font-size: 1.6rem !important;
        font-weight: 800 !important;
        margin: 0 !important;
        letter-spacing: -0.5px;
    }
    .gchi-header p {
        color: #1A1D26 !important;
        font-size: 0.85rem !important;
        margin: 0 !important;
        opacity: 0.8;
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        text-align: center;
    }
    .metric-card .metric-value {
        font-size: 2.2rem;
        font-weight: 800;
        line-height: 1;
    }
    .metric-card .metric-label {
        font-size: 0.78rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 0.3rem;
    }
    .metric-card.success .metric-value { color: var(--success); }
    .metric-card.error .metric-value   { color: var(--error); }
    .metric-card.warning .metric-value { color: var(--warning); }
    .metric-card.gold .metric-value    { color: var(--gold-light); }

    /* ── Status Banner ── */
    .status-banner {
        border-radius: 10px;
        padding: 1rem 1.5rem;
        margin: 1rem 0;
        font-weight: 600;
        font-size: 1rem;
    }
    .status-banner.pass {
        background: rgba(40, 167, 69, 0.15);
        border: 1px solid var(--success);
        color: var(--success);
    }
    .status-banner.fail {
        background: rgba(220, 53, 69, 0.15);
        border: 1px solid var(--error);
        color: var(--error);
    }

    /* ── Section Headers ── */
    .section-header {
        font-size: 1rem;
        font-weight: 700;
        color: var(--gold-light);
        text-transform: uppercase;
        letter-spacing: 1px;
        border-bottom: 1px solid var(--card-border);
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }

    /* ── Upload Zone ── */
    [data-testid="stFileUploader"] {
        background: var(--card-bg) !important;
        border: 2px dashed var(--gold-dark) !important;
        border-radius: 12px !important;
    }

    /* ── Dataframe ── */
    [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

    /* ── Buttons ── */
    .stDownloadButton > button {
        background: linear-gradient(135deg, var(--gold-dark), var(--gold-light)) !important;
        color: #0F1117 !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.6rem 1.5rem !important;
        font-size: 1rem !important;
        width: 100%;
    }
    .stDownloadButton > button:hover {
        opacity: 0.9;
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(184, 134, 11, 0.4) !important;
    }

    /* ── Sidebar Contact Card ── */
    .contact-card {
        background: rgba(184, 134, 11, 0.08);
        border: 1px solid rgba(184, 134, 11, 0.3);
        border-radius: 10px;
        padding: 1rem;
        margin-top: 1rem;
    }
    .contact-card p { margin: 0.2rem 0; font-size: 0.82rem; }
    .contact-card .contact-name {
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--gold-light) !important;
    }

    /* ── Reference Tags ── */
    .ref-tag {
        display: inline-block;
        background: rgba(184, 134, 11, 0.15);
        border: 1px solid rgba(184, 134, 11, 0.4);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.75rem;
        color: var(--gold-light);
        margin: 0.15rem;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        background: var(--card-bg) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }

    /* ── Hide Streamlit branding ── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Initialize Validator (cached for performance)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def load_validator() -> GCHIValidator:
    """Load the validator once and cache it for the session."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    return GCHIValidator(data_dir=data_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(validator: GCHIValidator) -> None:
    with st.sidebar:
        # Logo
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "gchi_logo.png")
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=True)
        else:
            st.markdown("## 🏗️ GCHI")

        st.markdown("---")

        # Contact Card
        st.markdown("""
        <div class="contact-card">
            <p class="contact-name">Wellington Silva</p>
            <p>Founder & Managing Director</p>
            <p>📞 (843) 489-7293</p>
            <p>✉️ contact@gchomeimprovementsc.com</p>
            <p>🌐 gchomeimprovementsc.com</p>
            <p style="margin-top:0.5rem; font-size:0.75rem; opacity:0.7;">
                B.S. Environmental Engineering<br>
                Sustainable Development Specialist<br>
                20+ Years Experience
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # System Status
        st.markdown('<div class="section-header">System Status v8.4</div>', unsafe_allow_html=True)
        counts = validator.reference_counts
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Cost Codes", counts["cost_codes"])
            st.metric("Units", counts["units"])
        with col2:
            st.metric("Cost Types", counts["cost_types"])
            st.metric("Status", "✅ Live")

        st.markdown("---")

        # Reference Quick View
        with st.expander("📋 Valid Cost Types"):
            for ct in sorted(validator.valid_cost_types):
                st.markdown(f'<span class="ref-tag">{ct}</span>', unsafe_allow_html=True)

        with st.expander("📐 Valid Units"):
            for u in sorted(validator.valid_units):
                st.markdown(f'<span class="ref-tag">{u}</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.7rem; color:#555; text-align:center;">GCHI Dominance Engine v8.4<br>© 2026 GC Home Improvement LLC</p>',
            unsafe_allow_html=True
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Build Donut Chart
# ─────────────────────────────────────────────────────────────────────────────

def build_donut_chart(result: ValidationResult) -> go.Figure:
    """Build a Plotly donut chart showing validation results breakdown."""
    valid_rows = result.total_rows - len({e.row for e in result.errors})
    error_rows = len({e.row for e in result.errors})
    warning_rows = len({w.row for w in result.warnings if w.row not in {e.row for e in result.errors}})

    labels = ["Valid Rows", "Rows with Errors", "Rows with Warnings"]
    values = [max(0, valid_rows - warning_rows), error_rows, warning_rows]
    colors = ["#28A745", "#DC3545", "#FFC107"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.65,
        marker=dict(colors=colors, line=dict(color="#0F1117", width=2)),
        textinfo="percent+label",
        textfont=dict(size=11, color="white"),
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    )])

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=220,
        annotations=[dict(
            text=f"<b>{result.total_rows}</b><br><span style='font-size:10px'>rows</span>",
            x=0.5, y=0.5,
            font=dict(size=18, color="white"),
            showarrow=False,
        )],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Build Error Distribution Bar Chart
# ─────────────────────────────────────────────────────────────────────────────

def build_error_bar_chart(result: ValidationResult) -> go.Figure:
    """Build a horizontal bar chart showing errors by column."""
    if not result.summary.get("errors_by_column"):
        return None

    cols = list(result.summary["errors_by_column"].keys())
    counts = list(result.summary["errors_by_column"].values())

    # Sort by count descending
    sorted_pairs = sorted(zip(counts, cols), reverse=True)
    counts, cols = zip(*sorted_pairs)

    fig = go.Figure(go.Bar(
        x=list(counts),
        y=list(cols),
        orientation="h",
        marker=dict(
            color=list(counts),
            colorscale=[[0, "#B8860B"], [1, "#DC3545"]],
            line=dict(color="#0F1117", width=1),
        ),
        text=list(counts),
        textposition="outside",
        textfont=dict(color="white", size=11),
        hovertemplate="<b>%{y}</b><br>Errors: %{x}<extra></extra>",
    ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, color="white"),
        yaxis=dict(showgrid=False, color="white", tickfont=dict(size=11)),
        margin=dict(t=5, b=5, l=10, r=40),
        height=max(150, len(cols) * 40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Helper: CSV to bytes for download
# ─────────────────────────────────────────────────────────────────────────────

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── Load Validator ────────────────────────────────────────────────────────
    try:
        validator = load_validator()
    except (FileNotFoundError, ValueError) as e:
        st.error(f"❌ **System Initialization Error:** {e}")
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    render_sidebar(validator)

    # ── Header Banner ─────────────────────────────────────────────────────────
    st.markdown("""
    <div class="gchi-header">
        <div>
            <h1>🏗️ GCHI Dominance Engine</h1>
            <p>JobTread CSV Validator & Compliance Engine — v8.4 | GC Home Improvement LLC</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Instructions ─────────────────────────────────────────────────────────
    with st.expander("📖 How to Use This Tool", expanded=False):
        st.markdown("""
        **Step 1 — Prepare your CSV** with the following required columns:

        | Column | Description |
        |---|---|
        | `Cost Group Name` | Must match one of the 199 official GCHI Cost Codes |
        | `Cost Item Name` | Descriptive name for the line item |
        | `Description` | Detailed description of the work or material |
        | `Quantity` | Numeric quantity |
        | `Unit` | Must be one of the 19 valid units (e.g., Hours, Square Feet, Bags) |
        | `Unit Cost` | Your direct cost per unit |
        | `Unit Price` | The price charged to the client per unit |
        | `Cost Type` | Must be one of the 7 valid types (Labor, Materials, Subcontractor, Equipment / Rental, Permits / Fees, Allowance, Other) |
        | `Taxable` | `true` or `false` |

        **Step 2 — Upload your CSV** using the uploader below.

        **Step 3 — Review the validation results.** Fix any errors shown in the table.

        **Step 4 — Download the JobTread-Ready CSV** once validation passes.
        """)

    # ── File Uploader ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">📤 Upload Proposal CSV</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        label="Drop your CSV file here or click to browse",
        type=["csv"],
        help="Upload a CSV file with your project estimate. The file must contain all required columns.",
        label_visibility="collapsed",
    )

    # ── Sample Download ───────────────────────────────────────────────────────
    sample_path = os.path.join(
        os.path.dirname(__file__), "..", "skills",
        "gchi-dominance-system", "templates", "jobtread_template.csv"
    )
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            sample_bytes = f.read()
        st.download_button(
            label="⬇️ Download Sample Template CSV",
            data=sample_bytes,
            file_name="GCHI_JobTread_Template_v8.4.csv",
            mime="text/csv",
            help="Download the official GCHI v8.4 template with sample data to use as a starting point.",
        )

    # ── Validation Flow ───────────────────────────────────────────────────────
    if uploaded_file is not None:
        st.markdown("---")

        # Parse the uploaded CSV — using preprocess_csv for robust format handling
        try:
            raw_bytes = uploaded_file.read()
            df = GCHIValidator.preprocess_csv(raw_bytes)
        except ValueError as e:
            st.error(f"❌ **Could not parse the uploaded file:** {e}")
            st.info(
                "💡 **Tip:** Make sure your file is a valid CSV. "
                "Common issues: file saved as Excel (.xlsx), encoding problems, "
                "or rows wrapped in extra quotes (this is auto-fixed by the engine)."
            )
            st.stop()

        # Run validation
        with st.spinner("🔍 Running GCHI v8.4 compliance validation..."):
            result = validator.validate(df)

        # ── Metrics Row ───────────────────────────────────────────────────────
        st.markdown('<div class="section-header">📊 Validation Summary</div>', unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card gold">
                <div class="metric-value">{result.total_rows}</div>
                <div class="metric-label">Total Rows</div>
            </div>""", unsafe_allow_html=True)
        with col2:
            status_class = "success" if result.error_count == 0 else "error"
            st.markdown(f"""
            <div class="metric-card {status_class}">
                <div class="metric-value">{result.error_count}</div>
                <div class="metric-label">Errors Found</div>
            </div>""", unsafe_allow_html=True)
        with col3:
            warn_class = "success" if result.warning_count == 0 else "warning"
            st.markdown(f"""
            <div class="metric-card {warn_class}">
                <div class="metric-value">{result.warning_count}</div>
                <div class="metric-label">Warnings</div>
            </div>""", unsafe_allow_html=True)
        with col4:
            pass_pct = int(((result.total_rows - result.error_count) / max(result.total_rows, 1)) * 100)
            pct_class = "success" if pass_pct == 100 else ("warning" if pass_pct >= 80 else "error")
            st.markdown(f"""
            <div class="metric-card {pct_class}">
                <div class="metric-value">{pass_pct}%</div>
                <div class="metric-label">Compliance Rate</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Status Banner ─────────────────────────────────────────────────────
        if result.is_valid:
            st.markdown("""
            <div class="status-banner pass">
                ✅ VALIDATION PASSED — This CSV is fully compliant with GCHI v8.4 rules and ready for JobTread import.
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="status-banner fail">
                ❌ VALIDATION FAILED — {result.error_count} error(s) must be corrected before this CSV can be imported into JobTread.
            </div>""", unsafe_allow_html=True)

        # ── Charts Row ────────────────────────────────────────────────────────
        chart_col1, chart_col2 = st.columns([1, 2])

        with chart_col1:
            st.markdown('<div class="section-header">Row Status</div>', unsafe_allow_html=True)
            fig_donut = build_donut_chart(result)
            st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

        with chart_col2:
            if result.summary.get("errors_by_column"):
                st.markdown('<div class="section-header">Errors by Column</div>', unsafe_allow_html=True)
                fig_bar = build_error_bar_chart(result)
                if fig_bar:
                    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})
            else:
                st.markdown('<div class="section-header">Error Distribution</div>', unsafe_allow_html=True)
                st.success("No column errors to display.")

        # ── Error Table ───────────────────────────────────────────────────────
        if not result.is_valid or result.warning_count > 0:
            st.markdown('<div class="section-header">🔎 Issue Details</div>', unsafe_allow_html=True)

            errors_df = validator.get_errors_dataframe(result)

            # Color-code the severity column
            def highlight_severity(val):
                if val == "ERROR":
                    return "background-color: rgba(220, 53, 69, 0.2); color: #FF6B7A; font-weight: bold;"
                elif val == "WARNING":
                    return "background-color: rgba(255, 193, 7, 0.2); color: #FFD700; font-weight: bold;"
                return ""

            styled_df = errors_df.style.applymap(
                highlight_severity, subset=["Severity"]
            )

            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                height=min(400, 40 + len(errors_df) * 38),
            )

            # Filter controls
            if len(errors_df) > 5:
                with st.expander("🔧 Filter Issues"):
                    filter_col = st.selectbox(
                        "Filter by Severity",
                        options=["All", "ERROR", "WARNING"],
                    )
                    if filter_col != "All":
                        filtered = errors_df[errors_df["Severity"] == filter_col]
                        st.dataframe(filtered, use_container_width=True, hide_index=True)

        # ── Preview Uploaded Data ─────────────────────────────────────────────
        with st.expander(f"👁️ Preview Uploaded Data ({len(df)} rows)", expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

        # ── Download Section ──────────────────────────────────────────────────
        st.markdown('<div class="section-header">📥 Export</div>', unsafe_allow_html=True)

        if result.is_valid:
            csv_bytes = df_to_csv_bytes(df)
            filename = uploaded_file.name.replace(".csv", "_jobtread_ready.csv")

            st.markdown("""
            <div style="background: rgba(40, 167, 69, 0.1); border: 1px solid #28A745;
                        border-radius: 10px; padding: 1rem; margin-bottom: 1rem;">
                <p style="color: #28A745; font-weight: 600; margin: 0;">
                    ✅ Your CSV passed all GCHI v8.4 compliance checks.
                    Click below to download the JobTread-ready file.
                </p>
            </div>""", unsafe_allow_html=True)

            st.download_button(
                label="⬇️ Download JobTread Ready CSV",
                data=csv_bytes,
                file_name=filename,
                mime="text/csv",
            )
        else:
            st.markdown("""
            <div style="background: rgba(220, 53, 69, 0.1); border: 1px solid #DC3545;
                        border-radius: 10px; padding: 1rem;">
                <p style="color: #DC3545; font-weight: 600; margin: 0;">
                    ❌ Fix all errors above before downloading.
                    The download button will appear once validation passes.
                </p>
            </div>""", unsafe_allow_html=True)

            if result.warning_count > 0 and result.error_count == 0:
                # Warnings only — allow download with disclaimer
                csv_bytes = df_to_csv_bytes(df)
                filename = uploaded_file.name.replace(".csv", "_jobtread_ready.csv")
                st.warning(
                    "⚠️ There are warnings but no hard errors. "
                    "Review the warnings carefully before importing."
                )
                st.download_button(
                    label="⬇️ Download CSV (with warnings — review first)",
                    data=csv_bytes,
                    file_name=filename,
                    mime="text/csv",
                )

    else:
        # ── Empty State ───────────────────────────────────────────────────────
        st.markdown("""
        <div style="text-align: center; padding: 3rem 1rem; color: #555;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h3 style="color: #888;">No file uploaded yet</h3>
            <p style="color: #555; max-width: 500px; margin: 0 auto;">
                Upload a CSV file above to validate it against the GCHI v8.4 rules.
                Download the sample template to get started quickly.
            </p>
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
