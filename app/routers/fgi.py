from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, date
import json
import csv
import threading
from typing import Any, Dict
import inspect
import time


import numpy as np
from fastapi import APIRouter, HTTPException

# --- pydantic v1/v2 compatibility ---
try:
    # pydantic v2
    from pydantic import BaseModel, Field, field_validator
except Exception:
    # pydantic v1 fallback
    from pydantic import BaseModel, Field, validator as field_validator  # type: ignore


# ==== Direktori Proyek ====
ROOT_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT_DIR / "models"
LOGS_DIR = ROOT_DIR / "logs"

BEST_PT = MODELS_DIR / "fgi_dl_best.pt"
SCALER_PKL = MODELS_DIR / "fgi_scaler.pkl"
META_PATH = MODELS_DIR / "fgi_dl.meta.json"

INFER_LOG = LOGS_DIR / "inference_log.csv"

_RETRAIN_LOCK = threading.Lock()
_LAST_RETRAIN_TS = 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _freshness_status(date_utc: str | None, ref_day_utc: str | None = None) -> str:
    d = _parse_date(date_utc)
    if d is None:
        return "unknown"
    ref = _parse_date(ref_day_utc) or datetime.now(timezone.utc).date()
    delta = (ref - d).days
    if delta <= 1:
        return "fresh"
    if delta <= 4:
        return "recent"
    return "stale"


def _plausibility_flags(temp: float, sal: float, chl: float) -> Dict[str, bool]:
    return {
        "temp": 15.0 <= temp <= 35.0,
        "sal": 20.0 <= sal <= 40.0,
        "chl": 0.0 <= chl <= 20.0,
    }


def _confidence_score(temp: float, sal: float, chl: float, date_utc: str | None) -> str:
    flags = _plausibility_flags(temp, sal, chl)
    plausible_count = sum(1 for v in flags.values() if v)
    freshness = _freshness_status(date_utc)

    if plausible_count == 3 and freshness in {"fresh", "recent"}:
        return "high"
    if plausible_count >= 2:
        return "medium"
    return "low"


def _temp_driver(temp: float) -> str:
    if 27.0 <= temp <= 30.5:
        return "Suhu berada di kisaran yang relatif mendukung kondisi permukaan laut tropis."
    if temp > 30.5:
        return "Suhu relatif sangat hangat; ini dapat menggeser kenyamanan habitat untuk sebagian ikan."
    return "Suhu relatif lebih sejuk dari kisaran tropis hangat yang umum."


def _sal_driver(sal: float) -> str:
    if 32.0 <= sal <= 35.5:
        return "Salinitas berada di kisaran laut terbuka yang relatif stabil."
    if sal < 32.0:
        return "Salinitas relatif lebih rendah; bisa menandakan pengaruh pencampuran atau air yang lebih encer."
    return "Salinitas relatif tinggi; interpretasi perlu hati-hati terhadap konteks lokal."


def _chl_driver(chl: float) -> str:
    if chl >= 0.5:
        return "Klorofil-a relatif tinggi, mengindikasikan produktivitas permukaan yang lebih baik."
    if chl >= 0.15:
        return "Klorofil-a berada pada level sedang, cukup mendukung tetapi belum menonjol."
    return "Klorofil-a relatif rendah, sehingga dukungan produktivitas permukaan cenderung terbatas."


def _build_explain(temp: float, sal: float, chl: float, score: float, band: str) -> Dict[str, Any]:
    return {
        "top_drivers": [
            _temp_driver(temp),
            _sal_driver(sal),
            _chl_driver(chl),
        ],
        "input_summary": {
            "temp_c": round(temp, 4),
            "sal_psu": round(sal, 4),
            "chl_mg_m3": round(chl, 6),
        },
        "score_summary": f"FGI env {score:.3f} diklasifikasikan sebagai {band}.",
        "model_note": "Explainability ini berbasis heuristik domain atas input utama, bukan attribution internal neural network.",
    }


def _build_trust(temp: float, sal: float, chl: float, date_utc: str | None, basis_type: str) -> Dict[str, Any]:
    generated_at = _utc_now_iso()
    return {
        "source": f"Internal Torch FGI model • {BEST_PT.name}",
        "date_utc": date_utc,
        "generated_at": generated_at,
        "freshness_status": _freshness_status(date_utc),
        "confidence": _confidence_score(temp, sal, chl, date_utc),
        "basis_type": basis_type,
        "mode": "upstream",
        "caveat": "FGI env adalah skor indikatif berbasis suhu, salinitas, dan klorofil-a; bukan jaminan hasil tangkapan.",
    }


