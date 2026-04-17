import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

OUT_DIR = Path("/home/coastalai/NELAYA-AI-LAB/data/decision_inputs")
OUT_PATH = OUT_DIR / "fgi_signal_today.json"

# Ganti jika nanti endpoint real kamu berbeda.
# Fallback aman: pakai endpoint public/internal yang sudah hidup.
FGI_API_URL = "http://127.0.0.1:8001/api/v1/fgi/recommendations/summary"

# Jika endpoint di atas belum ada, script akan fallback ke dummy-safe mode.
# Kamu bisa ganti ke endpoint yang memang sudah tersedia, mis.:
# http://127.0.0.1:8001/api/v1/fgi/recommendations/today
# http://127.0.0.1:8001/api/v1/fgi/score/today
# atau endpoint ringkas lain yang kamu punya.


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _ensure_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _read_url_json(url: str):
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text)


def _normalize_fgi_payload(payload: dict) -> dict:
    """
    Normalisasi longgar supaya tahan terhadap shape payload FGI yang berbeda-beda.
    Prioritas:
    - fgi_score
    - best_score
    - score
    - max_score
    """
    score = None
    area = None
    label = None
    note = None

    for key in ("fgi_score", "best_score", "score", "max_score"):
        if key in payload and payload[key] is not None:
            try:
                score = float(payload[key])
                break
            except Exception:
                pass

    # kalau score ada di nested object
    if score is None:
        for parent_key in ("data", "summary", "best", "top", "result"):
            obj = payload.get(parent_key)
            if isinstance(obj, dict):
                for key in ("fgi_score", "best_score", "score", "max_score"):
                    if key in obj and obj[key] is not None:
                        try:
                            score = float(obj[key])
                            break
                        except Exception:
                            pass
            if score is not None:
                break

    # cari area
    for key in ("best_area", "area", "grid_id", "location", "top_area"):
        if payload.get(key):
            area = str(payload[key])
            break

    if area is None:
        for parent_key in ("data", "summary", "best", "top", "result"):
            obj = payload.get(parent_key)
            if isinstance(obj, dict):
                for key in ("best_area", "area", "grid_id", "location", "top_area"):
                    if obj.get(key):
                        area = str(obj[key])
                        break
            if area is not None:
                break

    if score is None:
        score = 0.0

    if score >= 0.7:
        label = "tinggi"
        note = "indikasi area potensial berbasis kondisi laut terlihat cukup kuat"
    elif score >= 0.4:
        label = "sedang"
        note = "indikasi area potensial ada, tetapi masih perlu dibaca secara selektif"
    else:
        label = "rendah"
        note = "indikasi area potensial belum cukup kuat"

    return {
        "ok": True,
        "date": _today_str(),
        "fgi_score": round(score, 4),
        "fgi_label": label,
        "best_area": area,
        "note": note,
        "source": "fgi_api",
        "generated_at": _utcnow_iso(),
        "raw": payload,
    }


def _fallback_doc(reason: str) -> dict:
    return {
        "ok": False,
        "date": _today_str(),
        "fgi_score": 0.0,
        "fgi_label": "tidak tersedia",
        "best_area": None,
        "note": f"FGI harian belum berhasil disinkronkan: {reason}",
        "source": "fallback",
        "generated_at": _utcnow_iso(),
    }


def main():
    _ensure_dir()

    try:
        payload = _read_url_json(FGI_API_URL)
        doc = _normalize_fgi_payload(payload)
    except HTTPError as e:
        doc = _fallback_doc(f"HTTP {e.code}")
    except URLError as e:
        doc = _fallback_doc(str(e.reason))
    except Exception as e:
        doc = _fallback_doc(str(e))

    OUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
