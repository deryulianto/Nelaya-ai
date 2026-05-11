#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timezone, date
from typing import Any

BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB")

IN_CLUSTER_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_clusters_today.json"
HISTORY_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_cluster_history.json"
OUT_JSON = BASE_DIR / "data" / "upwelling" / "upwelling_temporal_memory_today.json"

MEMORY_WINDOW_DAYS = 7
MATCH_DISTANCE_KM = 80


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return datetime.now().date()


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )

    return 2 * r * math.asin(math.sqrt(a))


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def normalize_cluster(cluster: dict) -> dict:
    centroid = cluster.get("centroid") or {}

    lat = safe_float(centroid.get("lat"))
    lon = safe_float(centroid.get("lon"))

    return {
        "cluster_id": cluster.get("cluster_id"),
        "cluster_type": cluster.get("cluster_type"),
        "primary_zone": cluster.get("primary_zone") or "Zona tidak diketahui",
        "centroid": {
            "lat": lat,
            "lon": lon,
            "coordinate_text": centroid.get("coordinate_text")
            or (f"{lat:.4f}, {lon:.4f}" if lat is not None and lon is not None else None),
        },
        "candidate_count": cluster.get("candidate_count"),
        "candidate_ranks": cluster.get("candidate_ranks") or [],
        "upi_score_max": safe_float(cluster.get("upi_score_max"), 0) or 0,
        "upi_score_mean": safe_float(cluster.get("upi_score_mean"), 0) or 0,
        "core_support_text": cluster.get("core_support_text"),
        "evidence_level": cluster.get("evidence_level"),
        "evidence_label": cluster.get("evidence_label"),
        "dominant_drivers": cluster.get("dominant_drivers") or [],
        "interpretation_radius_km": safe_float(cluster.get("interpretation_radius_km"), 0) or 0,
        "interpretation": cluster.get("interpretation"),
    }


def update_history(today_payload: dict) -> dict:
    history = read_json(HISTORY_JSON, {"records": []})

    generated_at = today_payload.get("generated_at") or now_iso()
    snapshot_date = parse_date(generated_at).isoformat()

    clusters = [
        normalize_cluster(c)
        for c in today_payload.get("clusters", []) or []
        if (c.get("centroid") or {}).get("lat") is not None
        and (c.get("centroid") or {}).get("lon") is not None
    ]

    new_record = {
        "date": snapshot_date,
        "generated_at": generated_at,
        "cluster_count": len(clusters),
        "clusters": clusters,
    }

    records = history.get("records", []) or []

    # Replace record pada tanggal yang sama agar tidak dobel jika script dijalankan berkali-kali.
    records = [r for r in records if r.get("date") != snapshot_date]
    records.append(new_record)

    records.sort(key=lambda r: r.get("date", ""))

    history = {
        "module": "upwelling_cluster_history",
        "version": "0.6",
        "updated_at": now_iso(),
        "records": records[-60:],  # simpan 60 snapshot terakhir supaya file tidak membengkak
    }

    HISTORY_JSON.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    return history


def find_matches(current_cluster: dict, history_records: list[dict], current_date: date) -> list[dict]:
    cur_lat = current_cluster["centroid"]["lat"]
    cur_lon = current_cluster["centroid"]["lon"]
    cur_zone = current_cluster["primary_zone"]

    matches = []

    for record in history_records:
        record_date = parse_date(record.get("date"))

        if record_date >= current_date:
            continue

        age_days = (current_date - record_date).days

        if age_days <= 0 or age_days > MEMORY_WINDOW_DAYS:
            continue

        for old in record.get("clusters", []) or []:
            old_lat = safe_float((old.get("centroid") or {}).get("lat"))
            old_lon = safe_float((old.get("centroid") or {}).get("lon"))

            if old_lat is None or old_lon is None:
                continue

            dist = haversine_km(cur_lat, cur_lon, old_lat, old_lon)
            same_zone = old.get("primary_zone") == cur_zone

            if same_zone or dist <= MATCH_DISTANCE_KM:
                matches.append({
                    "date": record.get("date"),
                    "age_days": age_days,
                    "distance_km": round(dist, 1),
                    "old_cluster_id": old.get("cluster_id"),
                    "old_primary_zone": old.get("primary_zone"),
                    "old_upi_score_max": old.get("upi_score_max"),
                    "same_zone": same_zone,
                })

    # Ambil satu match terbaik per tanggal
    best_by_date = {}
    for m in matches:
        d = m["date"]
        if d not in best_by_date or m["distance_km"] < best_by_date[d]["distance_km"]:
            best_by_date[d] = m

    return sorted(best_by_date.values(), key=lambda x: x["age_days"])


def memory_label(score: float, persistence_days: int) -> tuple[str, str]:
    if score >= 70 and persistence_days >= 4:
        return "persistent_strong", "Persisten kuat"
    if score >= 55 and persistence_days >= 3:
        return "persistent_watch", "Persisten, perlu dipantau"
    if score >= 40 and persistence_days >= 2:
        return "emerging_memory", "Mulai berulang"
    if persistence_days >= 1:
        return "early_memory", "Jejak awal"
    return "new_or_episodic", "Baru/episodik"


