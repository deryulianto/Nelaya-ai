
import streamlit as st
st.set_page_config(page_title="NELAYA‑AI", layout="wide")
st.title("NELAYA‑AI — Frontier Ocean Platform")
st.write("Halo! Ini adalah landing sederhana. API healthcheck ada di `/api/v1/health`.")

with st.expander("Checklist awal"):
    st.markdown(
        "- [x] Repo & README  
"
        "- [x] Health API  
"
        "- [x] Streamlit landing  
"
        "- [ ] DVC + MinIO/S3  
"
        "- [ ] Model registry  
"
        "- [ ] CI/CD ke server (self-hosted runner)"
    )
