import requests
import json
from pathlib import Path

OUT_PATH = Path("/home/coastalai/NELAYA-AI-LAB/data/decision_inputs/fgi_signal_today.json")

FGI_URL = "http://127.0.0.1:8001/api/v1/fgi/map-grid/latest"


def extract_best_fgi(data):
    features = data.get("features", [])
    if not features:
        return None

    best = None
    best_score = -1

    for f in features:
        props = f.get("properties", {})
        score = props.get("score")

        if score is None:
            continue

        if score > best_score:
            best_score = score
            best = f

    if not best:
        return None

    coords = best["geometry"]["coordinates"]

    return {
        "fgi_score": round(best_score, 4),
        "fgi_label": (
            "tinggi" if best_score >= 0.7 else
            "sedang" if best_score >= 0.4 else
            "rendah"
        ),
        "best_area": {
            "lon": coords[0],
            "lat": coords[1]
        },
        "note": "diambil dari grid maksimum",
        "source": "fgi-map-grid"
    }


def main():
    try:
        res = requests.get(FGI_URL, timeout=10)
        res.raise_for_status()
        data = res.json()

        best = extract_best_fgi(data)

        if not best:
            raise Exception("FGI kosong")

        out = {
            "ok": True,
            **best
        }

    except Exception as e:
        out = {
            "ok": False,
            "fgi_score": 0.0,
            "fgi_label": "tidak tersedia",
            "best_area": None,
            "note": f"Gagal sync FGI: {e}",
            "source": "fallback"
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))

    print("[OK] FGI signal updated:", OUT_PATH)


if __name__ == "__main__":
    main()
