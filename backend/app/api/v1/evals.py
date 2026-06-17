"""Evaluation dashboard endpoints — admin/owner only, strictly tenant-scoped.

Read-only views over eval runs and their per-item results, for a later frontend
dashboard. Eval runs are created by the harness/CLI gate, never through the API, so
there is no write path here. Reads are tenant-scoped from the authenticated principal
(never a query parameter) and audited.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, client_ip, get_db, require_role
from app.errors import NotFoundError
from app.models.audit_log import AuditAction
from app.models.eval_result import EvalResult
from app.models.eval_run import EvalRun
from app.models.user import UserRole
from app.schemas.eval import EvalResultRead, EvalRunDetail, EvalRunSummary
from app.services import audit_service

router = APIRouter(prefix="/evals", tags=["evals"])


@router.get("/runs", response_model=list[EvalRunSummary])
async def list_eval_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[EvalRun]:
    """Return this tenant's eval runs, newest first."""
    result = await db.scalars(
        select(EvalRun)
        .where(EvalRun.tenant_id == current.tenant_id)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = list(result.all())
    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.EVAL_RESULTS_VIEWED,
        actor_user_id=current.id,
        resource_type="eval_run",
        metadata={"limit": limit, "offset": offset, "returned": len(runs)},
        ip_address=client_ip(request),
    )
    return runs


@router.get("/runs/{run_id}", response_model=EvalRunDetail)
async def get_eval_run(
    run_id: uuid.UUID,
    request: Request,
    current: CurrentUser = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> EvalRunDetail:
    """Return one eval run plus its per-item results (tenant-scoped; 404 cross-tenant)."""
    run = await db.get(EvalRun, run_id)
    if run is None or run.tenant_id != current.tenant_id:
        raise NotFoundError("Eval run not found.")

    results = (
        await db.scalars(
            select(EvalResult)
            .where(EvalResult.eval_run_id == run.id)
            .order_by(EvalResult.item_id)
        )
    ).all()

    await audit_service.write_event(
        db,
        tenant_id=current.tenant_id,
        action=AuditAction.EVAL_RESULTS_VIEWED,
        actor_user_id=current.id,
        resource_type="eval_run",
        resource_id=str(run.id),
        ip_address=client_ip(request),
    )

    return EvalRunDetail(
        id=run.id,
        status=run.status,
        passed=run.passed,
        dataset_name=run.dataset_name,
        dataset_size=run.dataset_size,
        llm_provider=run.llm_provider,
        evaluator_provider=run.evaluator_provider,
        git_sha=run.git_sha,
        mean_faithfulness=run.mean_faithfulness,
        mean_context_precision=run.mean_context_precision,
        mean_answer_relevancy=run.mean_answer_relevancy,
        thresholds=run.thresholds,
        created_at=run.created_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        results=[EvalResultRead.model_validate(r) for r in results],
    )
