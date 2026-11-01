from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging_config import get_logger, setup_logging
from app.core.security import MIN_JWT_SECRET_LENGTH

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB on startup."""
    await init_db()
    logger.info("Database initialized")
    if len(settings.JWT_SECRET_KEY) < MIN_JWT_SECRET_LENGTH:
        logger.error(
            "JWT_SECRET_KEY is missing or shorter than %s characters — admin login "
            "tokens can be forged. Set a long random value.",
            MIN_JWT_SECRET_LENGTH,
        )
    if not settings.META_APP_SECRET:
        logger.warning(
            "META_APP_SECRET is not set — webhook signatures are not verified, so "
            "anyone can post fake Messenger events."
        )
    yield


app = FastAPI(title="Norman Cellphone Center And Repair Shop", lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server origins plus any deployed dashboard
# origins listed in FRONTEND_ORIGINS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *[
            origin.strip().rstrip("/")
            for origin in settings.FRONTEND_ORIGINS.split(",")
            if origin.strip()
        ],
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Custom exception handler – ensure all HTTP errors follow our standard
# {"success": false, "error": {...}} format.
# ---------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = getattr(exc, "headers", None)
    # If the detail is already in our standard format, use it directly
    if isinstance(exc.detail, dict) and "success" in exc.detail:
        content = exc.detail
    else:
        content = {
            "success": False,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": str(exc.detail),
                "details": [],
            },
        }
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


app.include_router(api_v1_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

