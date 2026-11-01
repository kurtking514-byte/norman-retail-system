"""
Global AI chatbot switch for the admin dashboard.

Provides:
- ``GET /settings/ai-replies`` — whether the AI chatbot auto-replies.
- ``PUT /settings/ai-replies`` — turn AI auto-replies on or off for all
  customers. Incoming messages are still logged while it is off.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.services.ai_settings_service import (
    get_ai_replies_enabled,
    set_ai_replies_enabled,
)

router = APIRouter(tags=["Settings"])


class AiRepliesSetting(BaseModel):
    enabled: bool


@router.get("/settings/ai-replies", response_model=AiRepliesSetting)
async def read_ai_replies(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    return AiRepliesSetting(enabled=await get_ai_replies_enabled(db))


@router.put("/settings/ai-replies", response_model=AiRepliesSetting)
async def update_ai_replies(
    body: AiRepliesSetting,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    return AiRepliesSetting(enabled=await set_ai_replies_enabled(db, body.enabled))
