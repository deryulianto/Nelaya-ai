from pathlib import Path
import json

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/upwelling", tags=["upwelling"])

BASE_DIR = Path("/home/coastalai/NELAYA-AI-LAB")
UPWELLING_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_watch_today.json"
UPWELLING_GEOJSON_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_candidates_today.geojson"
UPWELLING_BUFFER_GEOJSON_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_buffers_today.geojson"
UPWELLING_CLUSTER_JSON_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_clusters_today.json"
UPWELLING_CLUSTER_GEOJSON_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_candidate_clusters_today.geojson"
UPWELLING_TEMPORAL_MEMORY_FILE = BASE_DIR / "data" / "upwelling" / "upwelling_temporal_memory_today.json"


def read_json_file(path: Path, label: str):
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{label} belum tersedia. File tidak ditemukan: {path}",
        )

    try:
        payload = json.loads(path.read_text())

        if isinstance(payload, dict):
            payload["_debug_source_file"] = str(path)
            payload["_debug_exists"] = path.exists()
            payload["_debug_file_size"] = path.stat().st_size
            payload["_debug_feature_count"] = len(payload.get("features", []))

        return payload

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal membaca {label}: {e}",
        )


@router.get("/watch/today")
def get_upwelling_watch_today():
    return read_json_file(UPWELLING_FILE, "Upwelling Watch data")


@router.get("/candidates/geojson")
def get_upwelling_candidates_geojson():
    return read_json_file(UPWELLING_GEOJSON_FILE, "GeoJSON kandidat upwelling")


@router.get("/candidates/buffers/geojson")
def get_upwelling_candidate_buffers_geojson():
    return read_json_file(
        UPWELLING_BUFFER_GEOJSON_FILE,
        "GeoJSON buffer kandidat upwelling",
    )

@router.get("/candidates/clusters")
def get_upwelling_candidate_clusters():
    return read_json_file(
        UPWELLING_CLUSTER_JSON_FILE,
        "Cluster kandidat upwelling",
    )


@router.get("/candidates/clusters/geojson")
def get_upwelling_candidate_clusters_geojson():
    return read_json_file(
        UPWELLING_CLUSTER_GEOJSON_FILE,
        "GeoJSON cluster kandidat upwelling",
    )

@router.get("/candidates/temporal-memory")
def get_upwelling_temporal_memory():
    return read_json_file(
        UPWELLING_TEMPORAL_MEMORY_FILE,
        "Temporal memory kandidat upwelling",
    )