from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.inventory import router as inventory_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.reservations import router as reservations_router
from app.api.v1.endpoints.repairs import router as repairs_router
from app.api.v1.endpoints.webhook import router as webhook_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.notifications import router as notifications_router

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router, prefix="/auth")
router.include_router(products_router, prefix="/products")
router.include_router(inventory_router, prefix="/inventory")
router.include_router(reservations_router, prefix="")
router.include_router(repairs_router, prefix="")
router.include_router(webhook_router, prefix="")
router.include_router(conversations_router, prefix="")
router.include_router(notifications_router, prefix="")
