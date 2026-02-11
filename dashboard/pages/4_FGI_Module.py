import streamlit as st
import requests

st.title("🌊 FGI Module (Fish Growth Intelligence)")

try:
    res = requests.get("http://127.0.0.1:8000/fgi/ping")
    st.success(res.json()["message"])
except:
    st.error("FGI module belum aktif atau server belum berjalan.")
