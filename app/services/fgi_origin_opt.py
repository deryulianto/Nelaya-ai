from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.schemas.fgi_origin_opt import OptimizeOriginRequest, OptimizeOriginResponse


def optimize_origin(payload: OptimizeOriginRequest) -> OptimizeOriginResponse:
    """
    Minimal implementation supaya server bisa jalan.
    Nanti bisa kita upgrade jadi ranking origin beneran (pakai recommend + cost model).
    """
    now = datetime.now(timezone.utc).isoformat()

    # Coba pakai pipeline recommend jika memang ada di repo kamu
    try:
        # Import di dalam fungsi (lazy) supaya module ini tidak bikin server gagal start
        from app.schemas.fgi_recommend import RecommendationsRequest  # type: ignore
        from app.services.fgi_recommend import recommend  # type: ignore

        # best-effort mapping: ambil data payload jadi dict
        try:
            data: Dict[str, Any] = payload.model_dump()  # pydantic v2
        except Exception:
            data = payload.dict()  # pydantic v1

        rec_req = RecommendationsRequest(**data)
        rec = recommend(rec_req)  # harapannya return dict / pydantic model

        # Balikin hasil apa adanya + wrap field standar
        return OptimizeOriginResponse(
            ok=True,
            message="optimize-origin OK (via recommend)",
            generated_at=now,
            mode=getattr(payload, "mode", None),
            detail=rec,
        )

    except Exception as e:
        # Kalau recommend pipeline belum ada / belum cocok, tetap balikin response yang jelas
        return OptimizeOriginResponse(
            ok=False,
            message="optimize-origin service stub is running, but recommend pipeline is not available / incompatible yet",
            generated_at=now,
            error=str(e),
        )
