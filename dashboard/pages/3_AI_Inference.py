import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from dashboard.utils.api_client import get_prediction

st.title("🤖 AI Inference")
st.markdown("Masukkan parameter laut untuk memprediksi *Fish Growth Index (FGI)*")

col1, col2, col3 = st.columns(3)
temp = col1.number_input("🌡️ Suhu Laut (°C)", 0.0, 40.0, 28.0)
sal = col2.number_input("🧂 Salinitas (PSU)", 0.0, 40.0, 33.0)
chl = col3.number_input("🌿 Klorofil (mg/m³)", 0.0, 10.0, 0.5)

if st.button("🔮 Prediksi FGI"):
    with st.spinner("Menghitung prediksi..."):
        result = get_prediction(temp, sal, chl)
        if "FGI_Score" in result:
            st.success(f"**FGI Score:** {result['FGI_Score']} — *{result['Category']}*")
        else:
            st.error(result.get("error", "Gagal mendapatkan prediksi."))

