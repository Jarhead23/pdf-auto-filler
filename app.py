import streamlit as st
import pandas as pd
from datetime import datetime
import json

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Moving Co. Inventory Audit",
    page_icon="🚛",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Mono', monospace;
}
h1, h2, h3 {
    font-family: 'Syne', sans-serif !important;
}
.block-container { padding-top: 2rem; }

.truck-header {
    background: #1a1a2e;
    color: #f0a500;
    padding: 0.6rem 1.2rem;
    border-radius: 6px;
    font-family: 'Syne', sans-serif;
    font-size: 1.15rem;
    font-weight: 800;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}
.audit-box {
    background: #f9f6f0;
    border: 2px solid #1a1a2e;
    border-radius: 8px;
    padding: 1.5rem;
    margin-top: 1rem;
    font-family: 'DM Mono', monospace;
    white-space: pre-wrap;
    font-size: 0.82rem;
    line-height: 1.7;
    color: #1a1a2e;
}
.stButton > button {
    background-color: #f0a500;
    color: #1a1a2e;
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    border: none;
    border-radius: 6px;
    padding: 0.5rem 1.4rem;
}
.stButton > button:hover {
    background-color: #1a1a2e;
    color: #f0a500;
}
div[data-testid="stDownloadButton"] > button {
    background-color: #1a1a2e;
    color: #f0a500;
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    border: none;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── 1. INITIALIZE SESSION STATE ───────────────────────────────────────────────
# Ensures the key exists the moment the app starts, preventing KeyError
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# ── 2. LOGIN FUNCTION ─────────────────────────────────────────────────────────
def check_password():
    """Returns True if the user entered the correct password."""
    def password_entered():
        if st.session_state["password_input"] == st.secrets["MY_APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            del st.session_state["password_input"]  # remove password from state for security
        else:
            st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.text_input(
            "Enter Password to access the Inventory Audit",
            type="password",
            on_change=password_entered,
            key="password_input",
        )
        return False
    return True

if not check_password():
    st.stop()

# ── Session state init ────────────────────────────────────────────────────────
TRUCKS = ["Truck 1", "Truck 2", "Truck 3", "Truck 4"]

if "inventory" not in st.session_state:
    st.session_state.inventory = {t: [] for t in TRUCKS}
if "auditor" not in st.session_state:
    st.session_state.auditor = ""
if "audit_date" not in st.session_state:
    st.session_state.audit_date = datetime.today()

# ── Helper functions ──────────────────────────────────────────────────────────
def build_template_json() -> str:
    """Export current inventory as a reusable JSON template."""
    template = {}
    for truck in TRUCKS:
        template[truck] = [
            {"Item": row.get("Item", ""), "Quantity": row.get("Quantity", 0)}
            for row in st.session_state.inventory[truck]
            if str(row.get("Item", "")).strip()
        ]
    return json.dumps(template, indent=2)


def load_template_file(uploaded_file) -> dict:
    """Parse an uploaded JSON template."""
    raw = uploaded_file.read()
    return json.loads(raw)


def build_report_text() -> str:
    date_str = st.session_state.audit_date.strftime("%B %d, %Y")
    auditor = st.session_state.auditor.strip() or "N/A"
    lines = []
    lines.append("=" * 58)
    lines.append("       MONTHLY INVENTORY AUDIT REPORT")
    lines.append("=" * 58)
    lines.append(f"  Date     : {date_str}")
    lines.append(f"  Auditor  : {auditor}")
    lines.append(f"  Company  : Moving Company")
    lines.append("=" * 58)

    grand_total = 0
    for truck in TRUCKS:
        items = st.session_state.inventory[truck]
        lines.append("")
        lines.append(f"  ── {truck.upper()} ──────────────────────────────────")
        if not items:
            lines.append("    (no items recorded)")
        else:
            lines.append(f"    {'ITEM':<35} {'QTY':>6}")
            lines.append(f"    {'-'*35} {'------':>6}")
            truck_total = 0
            for row in items:
                name = str(row.get("Item", "")).strip()
                qty = int(row.get("Quantity", 0) or 0)
                truck_total += qty
                lines.append(f"    {name:<35} {qty:>6}")
            lines.append(f"    {'─'*35} {'──────':>6}")
            lines.append(f"    {'TRUCK TOTAL':<35} {truck_total:>6}")
            grand_total += truck_total

    lines.append("")
    lines.append("=" * 58)
    lines.append(f"  {'GRAND TOTAL (ALL TRUCKS)':<34} {grand_total:>6}")
    lines.append("=" * 58)
    lines.append(f"\n  Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 58)
    return "\n".join(lines)


def build_csv() -> str:
    rows = []
    for truck in TRUCKS:
        for row in st.session_state.inventory[truck]:
            rows.append({
                "Truck": truck,
                "Item": row.get("Item", ""),
                "Quantity": row.get("Quantity", 0),
                "Audit Date": st.session_state.audit_date.strftime("%Y-%m-%d"),
                "Auditor": st.session_state.auditor.strip(),
            })
    if not rows:
        return "Truck,Item,Quantity,Audit Date,Auditor\n"
    return pd.DataFrame(rows).to_csv(index=False)


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# 🚛 Monthly Inventory Audit")
st.markdown("**Moving Company — Truck Inventory Tracker**")

st.divider()

# ── Import / Save Template ────────────────────────────────────────────────────
with st.expander("📂 Import / Save Item Template", expanded=False):
    st.markdown(
        "**Save** your current items as a template to reuse next month. "
        "**Import** a saved template to pre-fill items and quantities — "
        "then just update the counts before generating your report."
    )
    imp_col, exp_col = st.columns(2)

    with imp_col:
        st.markdown("#### ⬆️ Import Template")
        uploaded = st.file_uploader(
            "Upload a saved `.json` template", type=["json"], key="template_upload"
        )
        load_mode = st.radio(
            "On import:",
            ["Replace all items", "Merge with existing items"],
            horizontal=True,
        )
        if st.button("Load Template") and uploaded:
            try:
                data = load_template_file(uploaded)
                for truck in TRUCKS:
                    incoming = data.get(truck, [])
                    if load_mode == "Replace all items":
                        st.session_state.inventory[truck] = incoming
                    else:
                        existing_names = {
                            r.get("Item", "").lower()
                            for r in st.session_state.inventory[truck]
                        }
                        for row in incoming:
                            if row.get("Item", "").lower() not in existing_names:
                                st.session_state.inventory[truck].append(row)
                st.success("✅ Template loaded! Update quantities in each truck tab.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not read template: {e}")

    with exp_col:
        st.markdown("#### 💾 Save as Template")
        st.markdown(
            "Downloads a `.json` file with all current items and quantities. "
            "Re-import it at the start of next month's audit."
        )
        st.download_button(
            label="⬇️ Download Template (.json)",
            data=build_template_json(),
            file_name=f"inventory_template_{datetime.today().strftime('%Y%m')}.json",
            mime="application/json",
        )

st.divider()

# ── Audit meta ────────────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)
with col_a:
    st.session_state.auditor = st.text_input(
        "Auditor Name", value=st.session_state.auditor, placeholder="Your name"
    )
with col_b:
    st.session_state.audit_date = st.date_input(
        "Audit Date", value=st.session_state.audit_date
    )

st.divider()

# ── Truck tabs ────────────────────────────────────────────────────────────────
tabs = st.tabs([f"🚛 {t}" for t in TRUCKS])

for i, tab in enumerate(tabs):
    truck = TRUCKS[i]
    with tab:
        st.markdown(
            f'<div class="truck-header">📦 {truck} — Item Entry</div>',
            unsafe_allow_html=True,
        )

        with st.form(key=f"form_{truck}", clear_on_submit=True):
            c1, c2, c3 = st.columns([4, 2, 1])
            with c1:
                item_name = st.text_input(
                    "Item Name", placeholder="e.g. Moving blankets", key=f"item_{truck}"
                )
            with c2:
                qty = st.number_input("Quantity", min_value=0, step=1, key=f"qty_{truck}")
            with c3:
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("➕ Add")

            if submitted:
                if item_name.strip():
                    st.session_state.inventory[truck].append(
                        {"Item": item_name.strip(), "Quantity": int(qty)}
                    )
                    st.success(f"Added: {item_name.strip()} × {qty}")
                else:
                    st.warning("Please enter an item name.")

        items = st.session_state.inventory[truck]
        if items:
            df = pd.DataFrame(items)
            df.index = df.index + 1

            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"editor_{truck}",
            )
            st.session_state.inventory[truck] = edited.to_dict("records")

            total = sum(r.get("Quantity", 0) or 0 for r in st.session_state.inventory[truck])
            st.markdown(f"**Total items counted: `{total}`**")

            if st.button(f"🗑 Clear {truck}", key=f"clear_{truck}"):
                st.session_state.inventory[truck] = []
                st.rerun()
        else:
            st.info("No items yet. Add items above, or import a template using the panel at the top.")

st.divider()

# ── Generate report ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    if st.button("📋 Generate Audit Report"):
        report = build_report_text()
        st.markdown(
            '<div class="audit-box">' + report.replace("\n", "<br>") + "</div>",
            unsafe_allow_html=True,
        )
        st.session_state["last_report"] = report

if "last_report" in st.session_state:
    with col2:
        st.download_button(
            label="⬇️ Download .txt",
            data=st.session_state["last_report"],
            file_name=f"audit_{st.session_state.audit_date.strftime('%Y%m')}.txt",
            mime="text/plain",
        )
    with col3:
        st.download_button(
            label="⬇️ Download .csv",
            data=build_csv(),
            file_name=f"audit_{st.session_state.audit_date.strftime('%Y%m')}.csv",
            mime="text/csv",
        )
