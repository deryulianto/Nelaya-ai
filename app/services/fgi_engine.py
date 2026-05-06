import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


from app.schemas.fgi_plan import (
    CandidatePoint,
    FGIPlanRequest,
    FGIPlanResponse,
    ModelMeta,
    PlanSummary,
    ProbabilityBreakdown,
    RegulationResult,
    ScoreBreakdown,
)

from app.services.fgi_calibration import compute_trip_success_rate
from app.services.fgi_calibration_adjustment import adjust_trip_probability

BASE_DIR = Path(__file__).resolve().parents[2]

DATA_STATIC_DIR = BASE_DIR / "data" / "static"
DATA_FGI_DIR = BASE_DIR / "data" / "fgi"
DATA_FGI_CANDIDATES_DIR = DATA_FGI_DIR / "candidates"
DATA_FGI_PREDICTIONS_DIR = DATA_FGI_DIR / "predictions"

PORTS_CANDIDATES = [
    DATA_STATIC_DIR / "ports_aceh.json",
    BASE_DIR / "data" / "ports_aceh.json",
]
VESSELS_PATH = DATA_STATIC_DIR / "vessel_profiles.json"
REGULATIONS_PATH = DATA_STATIC_DIR / "regulation_zones.geojson"

EARTH_SIGNALS_CANDIDATES = [
    BASE_DIR / "data" / "earth_signals_today.json",
    BASE_DIR / "data" / "earth" / "earth_signals_today.json",
    BASE_DIR / "data" / "signals_today.json",
]

PRIORITY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "seimbang": {"ocean": 0.35, "safety": 0.25, "economy": 0.20, "regulation": 0.15, "confidence": 0.05},
    "aman": {"ocean": 0.20, "safety": 0.40, "economy": 0.15, "regulation": 0.20, "confidence": 0.05},
    "hemat": {"ocean": 0.25, "safety": 0.20, "economy": 0.35, "regulation": 0.15, "confidence": 0.05},
    "peluang": {"ocean": 0.45, "safety": 0.20, "economy": 0.15, "regulation": 0.15, "confidence": 0.05},
}

DEFAULT_VESSEL_LIMITS = {
    "perahu_kecil": {"max_safe_wave_m": 1.5, "max_safe_wind_ms": 9.0, "max_trip_hours": 12},
    "perahu_sedang": {"max_safe_wave_m": 2.2, "max_safe_wind_ms": 12.0, "max_trip_hours": 24},
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def round4(value: float) -> float:
    return round(float(value), 4)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return default

    if isinstance(value, dict):
        for key in ["value", "mean", "avg", "daily_mean", "metric", "score", "current"]:
            if key in value:
                return as_float(value.get(key), default)

    return default

    if isinstance(value, dict):
        # bentuk umum yang sering muncul pada metrics terstruktur
        for key in [
            "value",
            "mean",
            "avg",
            "daily_mean",
            "metric",
            "score",
            "current",
        ]:
            if key in value:
                return as_float(value.get(key), default)

    return default

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def destination_point(lat: float, lon: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    r = 6371.0
    b = math.radians(bearing_deg)
    d = distance_km / r
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) +
        math.cos(lat1) * math.sin(d) * math.cos(b)
    )
    lon2 = lon1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return (math.degrees(lat2), math.degrees(lon2))


