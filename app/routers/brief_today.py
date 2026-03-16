from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.services.brief_builder import build_today_brief

router = APIRouter(prefix="/api/v1/brief", tags=["brief-v1"])


@router.get("/today")
async def brief_today(
    audience: str = Query("nelayan", pattern="^(nelayan|stakeholder|internal)$"),
    format: str = Query("json", pattern="^(json|text)$"),
):
    brief = await build_today_brief(audience=audience)

    if format == "text":
        return PlainTextResponse(brief.get("whatsapp_text", ""))

    return brief
