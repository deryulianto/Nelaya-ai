from __future__ import annotations

import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "aceh_simeulue"
OUT = ROOT / "data" / "fgi_daily"
OUT.mkdir(parents=True, exist_ok=True)

MIN_BYTES = 10_000
KINDS = ["sst_nrt", "chl_nrt", "wind_nrt", "wave_anfc", "ssh_anfc", "sal_anfc"]

API_BASE = os.environ.get("NELAYA_FGI_API_BASE", "http://127.0.0.1:8001").rstrip("/")
SCORE_URL = f"{API_BASE}/api/v1/fgi/score"

REGION_BOX = {"min_lon": 92, "max_lon": 99, "min_lat": 1, "max_lat": 7}
CENTER_POINT = {"lat": (REGION_BOX["min_lat"] + REGION_BOX["max_lat"]) / 2.0,
                "lon": (REGION_BOX["min_lon"] + REGION_BOX["max_lon"]) / 2.0}

def ok_file(p: Path) -> bool:
    try:
        return p.exists() and p.is_file() and p.stat().st_size >= MIN_BYTES
    except Exception:
        return False

def out_path(kind: str, d: date) -> Path:
    y = f"{d.year:04d}"
    m = f"{d.month:02d}"
    day = d.isoformat()
    if kind in ("sst_nrt", "chl_nrt", "wind_nrt"):
        return RAW / kind / y / m / f"{kind}_aceh_{day}.nc"
    if kind == "wave_anfc":
        return RAW / kind / y / m / f"wave_aceh_{day}.nc"
    if kind == "ssh_anfc":
        return RAW / kind / y / m / f"ssh_aceh_{day}.nc"
    if kind == "sal_anfc":
        return RAW / kind / y / m / f"sal_aceh_{day}.nc"
    return RAW / kind / y / m / f"{kind}_aceh_{day}.nc"

def latest_existing(kind: str, base: date, back: int = 15) -> tuple[date | None, Path | None]:
    for i in range(back + 1):
        d = base - timedelta(days=i)
        p = out_path(kind, d)
        if ok_file(p):
            return d, p
    return None, None

def mean_from_nc(p: Path, kind: str) -> dict:
    import xarray as xr  # type: ignore

    ds = xr.open_dataset(p)

    def pick(names: list[str]) -> str | None:
        for n in names:
            if n in ds.data_vars:
                return n
        return None

    def mean_all(da) -> float:
        return float(da.mean(dim=list(da.dims), skipna=True).values)

    out: dict[str, float] = {}

    if kind == "sst_nrt":
        v = pick(["thetao", "sst"])
        if not v: raise RuntimeError("No thetao/sst in dataset")
        out["sst_c"] = mean_all(ds[v])

    elif kind == "chl_nrt":
        v = pick(["CHL", "chl", "chlor_a", "chlorophyll"])
        if not v: raise RuntimeError("No CHL variable in dataset")
        out["chl_mg_m3"] = mean_all(ds[v])

    elif kind == "wind_nrt":
        u = pick(["eastward_wind", "u10", "uwnd", "u"])
        v = pick(["northward_wind", "v10", "vwnd", "v"])
        sp = pick(["wind_speed", "ws"])
        if sp:
            out["wind_ms"] = mean_all(ds[sp])
        elif u and v:
            out["wind_ms"] = mean_all((ds[u] ** 2 + ds[v] ** 2) ** 0.5)
        else:
            raise RuntimeError("No wind variables found")

    elif kind == "wave_anfc":
        hs = pick(["VHM0", "hs", "swh"])
        if not hs: raise RuntimeError("No wave height variable found")
        out["wave_m"] = mean_all(ds[hs])

        tp = pick(["VTPK", "tp"])
        if tp:
            out["period_s"] = mean_all(ds[tp])

    elif kind == "ssh_anfc":
        v = pick(["zos", "adt", "sla"])
        if not v: raise RuntimeError("No zos/adt/sla variable found")
        val = mean_all(ds[v])
        out["ssh_cm"] = val * 100.0 if abs(val) < 20 else val

    elif kind == "sal_anfc":
        v = pick(["so", "salinity"])
        if not v: raise RuntimeError("No salinity variable found")
        out["sal_psu"] = mean_all(ds[v])

    ds.close()
    return out

