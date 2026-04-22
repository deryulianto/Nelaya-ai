import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
df = pd.read_csv("data_ocean.csv", parse_dates=["Date"])

# Sort
df = df.sort_values("Date")

# =========================
# 1. SST TIME SERIES
# =========================
plt.figure(figsize=(10,5))
plt.plot(df["Date"], df["SST"], label="SST")
plt.title("Sea Surface Temperature (2024–2026)")
plt.xlabel("Date")
plt.ylabel("°C")
plt.grid()
plt.legend()
plt.savefig("sst_timeseries.png", dpi=300)
plt.close()

# =========================
# 2. CHL TIME SERIES
# =========================
plt.figure(figsize=(10,5))
plt.plot(df["Date"], df["CHL"], label="CHL", color="green")
plt.title("Chlorophyll-a (Productivity)")
plt.xlabel("Date")
plt.ylabel("mg/m³")
plt.grid()
plt.legend()
plt.savefig("chl_timeseries.png", dpi=300)
plt.close()

# =========================
# 3. SCATTER SST vs CHL
# =========================
plt.figure(figsize=(6,6))
sns.scatterplot(x=df["SST"], y=df["CHL"])
plt.title("SST vs CHL Relationship")
plt.xlabel("SST (°C)")
plt.ylabel("CHL (mg/m³)")
plt.grid()
plt.savefig("sst_chl_scatter.png", dpi=300)
plt.close()

print("All plots generated successfully.")
