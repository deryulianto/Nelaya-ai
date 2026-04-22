import requests
import pandas as pd
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8001/api/v1/signals/today"

# jumlah hari mundur
DAYS_BACK = 120  # bisa ubah jadi 365 / 730

data_list = []

for i in range(DAYS_BACK):
    date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    
    try:
        url = f"{BASE_URL}?date={date}"
        r = requests.get(url, timeout=10)

        if r.status_code == 200:
            d = r.json()

            data_list.append({
                "Date": date,
                "SST": d.get("sst"),
                "CHL": d.get("chl"),
                "Wind": d.get("wind"),
                "Wave": d.get("wave")
            })

            print(f"[OK] {date}")
        else:
            print(f"[MISS] {date}")

    except Exception as e:
        print(f"[ERR] {date}: {e}")

# buat dataframe
df = pd.DataFrame(data_list)
df = df.sort_values("Date")

# simpan
df.to_csv("data_ocean.csv", index=False)

print("✅ data_ocean.csv berhasil dibuat")
