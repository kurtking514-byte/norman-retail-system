from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    if (
        body.username != settings.ADMIN_USERNAME
        or not verify_password(body.password, settings.ADMIN_PASSWORD_HASH)
    ):
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
    access_token = create_access_token(data={"sub": body.username})
    return TokenResponse(access_token=access_token)
