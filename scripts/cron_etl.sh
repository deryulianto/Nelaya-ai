#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

echo "[ETL] CMEMS..."
python etl/etl_cmems_sst_chl.py || echo "[WARN] CMEMS failed"

echo "[ETL] PO.DAAC MUR..."
python etl/etl_podaac_mur.py || echo "[WARN] MUR failed"

echo "[ETL] ERDDAP buoy..."
python etl/etl_erddap_buoy.py || echo "[WARN] ERDDAP failed"

echo "[ETL] Argo GDAC..."
python etl/etl_argo_gdac.py || echo "[WARN] Argo failed"

echo "[ETL] ✅ done."