def classify_band(score_01: float | None) -> str:
    if score_01 is None or not math.isfinite(score_01):
        return "Unknown"
    if score_01 >= 0.75: return "High"
    if score_01 >= 0.50: return "Medium"
    return "Low"

def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def score_via_internal_api(means: dict) -> dict:
    """
    Kirim payload ke /api/v1/fgi/score.
    Kita kirim superset field; pydantic biasanya ignore extra.
    Kalau ada required field beda nama, nanti error akan terlihat jelas.
    """
    payload = {
    # format field-per-field
    "sst_c": means.get("sst_c"),
    "chl_mg_m3": means.get("chl_mg_m3"),
    "wind_ms": means.get("wind_ms"),
    "sal_psu": means.get("sal_psu"),
    "wave_m": means.get("wave_m"),
    "ssh_cm": means.get("ssh_cm"),

    # alias naming (kalau schema beda)
    "sst": means.get("sst_c"),
    "chl": means.get("chl_mg_m3"),
    "wind": means.get("wind_ms"),

    # format vector (kalau scorer pakai X/features)
    "features": [means.get("sst_c"), means.get("chl_mg_m3"), means.get("wind_ms")],
    "x":        [means.get("sst_c"), means.get("chl_mg_m3"), means.get("wind_ms")],

    # lokasi (kalau dibutuhkan)
    "lat": CENTER_POINT["lat"],
    "lon": CENTER_POINT["lon"],
    "region": "aceh_simeulue",
}

    try:
        resp = post_json(SCORE_URL, payload)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTPError {e.code} calling {SCORE_URL}: {body[:500]}") from e
    except URLError as e:
        raise RuntimeError(f"URLError calling {SCORE_URL}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Error calling {SCORE_URL}: {e}") from e

    # Normalisasi output supaya konsisten: {score, band, note, raw}
    score = None
    band = None

    # beberapa kemungkinan bentuk response
    if isinstance(resp, dict):
        if "score" in resp and isinstance(resp["score"], (int, float)):
            score = float(resp["score"])
        elif "fgi" in resp and isinstance(resp["fgi"], dict) and isinstance(resp["fgi"].get("score"), (int, float)):
            score = float(resp["fgi"]["score"])

        if isinstance(resp.get("band"), str):
            band = resp["band"]
        elif "fgi" in resp and isinstance(resp["fgi"], dict) and isinstance(resp["fgi"].get("band"), str):
            band = resp["fgi"]["band"]

    if band is None:
        band = classify_band(score)

    return {
        "score": score,
        "band": band,
        "note": "scored by internal model (/api/v1/fgi/score)",
        "raw": resp,
    }

def main():
    base = datetime.now(timezone.utc).date()

    inputs: dict[str, str | None] = {}
    input_dates: dict[str, str | None] = {}
    means: dict[str, float] = {}
    errors: dict[str, str] = {}

    avail_dates: list[date] = []

    for k in KINDS:
        d, p = latest_existing(k, base, back=15)
        inputs[k] = str(p) if p else None
        input_dates[k] = d.isoformat() if d else None
        if d: avail_dates.append(d)
        if not p:
            errors[k] = "no raw file found (last 15d)"
            continue
        try:
            means.update(mean_from_nc(p, k))
        except Exception as e:
            errors[k] = str(e)

    as_of = (min(avail_dates).isoformat() if avail_dates else base.isoformat())

    # score by internal model
    fgi = None
    try:
        fgi = score_via_internal_api(means)
    except Exception as e:
        # kalau backend mati / schema mismatch, kita jangan gagal total.
        errors["fgi_score"] = str(e)
        fgi = {"score": None, "band": "Unknown", "note": "failed to score via internal model", "raw": None}

    payload = {
        "ok": True,
        "date_utc": base.isoformat(),
        "as_of_utc": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "region": REGION_BOX,
        "center_point": CENTER_POINT,
        "inputs": inputs,
        "input_dates": input_dates,
        "means": means,
        "fgi": fgi,
        "errors": errors,
    }

    (OUT / f"fgi_daily_{base.isoformat()}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("[OK] wrote data/fgi_daily/latest.json")

if __name__ == "__main__":
    main()