def point_in_ring(point_lon: float, point_lat: float, ring: List[List[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False

    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]

        intersects = ((yi > point_lat) != (yj > point_lat)) and (
            point_lon < (xj - xi) * (point_lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i

    return inside


def point_in_polygon_geom(point_lon: float, point_lat: float, geometry: Dict[str, Any]) -> bool:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])

    if geom_type == "Polygon":
        if not coords:
            return False
        outer = coords[0]
        return point_in_ring(point_lon, point_lat, outer)

    if geom_type == "MultiPolygon":
        for polygon in coords:
            if polygon and point_in_ring(point_lon, point_lat, polygon[0]):
                return True

    return False


class FGIPlanEngine:
    def __init__(self) -> None:
        self.ports = self._load_ports()
        self.vessels = self._load_vessels()
        self.regulations = self._load_regulations()

    def generate_plan(self, req: FGIPlanRequest) -> FGIPlanResponse:
        port = self._find_port(req.port_name)
        if not port:
            raise ValueError(f"Pelabuhan tidak ditemukan: {req.port_name}")

        vessel_limits = self._resolve_vessel_limits(req.vessel_type)
        candidates_raw, model_version = self._load_or_generate_candidates(req.date, port)

        ranked: List[CandidatePoint] = []

        for item in candidates_raw:
            lat = as_float(item.get("lat"))
            lon = as_float(item.get("lon"))

            if lat is None or lon is None:
                continue

            distance_km = haversine_km(port["lat"], port["lon"], lat, lon)
            if distance_km > req.constraints.max_radius_km:
                continue

            ocean_score = self._compute_ocean_score(item)
            if ocean_score < req.constraints.fgi_min:
                continue

            wave_hs = as_float(item.get("wave_hs"), 1.0)
            wind_ms = as_float(item.get("wind_ms"), 5.0)
            eta_hours = distance_km / max(req.boat.speed_kmh, 0.1)

            safety_score = self._compute_safety_score(
                wave_hs=wave_hs,
                wind_ms=wind_ms,
                vessel_limits=vessel_limits,
                max_wave=req.constraints.max_wave_m,
                max_wind=req.constraints.max_wind_ms,
            )

            economy_score = self._compute_economy_score(
                distance_km=distance_km,
                speed_kmh=req.boat.speed_kmh,
                burn_lph=req.boat.burn_lph,
                fuel_price=req.boat.fuel_price,
                budget_idr=req.budget_idr,
            )

            regulation = self._check_regulations(
                lat=lat,
                lon=lon,
                vessel_type=req.vessel_type,
            )
            confidence_score = self._compute_confidence_score(item)

            if regulation["status"] == "terlarang":
                continue

            scores = {
                "ocean": ocean_score,
                "safety": safety_score,
                "economy": economy_score,
                "regulation": regulation["score"],
                "confidence": confidence_score,
            }

            final_score = self._combine_scores(scores, req.priority)
            probs = self._estimate_probabilities(
                scores=scores,
                final_score=final_score,
                regulation_status=regulation["status"],
            )

            drivers_positive, drivers_negative = self._build_drivers(
                ocean_score=ocean_score,
                safety_score=safety_score,
                economy_score=economy_score,
                regulation_status=regulation["status"],
                confidence_score=confidence_score,
                wave_hs=wave_hs,
                wind_ms=wind_ms,
                distance_km=distance_km,
            )

            ranked.append(
                CandidatePoint(
                    rank=0,
                    lat=lat,
                    lon=lon,
                    distance_km=round4(distance_km),
                    eta_hours=round4(eta_hours),
                    scores=ScoreBreakdown(
                        ocean=round4(scores["ocean"]),
                        safety=round4(scores["safety"]),
                        economy=round4(scores["economy"]),
                        regulation=round4(scores["regulation"]),
                        confidence=round4(scores["confidence"]),
                        final=round4(final_score),
                    ),
                    probabilities=ProbabilityBreakdown(
                        trip_success=round4(probs["trip_success"]),
                        high_cpue=round4(probs["high_cpue"]),
                        operational_feasible=round4(probs["operational_feasible"]),
                    ),
                    regulation=RegulationResult(
                        status=regulation["status"],
                        matched_zone_ids=regulation["matched_zone_ids"],
                        reasons=regulation["reasons"],
                    ),
                    drivers_positive=drivers_positive,
                    drivers_negative=drivers_negative,
                )
            )

        ranked.sort(key=lambda x: x.scores.final, reverse=True)
        ranked = ranked[: max(1, req.constraints.trip_n)]

        for i, cand in enumerate(ranked, start=1):
            cand.rank = i

        summary, top_scores, top_probs = self._build_summary(ranked)

        calibration_adjustment = None
        if top_probs is not None:
            calibration_adjustment = adjust_trip_probability(top_probs.trip_success)

        response = FGIPlanResponse(
            date=req.date,
            port_name=req.port_name,
            vessel_type=req.vessel_type,
            priority=req.priority,
            summary=summary,
            top_scores=top_scores,
            top_probabilities=top_probs,
            calibration_adjustment=calibration_adjustment,
            candidates=ranked,
            model=ModelMeta(
                version=model_version,
                generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                calibration=None,
                mode="alpha",
            ),
        )

        self._save_prediction_snapshot(req, response)
        return response

    def _load_ports(self) -> List[Dict[str, Any]]:
        for path in PORTS_CANDIDATES:
            data = load_json(path, default=None)
            if isinstance(data, list):
                return self._normalize_ports(data)
            if isinstance(data, dict):
                if isinstance(data.get("ports"), list):
                    return self._normalize_ports(data["ports"])
                if isinstance(data.get("items"), list):
                    return self._normalize_ports(data["items"])
        return []

    def _normalize_ports(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ports = []
        for item in items:
            try:
                name = str(item.get("name") or item.get("port_name") or item.get("label"))
                lat = as_float(item.get("lat"))
                lon = as_float(item.get("lon"))

                if not name or lat is None or lon is None:
                    continue

                ports.append(
                    {
                        "name": name,
                        "district": item.get("district") or item.get("kabupaten"),
                        "lat": lat,
                        "lon": lon,
                    }
                )
            except Exception:
                continue
        return ports

    def _load_vessels(self) -> Dict[str, Dict[str, Any]]:
        data = load_json(VESSELS_PATH, default=[])
        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(data, list):
            for item in data:
                key = item.get("vessel_type")
                if key:
                    out[key] = item
        return out

    def _load_regulations(self) -> List[Dict[str, Any]]:
        data = load_json(REGULATIONS_PATH, default={"type": "FeatureCollection", "features": []})
        if isinstance(data, dict) and isinstance(data.get("features"), list):
            return data["features"]
        return []

    def _resolve_vessel_limits(self, vessel_type: str) -> Dict[str, float]:
        base = dict(DEFAULT_VESSEL_LIMITS.get(vessel_type, DEFAULT_VESSEL_LIMITS["perahu_kecil"]))
        meta = self.vessels.get(vessel_type, {})
        if meta:
            base["max_safe_wave_m"] = as_float(meta.get("max_safe_wave_m"), base["max_safe_wave_m"])
            base["max_safe_wind_ms"] = as_float(meta.get("max_safe_wind_ms"), base["max_safe_wind_ms"])
            base["max_trip_hours"] = as_float(meta.get("max_trip_hours"), base["max_trip_hours"])
        return base

    def _find_port(self, port_name: str) -> Optional[Dict[str, Any]]:
        needle = port_name.strip().lower()
        for port in self.ports:
            if port["name"].strip().lower() == needle:
                return port
        for port in self.ports:
            if needle in port["name"].strip().lower():
                return port
        return None

    def _load_or_generate_candidates(self, date_str: str, port: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
        dated_path = DATA_FGI_CANDIDATES_DIR / f"candidates_{date_str}.json"
        latest_path = DATA_FGI_CANDIDATES_DIR / "latest.json"

        for path in [dated_path, latest_path]:
            data = load_json(path, default=None)
            if isinstance(data, list) and data:
                return data, "fgi-2.0.0-alpha-candidate-file"

        return self._generate_fallback_candidates(port), "fgi-2.0.0-alpha-fallback"

    def _generate_fallback_candidates(self, port: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = self._load_seed_signals()

        base_ocean = self._ocean_proxy_from_signals(
            sst=signals["sst"],
            chl=signals["chl"],
            salinity=signals["salinity"],
            wave_hs=signals["wave_hs"],
            wind_ms=signals["wind_ms"],
        )

        candidates: List[Dict[str, Any]] = []
        bearings = [285, 300, 315, 330, 345, 0, 15, 30]
        distances = [12, 18, 24, 30, 36]

        for i, bearing in enumerate(bearings):
          for j, distance in enumerate(distances):
            lat2, lon2 = destination_point(port["lat"], port["lon"], bearing, distance)
            jitter = ((i + 1) * (j + 2)) % 7 / 100.0
            ocean_score = clamp(base_ocean + jitter - (distance / 300.0), 0.25, 0.92)

        candidates.append(
            {
                "lat": lat2,
                "lon": lon2,
                "ocean_score": round4(ocean_score),
                "sst": round4(signals["sst"] + (j * 0.03) - 0.05),
                "chl": round4(max(0.05, signals["chl"] + (i * 0.01) - 0.02)),
                "salinity": round4(signals["salinity"]),
                "wave_hs": round4(max(0.3, signals["wave_hs"] + (distance / 120.0) - 0.15)),
                "wind_ms": round4(max(1.0, signals["wind_ms"] + (i / 4.0) - 0.5)),
            }
        )

        return candidates

    def _load_seed_signals(self) -> Dict[str, float]:
        for path in EARTH_SIGNALS_CANDIDATES:
            data = load_json(path, default=None)
            if not isinstance(data, dict):
                continue

            metrics = data.get("metrics", {}) if isinstance(data.get("metrics"), dict) else {}
            inputs = data.get("inputs", {}) if isinstance(data.get("inputs"), dict) else {}
            quick_compare = data.get("quick_compare", {}) if isinstance(data.get("quick_compare"), dict) else {}

            sst = (
                as_float(metrics.get("sst"))
                or as_float(data.get("sst"))
                or as_float(inputs.get("sst"))
                or 29.5
            )

            chl = (
                as_float(metrics.get("chl"))
                or as_float(metrics.get("chlorophyll"))
                or as_float(data.get("chl"))
                or as_float(inputs.get("chl"))
                or 0.28
            )

            wave_hs = (
                as_float(metrics.get("wave_hs"))
                or as_float(metrics.get("wave"))
                or as_float(data.get("wave_hs"))
                or as_float(inputs.get("wave_hs"))
                or 0.9
            )

            wind_ms = (
                as_float(metrics.get("wind_speed"))
                or as_float(metrics.get("wind"))
                or as_float(data.get("wind_speed"))
                or as_float(inputs.get("wind_speed"))
                or 4.8
            )

            salinity = (
                as_float(metrics.get("salinity"))
                or as_float(data.get("salinity"))
                or as_float(inputs.get("salinity"))
                or 33.2
            )

            sst = sst or as_float(quick_compare.get("sst")) or 29.5
            chl = chl or as_float(quick_compare.get("chl")) or 0.28
            wave_hs = wave_hs or as_float(quick_compare.get("wave_hs")) or 0.9
            wind_ms = wind_ms or as_float(quick_compare.get("wind_speed")) or 4.8
            salinity = salinity or as_float(quick_compare.get("salinity")) or 33.2

            return {
                "sst": float(sst),
                "chl": float(chl),
                "wave_hs": float(wave_hs),
                "wind_ms": float(wind_ms),
                "salinity": float(salinity),
            }

        return {
            "sst": 29.5,
            "chl": 0.28,
            "wave_hs": 0.9,
            "wind_ms": 4.8,
            "salinity": 33.2,
        }

    def _ocean_proxy_from_signals(self, sst: float, chl: float, salinity: float, wave_hs: float, wind_ms: float) -> float:
        sst_score = clamp(1.0 - abs(sst - 29.5) / 2.5)
        chl_score = clamp(chl / 0.6)
        sal_score = clamp(1.0 - abs(salinity - 33.5) / 2.5)
        sea_penalty = clamp(1.0 - (wave_hs / 3.0))
        wind_penalty = clamp(1.0 - (wind_ms / 15.0))
        return round4(0.35 * sst_score + 0.35 * chl_score + 0.15 * sal_score + 0.10 * sea_penalty + 0.05 * wind_penalty)

    def _compute_ocean_score(self, item: Dict[str, Any]) -> float:
     raw_ocean = as_float(item.get("ocean_score"))
     if raw_ocean is not None:
        return clamp(raw_ocean)

     return self._ocean_proxy_from_signals(
        sst=as_float(item.get("sst"), 29.5),
        chl=as_float(item.get("chl"), 0.25),
        salinity=as_float(item.get("salinity"), 33.2),
        wave_hs=as_float(item.get("wave_hs"), 1.0),
        wind_ms=as_float(item.get("wind_ms"), 5.0),
    )

    def _compute_safety_score(
        self,
        wave_hs: float,
        wind_ms: float,
        vessel_limits: Dict[str, float],
        max_wave: Optional[float],
        max_wind: Optional[float],
    ) -> float:
        wave_limit = float(max_wave or vessel_limits["max_safe_wave_m"])
        wind_limit = float(max_wind or vessel_limits["max_safe_wind_ms"])

        wave_ratio = clamp(1.0 - (wave_hs / max(wave_limit, 0.1)))
        wind_ratio = clamp(1.0 - (wind_ms / max(wind_limit, 0.1)))
        return round4(0.6 * wave_ratio + 0.4 * wind_ratio)

    def _compute_economy_score(
        self,
        distance_km: float,
        speed_kmh: float,
        burn_lph: float,
        fuel_price: float,
        budget_idr: Optional[float],
    ) -> float:
        eta_hours = distance_km / max(speed_kmh, 0.1)
        fuel_need = eta_hours * 2.0 * burn_lph
        fuel_cost = fuel_need * fuel_price

        if not budget_idr or budget_idr <= 0:
            ratio = fuel_cost / 1_500_000.0
            return round4(clamp(1.0 - ratio, 0.35, 0.9))

        ratio = fuel_cost / budget_idr
        return round4(clamp(1.0 - ratio, 0.0, 1.0))

    def _compute_confidence_score(self, item: Dict[str, Any]) -> float:
        confidence = 0.45
        keys_present = sum(1 for key in ["ocean_score", "sst", "chl", "salinity", "wave_hs", "wind_ms"] if key in item and item[key] is not None)
        confidence += min(keys_present / 10.0, 0.35)

        if "source" in item:
            confidence += 0.08

        if "history_count" in item:
            try:
                confidence += min(float(item["history_count"]) / 100.0, 0.12)
            except Exception:
                pass

        return round4(clamp(confidence, 0.2, 0.95))

    def _check_regulations(self, lat: float, lon: float, vessel_type: str) -> Dict[str, Any]:
        matched_zone_ids: List[str] = []
        reasons: List[str] = []
        score = 1.0
        status = "aman"

        for feature in self.regulations:
            geometry = feature.get("geometry") or {}
            if not point_in_polygon_geom(lon, lat, geometry):
                continue

            props = feature.get("properties", {})
            zone_id = str(props.get("zone_id", "ZONE-UNKNOWN"))
            zone_name = str(props.get("zone_name", zone_id))
            rule_type = str(props.get("rule_type", "note_only"))
            penalty = float(props.get("penalty", 0.25))
            allowed_vessels = props.get("allowed_vessel_types", [])

            matched_zone_ids.append(zone_id)

            if isinstance(allowed_vessels, list) and allowed_vessels and vessel_type not in allowed_vessels:
                status = "terlarang"
                score = 0.0
                reasons.append(f"{zone_name}: tipe perahu tidak diizinkan")
                break

            if rule_type == "hard_block":
                status = "terlarang"
                score = 0.0
                reasons.append(f"{zone_name}: zona larangan tangkap")
                break

            if rule_type == "soft_penalty":
                status = "terbatas"
                score = min(score, clamp(1.0 - penalty, 0.2, 0.85))
                reasons.append(f"{zone_name}: area terbatas, perlu kehati-hatian")
                continue

            reasons.append(f"{zone_name}: area sensitif, cek ketentuan lapangan")

        if not reasons:
            reasons.append("Tidak berada pada zona larangan tangkap")

        return {
            "status": status,
            "score": round4(score),
            "matched_zone_ids": matched_zone_ids,
            "reasons": reasons,
        }

    def _combine_scores(self, scores: Dict[str, float], priority: str) -> float:
        weights = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["seimbang"])
        final_score = (
            scores["ocean"] * weights["ocean"] +
            scores["safety"] * weights["safety"] +
            scores["economy"] * weights["economy"] +
            scores["regulation"] * weights["regulation"] +
            scores["confidence"] * weights["confidence"]
        )
        return round4(clamp(final_score))

    def _estimate_probabilities(self, scores: Dict[str, float], final_score: float, regulation_status: str) -> Dict[str, float]:
        trip_success = clamp(0.10 + 0.55 * final_score + 0.20 * scores["ocean"] + 0.10 * scores["economy"] + 0.05 * scores["confidence"])
        high_cpue = clamp(0.08 + 0.68 * scores["ocean"] + 0.12 * scores["confidence"])
        operational_feasible = clamp(0.10 + 0.55 * scores["safety"] + 0.20 * scores["economy"] + 0.10 * scores["regulation"] + 0.05 * scores["confidence"])

        if regulation_status == "terbatas":
            trip_success = clamp(trip_success - 0.05)
            operational_feasible = clamp(operational_feasible - 0.08)

        return {
            "trip_success": round4(trip_success),
            "high_cpue": round4(high_cpue),
            "operational_feasible": round4(operational_feasible),
        }

    def _build_drivers(
        self,
        ocean_score: float,
        safety_score: float,
        economy_score: float,
        regulation_status: str,
        confidence_score: float,
        wave_hs: float,
        wind_ms: float,
        distance_km: float,
    ) -> Tuple[List[str], List[str]]:
        pos: List[str] = []
        neg: List[str] = []

        if ocean_score >= 0.7:
            pos.append("Produktivitas perairan mendukung")
        elif ocean_score >= 0.55:
            pos.append("Sinyal laut cukup mendukung")
        else:
            neg.append("Sinyal laut belum terlalu kuat")

        if safety_score >= 0.7:
            pos.append("Gelombang dan angin masih aman untuk operasi")
        else:
            neg.append(f"Perlu kehati-hatian: Hs≈{wave_hs:.2f} m, angin≈{wind_ms:.1f} m/s")

        if economy_score >= 0.7:
            pos.append("Jarak operasi masih efisien")
        elif economy_score < 0.45:
            neg.append(f"Biaya operasi relatif berat untuk jarak sekitar {distance_km:.1f} km")

        if regulation_status == "aman":
            pos.append("Area lolos pemeriksaan regulasi awal")
        elif regulation_status == "terbatas":
            neg.append("Area tidak terlarang, tetapi berada pada zona dengan pembatasan")

        if confidence_score < 0.6:
            neg.append("Confidence masih sedang-rendah karena histori/fitur belum penuh")
        else:
            pos.append("Kualitas input cukup baik untuk estimasi awal")

        return pos[:4], neg[:4]

    def _build_summary(self, ranked: List[CandidatePoint]):
        if not ranked:
            return (
                PlanSummary(
                    decision="tidak_dianjurkan",
                    decision_note="Tidak ada kandidat yang lolos ambang peluang, keselamatan, atau regulasi pada parameter saat ini.",
                ),
                None,
                None,
            )

        top = ranked[0]
        final_score = top.scores.final

        if final_score >= 0.72 and top.regulation.status == "aman" and top.scores.safety >= 0.60:
            decision = "layak"
            note = "Peluang cukup baik, kondisi operasi masih memadai, dan area lolos pemeriksaan regulasi awal."
        elif final_score >= 0.55:
            decision = "hati_hati"
            note = "Ada peluang operasi, tetapi perlu kehati-hatian pada keselamatan, biaya, atau keterbatasan area."
        else:
            decision = "tidak_dianjurkan"
            note = "Skor total belum cukup kuat untuk direkomendasikan sebagai rencana utama."

        return (PlanSummary(decision=decision, decision_note=note), top.scores, top.probabilities)

    def _save_prediction_snapshot(self, req: FGIPlanRequest, response: FGIPlanResponse) -> None:
        ensure_dir(DATA_FGI_PREDICTIONS_DIR)
        out_path = DATA_FGI_PREDICTIONS_DIR / f"predictions_{req.date}.jsonl"
        payload = {
            "requested_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "request": req.model_dump(),
            "response": response.model_dump(),
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")