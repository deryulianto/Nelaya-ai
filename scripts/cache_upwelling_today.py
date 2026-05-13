#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError, HTTPError
from urllib.request import urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ENDPOINT = "http://127.0.0.1:8001/api/v1/upwelling/candidates/temporal-memory"
OUT_FILE = ROOT / "data/upwelling/upwelling_candidates_today.json"


def now_jakarta() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).isoformat()


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def normalize_score(value: Any) -> Optional[float]:
    x = to_float(value)
    if x is None:
        return None

    # Endpoint lama bisa memakai skala 0–100, Feature Store memakai 0–1.
    if x > 1.0:
        x = x / 100.0

    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def label_from_score(score: Optional[float]) -> str:
    if score is None:
        return "tidak_tersedia"
    if score >= 0.70:
        return "kuat"
    if score >= 0.45:
        return "sedang"
    if score >= 0.20:
        return "lemah"
    return "sangat_lemah"


def fetch_json(endpoint: str) -> dict[str, Any]:
    try:
        with urlopen(endpoint, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error from {endpoint}: {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to {endpoint}: {exc}") from exc


def main() -> None:
    endpoint = os.getenv("UPWELLING_ENDPOINT", DEFAULT_ENDPOINT)
    payload = fetch_json(endpoint)

    clusters = payload.get("clusters") or []
    first = clusters[0] if clusters else {}

    summary = payload.get("summary") or {}

    raw_memory_score = (
        first.get("memory_score")
        or first.get("upwelling_score")
        or summary.get("memory_score")
        or summary.get("upwelling_score")
    )

    upwelling_score = normalize_score(raw_memory_score)

    primary_zone = (
        first.get("primary_zone")
        or summary.get("primary_zone")
        or summary.get("main_zone")
    )

    memory_label = (
        first.get("memory_label")
        or summary.get("memory_label")
        or label_from_score(upwelling_score)
    )

    persistence_days = (
        first.get("persistence_days")
        or summary.get("persistence_days")
        or 0
    )

    out = {
        "module": "upwelling_candidates_cache",
        "version": "0.1",
        "generated_at": now_jakarta(),
        "source_endpoint": endpoint,

        # Field utama yang langsung bisa dibaca FGI Feature Store
        "upwelling_score": upwelling_score,
        "upwelling_score_raw": raw_memory_score,
        "label": label_from_score(upwelling_score),

        "summary": {
            "upwelling_score": upwelling_score,
            "upwelling_score_raw": raw_memory_score,
            "active_cluster_count": summary.get("active_cluster_count"),
            "persistent_cluster_count": summary.get("persistent_cluster_count"),
            "primary_zone": primary_zone,
            "persistence_days": persistence_days,
            "memory_label": memory_label,
            "main_message": summary.get("main_message"),
        },

        "primary_cluster": first,
        "clusters": clusters,

        "notes": [
            "Skor upwelling dinormalisasi ke skala 0–1 untuk FGI Feature Store.",
            "Jika endpoint sumber memakai skala 0–100, nilai otomatis dibagi 100.",
            "Layer ini adalah indikator proses produktivitas/upwelling, bukan jaminan keberadaan ikan.",
        ],

        "raw_response": payload,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK: wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
