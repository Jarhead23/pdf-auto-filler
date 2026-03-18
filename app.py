import streamlit as st
import pandas as pd
import pdfrw
import io
import zipfile
import base64
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

# --- 3. RUN THE CHECK ---
if not check_password():
    st.stop()  # Stop the rest of the app from running until they login

# --- YOUR PDF CODE STARTS HERE ---
st.success("Access Granted")

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
        st.header("Workspace Config")
        uploaded_config = st.file_uploader("Import Mapping (.json)", type="json")
        loaded_map = json.load(uploaded_config) if uploaded_config else {}

    st.title("🎯 GGC Fill Pro")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_tpl = st.file_uploader("Upload PDF Template", type="pdf")
    with col_up2:
        uploaded_data = st.file_uploader("Upload Data (CSV/XLSX)", type=["csv", "xlsx"])

    if uploaded_tpl and uploaded_data:
        # Data Loading & Formatting
        if uploaded_data.name.endswith('.csv'):
            df = pd.read_csv(uploaded_data, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_data, dtype=str, keep_default_na=False)
        
        for c in ['Zip', 'Zip/Postal', 'Job ID']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(5)

        excel_cols = ["None"] + list(df.columns)
        pdf_fields = get_pdf_fields(uploaded_tpl)
        
        st.divider()
        st.subheader("🛠️ Smart Mapping")
        mapping_results = {}
        m_cols = st.columns(3)
        for i, field in enumerate(pdf_fields):
            with m_cols[i % 3]:
                if field in loaded_map and loaded_map[field] in excel_cols:
                    idx = excel_cols.index(loaded_map[field])
                elif field in excel_cols:
                    idx = excel_cols.index(field)
                else:
                    idx = 0
                mapping_results[field] = st.selectbox(f"PDF: {field}", excel_cols, index=idx, key=f"m_{field}")

        st.download_button("💾 Export Mapping", json.dumps(mapping_results), 
                           file_name="mapping.json", mime="application/json")

        st.divider()
        p_col, b_col = st.columns(2)
        with p_col:
            if st.button("👁️ Preview Row 1", use_container_width=True):
                pdf = fill_single_pdf(uploaded_tpl, mapping_results, df.iloc[0])
                b64 = base64.b64encode(pdf.read()).decode('utf-8')
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="600"></iframe>', unsafe_allow_html=True)

        with b_col:
            if st.button("🚀 Start Full Batch", type="primary", use_container_width=True):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    p = st.progress(0)
                    for idx, row in df.iterrows():
                        fname = f"Filled_{idx+1}.pdf"
                        zf.writestr(fname, fill_single_pdf(uploaded_tpl, mapping_results, row).getvalue())
                        p.progress((idx + 1) / len(df))
                st.success("Batch Done!")
                st.download_button("📥 Download ZIP", zip_buffer.getvalue(), "results.zip", "application/zip", use_container_width=True)
