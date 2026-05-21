#!/usr/bin/env python3
"""
Enrich earth_signals_today.json with a transparent Data Trust Layer.

Tujuan:
- Menambahkan data_quality per variabel utama: SST, CHL, wind, wave, salinity, SSH, FGI.
- Menambahkan ringkasan data_trust untuk dibaca frontend NELAYA-AI.
- Aman dipakai sebagai post-processing setelah build_earth_signals_from_raw.py.
- Tidak merusak field lama; hanya menambah/memperbarui field data_quality dan data_trust.

Cara pakai:
python scripts/enrich_earth_signals_data_trust.py \
  --input /home/coastalai/NELAYA-AI-LAB/data/earth/earth_signals_today.json

Opsional:
python scripts/enrich_earth_signals_data_trust.py --input data/earth/earth_signals_today.json --backup
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("/home/coastalai/NELAYA-AI-LAB/data/earth/earth_signals_today.json")


METRIC_CONFIG = {
    "sst": {
        "label": "SST",
        "unit": "°C",
        "value_keys": ["sst", "sst_c", "sst_mean_c", "sst_value"],
        "date_keys": ["sst_source_date", "sst_date", "sst_snapshot_date", "source_date_sst"],
        "lag_keys": ["sst_lag_days", "lag_days_sst"],
        "ratio_keys": ["sst_valid_ratio", "valid_ratio_sst"],
        "role": "thermal habitat signal",
    },
    "chl": {
        "label": "CHL",
        "unit": "mg/m³",
        "value_keys": ["chl", "chl_mg_m3", "chl_mean_mg_m3", "chlorophyll", "chlorophyll_mg_m3"],
        "date_keys": ["chl_source_date", "chl_date", "chl_snapshot_date", "source_date_chl"],
        "lag_keys": ["chl_lag_days", "lag_days_chl"],
        "ratio_keys": ["chl_valid_ratio", "valid_ratio_chl"],
        "role": "surface productivity signal",
    },
    "wind": {
        "label": "Angin",
        "unit": "m/s",
        "value_keys": ["wind", "wind_ms", "wind_speed_ms", "wind_mean_ms"],
        "date_keys": ["wind_source_date", "wind_date", "wind_snapshot_date", "source_date_wind"],
        "lag_keys": ["wind_lag_days", "lag_days_wind"],
        "ratio_keys": ["wind_valid_ratio", "valid_ratio_wind"],
        "role": "operational sea condition",
    },
    "wave": {
        "label": "Gelombang",
        "unit": "m",
        "value_keys": ["wave", "wave_m", "wave_height_m", "hs_m", "swh_m"],
        "date_keys": ["wave_source_date", "wave_date", "wave_snapshot_date", "source_date_wave"],
        "lag_keys": ["wave_lag_days", "lag_days_wave"],
        "ratio_keys": ["wave_valid_ratio", "valid_ratio_wave"],
        "role": "safety and operability signal",
    },
    "sal": {
        "label": "Salinitas",
        "unit": "PSU",
        "value_keys": ["sal", "salinity", "salinity_psu", "sss_psu"],
        "date_keys": ["sal_source_date", "salinity_source_date", "sal_date", "source_date_salinity"],
        "lag_keys": ["sal_lag_days", "salinity_lag_days", "lag_days_salinity"],
        "ratio_keys": ["sal_valid_ratio", "salinity_valid_ratio", "valid_ratio_salinity"],
        "role": "water mass stability signal",
    },
    "ssh": {
        "label": "SSH",
        "unit": "cm",
        "value_keys": ["ssh", "ssh_cm", "ssh_mean_cm", "sea_surface_height_cm"],
        "date_keys": ["ssh_source_date", "ssh_date", "ssh_snapshot_date", "source_date_ssh"],
        "lag_keys": ["ssh_lag_days", "lag_days_ssh"],
        "ratio_keys": ["ssh_valid_ratio", "valid_ratio_ssh"],
        "role": "relative sea level / dynamic height signal",
    },
    "fgi": {
        "label": "FGI",
        "unit": "score",
        "value_keys": ["final", "fgi_final", "fgi", "score"],
        "date_keys": ["fgi_source_date", "fgi_date", "snapshot_date", "date"],
        "lag_keys": ["fgi_lag_days", "lag_days_fgi"],
        "ratio_keys": ["fgi_valid_ratio", "valid_ratio_fgi"],
        "role": "indicative fish-ground environment score",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--today", default=None, help="Override today date, format YYYY-MM-DD")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def deep_get(mapping: dict[str, Any], path: str) -> Any:
    current: Any = mapping
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def first_value(*containers: dict[str, Any], keys: list[str]) -> Any:
    search_keys = []
    for key in keys:
        search_keys.append(key)
        search_keys.append(f"metrics.{key}")
        search_keys.append(f"signals.{key}")
        search_keys.append(f"data.{key}")
        search_keys.append(f"data_quality.{key}.{key}")
        search_keys.append(f"data_quality.{key}.value")

    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in search_keys:
            value = deep_get(container, key)
            if value is not None:
                return value
    return None


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def normalize_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    # Handle common ISO formats, including Z.
    cleaned = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date().isoformat()
    except Exception:
        pass

    # Fallback: first 10 chars if looks like YYYY-MM-DD.
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def parse_date(value: Any) -> date | None:
    normalized = normalize_date(value)
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized[:10])
    except Exception:
        return None


def infer_lag_days(source_date: str | None, today_date: date) -> int | None:
    d = parse_date(source_date)
    if d is None:
        return None
    return max((today_date - d).days, 0)


def status_from_lag(lag_days: int | None) -> tuple[str, str]:
    if lag_days is None:
        return ("unknown", "Tanggal sumber belum tersedia")
    if lag_days <= 0:
        return ("fresh", "Data terbaru untuk tanggal pembacaan")
    if lag_days == 1:
        return ("lag_1_day", "Data terlambat 1 hari")
    if lag_days <= 3:
        return ("lag_few_days", f"Data terlambat {lag_days} hari")
    return ("stale", f"Data cukup lama: tertinggal {lag_days} hari")


def confidence_from_quality(value: float | None, lag_days: int | None, valid_ratio: float | None) -> float:
    score = 0.90

    if value is None:
        score -= 0.35

    if lag_days is None:
        score -= 0.12
    elif lag_days == 0:
        score -= 0.00
    elif lag_days == 1:
        score -= 0.05
    elif lag_days <= 3:
        score -= 0.12
    else:
        score -= 0.25

    if valid_ratio is None:
        score -= 0.05
    elif valid_ratio < 0.25:
        score -= 0.25
    elif valid_ratio < 0.50:
        score -= 0.18
    elif valid_ratio < 0.70:
        score -= 0.10
    elif valid_ratio < 0.85:
        score -= 0.05

    return round(min(max(score, 0.20), 0.98), 2)


def classify_confidence(score: float) -> str:
    if score >= 0.85:
        return "tinggi"
    if score >= 0.65:
        return "sedang"
    return "rendah"


def build_metric_quality(root: dict[str, Any], key: str, cfg: dict[str, Any], today_date: date) -> dict[str, Any]:
    metrics = root.get("metrics") if isinstance(root.get("metrics"), dict) else {}
    signals = root.get("signals") if isinstance(root.get("signals"), dict) else {}
    fgi = root.get("fgi") if isinstance(root.get("fgi"), dict) else {}
    existing_q = root.get("data_quality") if isinstance(root.get("data_quality"), dict) else {}

    extra_container = fgi if key == "fgi" else {}

    value = as_float(first_value(root, metrics, signals, extra_container, keys=cfg["value_keys"]))
    source_date = normalize_date(first_value(root, metrics, signals, extra_container, existing_q, keys=cfg["date_keys"]))
    lag_days_raw = first_value(root, metrics, signals, extra_container, existing_q, keys=cfg["lag_keys"])
    valid_ratio_raw = first_value(root, metrics, signals, extra_container, existing_q, keys=cfg["ratio_keys"])

    lag_days = as_float(lag_days_raw)
    if lag_days is not None:
        lag_days = int(lag_days)
    else:
        lag_days = infer_lag_days(source_date, today_date)

    valid_ratio = as_float(valid_ratio_raw)
    if valid_ratio is not None and valid_ratio > 1:
        # Support ratio reported as percent.
        valid_ratio = valid_ratio / 100.0
    if valid_ratio is not None:
        valid_ratio = round(min(max(valid_ratio, 0.0), 1.0), 3)

    status, status_note = status_from_lag(lag_days)
    confidence = confidence_from_quality(value, lag_days, valid_ratio)

    notes = []
    notes.append(status_note)
    if valid_ratio is not None:
        notes.append(f"Cakupan data {round(valid_ratio * 100)}%")
    else:
        notes.append("Cakupan data belum dihitung")
    if key in {"iod", "enso"}:
        notes.append("Konteks regional, bukan prediksi harian lokal")

    return {
        "key": key,
        "label": cfg["label"],
        "value": value,
        "unit": cfg["unit"],
        "source_date": source_date,
        "lag_days": lag_days,
        "valid_ratio": valid_ratio,
        "status": status,
        "confidence": confidence,
        "confidence_label": classify_confidence(confidence),
        "role": cfg["role"],
        "note": " · ".join(notes),
    }


def build_data_trust(root: dict[str, Any], today_date: date) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    for key, cfg in METRIC_CONFIG.items():
        quality[key] = build_metric_quality(root, key, cfg, today_date)

    confidence_values = [
        item["confidence"]
        for item in quality.values()
        if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
    ]
    overall = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0

    stale_keys = [
        item["label"]
        for item in quality.values()
        if item.get("status") in {"lag_few_days", "stale", "unknown"}
    ]

    if overall >= 0.85:
        level = "high"
        summary = "Data utama cukup kuat untuk pembacaan harian, tetap perlu kehati-hatian operasional."
    elif overall >= 0.65:
        level = "moderate"
        summary = "Data cukup memadai, tetapi beberapa variabel perlu dibaca dengan kehati-hatian."
    else:
        level = "low"
        summary = "Data terbatas atau sebagian tertinggal; hasil sebaiknya dipakai sebagai indikasi awal."

    if stale_keys:
        summary += f" Perhatian khusus: {', '.join(stale_keys)}."

    return {
        "version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": today_date.isoformat(),
        "overall_confidence": overall,
        "overall_confidence_label": classify_confidence(overall),
        "level": level,
        "summary": summary,
        "metrics": quality,
    }


def main() -> None:
    args = parse_args()
    path: Path = args.input

    root = load_json(path)

    today_text = (
        args.today
        or normalize_date(root.get("snapshot_date"))
        or normalize_date(root.get("latest_available_date"))
        or normalize_date(root.get("date"))
        or normalize_date(root.get("generated_at"))
        or date.today().isoformat()
    )
    today_date = parse_date(today_text) or date.today()

    if args.backup:
        backup_path = path.with_suffix(path.suffix + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup_path)
        print(f"Backup dibuat: {backup_path}")

    data_trust = build_data_trust(root, today_date)

    # Keep a compact old-compatible object and a richer new object.
    root["data_trust"] = data_trust
    root["data_quality"] = data_trust["metrics"]

    save_json(path, root)

    print("✅ Data Trust Layer berhasil ditambahkan")
    print(f"File: {path}")
    print(f"Snapshot: {data_trust['snapshot_date']}")
    print(f"Overall confidence: {data_trust['overall_confidence']} ({data_trust['overall_confidence_label']})")
    print(data_trust["summary"])


if __name__ == "__main__":
    main()