def _kick_retrain_async(threshold: int = 10, cooldown_s: int = 3600):
    """Start retrain async max 1x per cooldown (default 1 jam)."""
    global _LAST_RETRAIN_TS
    now = time.time()
    with _RETRAIN_LOCK:
        if now - _LAST_RETRAIN_TS < cooldown_s:
            return
        _LAST_RETRAIN_TS = now

    try:
        from app.trainers.retrain_fgi import retrain_model

        kwargs = {}
        try:
            if "threshold" in inspect.signature(retrain_model).parameters:
                kwargs["threshold"] = threshold
        except Exception:
            kwargs = {}

        threading.Thread(target=retrain_model, kwargs=kwargs, daemon=True).start()
    except Exception:
        pass



def _to_prob(y: float) -> float:
    """Kalau output bukan 0..1, anggap logit -> sigmoid."""
    y = float(y)
    if y < 0.0 or y > 1.0:
        y = 1.0 / (1.0 + float(np.exp(-y)))
    return float(max(0.0, min(1.0, y)))



def _to_band(p: float) -> str:
    return "High" if p >= 0.75 else ("Medium" if p >= 0.50 else "Low")


# ==== Optional imports (Torch & joblib) ====
TORCH_AVAILABLE = False
torch = None
nn = None
joblib = None

try:
    import torch as _torch  # type: ignore
    import torch.nn as _nn  # type: ignore
    import joblib as _joblib  # type: ignore

    torch = _torch
    nn = _nn
    joblib = _joblib
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False


# ==== Router ====
router = APIRouter(prefix="/fgi", tags=["FGI (Fish Growth Intelligence)"])


# ==== Model Input ====
class FGIRequest(BaseModel):
    temp: float = Field(..., description="Suhu laut dalam °C")
    sal: float = Field(..., description="Salinitas air laut (PSU)")
    chl: float = Field(..., description="Klorofil-a (mg/m³)")
    date_utc: str | None = Field(None, description="Tanggal data dalam format YYYY-MM-DD")

    @field_validator("temp", "sal", "chl")
    def check_positive(cls, v, *args, **kwargs):
        if v < 0:
            raise ValueError("Nilai tidak boleh negatif")
        return v


# ==== Neural Network (sesuai training) ====
if TORCH_AVAILABLE:
    class SimpleNet(nn.Module):  # type: ignore
        def __init__(self, n_input: int = 3, n_hidden: int = 8):
            super().__init__()
            self.fc = nn.Sequential(  # type: ignore
                nn.Linear(n_input, n_hidden),  # type: ignore
                nn.ReLU(),  # type: ignore
                nn.Linear(n_hidden, 1),  # type: ignore
            )

        def forward(self, x):
            return self.fc(x)
else:
    SimpleNet = object  # type: ignore



def _extract_state_dict(ckpt: Any) -> Dict[str, Any]:
    if isinstance(ckpt, dict):
        if "state_dict" in ckpt and isinstance(ckpt["state_dict"], dict):
            return ckpt["state_dict"]
        if "model_state_dict" in ckpt and isinstance(ckpt["model_state_dict"], dict):
            return ckpt["model_state_dict"]
        return ckpt
    raise TypeError(f"Unsupported checkpoint type: {type(ckpt)}")



def _strip_module_prefix(state: Dict[str, Any]) -> Dict[str, Any]:
    if any(k.startswith("module.") for k in state.keys()):
        return {k.replace("module.", "", 1): v for k, v in state.items()}
    return state



