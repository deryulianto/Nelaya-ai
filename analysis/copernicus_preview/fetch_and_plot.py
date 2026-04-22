import requests
import pandas as pd
import matplotlib.pyplot as plt

BASE = "http://127.0.0.1:8001/api/v1/fgi/time-series/daily-mean?days=120"

def fetch_metric(metric_name):
    url = f"{BASE}&metric={metric_name}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    if "points" not in data:
        raise ValueError(f"{metric_name}: format tidak sesuai")

    df = pd.DataFrame(data["points"])

    df = df.rename(columns={
        "date": "Date",
        "mean": metric_name.upper()
    })

    df["Date"] = pd.to_datetime(df["Date"])
    return df

# =========================
# Ambil data
# =========================
df_sst = fetch_metric("sst")
df_chl = fetch_metric("chl")

# =========================
# Gabungkan
# =========================
df = pd.merge(df_sst, df_chl, on="Date", how="inner")
df = df.sort_values("Date")

print("DATA GABUNG:")
print(df.head())

# Simpan CSV
df.to_csv("sst_chl_combined.csv", index=False)

# =========================
# GRAFIK 1: SST
# =========================
plt.figure(figsize=(12,5))
plt.plot(df["Date"], df["SST"])
plt.title("Sea Surface Temperature (Aceh)")
plt.xlabel("Date")
plt.ylabel("°C")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("sst.png", dpi=300)
plt.close()

# =========================
# GRAFIK 2: CHL
# =========================
plt.figure(figsize=(12,5))
plt.plot(df["Date"], df["CHL"])
plt.title("Chlorophyll-a (Productivity)")
plt.xlabel("Date")
plt.ylabel("mg/m³")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("chl.png", dpi=300)
plt.close()

# =========================
# GRAFIK 3: SCATTER (PALING PENTING)
# =========================
plt.figure(figsize=(6,6))
plt.scatter(df["SST"], df["CHL"])
plt.xlabel("SST (°C)")
plt.ylabel("CHL (mg/m³)")
plt.title("SST vs CHL Relationship")
plt.tight_layout()
plt.savefig("sst_chl_scatter.png", dpi=300)
plt.close()

print("✅ SELESAI TOTAL")
print("File:")
print("- sst.png")
print("- chl.png")
print("- sst_chl_scatter.png")
print("- sst_chl_combined.csv")
