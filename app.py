import streamlit as st
import pandas as pd
import pdfrw
import io
import zipfile
import json

# --- 1. SECURE AUTHENTICATION ---
st.set_page_config(page_title="GGC Fill Pro", layout="wide", page_icon="🎯")

def check_password():
    if "password_correct" not in st.session_state:
        st.title("🔐 GGC Portal")
        pw = st.text_input("Enter Access Code", type="password")
        if st.button("Log In"):
            # This looks for 'password' in your Streamlit Cloud Secrets
            if pw == st.secrets.get("password", "admin"): 
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Invalid Code")
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
    
    # Apply the mapping: {PDF_Field: Excel_Value}
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
    
    # SIDEBAR: The Import Logic
    with st.sidebar:
        st.header("💾 Configuration")
        uploaded_config = st.file_uploader("Import Saved Mapping (.json)", type="json")
        
        # If a file is uploaded, load it into session state
        if uploaded_config:
            st.session_state['loaded_map'] = json.load(uploaded_config)
            st.success("Config Loaded!")
        else:
            if 'loaded_map' not in st.session_state:
                st.session_state['loaded_map'] = {}

    st.title("🎯 InstaFill Pro")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_tpl = st.file_uploader("1. Upload PDF Template", type="pdf")
    with col_up2:
        uploaded_data = st.file_uploader("2. Upload Spreadsheet", type=["csv", "xlsx"])

    if uploaded_tpl and uploaded_data:
        # DATA LOADING WITH LEADING ZERO FIX
        if uploaded_data.name.endswith('.csv'):
            df = pd.read_csv(uploaded_data, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_data, dtype=str, keep_default_na=False)
        
        # Ensure Zip and Job IDs keep leading zeros
        for c in ['Zip', 'Zip/Postal', 'Job ID', 'Postal Code', 'Destination Zip']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(5)

        excel_cols = ["None"] + list(df.columns)
        pdf_fields = get_pdf_fields(uploaded_tpl)
        
        st.divider()
        st.subheader("🛠️ Smart Mapping")
        
        mapping_results = {}
        m_cols = st.columns(3)
        
        # Pull from the imported JSON if it exists
        current_map = st.session_state.get('loaded_map', {})

        for i, field in enumerate(pdf_fields):
            with m_cols[i % 3]:
                # 1. Check if the field is in the IMPORTED JSON
                if field in current_map and current_map[field] in excel_cols:
                    idx = excel_cols.index(current_map[field])
                # 2. Check for an exact name match in Excel
                elif field in excel_cols:
                    idx = excel_cols.index(field)
                else:
                    idx = 0
                
                mapping_results[field] = st.selectbox(f"PDF: {field}", excel_cols, index=idx, key=f"m_{field}")

        # EXPORT CONFIG BUTTON
        st.download_button("💾 Export Current Mapping", json.dumps(mapping_results, indent=4), 
                           file_name=f"map_{uploaded_tpl.name.replace('.pdf', '')}.json", 
                           mime="application/json")

        st.divider()
        p_col, b_col = st.columns(2)
        
        with p_col:
            # FIX: Switched to Download Preview for better reliability
            preview_pdf = fill_single_pdf(uploaded_tpl, mapping_results, df.iloc[0])
            st.download_button("👁️ Download Preview (Row 1)", preview_pdf.getvalue(), 
                               file_name="PREVIEW.pdf", mime="application/pdf", use_container_width=True)

        with b_col:
            if st.button("🚀 Start Full Batch", type="primary", use_container_width=True):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    p = st.progress(0)
                    for idx, row in df.iterrows():
                        # FILENAME FIX: Use JobID_LastName_FirstName if available
                        jid = str(row.get("Job ID", f"ID-{idx+1}"))
                        ln = str(row.get("Last Name", "")).strip()
                        fn = str(row.get("First Name", "")).strip()
                        safe_name = f"{jid}_{ln}_{fn}".strip("_") or f"File_{idx+1}"
                        
                        full_name = f"{safe_name}.pdf"
                        zf.writestr(full_name, fill_single_pdf(uploaded_tpl, mapping_results, row).getvalue())
                        p.progress((idx + 1) / len(df))
                
                st.success("Batch Processing Complete!")
                st.download_button("📥 Download Final ZIP", zip_buffer.getvalue(), 
                                   "InstaFill_Results.zip", "application/zip", use_container_width=True)