def _compat_rename_fc_keys(model: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    model_keys = set(model.state_dict().keys())
    needs_new = ("fc.0.weight" in model_keys) or ("fc.2.weight" in model_keys)
    has_old = ("fc1.weight" in state) and ("fc2.weight" in state)

    if needs_new and has_old:
        state = dict(state)
        state["fc.0.weight"] = state.pop("fc1.weight")
        state["fc.0.bias"] = state.pop("fc1.bias")
        state["fc.2.weight"] = state.pop("fc2.weight")
        state["fc.2.bias"] = state.pop("fc2.bias")
    return state



def _load_meta(meta_path: Path) -> Dict[str, Any]:
    if not meta_path.exists():
        return {}
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ==== Load Model dan Scaler ====
MODEL = None
SCALER = None
META: Dict[str, Any] = {}

if TORCH_AVAILABLE and BEST_PT.exists() and SCALER_PKL.exists():
    try:
        SCALER = joblib.load(SCALER_PKL)  # type: ignore
        META = _load_meta(META_PATH)

        feats = META.get("features") or META.get("input_features")
        if isinstance(feats, list) and len(feats) > 0:
            n_features = len(feats)
        else:
            n_features = 3

        MODEL = SimpleNet(n_input=n_features)  # type: ignore

        ckpt = torch.load(BEST_PT, map_location="cpu")  # type: ignore
        state = _extract_state_dict(ckpt)
        state = _strip_module_prefix(state)
        state = _compat_rename_fc_keys(MODEL, state)

        MODEL.load_state_dict(state, strict=True)  # type: ignore
        MODEL.eval()  # type: ignore
        print(f"[INFO] ✅ Model FGI loaded successfully ({n_features} features)")

    except Exception as e:
        MODEL = None
        SCALER = None
        print(f"[WARN] ⚠️ Gagal memuat model FGI: {e}")
else:
    print("[WARN] ⚠️ Model file tidak ditemukan atau Torch belum tersedia.")


# ==== Endpoint Health Check ====
@router.get("/ping")
def ping():
    return {
        "status": "ok",
        "message": "FGI module alive",
        "torch_available": TORCH_AVAILABLE,
        "model_loaded": MODEL is not None and SCALER is not None,
        "trust": {
            "source": f"Internal Torch FGI model • {BEST_PT.name}",
            "date_utc": None,
            "generated_at": _utc_now_iso(),
            "freshness_status": "unknown",
            "confidence": "high" if MODEL is not None and SCALER is not None else "low",
            "basis_type": "service_health",
            "mode": "upstream",
            "caveat": "Ping hanya memeriksa kesiapan service, bukan mutu skor FGI env.",
        },
    }


# ==== Endpoint Inferensi ====
@router.post("/predict")
def predict_fgi(data: FGIRequest):
    if not TORCH_AVAILABLE or MODEL is None or SCALER is None:
        raise HTTPException(status_code=503, detail="FGI model/scaler belum siap.")

    try:
        X = np.array([[data.temp, data.sal, data.chl]], dtype=np.float32)
        X_scaled = SCALER.transform(X)
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)  # type: ignore

        with torch.no_grad():  # type: ignore
            raw = float(MODEL(X_tensor).item())  # type: ignore

        p = _to_prob(raw)
        category = _to_band(p)

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        is_new = not INFER_LOG.exists()
        with INFER_LOG.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "temp", "sal", "chl", "raw", "prob", "category"])
            w.writerow([datetime.now().isoformat(), data.temp, data.sal, data.chl, round(raw, 6), round(p, 6), category])

        _kick_retrain_async()

        trust = _build_trust(data.temp, data.sal, data.chl, data.date_utc, "model_based_score")
        explain = _build_explain(data.temp, data.sal, data.chl, p, category)
        return {
            "ok": True,
            "FGI_Score": round(p, 4),
            "Category": category,
            "raw": round(raw, 6),
            "inputs": {"temp": float(data.temp), "sal": float(data.sal), "chl": float(data.chl)},
            "trust": trust,
            "explain": explain,
            "note": "scored by internal torch model (temp,sal,chl)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrain")
def retrain_from_log():
    try:
        from app.trainers.retrain_fgi import retrain_model
        result = retrain_model()
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/score")
def score(payload: dict):
    if not TORCH_AVAILABLE or MODEL is None or SCALER is None:
        raise HTTPException(status_code=503, detail="FGI model/scaler belum siap.")

    def pick(keys):
        for k in keys:
            if k in payload and payload[k] is not None:
                return payload[k]
        return None

    temp = pick(["temp", "sst_c", "sst", "temperature", "thetao"])
    sal = pick(["sal", "sal_psu", "salinity", "so"])
    chl = pick(["chl", "chl_mg_m3", "CHL", "chlorophyll"])
    date_utc = pick(["date_utc", "date", "valid_date", "snapshot_date"])

    feats = payload.get("features") or payload.get("x")
    if (temp is None or sal is None or chl is None) and isinstance(feats, list) and len(feats) >= 3:
        temp, sal, chl = feats[0], feats[1], feats[2]

    if temp is None or sal is None or chl is None:
        raise HTTPException(
            status_code=422,
            detail=f"Missing features. Need (temp/sal/chl) or aliases (sst_c/sal_psu/chl_mg_m3). Got keys={list(payload.keys())}",
        )

    try:
        temp_f, sal_f, chl_f = float(temp), float(sal), float(chl)
        X = np.array([[temp_f, sal_f, chl_f]], dtype=np.float32)
        X_scaled = SCALER.transform(X)
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32)  # type: ignore

        with torch.no_grad():  # type: ignore
            raw = float(MODEL(X_tensor).item())  # type: ignore

        p = _to_prob(raw)
        band = _to_band(p)
        trust = _build_trust(temp_f, sal_f, chl_f, date_utc, "model_based_score")
        explain = _build_explain(temp_f, sal_f, chl_f, p, band)

        return {
            "ok": True,
            "score": round(p, 6),
            "band": band,
            "raw": round(raw, 6),
            "inputs": {"temp": temp_f, "sal": sal_f, "chl": chl_f},
            "trust": trust,
            "explain": explain,
            "note": "scored by internal torch model (temp,sal,chl)",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
