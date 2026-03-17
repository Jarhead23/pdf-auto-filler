import streamlit as st
import pandas as pd
import pdfrw
import io
import zipfile
import os

# --- Helper to handle leading zeros ---
def format_data(df):
    """Ensures specific columns maintain leading zeros."""
    cols_to_fix = ['Zip/Postal', 'Destination Zip/Postal', 'Job ID', 'Zip']
    for col in cols_to_fix:
        if col in df.columns:
            # Convert to string, remove .0 if it came from Excel, then pad
            df[col] = df[col].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(5)
    return df

# --- PDF Logic ---
def fill_pdf(template_stream, data_dict):
    template_data = template_stream.read()
    template = pdfrw.PdfReader(fdata=template_data)
    
    if template.Root.AcroForm:
        template.Root.AcroForm.update(
            pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true"))
        )
        
    for page in template.pages:
        if page.Annots is None: continue
        for annotation in page.Annots:
            if annotation.Subtype == "/Widget":
                key = annotation.T
                if key:
                    field_name = key[1:-1] if key.startswith("(") else str(key)
                    if field_name in data_dict:
                        # Use encode to handle special characters correctly
                        annotation.update(
                            pdfrw.PdfDict(V=pdfrw.PdfString.encode(str(data_dict[field_name])))
                        )
                        annotation.AP = ""
    
    out_stream = io.BytesIO()
    pdfrw.PdfWriter().write(out_stream, template)
    out_stream.seek(0)
    return out_stream

# --- Streamlit UI ---
st.set_page_config(page_title="PDF Auto Generator", page_icon="📄", layout="centered")

st.title("📄 PDF Auto Generator")
st.info("Mobile-friendly version: Upload files and download the results as a ZIP.")

# 1. File Uploads
st.subheader("1. Upload Files")
uploaded_templates = st.file_uploader("Upload PDF Templates", type="pdf", accept_multiple_files=True)
uploaded_data = st.file_uploader("Upload Data File (CSV or XLSX)", type=["csv", "xlsx"])

if uploaded_templates and uploaded_data:
    try:
        # Load Data
        if uploaded_data.name.endswith('.csv'):
            df = pd.read_csv(uploaded_data, dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(uploaded_data, dtype=str, keep_default_na=False)
        
        # Apply the leading zero fix
        df = format_data(df)
        
        st.success(f"Successfully loaded {len(df)} records.")
        
        # 2. Generation Process
        if st.button("🚀 GENERATE ALL PDFs", use_container_width=True):
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                progress_bar = st.progress(0)
                total_steps = len(df) * len(uploaded_templates)
                current_step = 0
                
                for idx, row in df.iterrows():
                    # Filename logic: JobID_Last_First
                    job_id = str(row.get("Job ID", f"record_{idx+1}"))
                    last_name = str(row.get("Last Name", ""))
                    first_name = str(row.get("First Name", ""))
                    
                    # Clean filename characters
                    base_name = f"{job_id}_{last_name}_{first_name}".strip("_").replace(" ", "_")
                    base_name = "".join(c for c in base_name if c not in r'\/:*?"<>|')

                    for tpl in uploaded_templates:
                        tpl.seek(0)
                        
                        # Read template fields
                        reader = pdfrw.PdfReader(fdata=tpl.read())
                        tpl.seek(0)
                        
                        fields = []
                        for page in reader.pages:
                            if page.Annots:
                                for ann in page.Annots:
                                    if ann.Subtype == "/Widget" and ann.T:
                                        fields.append(ann.T[1:-1] if ann.T.startswith("(") else str(ann.T))
                        
                        data_dict = {f: str(row[f]) for f in fields if f in df.columns}
                        
                        # Process PDF
                        pdf_output = fill_pdf(tpl, data_dict)
                        
                        # Add to ZIP naming
                        tpl_short_name = os.path.splitext(tpl.name)[0]
                        final_filename = f"{base_name}_{tpl_short_name}.pdf"
                        zf.writestr(final_filename, pdf_output.getvalue())
                        
                        current_step += 1
                        progress_bar.progress(current_step / total_steps)

            st.balloons()
            
            # 3. Download
            st.download_button(
                label="📥 Download ZIP File",
                data=zip_buffer.getvalue(),
                file_name="Automated_PDFs.zip",
                mime="application/zip",
                use_container_width=True
            )
            
    except Exception as e:
        st.error(f"Critical Error: {e}")
