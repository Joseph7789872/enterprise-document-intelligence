"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_current_user, get_db
from app.errors import AuthenticationError, ConflictError
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
)
from app.schemas.user import UserRead
from app.services import auth_service
from app.services.auth_service import CredentialsError, RegistrationConflict

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Bootstrap a new tenant and its first owner user."""
    try:
        tenant, user, tokens = await auth_service.register_tenant_and_owner(
            db,
            tenant_name=body.tenant_name,
            tenant_slug=body.tenant_slug,
            email=body.email,
            password=body.password,
            ip_address=client_ip(request),
        )
    except RegistrationConflict as exc:
        raise ConflictError(str(exc)) from exc

    return RegisterResponse.model_validate(
        {"tenant": tenant, "user": user, "tokens": tokens}
    )


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    try:
        _, tokens = await auth_service.authenticate(
            db,
            tenant_slug=body.tenant_slug,
            email=body.email,
            password=body.password,
            ip_address=client_ip(request),
        )
    except CredentialsError as exc:
        raise AuthenticationError("Invalid credentials.") from exc
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    try:
        return await auth_service.refresh_tokens(
            db, refresh_token=body.refresh_token, ip_address=client_ip(request)
        )
    except CredentialsError as exc:
        raise AuthenticationError("Invalid refresh token.") from exc


@router.get("/me", response_model=UserRead)
async def me(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    from app.models.user import User

    user = await db.get(User, current.id)
    if user is None:
        raise AuthenticationError("User no longer valid.")
    return UserRead.model_validate(user)
