"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, client_ip, get_current_user, get_db
from app.errors import AuthenticationError, ConflictError, NotFoundError
from app.schemas.auth import (
    AcceptInviteRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenPair,
)
from app.schemas.invitation import AcceptInviteResponse
from app.schemas.user import UserRead
from app.services import auth_service, invitation_service, password_reset_service
from app.services.auth_service import CredentialsError, RegistrationConflict

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Bootstrap a new tenant and its first owner user."""
    # Self-serve signup gate: hidden (404) when disabled or outside the SaaS deployment.
    if not settings.ENABLE_SIGNUP or settings.DEPLOYMENT_MODE != "saas":
        raise NotFoundError("Not found.")
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


# ── Phase D: invitation acceptance + password reset (all public) ─────────────────────
@router.post(
    "/accept-invite", response_model=AcceptInviteResponse, status_code=status.HTTP_201_CREATED
)
async def accept_invite(
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
) -> AcceptInviteResponse:
    """Join a workspace with a shared invite key; returns tokens for auto-login."""
    user, _tenant, tokens = await invitation_service.accept_invitation(
        db,
        tenant_slug=body.tenant_slug,
        email=body.email,
        invite_key=body.invite_key,
        password=body.password,
    )
    return AcceptInviteResponse(
        user_id=user.id,
        tenant_id=user.tenant_id,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Request a password-reset email. Always 202 (never reveals whether the account exists)."""
    await password_reset_service.request_reset(
        db, tenant_slug=body.tenant_slug, email=body.email, ip_address=client_ip(request)
    )
    return {"detail": "If that account exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Set a new password from a valid reset token."""
    await password_reset_service.complete_reset(
        db, raw_token=body.token, new_password=body.new_password, ip_address=client_ip(request)
    )
    return {"detail": "Your password has been reset. You can now sign in."}
