import requests

API_BASE = "http://127.0.0.1:8000"

def get_status():
    try:
        res = requests.get(f"{API_BASE}/system/status", timeout=3)
        return res.json()
    except:
        return {"error": "Backend API belum aktif. Jalankan FastAPI server dulu."}

def get_datasets():
    res = requests.get(f"{API_BASE}/data/list")
    return res.json()



def get_prediction(temp: float, sal: float, chl: float):
    url = f"{API_BASE}/fgi/predict"
    payload = {"temp": temp, "sal": sal, "chl": chl}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Request failed: {response.status_code}"}
