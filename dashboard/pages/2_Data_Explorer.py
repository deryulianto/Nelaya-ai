import streamlit as st
from dashboard.utils.api_client import get_datasets

st.title("📊 Data Explorer")
st.markdown("Lihat dataset yang tersedia di sistem NELAYA-AI.")

data = get_datasets()
st.json(data)
