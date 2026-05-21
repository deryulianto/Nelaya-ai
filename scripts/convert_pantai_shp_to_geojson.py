#!/usr/bin/env python3
from pathlib import Path
import json
import shapefile

ROOT = Path(__file__).resolve().parents[1]

IN_SHP = ROOT / "data/coastline/pantai_4326/pantai_4326.shp"
OUT_GEOJSON = ROOT / "data/coastline/aceh_coastline_pantai_4326.geojson"

r = shapefile.Reader(str(IN_SHP))

fields = [f[0] for f in r.fields[1:]]
features = []

for sr in r.shapeRecords():
    shp = sr.shape
    rec = sr.record.as_dict() if hasattr(sr.record, "as_dict") else dict(zip(fields, sr.record))

    parts = list(shp.parts) + [len(shp.points)]
    lines = []

    for start, end in zip(parts[:-1], parts[1:]):
        coords = [[float(lon), float(lat)] for lon, lat in shp.points[start:end]]
        if len(coords) >= 2:
            lines.append(coords)

    if not lines:
        continue

    if len(lines) == 1:
        geom = {
            "type": "LineString",
            "coordinates": lines[0],
        }
    else:
        geom = {
            "type": "MultiLineString",
            "coordinates": lines,
        }

    features.append(
        {
            "type": "Feature",
            "properties": {
                **rec,
                "source": "pantai_4326.shp",
                "note": "Coastline vector untuk Legal-Aware FGI; verifikasi status legal/resmi tetap diperlukan.",
            },
            "geometry": geom,
        }
    )

geojson = {
    "type": "FeatureCollection",
    "module": "aceh_coastline_pantai_4326",
    "version": "0.1",
    "source_file": "data/coastline/pantai_4326/pantai_4326.shp",
    "feature_count": len(features),
    "limitations": [
        "Bersumber dari shapefile pantai_4326.",
        "Dipakai sebagai coastline vector operasional untuk Legal-Aware FGI.",
        "Belum dinyatakan sebagai garis pantai resmi untuk keputusan hukum final.",
    ],
    "features": features,
}

OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)

with OUT_GEOJSON.open("w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)

print(f"OK: wrote {OUT_GEOJSON}")
print(f"features={len(features)}")
print(f"bbox={r.bbox}")
print(f"shapeType={r.shapeTypeName}")
