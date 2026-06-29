"""Agent workflow nodes.

``WorkflowRunner`` binds one request's context (DB session, tenant/user, trace id,
LLM/embedder/reranker) and exposes the graph nodes as async methods. Each node is
wrapped in a trace span; every LLM call is audited. Retrieval is tenant-scoped via the
Phase 2 hybrid retriever and chunk text is decrypted only into in-memory state.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import (
    PLANNER_SYSTEM,
    SYNTHESIZER_SYSTEM,
    VERIFIER_SYSTEM,
    format_history,
    format_sources,
)
from app.agents.state import (
    AgentState,
    Citation,
    QueryState,
    RetrievedChunk,
    SubQueryPlan,
    Verification,
)
from app.core.config import settings
from app.core.crypto import decrypt_str
from app.models.audit_log import AuditAction
from app.models.document import Document
from app.models.tenant import Tenant
from app.models.user import UserRole
from app.observability.tracing import record_generation, trace_span
from app.schemas.tenant import TenantSettings
from app.services import audit_service, authz, retrieval
from app.services.authz import Permission
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import LLMClient
from app.services.model_router import (
    ModelRouter,
    Node,
    Route,
    _SingleClientRouter,
    get_model_router,
)
from app.services.reranker import Reranker, get_reranker

_MARKER_RE = re.compile(r"\[(\d+)\]")


class WorkflowRunner:
    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: UserRole = UserRole.MEMBER,
        trace_id: str | None = None,
        llm: LLMClient | None = None,
        router: ModelRouter | None = None,
        tenant_settings: TenantSettings | None = None,
        deployment_mode: str | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        # The caller's role drives retrieval-time ACL scoping (OWNER/ADMIN ⇒ unrestricted).
        self.role = role
        self.trace_id = trace_id
        # Phase 7 model routing. An injected `llm` (tests / eval harness / MCP) pins every
        # node to that one client; otherwise the classification-aware router is used.
        self.router: ModelRouter = (
            _SingleClientRouter(llm) if llm is not None else (router or get_model_router())
        )
        self._tenant_settings = tenant_settings
        self.deployment_mode = deployment_mode or settings.DEPLOYMENT_MODE
        self.embedder = embedder or get_embedder()
        self.reranker = reranker or get_reranker()

    async def _resolve_tenant_settings(self) -> TenantSettings:
        """Load (and cache) this tenant's routing policy. Defaults when unset/missing."""
        if self._tenant_settings is None:
            tenant = await self.db.get(Tenant, self.tenant_id)
            self._tenant_settings = TenantSettings.from_raw(
                tenant.settings if tenant is not None else None
            )
        return self._tenant_settings

    async def _route(self, node: Node, state: AgentState) -> Route:
        """Resolve the client/model for a node from this tenant's policy + the deployment
        mode (air-gapped/private-cloud or a tenant self-hosted policy force self-hosted).
        Raises ``LLMRoutingError`` (fail-closed) when a self-hosted route is required but
        not configured — callers must let it propagate (not swallow it)."""
        return self.router.resolve(
            node,
            tenant_settings=await self._resolve_tenant_settings(),
            deployment_mode=self.deployment_mode,
        )

    async def _audit_llm(self, node: str, model: str, extra: dict | None = None) -> None:
        await audit_service.write_event(
            self.db,
            tenant_id=self.tenant_id,
            action=AuditAction.LLM_CALL,
            actor_user_id=self.user_id,
            resource_type="llm",
            metadata={"node": node, "model": model, **(extra or {})},
            trace_id=self.trace_id,
        )
        # Mirror the call into the trace as a generation (metadata only by default).
        record_generation(node=node, model=model, **(extra or {}))

    # ── Nodes ────────────────────────────────────────────────────────────────────

    async def planner(self, state: AgentState) -> AgentState:
        with trace_span("planner"):
            question = state["question"]
            # The planner runs pre-retrieval (no document classification yet) → baseline
            # profile. Resolve outside the try so a routing failure (e.g. self-hosted
            # required but unconfigured in a private deployment) is not swallowed.
            route = self.router.resolve(
                "planner",
                tenant_settings=await self._resolve_tenant_settings(),
                deployment_mode=self.deployment_mode,
            )
            # Prepend prior turns (if any) so the planner can resolve follow-up
            # references; empty for one-shot asks, leaving the prompt unchanged.
            user_content = format_history(state.get("history", [])) + question
            try:
                plan = await route.client.parse(
                    model=route.model,
                    system=PLANNER_SYSTEM,
                    messages=[{"role": "user", "content": user_content}],
                    schema=SubQueryPlan,
                    max_tokens=1024,
                )
                subs = [s.strip() for s in plan.subqueries if s.strip()][: settings.MAX_SUBQUERIES]
            except Exception:  # noqa: BLE001 - degrade to the original question
                subs = []
            subs = subs or [question]
            await self._audit_llm(
                "planner", route.model, {"subqueries": len(subs), "profile": route.profile}
            )
            return {"subqueries": subs, "status": QueryState.PROCESSING}

    async def retriever(self, state: AgentState) -> AgentState:
        with trace_span("retriever"):
            # Retrieval-time ACL: restrict to documents the user may QUERY (None for
            # OWNER/ADMIN ⇒ unrestricted). Computed once per request.
            allowed = await authz.accessible_document_ids(
                self.db,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                role=self.role,
                permission=Permission.QUERY,
            )
            merged: dict[uuid.UUID, retrieval.ScoredChunk] = {}
            for sq in state.get("subqueries", []):
                emb = await self.embedder.embed_query(sq)
                results = await retrieval.hybrid_search(
                    self.db,
                    tenant_id=self.tenant_id,
                    query=sq,
                    query_embedding=emb,
                    reranker=self.reranker,
                    final_k=settings.FINAL_TOP_K,
                    allowed_document_ids=allowed,
                )
                for sc in results:
                    cur = merged.get(sc.chunk.id)
                    if cur is None or sc.score > cur.score:
                        merged[sc.chunk.id] = sc

            scored = sorted(merged.values(), key=lambda s: s.score, reverse=True)
            scored = scored[: settings.FINAL_TOP_K]

            filename_cache: dict[uuid.UUID, str] = {}
            chunks: list[RetrievedChunk] = []
            for sc in scored:
                ch = sc.chunk
                if ch.document_id not in filename_cache:
                    doc = await self.db.get(Document, ch.document_id)
                    filename_cache[ch.document_id] = doc.filename if doc else ""
                chunks.append(
                    RetrievedChunk(
                        chunk_id=ch.id,
                        document_id=ch.document_id,
                        chunk_index=ch.chunk_index,
                        text=decrypt_str(ch.content_encrypted),
                        score=sc.score,
                        filename=filename_cache[ch.document_id],
                    )
                )
            return {"chunks": chunks}

    async def verifier(self, state: AgentState) -> AgentState:
        with trace_span("verifier"):
            chunks = state.get("chunks", [])
            if not chunks:
                return {
                    "verification": Verification(
                        confidence=0.0, is_grounded=False, issues=["no sources retrieved"]
                    )
                }
            prompt = f"Question: {state['question']}\n\n{format_sources(chunks)}"
            route = await self._route("verifier", state)
            try:
                ver = await route.client.parse(
                    model=route.model,
                    system=VERIFIER_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    schema=Verification,
                    max_tokens=1024,
                )
            except Exception as exc:  # noqa: BLE001 - treat verifier failure as low-confidence
                ver = Verification(
                    confidence=0.0, is_grounded=False, issues=[f"verifier error: {exc}"]
                )
            await self._audit_llm(
                "verifier", route.model, {"confidence": ver.confidence, "profile": route.profile}
            )
            return {"verification": ver}

    async def human_review(self, state: AgentState) -> AgentState:
        with trace_span("human_review"):
            return {"requires_approval": True, "status": QueryState.PENDING_APPROVAL}

    def _synth_messages(self, state: AgentState) -> list[dict[str, str]]:
        prompt = f"Question: {state['question']}\n\n{format_sources(state.get('chunks', []))}"
        return [{"role": "user", "content": prompt}]

    async def synthesizer(self, state: AgentState) -> AgentState:
        with trace_span("synthesizer"):
            # Resolve the route outside the try so a fail-closed LLMRoutingError
            # propagates (→ 503); the try guards only the inference call so a self-hosted
            # endpoint outage degrades to a clean failed status, not a 500.
            route = await self._route("synthesizer", state)
            try:
                answer = await route.client.complete(
                    model=route.model,
                    system=SYNTHESIZER_SYSTEM,
                    messages=self._synth_messages(state),
                    max_tokens=settings.SYNTHESIS_MAX_TOKENS,
                )
            except Exception as exc:  # noqa: BLE001 - endpoint failure → clean failed state
                await self._audit_llm(
                    "synthesizer", route.model, {"profile": route.profile, "error": True}
                )
                return {"status": QueryState.FAILED, "error": f"synthesis failed: {exc}"}
            await self._audit_llm("synthesizer", route.model, {"profile": route.profile})
            return {"answer": answer}

    async def synthesize_stream(self, state: AgentState) -> AsyncIterator[str]:
        """Token stream for the synthesizer, used by the streaming endpoint.

        The route is resolved before streaming begins, so a fail-closed routing error
        surfaces immediately rather than mid-stream."""
        route = await self._route("synthesizer", state)
        async for piece in route.client.stream(
            model=route.model,
            system=SYNTHESIZER_SYSTEM,
            messages=self._synth_messages(state),
            max_tokens=settings.SYNTHESIS_MAX_TOKENS,
        ):
            yield piece

    async def source_attributor(self, state: AgentState) -> AgentState:
        with trace_span("source_attributor"):
            # Preserve a failed synthesis instead of overwriting it with COMPLETED.
            if state.get("status") == QueryState.FAILED:
                return {}
            return {
                "citations": build_citations(state.get("answer", ""), state.get("chunks", [])),
                "status": QueryState.COMPLETED,
            }


def build_citations(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Map the ``[n]`` markers in the answer to their source chunks (deterministic)."""
    markers = sorted({int(m) for m in _MARKER_RE.findall(answer)})
    citations: list[Citation] = []
    for marker in markers:
        if 1 <= marker <= len(chunks):
            c = chunks[marker - 1]
            citations.append(
                Citation(
                    marker=marker,
                    document_id=c.document_id,
                    chunk_id=c.chunk_id,
                    filename=c.filename,
                    snippet=c.text[:300],
                )
            )
    return citations


def route_after_verify(state: AgentState) -> str:
    """Conditional edge: low confidence or a confidentiality flag → human review.

    When the human-review gate is disabled (the v1 sales default), we always synthesize:
    a low-confidence answer is still delivered (with its confidence surfaced) as an honest
    "here's what I found, I'm not fully sure" rather than being held for a human.
    """
    if not settings.ENABLE_HUMAN_REVIEW:
        return "synthesizer"
    ver = state.get("verification")
    if ver is None:
        return "human_review"
    if ver.confidentiality_concern or ver.confidence < settings.CONFIDENCE_THRESHOLD:
        return "human_review"
    return "synthesizer"
