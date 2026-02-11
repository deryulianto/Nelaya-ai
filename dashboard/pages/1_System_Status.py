import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from dashboard.utils.api_client import get_status

st.title("⚙️ System Status Monitor")
st.markdown("Pantau kondisi CPU, RAM, dan OS dari backend server FastAPI.")

status = get_status()
st.json(status)
