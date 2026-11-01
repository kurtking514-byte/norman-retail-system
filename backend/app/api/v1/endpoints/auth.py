from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.rate_limit import login_limiter
from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(tags=["Auth"])


def _client_ip(request: Request) -> str:
    # Render sits behind a proxy, so the real client IP is in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    ip = _client_ip(request)

    retry_after = login_limiter.retry_after(ip, body.username)
    if retry_after:
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "success": False,
                "error": {
                    "code": "TOO_MANY_ATTEMPTS",
                    "message": f"Too many failed login attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                    "details": [],
                },
            },
            headers={"Retry-After": str(retry_after)},
        )

    if (
        body.username != settings.ADMIN_USERNAME
        or not verify_password(body.password, settings.ADMIN_PASSWORD_HASH)
    ):
        login_limiter.record_failure(ip, body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Incorrect username or password.",
                    "details": [],
                },
            },
        )

    login_limiter.record_success(ip)
    access_token = create_access_token(data={"sub": body.username})
    return TokenResponse(access_token=access_token)
