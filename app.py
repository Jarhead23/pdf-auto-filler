import streamlit as st
import pandas as pd
import pdfrw
import io
import zipfile
import json

# --- 1. INITIALIZE SESSION STATE ---
# This prevents the KeyError by ensuring the key exists the moment the app starts
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# --- 2. THE LOGIN FUNCTION ---
def check_password():
    """Returns True if the user had the correct password."""
    def password_entered():
        # Compare entered text to your secret password
        if st.session_state["password_input"] == st.secrets["MY_APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            del st.session_state["password_input"]  # remove password from state for security
        else:
            st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        # Show input box if not authenticated
        st.text_input(
            "Enter Password to access the Batch Processor", 
            type="password", 
            on_change=password_entered, 
            key="password_input"
        )
        return False
    return True

# --- 2. CORE LOGIC ---
def get_pdf_fields(template_stream):
    template_stream.seek(0)
    reader = pdfrw.PdfReader(fdata=template_stream.read())
    fields = []
    for page in reader.pages:
        if page.Annots:
            for ann in page.Annots:
                if ann.Subtype == "/Widget" and ann.T:
                    name = ann.T[1:-1] if ann.T.startswith("(") else str(ann.T)
                    if name not in fields: fields.append(name)
    return fields

def fill_single_pdf(template_stream, mapping_dict, row_data):
    template_stream.seek(0)
    template = pdfrw.PdfReader(fdata=template_stream.read())
    if template.Root.AcroForm:
        template.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true")))
    
    final_data = {pdf_f: str(row_data[ex_c]) for pdf_f, ex_c in mapping_dict.items() 
                  if ex_c != "None" and ex_c in row_data}

    for page in template.pages:
        if page.Annots:
            for ann in page.Annots:
                if ann.Subtype == "/Widget":
                    key = ann.T[1:-1] if ann.T and ann.T.startswith("(") else str(ann.T)
                    if key in final_data:
                        ann.update(pdfrw.PdfDict(V=pdfrw.PdfString.encode(final_data[key])))
                        ann.AP = ""
    
    out = io.BytesIO()
    pdfrw.PdfWriter().write(out, template)
    out.seek(0)
    return out

# --- 3. MAIN INTERFACE ---
if check_password():
    
    with st.sidebar:
        st.header("💾 Configuration")
        uploaded_config = st.file_uploader("Import Multi-Mapping (.json)", type="json")
        if uploaded_config:
            st.session_state['loaded_map'] = json.load(uploaded_config)
            st.success("Config Loaded!")
        elif 'loaded_map' not in st.session_state:
            st.session_state['loaded_map'] = {}

    st.title("🎯 GGC Fill Multi-Pro")
    
    # 1. UPLOADS
    col_up1, col_up2 = st.columns([1, 1])
    with col_up1:
        # ALLOW MULTIPLE PDFS
        uploaded_tpls = st.file_uploader("1. Upload PDF Templates", type="pdf", accept_multiple_files=True)
    with col_up2:
        uploaded_data = st.file_uploader("2. Upload Spreadsheet", type=["csv", "xlsx"])

    if uploaded_tpls and uploaded_data:
        # DATA LOADING & LEADING ZERO FIX
        if uploaded_data.name.endswith('.csv'):
            df = pd.read_csv(uploaded_data, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_data, dtype=str, keep_default_na=False)
        
        cols_to_pad = ['Zip/Postal', 'Job ID', 'Destination Zip/Postal']
        for c in cols_to_pad:
            if c in df.columns:
                df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(5)

        excel_cols = ["None"] + list(df.columns)
        
        st.divider()
        st.subheader("🛠️ Smart Mapping (Per Template)")
        
        # 2. MULTI-TEMPLATE MAPPING UI
        all_mappings = {}
        current_global_map = st.session_state.get('loaded_map', {})

        # Create tabs for each PDF uploaded
        tabs = st.tabs([tpl.name for tpl in uploaded_tpls])
        
        for i, tpl in enumerate(uploaded_tpls):
            with tabs[i]:
                pdf_fields = get_pdf_fields(tpl)
                template_map = {}
                # Get the saved map for THIS specific file if it exists in the JSON
                saved_template_map = current_global_map.get(tpl.name, {})
                
                m_cols = st.columns(3)
                for j, field in enumerate(pdf_fields):
                    with m_cols[j % 3]:
                        # Logic: Saved JSON -> Auto-Match -> None
                        if field in saved_template_map and saved_template_map[field] in excel_cols:
                            idx = excel_cols.index(saved_template_map[field])
                        elif field in excel_cols:
                            idx = excel_cols.index(field)
                        else:
                            idx = 0
                        
                        template_map[field] = st.selectbox(
                            f"Field: {field}", excel_cols, index=idx, key=f"m_{tpl.name}_{field}"
                        )
                all_mappings[tpl.name] = template_map

        # EXPORT MULTI-CONFIG
        st.download_button("💾 Export All Mappings", json.dumps(all_mappings, indent=4), 
                           file_name="multi_template_config.json", mime="application/json")

        st.divider()
        
        # 3. BATCH EXECUTION
        if st.button("🚀 Start Multi-Template Batch", type="primary", use_container_width=True):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                total_files = len(df) * len(uploaded_tpls)
                p = st.progress(0)
                count = 0
                
                for idx, row in df.iterrows():
                    jid = str(row.get("Job ID", f"ID-{idx+1}"))
                    ln = str(row.get("Last Name", "")).strip()
                    fn = str(row.get("First Name", "")).strip()
                    
                    for tpl in uploaded_tpls:
                        tpl_short = tpl.name.replace(".pdf", "")
                        file_name = f"{jid}_{ln}_{fn}_{tpl_short}.pdf".strip("_")
                        
                        pdf_bytes = fill_single_pdf(tpl, all_mappings[tpl.name], row)
                        zf.writestr(file_name, pdf_bytes.getvalue())
                        
                        count += 1
                        p.progress(count / total_files)
                
            st.success(f"Batch Complete! Generated {count} documents.")
            st.download_button("📥 Download ZIP Package", zip_buffer.getvalue(), 
                               "GGC_Final.zip", "application/zip", use_container_width=True)
            
                           # --- DOCUMENTATION GENERATOR ---
    st.divider()
    st.subheader("📄 Project Documentation")
    st.info("Download the official manuals and technical specifications for this software.")
    
    doc_col1, doc_col2, doc_col3 = st.columns(3)
    
    # 1. User Guide Content
    user_guide_text = """# GGC Fill Multi-Pro: User Guide
    1. **Login:** Enter your Access Code.
    2. **Upload:** Add multiple PDF templates and one Excel/CSV file.
    3. **Map:** Use the tabs to link PDF fields to Spreadsheet columns.
    4. **Export Config:** Save your mapping as a .json file for future use.
    5. **Batch:** Click 'Start Multi-Template Batch' to generate your ZIP."""
    
    with doc_col1:
        st.download_button("📥 Download User Guide", user_guide_text, 
                           file_name="User_Guide_.md", mime="text/markdown")
    
    # 2. Technical Docs Content
    tech_docs_text = """# Technical Documentation
    - **Stack:** Streamlit, Pandas, pdfrw, Openpyxl.
    - **Logic:** In-memory PDF dictionary injection via /Annots key.
    - **Security:** st.secrets for authentication; zero-disk persistence.
    - **Data:** Regex padding for leading zeros on Zip/ID columns."""
    
    with doc_col2:
        st.download_button("📥 Download Tech Docs", tech_docs_text, 
                           file_name="Technical_Docs.md", mime="text/markdown")
    
    # 3. SRS Content
    srs_text = """# Software Requirements Specification (SRS)
    - **FR1:** Secure authentication gate.
    - **FR2:** Support for N-templates to 1-dataset.
    - **FR3:** JSON-based configuration portability.
    - **FR4:** Preservation of numerical string formatting."""
    
    with doc_col3:
        st.download_button("📥 Download SRS", srs_text, 
                           file_name="SRS_Specification.md", mime="text/markdown")
