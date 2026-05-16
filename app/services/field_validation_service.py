from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = Path("data/field_validation/nelayan_feedback.db")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS fisher_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT,
            nama_responden TEXT,
            pelabuhan TEXT,
            panglima_laot TEXT,
            lat REAL,
            lon REAL,
            alat_tangkap TEXT,
            jenis_ikan TEXT,
            hasil_kg REAL,
            kondisi_laut TEXT,
            arus_nelayan TEXT,
            warna_air TEXT,
            cuaca TEXT,
            catatan_lokal TEXT,
            created_at TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS fgi_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id INTEGER,
            fgi_value REAL,
            fgi_label TEXT,
            actual_result TEXT,
            match_score REAL,
            bias_direction TEXT,
            confidence REAL,
            notes TEXT,
            created_at TEXT
        )
        """)


def save_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    init_db()

    ensure_ocean_context_column()

    fields = [
        "tanggal", "nama_responden", "pelabuhan", "panglima_laot",
        "lat", "lon", "alat_tangkap", "jenis_ikan", "hasil_kg",
        "kondisi_laut", "arus_nelayan", "warna_air", "cuaca",
        "catatan_lokal", "ocean_context_json"
    ]

    values = {k: payload.get(k) for k in fields}

    oc = payload.get("ocean_context_json")
    if isinstance(oc, dict):
        values["ocean_context_json"] = json.dumps(oc, ensure_ascii=False)
    elif oc is None and (payload.get("lat") is not None or payload.get("lon") is not None):
        values["ocean_context_json"] = json.dumps(
            get_ocean_context(payload.get("lat"), payload.get("lon")),
            ensure_ascii=False,
        )

    values["created_at"] = _now()

    with _connect() as conn:
        cur = conn.execute(
            f"""
            INSERT INTO fisher_feedback ({",".join(values.keys())})
            VALUES ({",".join(["?"] * len(values))})
            """,
            list(values.values())
        )
        feedback_id = cur.lastrowid

    return {
        "ok": True,
        "message": "Masukan nelayan berhasil disimpan.",
        "feedback_id": feedback_id,
        "database": str(DB_PATH)
    }


def list_feedback(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    limit = max(1, min(limit, 500))

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM fisher_feedback ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()

    return [dict(r) for r in rows]


def classify_actual_result(hasil_kg: Optional[float]) -> str:
    if hasil_kg is None:
        return "unknown"
    if hasil_kg >= 50:
        return "baik"
    if hasil_kg >= 15:
        return "sedang"
    if hasil_kg > 0:
        return "rendah"
    return "nihil"


def validation_summary() -> Dict[str, Any]:
    init_db()

    with _connect() as conn:
        rows = conn.execute("SELECT * FROM fisher_feedback").fetchall()

    total = len(rows)
    catches = [
        r["hasil_kg"] for r in rows
        if r["hasil_kg"] is not None
    ]

    avg_catch = round(sum(catches) / len(catches), 2) if catches else None

    result_counts = {"baik": 0, "sedang": 0, "rendah": 0, "nihil": 0, "unknown": 0}
    port_counts: Dict[str, int] = {}
    fish_counts: Dict[str, int] = {}

    for r in rows:
        result = classify_actual_result(r["hasil_kg"])
        result_counts[result] = result_counts.get(result, 0) + 1

        port = r["pelabuhan"] or "tidak_diisi"
        fish = r["jenis_ikan"] or "tidak_diisi"

        port_counts[port] = port_counts.get(port, 0) + 1
        fish_counts[fish] = fish_counts.get(fish, 0) + 1

    return {
        "module": "NELAYA-AI Field Validation Database",
        "version": "0.1",
        "total_reports": total,
        "avg_catch_kg": avg_catch,
        "actual_result_counts": result_counts,
        "top_ports": sorted(port_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        "top_fish": sorted(fish_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        "scientific_caution": "Ringkasan ini masih indikatif. Validasi kuat membutuhkan jumlah laporan yang lebih banyak dan konsisten."
    }


def local_patterns(limit: int = 20) -> Dict[str, Any]:
    init_db()

    with _connect() as conn:
        rows = conn.execute("""
            SELECT pelabuhan, jenis_ikan, warna_air, arus_nelayan, kondisi_laut,
                   COUNT(*) as n,
                   AVG(hasil_kg) as avg_kg
            FROM fisher_feedback
            GROUP BY pelabuhan, jenis_ikan, warna_air, arus_nelayan, kondisi_laut
            HAVING n >= 2
            ORDER BY avg_kg DESC
            LIMIT ?
        """, (limit,)).fetchall()

    patterns = []
    for r in rows:
        patterns.append({
            "pelabuhan": r["pelabuhan"],
            "jenis_ikan": r["jenis_ikan"],
            "warna_air": r["warna_air"],
            "arus_nelayan": r["arus_nelayan"],
            "kondisi_laut": r["kondisi_laut"],
            "sample_count": r["n"],
            "avg_catch_kg": round(r["avg_kg"], 2) if r["avg_kg"] is not None else None,
            "interpretation": "Pola awal; belum dapat dianggap kausal sampai sampel bertambah."
        })

    return {
        "module": "Fisher Knowledge Pattern",
        "version": "0.1",
        "patterns": patterns,
        "note": "Pola hanya ditampilkan jika kombinasi kondisi muncul minimal 2 kali."
    }

import csv
import io


def export_feedback_csv() -> str:
    init_db()

    rows = list_feedback(limit=10000)
    if not rows:
        return "id,tanggal,nama_responden,pelabuhan,panglima_laot,lat,lon,alat_tangkap,jenis_ikan,hasil_kg,kondisi_laut,arus_nelayan,warna_air,cuaca,catatan_lokal,created_at\n"

    output = io.StringIO()
    fieldnames = [
        "id", "tanggal", "nama_responden", "pelabuhan", "panglima_laot",
        "lat", "lon", "alat_tangkap", "jenis_ikan", "hasil_kg",
        "kondisi_laut", "arus_nelayan", "warna_air", "cuaca",
        "catatan_lokal", "created_at"
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in rows:
        writer.writerow({k: row.get(k) for k in fieldnames})

    return output.getvalue()


def validation_dashboard() -> Dict[str, Any]:
    summary = validation_summary()

    total_reports = summary.get("total_reports", 0) or 0
    top_ports = summary.get("top_ports", [])
    top_fish = summary.get("top_fish", [])

    active_ports = len(top_ports)
    top_species = top_fish[0][0] if top_fish else None

    if total_reports >= 300:
        confidence = "tinggi"
        progress_label = "validasi kuat mulai terbentuk"
    elif total_reports >= 100:
        confidence = "sedang"
        progress_label = "validasi awal cukup berkembang"
    elif total_reports >= 30:
        confidence = "awal"
        progress_label = "sinyal lapangan mulai terbaca"
    else:
        confidence = "rendah"
        progress_label = "fase belajar awal"

    target_min_reports = 300
    progress_percent = round(min(total_reports / target_min_reports * 100, 100), 1)

    return {
        "module": "NELAYA-AI Field Validation Dashboard",
        "version": "0.1",
        "total_reports": total_reports,
        "active_ports": active_ports,
        "top_species": top_species,
        "avg_catch_kg": summary.get("avg_catch_kg"),
        "confidence": confidence,
        "field_validation_progress_percent": progress_percent,
        "field_validation_status": progress_label,
        "top_ports": top_ports,
        "actual_result_counts": summary.get("actual_result_counts"),
        "next_steps": [
            "Tambah laporan dari nelayan mitra",
            "Kumpulkan data dari beberapa pelabuhan",
            "Bandingkan hasil lapangan dengan nilai FGI harian",
            "Bangun confidence layer berbasis bukti lapangan"
        ],
        "scientific_caution": "Dashboard ini masih ringkasan awal. Kekuatan validasi meningkat setelah laporan bertambah dan tersebar lintas wilayah."
    }

import shutil


def backup_database() -> Dict[str, Any]:
    init_db()

    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"nelayan_feedback_backup_{timestamp}.db"

    shutil.copy2(DB_PATH, backup_path)

    return {
        "ok": True,
        "message": "Backup database berhasil dibuat.",
        "source": str(DB_PATH),
        "backup_path": str(backup_path),
        "created_at": _now()
    }

import json


def ensure_ocean_context_column() -> None:
    init_db()
    with _connect() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(fisher_feedback)").fetchall()]
        if "ocean_context_json" not in cols:
            conn.execute("ALTER TABLE fisher_feedback ADD COLUMN ocean_context_json TEXT")


def get_ocean_context(lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Any]:
    earth_path = Path("data/earth/earth_signals_today.json")

    context = {
        "available": False,
        "lat": lat,
        "lon": lon,
        "scope": "regional_daily_context",
        "note": "Konteks laut regional/harian NELAYA-AI, bukan pengukuran langsung di titik GPS."
    }

    if not earth_path.exists():
        context["reason"] = "earth_signals_today.json tidak ditemukan"
        return context

    try:
        data = json.loads(earth_path.read_text())
        metrics = data.get("metrics", {}) or {}

        context.update({
            "available": True,
            "date": data.get("date") or data.get("generated_at"),
            "fgi": metrics.get("fgi"),
            "fgi_current_aware": metrics.get("fgi_current_aware"),
            "sst_c": metrics.get("sst_c"),
            "chl_mg_m3": metrics.get("chl_mg_m3"),
            "current_ms": metrics.get("current_ms"),
            "current_direction_label": metrics.get("current_direction_label"),
            "wave_m": metrics.get("wave_m") or metrics.get("hs_m"),
            "wind_ms": metrics.get("wind_ms"),
            "osi": metrics.get("osi"),
            "source_file": str(earth_path),
        })
        return context

    except Exception as e:
        context["reason"] = f"gagal membaca earth_signals_today.json: {e}"
        return context

def ocean_context_analytics() -> Dict[str, Any]:
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT ocean_context_json, jenis_ikan, warna_air, arus_nelayan FROM fisher_feedback"
        ).fetchall()

    import json

    fgi_values=[]
    fgi_ca_values=[]
    sst_values=[]
    current_values=[]
    wave_values=[]
    osi_values=[]

    fish_patterns={}

    for r in rows:
        oc = r["ocean_context_json"]

        if not oc:
            continue

        try:
            if isinstance(oc,str):
                oc=json.loads(oc)

            fgi=oc.get("fgi",{})
            fgi_ca=oc.get("fgi_current_aware",{})
            osi=oc.get("osi",{})

            fgi_values.append(fgi.get("value"))
            fgi_ca_values.append(fgi_ca.get("value"))
            osi_values.append(osi.get("value"))

            sst=oc.get("sst_c") or fgi.get("inputs",{}).get("sst_c")
            wave=oc.get("wave_m") or osi.get("inputs",{}).get("wave_m")

            if sst is not None:
                sst_values.append(sst)

            if wave is not None:
                wave_values.append(wave)

            if oc.get("current_ms") is not None:
                current_values.append(oc.get("current_ms"))

            fish=r["jenis_ikan"] or "unknown"

            if fish not in fish_patterns:
                fish_patterns[fish]=0

            fish_patterns[fish]+=1

        except:
            pass

    def avg(arr):
        vals=[x for x in arr if x is not None]
        return round(sum(vals)/len(vals),3) if vals else None

    total_reports=len(rows)

    return {
        "module":"Ocean Context Analytics",
        "version":"0.1",
        "total_reports":total_reports,

        "averages":{
            "fgi":avg(fgi_values),
            "fgi_current_aware":avg(fgi_ca_values),
            "sst_c":avg(sst_values),
            "current_ms":avg(current_values),
            "wave_m":avg(wave_values),
            "osi":avg(osi_values)
        },

        "fish_patterns":fish_patterns,

        "evidence_status":
            "cukup awal" if total_reports>=20
            else "belum cukup bukti",

        "scientific_caution":
        "Hubungan awal bersifat indikatif dan belum menunjukkan hubungan sebab-akibat."
    }

def ocean_context_analytics() -> Dict[str, Any]:
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT ocean_context_json, jenis_ikan, warna_air, arus_nelayan FROM fisher_feedback"
        ).fetchall()

    import json

    fgi_values=[]
    fgi_ca_values=[]
    sst_values=[]
    current_values=[]
    wave_values=[]
    osi_values=[]

    fish_patterns={}

    for r in rows:
        oc = r["ocean_context_json"]

        if not oc:
            continue

        try:
            if isinstance(oc,str):
                oc=json.loads(oc)

            fgi=oc.get("fgi",{})
            fgi_ca=oc.get("fgi_current_aware",{})
            osi=oc.get("osi",{})

            fgi_values.append(fgi.get("value"))
            fgi_ca_values.append(fgi_ca.get("value"))
            osi_values.append(osi.get("value"))

            sst=oc.get("sst_c") or fgi.get("inputs",{}).get("sst_c")
            wave=oc.get("wave_m") or osi.get("inputs",{}).get("wave_m")

            if sst is not None:
                sst_values.append(sst)

            if wave is not None:
                wave_values.append(wave)

            if oc.get("current_ms") is not None:
                current_values.append(oc.get("current_ms"))

            fish=r["jenis_ikan"] or "unknown"

            if fish not in fish_patterns:
                fish_patterns[fish]=0

            fish_patterns[fish]+=1

        except:
            pass

    def avg(arr):
        vals=[x for x in arr if x is not None]
        return round(sum(vals)/len(vals),3) if vals else None

    total_reports=len(rows)

    return {
        "module":"Ocean Context Analytics",
        "version":"0.1",
        "total_reports":total_reports,

        "averages":{
            "fgi":avg(fgi_values),
            "fgi_current_aware":avg(fgi_ca_values),
            "sst_c":avg(sst_values),
            "current_ms":avg(current_values),
            "wave_m":avg(wave_values),
            "osi":avg(osi_values)
        },

        "fish_patterns":fish_patterns,

        "evidence_status":
            "cukup awal" if total_reports>=20
            else "belum cukup bukti",

        "scientific_caution":
        "Hubungan awal bersifat indikatif dan belum menunjukkan hubungan sebab-akibat."
    }

def relationship_analytics():
    init_db()

    with _connect() as conn:
        rows = conn.execute("""
        SELECT
            jenis_ikan,
            arus_nelayan,
            warna_air,
            ocean_context_json
        FROM fisher_feedback
        """).fetchall()

    import json
    from collections import Counter

    groups = {}

    for r in rows:
        fish = r["jenis_ikan"] or "unknown"

        if fish not in groups:
            groups[fish] = {
                "fgi": [],
                "sst": [],
                "arus": [],
                "warna": [],
                "count": 0
            }

        groups[fish]["count"] += 1
        groups[fish]["arus"].append(r["arus_nelayan"])
        groups[fish]["warna"].append(r["warna_air"])

        oc = r["ocean_context_json"]

        if oc:
            try:
                if isinstance(oc, str):
                    oc = json.loads(oc)

                fgi = oc.get("fgi",{}).get("value")
                sst = (
                    oc.get("sst_c")
                    or oc.get("fgi",{}).get("inputs",{}).get("sst_c")
                )

                if fgi is not None:
                    groups[fish]["fgi"].append(fgi)

                if sst is not None:
                    groups[fish]["sst"].append(sst)

            except:
                pass

    def avg(arr):
        vals=[x for x in arr if x is not None]
        return round(sum(vals)/len(vals),3) if vals else None

    signals=[]

    for fish,v in groups.items():

        dominant_current = (
            Counter([x for x in v["arus"] if x]).most_common(1)
        )

        dominant_color = (
            Counter([x for x in v["warna"] if x]).most_common(1)
        )

        signals.append({
            "fish": fish,
            "sample_count": v["count"],
            "avg_fgi": avg(v["fgi"]),
            "avg_sst_c": avg(v["sst"]),
            "dominant_current":
                dominant_current[0][0] if dominant_current else None,
            "dominant_water_color":
                dominant_color[0][0] if dominant_color else None,
            "evidence":
                "cukup awal"
                if v["count"]>=20
                else "belum cukup bukti"
        })

    return {
        "module":"Relationship Analytics",
        "version":"0.1",
        "signals":signals,
        "scientific_caution":
        "Hubungan awal bersifat indikatif dan tidak menunjukkan hubungan sebab-akibat."
    }


def list_ports() -> Dict[str, Any]:
    path = Path("data/reference/pelabuhan_aceh.json")

    if not path.exists():
        return {"ok": False, "ports": [], "reason": "pelabuhan_aceh.json tidak ditemukan"}

    try:
        ports = json.loads(path.read_text())
        return {
            "ok": True,
            "source": str(path),
            "count": len(ports),
            "ports": ports
        }
    except Exception as e:
        return {"ok": False, "ports": [], "reason": str(e)}
