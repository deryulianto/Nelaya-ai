from collections import Counter
from fastapi import APIRouter, HTTPException

from auth_service.app.services.listing_store import list_all_listings
from auth_service.app.services.buyer_interest_store import list_all_buyer_interests

router = APIRouter(prefix="/api/v1/public", tags=["Marketplace Insight"])


def _safe_top(counter: Counter):
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _build_signals(active_listings: int, buyer_interests: int, dsr: float, top_quality: str | None):
    signals: list[str] = []

    if active_listings <= 0:
        signals.append("Belum ada listing aktif")
        return signals

    if dsr < 1:
        signals.append("Pasar masih relatif tenang")
    elif dsr <= 2:
        signals.append("Permintaan mulai terbentuk")
    else:
        signals.append("Minat buyer lebih cepat daripada suplai")

    if active_listings <= 3:
        signals.append("Suplai masih terbatas")
    else:
        signals.append("Pilihan listing mulai bertambah")

    if top_quality == "A":
        signals.append("Mutu tinggi menarik minat awal")
    elif top_quality:
        signals.append("Minat buyer mulai terbentuk lintas mutu")

    return signals


def _build_narrative(
    active_listings: int,
    buyer_interests: int,
    dsr: float,
    top_port: str | None,
    top_species: str | None,
    top_quality: str | None,
):
    port_label = {
        "tamiang": "Aceh Tamiang",
        "langsa": "Kota Langsa",
        "aceh_timur": "Aceh Timur",
        "aceh_utara": "Aceh Utara",
        "banda_aceh": "Banda Aceh",
        "aceh_besar": "Aceh Besar",
    }.get(top_port or "", top_port or "wilayah yang belum dominan")

    species_label = {
        "pelagis_campuran": "pelagis campuran",
        "demersal": "demersal",
        "campuran": "campuran",
    }.get(top_species or "", top_species or "hasil tangkap umum")

    quality_label = top_quality or "belum dominan"

    if active_listings <= 0:
        return (
            "Belum ada listing aktif pada marketplace saat ini, sehingga sinyal pasar belum cukup "
            "untuk dibaca. Tahap berikutnya adalah menambah listing yang tervalidasi agar dinamika "
            "minat buyer dapat diamati dengan lebih jelas."
        )

    if dsr > 2:
        return (
            f"Minat buyer saat ini lebih tinggi daripada jumlah listing aktif. Pada fase awal ini, "
            f"hasil tangkap {species_label} dari {port_label} dengan mutu {quality_label} mulai "
            f"menarik perhatian, sementara sisi suplai masih terbatas. Ini memberi sinyal awal bahwa "
            f"transparansi listing dan ketertelusuran dapat membantu membangun kepercayaan pasar."
        )

    if dsr >= 1:
        return (
            f"Marketplace mulai menunjukkan interaksi awal yang sehat. Listing aktif dan minat buyer "
            f"mulai bertemu, dengan kecenderungan pada hasil tangkap {species_label} dari {port_label} "
            f"dan mutu {quality_label}. Pada tahap ini, kualitas informasi listing dan jejak asal hasil "
            f"tangkap menjadi faktor penting untuk menjaga kepercayaan pasar."
        )

    return (
        f"Listing aktif saat ini masih lebih banyak daripada minat buyer yang masuk. Ini menunjukkan "
        f"bahwa tahap awal marketplace masih membutuhkan penguatan pada sisi permintaan, meskipun "
        f"hasil tangkap {species_label} dari {port_label} dengan mutu {quality_label} sudah mulai "
        f"tersusun dengan baik. Transparansi dan konsistensi data akan membantu pasar tumbuh lebih stabil."
    )


@router.get("/marketplace/insight")
def public_marketplace_insight():
    try:
        listings = list_all_listings()
        active_listings_rows = [
            r for r in listings if str(r.get("status", "")).lower() == "available"
        ]
        interests = list_all_buyer_interests()

        active_listings = len(active_listings_rows)
        buyer_interests = len(interests)
        dsr = round(buyer_interests / max(active_listings, 1), 2)

        port_counter = Counter()
        species_counter = Counter()
        quality_counter = Counter()

        for row in active_listings_rows:
            if row.get("landing_port"):
                port_counter[row["landing_port"]] += 1
            if row.get("species_group"):
                species_counter[row["species_group"]] += 1
            if row.get("quality_grade"):
                quality_counter[row["quality_grade"]] += 1

        top_port = _safe_top(port_counter)
        top_species = _safe_top(species_counter)
        top_quality = _safe_top(quality_counter)

        snapshot = {
            "active_listings": active_listings,
            "buyer_interests": buyer_interests,
            "demand_supply_ratio": dsr,
            "top_port": top_port,
            "top_species_group": top_species,
            "top_quality_grade": top_quality,
        }

        signals = _build_signals(active_listings, buyer_interests, dsr, top_quality)
        narrative = _build_narrative(
            active_listings,
            buyer_interests,
            dsr,
            top_port,
            top_species,
            top_quality,
        )

        return {
            "ok": True,
            "snapshot": snapshot,
            "signals": signals,
            "narrative": narrative,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
