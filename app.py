import streamlit as st
import pandas as pd
import pdfrw
import io
import zipfile
import os

# --- 1. SECURITY GATE ---
def check_password():
    """Returns True if the user had the correct password."""
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Restricted Access")
    
    # Retrieve password from Streamlit Secrets
    try:
        correct_password = st.secrets["MY_APP_PASSWORD"]
    except KeyError:
        st.error("Setup Error: Please add 'MY_APP_PASSWORD' to the Streamlit Secrets dashboard.")
        st.stop()

    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock"):
        if pwd == correct_password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("🚫 Incorrect Password")
    return False

# --- STOP EXECUTION IF NOT LOGGED IN ---
if not check_password():
    st.stop()

# --- 2. DATA & PDF HELPERS ---
def format_data(df):
    """Ensures specific columns maintain leading zeros and cleans Excel decimals."""
    cols_to_fix = ['Zip/Postal', 'Destination Zip/Postal', 'Job ID', 'Zip']
    for col in cols_to_fix:
        if col in df.columns:
            # Convert to string, strip '.0', and pad to 5 digits
            df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(5)
    return df

def fill_pdf(template_stream, data_dict):
    """Fills AcroForm fields in a PDF using pdfrw."""
    template_data = template_stream.read()
    template = pdfrw.PdfReader(fdata=template_data)
    
    if template.Root.AcroForm:
        template.Root.AcroForm.update(
            pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true"))
        )
        
    for page in template.pages:
        if page.Annots:
            for annotation in page.Annots:
                if annotation.Subtype == "/Widget":
                    key = annotation.T
                    if key:
                        field_name = key[1:-1] if key.startswith("(") else str(key)
                        if field_name in data_dict:
                            annotation.update(
                                pdfrw.PdfDict(V=pdfrw.PdfString.encode(str(data_dict[field_name])))
                            )
                            annotation.AP = ""
    
    out_stream = io.BytesIO()
    pdfrw.PdfWriter().write(out_stream, template)
    out_stream.seek(0)
    return out_stream

# --- 3. MAIN UI ---
st.title("📄 PDF Auto Generator Pro")
st.sidebar.success("Logged In")
if st.sidebar.button("Log Out"):
    st.session_state["password_correct"] = False
    st.rerun()

st.subheader("1. Upload Your Files")
col1, col2 = st.columns(2)

with col1:
    uploaded_templates = st.file_uploader("Upload PDF Templates", type="pdf", accept_multiple_files=True)
with col2:
    uploaded_data = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"])

if uploaded_templates and uploaded_data:
    try:
        # Load and clean data
        if uploaded_data.name.endswith('.csv'):
            df = pd.read_csv(uploaded_data, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_data, dtype=str, keep_default_na=False)
        
        df = format_data(df)

        # --- PREVIEW FEATURE ---
        st.subheader("2. Data Preview")
        st.write("Check below to ensure leading zeros (e.g., Job ID or Zip) are correct:")
        st.dataframe(df.head(5)) # Shows the first 5 rows

        # 3. GENERATION
        st.subheader("3. Generate Batch")
        if st.button("🚀 START GENERATION", use_container_width=True):
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                progress_bar = st.progress(0)
                total_files = len(df) * len(uploaded_templates)
                step = 0
                
                for idx, row in df.iterrows():
                    # Filename logic
                    job_id = str(row.get("Job ID", f"ID_{idx+1}"))
                    last = str(row.get("Last Name", ""))
                    first = str(row.get("First Name", ""))
                    base_name = f"{job_id}_{last}_{first}".strip("_").replace(" ", "_")
                    base_name = "".join(c for c in base_name if c not in r'\/:*?"<>|')

                    for tpl in uploaded_templates:
                        tpl.seek(0)
                        
                        # Get field names for this PDF
                        reader = pdfrw.PdfReader(fdata=tpl.read())
                        tpl.seek(0)
                        
                        pdf_fields = []
                        for page in reader.pages:
                            if page.Annots:
                                for ann in page.Annots:
                                    if ann.Subtype == "/Widget" and ann.T:
                                        pdf_fields.append(ann.T[1:-1] if ann.T.startswith("(") else str(ann.T))
                        
                        # Map and fill
                        data_dict = {f: str(row[f]) for f in pdf_fields if f in df.columns}
                        filled_pdf = fill_pdf(tpl, data_dict)
                        
                        tpl_name = os.path.splitext(tpl.name)[0]
                        zf.writestr(f"{base_name}_{tpl_name}.pdf", filled_pdf.getvalue())
                        
                        step += 1
                        progress_bar.progress(step / total_files)

            st.balloons()
            st.success("Generation Complete!")
            st.download_button(
                label="📥 Download ZIP File",
                data=zip_buffer.getvalue(),
                file_name="Processed_PDFs.zip",
                mime="application/zip",
                use_container_width=True
            )
            
    except Exception as e:
        st.error(f"An error occurred: {e}")
        st.error(f"Critical Error: {e}")
