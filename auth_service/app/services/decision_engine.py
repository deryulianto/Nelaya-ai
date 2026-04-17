import json
from pathlib import Path
from typing import Dict, Any


OCEAN_SIGNAL_PATH = Path("/home/coastalai/NELAYA-AI-LAB/data/decision_inputs/ocean_signal_today.json")
FGI_SIGNAL_PATH = Path("/home/coastalai/NELAYA-AI-LAB/data/decision_inputs/fgi_signal_today.json")
MARKETPLACE_INSIGHT_LATEST_PATH = Path("/home/coastalai/NELAYA-AI-LAB/data/marketplace_insights/latest.json")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _pasar_score_from_ratio(ratio: float) -> int:
    if ratio > 2:
        return 3
    if ratio >= 1:
        return 2
    return 1


def _fgi_category(fgi_score: float) -> str:
    if fgi_score >= 0.7:
        return "tinggi"
    if fgi_score >= 0.4:
        return "sedang"
    return "rendah"


def _fgi_adjustment(fgi_score: float | None, fgi_ok: bool) -> int:
    """
    Penyesuaian ringan agar FGI ikut memengaruhi pembacaan laut:
    - tinggi  -> +1
    - sedang  ->  0
    - rendah  -> -1
    - tidak tersedia -> 0
    """
    if not fgi_ok or fgi_score is None:
        return 0
    if fgi_score >= 0.7:
        return 1
    if fgi_score >= 0.4:
        return 0
    return -1


def _decision_label(laut_score: int, pasar_score: int) -> str:
    total = laut_score + pasar_score
    if total >= 6:
        return "Peluang sangat kuat"
    if total == 5:
        return "Peluang kuat"
    if total == 4:
        return "Peluang cukup baik"
    if total == 3:
        return "Peluang selektif"
    return "Belum kuat"


def _signals_text(laut_score: int, ocean_label: str, market_signals: list[str]):
    if laut_score == 3:
        laut_text = f"{ocean_label.capitalize()}."
    elif laut_score == 2:
        laut_text = f"{ocean_label.capitalize()}, tetapi pembacaan masih selektif."
    else:
        laut_text = f"{ocean_label.capitalize()}, sehingga keputusan operasional perlu lebih hati-hati."

    pasar_text = market_signals[0] if market_signals else "Sinyal pasar belum cukup kuat terbaca."
    return laut_text, pasar_text


def _decision_narrative(
    laut_score: int,
    pasar_score: int,
    ocean_label: str,
    fgi_score: float | None,
    fgi_label: str,
    fgi_ok: bool,
) -> str:
    if fgi_ok and fgi_score is not None:
        fgi_part = f"FGI hari ini berada pada level {fgi_label} ({fgi_score:.2f}) sebagai indikasi peluang area."
    else:
        fgi_part = "FGI hari ini belum tersedia sehingga pembacaan peluang area masih mengandalkan kondisi laut umum."

    if laut_score == 3 and pasar_score == 3:
        return (
            "Laut dan pasar sama-sama memberi sinyal yang mendukung. "
            + fgi_part + " "
            + "Sementara pasar menunjukkan tekanan permintaan yang lebih cepat daripada suplai. "
            + "Keputusan operasional dapat dibaca sebagai peluang yang sangat kuat, dengan catatan mutu hasil tangkap, "
            + "konsistensi listing, dan ketertelusuran tetap dijaga."
        )

    if laut_score == 3 and pasar_score == 2:
        return (
            "Laut memberi dukungan yang baik. "
            + fgi_part + " "
            + "Sementara pasar mulai menunjukkan minat yang sehat. "
            + "Keputusan hari ini dapat dibaca cukup positif, tetapi nilai hasil tangkap tetap sangat bergantung "
            + "pada mutu dan kejelasan informasi listing."
        )

    if laut_score == 3 and pasar_score == 1:
        return (
            "Laut memberi dukungan yang baik. "
            + fgi_part + " "
            + "Namun pasar belum sekuat sisi suplai. "
            + "Dalam kondisi seperti ini, keputusan tetap mungkin diambil, namun akses pasar dan kualitas informasi "
            + "tetap menjadi kunci."
        )

    if laut_score == 2 and pasar_score == 3:
        return (
            "Pasar terlihat lebih kuat daripada sisi laut. "
            + fgi_part + " "
            + "Keputusan tetap dapat dibaca baik, tetapi lebih selektif karena dukungan spasial belum sepenuhnya kuat. "
            + "Mutu hasil tangkap dan efisiensi operasi menjadi sangat penting."
        )

    if laut_score == 2 and pasar_score == 2:
        return (
            "Laut dan pasar sama-sama memberi sinyal menengah. "
            + fgi_part + " "
            + "Peluang tetap ada tetapi keputusan terbaik adalah membaca kesempatan secara selektif, "
            + "menjaga mutu hasil tangkap, dan memastikan informasi listing tetap konsisten."
        )

    if laut_score == 1 and pasar_score == 3:
        return (
            "Pasar terlihat kuat, tetapi laut belum memberi dukungan optimal. "
            + fgi_part + " "
            + "Keputusan operasional perlu lebih hati-hati agar biaya dan risiko tidak menggerus nilai."
        )

    return (
        "Baik laut maupun pasar belum memberi dukungan yang cukup kuat secara bersamaan. "
        + fgi_part + " "
        + "Keputusan operasional perlu dibaca lebih hati-hati dan selektif."
    )