def build_temporal_memory(today_payload: dict, history: dict) -> dict:
    generated_at = today_payload.get("generated_at") or now_iso()
    current_date = parse_date(generated_at)

    records = history.get("records", []) or []
    current_clusters = [
        normalize_cluster(c)
        for c in today_payload.get("clusters", []) or []
    ]

    memory_clusters = []

    for cluster in current_clusters:
        matches = find_matches(cluster, records, current_date)
        persistence_days = len({m["date"] for m in matches})

        avg_distance = None
        if matches:
            avg_distance = sum(m["distance_km"] for m in matches) / len(matches)

        current_upi = safe_float(cluster.get("upi_score_max"), 0) or 0

        persistence_score = min(100, (persistence_days / MEMORY_WINDOW_DAYS) * 100)

        if avg_distance is None:
            distance_score = 0
        else:
            distance_score = max(0, 100 - (avg_distance / MATCH_DISTANCE_KM) * 100)

        memory_score = (
            0.45 * persistence_score
            + 0.25 * distance_score
            + 0.30 * current_upi
        )

        level, label = memory_label(memory_score, persistence_days)

        interpretation = build_memory_interpretation(
            cluster=cluster,
            persistence_days=persistence_days,
            avg_distance=avg_distance,
            memory_label=label,
        )

        memory_clusters.append({
            "cluster_id": cluster.get("cluster_id"),
            "primary_zone": cluster.get("primary_zone"),
            "centroid": cluster.get("centroid"),
            "candidate_count": cluster.get("candidate_count"),
            "upi_score_max": cluster.get("upi_score_max"),
            "upi_score_mean": cluster.get("upi_score_mean"),
            "evidence_label": cluster.get("evidence_label"),
            "core_support_text": cluster.get("core_support_text"),
            "dominant_drivers": cluster.get("dominant_drivers"),
            "persistence_days": persistence_days,
            "matched_dates": [m["date"] for m in matches],
            "avg_match_distance_km": round(avg_distance, 1) if avg_distance is not None else None,
            "memory_score": round(memory_score, 1),
            "memory_level": level,
            "memory_label": label,
            "matches": matches,
            "interpretation": interpretation,
        })

    memory_clusters.sort(
        key=lambda c: (
            c.get("memory_score") or 0,
            c.get("upi_score_max") or 0,
        ),
        reverse=True,
    )

    persistent_count = len([
        c for c in memory_clusters
        if c["memory_level"] in ["persistent_strong", "persistent_watch", "emerging_memory"]
    ])

    if not memory_clusters:
        main_message = "Belum ada klaster UPI yang dapat dibaca untuk temporal memory."
    elif persistent_count > 0:
        main_message = (
            f"NELAYA-AI membaca {persistent_count} klaster yang mulai menunjukkan jejak temporal "
            f"dalam jendela {MEMORY_WINDOW_DAYS} hari."
        )
    else:
        main_message = (
            "Klaster UPI hari ini lebih tepat dibaca sebagai sinyal baru atau episodik. "
            "Temporal memory akan menjadi lebih kuat setelah data beberapa hari terkumpul."
        )

    return {
        "module": "upwelling_temporal_memory",
        "version": "0.6",
        "generated_at": now_iso(),
        "source_cluster_file": str(IN_CLUSTER_JSON),
        "history_file": str(HISTORY_JSON),
        "memory_window_days": MEMORY_WINDOW_DAYS,
        "match_distance_km": MATCH_DISTANCE_KM,
        "summary": {
            "active_cluster_count": len(memory_clusters),
            "persistent_cluster_count": persistent_count,
            "main_message": main_message,
        },
        "clusters": memory_clusters,
        "scientific_caution": (
            "Temporal memory membaca apakah klaster kandidat UPI berulang dalam beberapa hari. "
            "Ini bukan bukti final upwelling, melainkan indikasi persistensi spasial-temporal "
            "yang tetap perlu validasi data vertikal atau observasi lapangan."
        ),
    }


def build_memory_interpretation(
    cluster: dict,
    persistence_days: int,
    avg_distance: float | None,
    memory_label: str,
) -> str:
    zone = cluster.get("primary_zone") or "zona ini"

    if persistence_days >= 4:
        return (
            f"Klaster di {zone} menunjukkan jejak temporal yang cukup kuat karena muncul berulang "
            f"selama {persistence_days} hari dalam jendela {MEMORY_WINDOW_DAYS} hari. "
            "Zona ini layak menjadi prioritas validasi lapangan."
        )

    if persistence_days >= 2:
        return (
            f"Klaster di {zone} mulai menunjukkan pengulangan spasial-temporal selama "
            f"{persistence_days} hari. Ini menarik untuk dipantau, tetapi belum cukup untuk disebut persisten kuat."
        )

    if persistence_days == 1:
        return (
            f"Klaster di {zone} memiliki satu jejak kemunculan sebelumnya dalam jendela "
            f"{MEMORY_WINDOW_DAYS} hari. Statusnya masih jejak awal."
        )

    return (
        f"Klaster di {zone} belum memiliki jejak kemunculan sebelumnya dalam jendela "
        f"{MEMORY_WINDOW_DAYS} hari. Untuk saat ini lebih tepat dibaca sebagai sinyal baru atau episodik."
    )


def main():
    if not IN_CLUSTER_JSON.exists():
        raise SystemExit(
            f"Input cluster tidak ditemukan: {IN_CLUSTER_JSON}. "
            "Jalankan scripts/export_upwelling_candidate_clusters.py terlebih dahulu."
        )

    today_payload = json.loads(IN_CLUSTER_JSON.read_text())

    history = update_history(today_payload)
    memory_payload = build_temporal_memory(today_payload, history)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(memory_payload, indent=2, ensure_ascii=False))

    print(f"Wrote: {HISTORY_JSON}")
    print(f"Wrote: {OUT_JSON}")
    print(f"Active clusters: {memory_payload['summary']['active_cluster_count']}")
    print(f"Persistent clusters: {memory_payload['summary']['persistent_cluster_count']}")


if __name__ == "__main__":
    main()
