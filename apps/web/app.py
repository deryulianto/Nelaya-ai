import os
import json
import urllib.request
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="NELAYA-AI", layout="wide")
st.title("NELAYA-AI — Frontier Ocean Platform")
st.write("Halo! Ini landing sederhana. API healthcheck ada di `/api/v1/health`.")

col1, col2 = st.columns([1,3])
with col1:
    if st.button("🔄 Ping API"):
        try:
            with urllib.request.urlopen(f"{API_BASE}/api/v1/health", timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            st.success(f"OK: {data}")
        except Exception as e:
            st.error(f"Gagal ping: {e}")
with col2:
    st.text_input("API Base URL", value=API_BASE, disabled=True)

with st.expander("Checklist awal"):
    st.markdown("""
- [x] Repo & README  
- [x] Health API  
- [x] Streamlit landing  
- [ ] DVC + MinIO/S3  
- [ ] Model registry  
- [ ] CI/CD ke server (self-hosted runner)
""")

st.markdown("[Buka API docs →](http://localhost:8000/docs)")
