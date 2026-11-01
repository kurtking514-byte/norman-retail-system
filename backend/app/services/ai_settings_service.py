"""
Service layer for the global AI auto-reply switch.

The switch is stored as a row in the ``settings`` table so staff can flip it
from the admin dashboard without redeploying. When no row exists yet, AI
replies are treated as enabled.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Setting

logger = logging.getLogger(__name__)

AI_REPLIES_KEY = "ai_replies_enabled"


async def get_ai_replies_enabled(db: AsyncSession) -> bool:
    """Return True if the AI chatbot should auto-reply to customers."""
    row = await db.get(Setting, AI_REPLIES_KEY)
    if row is None:
        return True
    return row.value == "true"


async def set_ai_replies_enabled(db: AsyncSession, enabled: bool) -> bool:
    """Persist the AI auto-reply switch and return the new value."""
    row = await db.get(Setting, AI_REPLIES_KEY)
    value = "true" if enabled else "false"
    if row is None:
        row = Setting(
            key=AI_REPLIES_KEY,
            value=value,
            description="Global switch for AI chatbot auto-replies on Messenger",
        )
        db.add(row)
    else:
        row.value = value
    await db.commit()
    logger.info("AI auto-replies globally set to %s", value)
    return enabled