def build_decision_today() -> Dict[str, Any]:
    ocean = _read_json(OCEAN_SIGNAL_PATH)
    market = _read_json(MARKETPLACE_INSIGHT_LATEST_PATH)

    try:
        fgi = _read_json(FGI_SIGNAL_PATH)
    except Exception:
        fgi = {
            "ok": False,
            "fgi_score": 0.0,
            "fgi_label": "tidak tersedia",
            "best_area": None,
            "note": "FGI harian belum tersedia",
            "source": "fallback",
        }

    base_laut_score = int(ocean.get("laut_score") or 1)
    ocean_label = str(ocean.get("label") or "laut belum terbaca kuat")
    ocean_note = str(ocean.get("note") or "")

    fgi_ok = bool(fgi.get("ok"))
    fgi_score = float(fgi.get("fgi_score") or 0.0) if fgi_ok else None
    fgi_label = str(fgi.get("fgi_label") or _fgi_category(fgi_score or 0.0))
    fgi_area = fgi.get("best_area")
    fgi_note = str(fgi.get("note") or "")
    fgi_adjust = _fgi_adjustment(fgi_score, fgi_ok)

    # base_laut_score dari kondisi laut umum
    # fgi_adjust memberi penalti ringan bila FGI rendah, bonus ringan bila FGI tinggi
    laut_score = max(1, min(3, base_laut_score + fgi_adjust))

    snapshot = market.get("snapshot") or {}
    ratio = float(snapshot.get("demand_supply_ratio") or 0)
    pasar_score = _pasar_score_from_ratio(ratio)

    label = _decision_label(laut_score, pasar_score)
    laut_text, pasar_text = _signals_text(
        laut_score,
        ocean_label,
        list(market.get("signals") or []),
    )

    narrative = _decision_narrative(
        laut_score,
        pasar_score,
        ocean_label,
        fgi_score,
        fgi_label,
        fgi_ok,
    )

    return {
        "ok": True,
        "date": ocean.get("date") or market.get("date"),
        "decision": {
            "label": label,
            "score": laut_score + pasar_score,
            "laut_score": laut_score,
            "pasar_score": pasar_score,
        },
        "signals": {
            "laut": laut_text,
            "pasar": pasar_text,
            "ocean_note": ocean_note,
        },
        "fgi": {
            "score": round(fgi_score, 4) if fgi_score is not None else None,
            "category": fgi_label,
            "best_area": fgi_area,
            "note": fgi_note,
            "source": fgi.get("source"),
            "adjustment": fgi_adjust,
        },
        "market_snapshot": snapshot,
        "narrative": narrative,
        "disclaimer": "FGI adalah indikator peluang area berbasis kondisi laut, bukan jaminan hasil tangkap.",
    }