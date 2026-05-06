import json
from pathlib import Path
import numpy as np

DATA_PATH = Path("data/fgi_feedback")

def load_feedback():
    all_data = []
    for f in DATA_PATH.glob("*.json"):
        all_data.extend(json.loads(f.read_text()))
    return all_data


def compute_trip_success_rate():
    data = load_feedback()
    if not data:
        return None

    y = [d["trip_success"] for d in data]

    return {
        "n": len(y),
        "mean": float(np.mean(y)),
    }
