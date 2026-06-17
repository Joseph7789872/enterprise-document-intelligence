"""Classification-aware LLM routing (Phase 7).

The router is the single place the platform decides *which client + model* answers a
given node, based on three inputs merged in order of authority:

    deployment mode  →  tenant policy  →  document classification

A "cloud" profile (the baseline ``get_llm()`` + per-node Claude models) and an optional
"self-hosted" profile (an OpenAI-compatible endpoint + ``SELF_HOSTED_LLM_MODEL``) are
built once. Sensitive documents route to the self-hosted profile.

Security: routing **fails closed**. If a route requires the self-hosted profile and it
is not configured, ``resolve`` raises ``LLMRoutingError`` (the caller audits it and
returns 503) — sensitive content is *never* sent to the cloud as a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.core.config import settings
from app.errors import LLMRoutingError
from app.models.document import ClassificationLevel
from app.schemas.tenant import TenantSettings
from app.services.llm import LLMClient, OpenAICompatibleLLM, get_llm

Profile = Literal["cloud", "self_hosted"]
Node = Literal["planner", "verifier", "synthesizer"]

# Sensitivity ordering used for "at/above the threshold" comparisons.
_RANK: dict[ClassificationLevel, int] = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.INTERNAL: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.PRIVILEGED: 3,
}


@dataclass(frozen=True)
class Route:
    """The resolved client/model for one node, plus which profile it came from (the
    profile is recorded in audit + trace metadata)."""

    client: LLMClient
    model: str
    profile: Profile


class ModelRouter:
    def __init__(self, *, cloud: LLMClient, self_hosted: LLMClient | None) -> None:
        self._cloud = cloud
        self._self_hosted = self_hosted

    def _cloud_model(self, node: Node) -> str:
        return {
            "planner": settings.PLANNER_MODEL,
            "verifier": settings.VERIFIER_MODEL,
            "synthesizer": settings.SYNTHESIZER_MODEL,
        }[node]

    def _self_hosted_route(self) -> Route:
        if self._self_hosted is None:
            raise LLMRoutingError(
                "Policy requires a self-hosted model for this content, but no "
                "self-hosted LLM endpoint (LLM_BASE_URL) is configured."
            )
        return Route(
            client=self._self_hosted,
            model=settings.SELF_HOSTED_LLM_MODEL,
            profile="self_hosted",
        )

    def resolve(
        self,
        node: Node,
        *,
        classification: ClassificationLevel | None = None,
        tenant_settings: TenantSettings | None = None,
        deployment_mode: str | None = None,
    ) -> Route:
        ts = tenant_settings or TenantSettings()
        mode = deployment_mode or settings.DEPLOYMENT_MODE

        # 1. Fully-private deployments run every node on the self-hosted profile.
        if mode in ("private_cloud", "air_gapped"):
            return self._self_hosted_route()
        # 2. Tenant policy forces self-hosted for all of this tenant's calls.
        if ts.require_self_hosted_llm:
            return self._self_hosted_route()
        # 3. Classification routing. The verifier/synthesizer carry the highest
        #    classification among retrieved documents; the planner runs pre-retrieval
        #    (classification=None) and stays on the baseline profile.
        if classification is not None:
            threshold = ClassificationLevel(ts.sensitive_classification)
            if _RANK[classification] >= _RANK[threshold]:
                return self._self_hosted_route()
        # 4. Default → cloud / baseline.
        return Route(client=self._cloud, model=self._cloud_model(node), profile="cloud")


class _SingleClientRouter(ModelRouter):
    """Routes every node to one injected client (used by tests, the eval harness and MCP
    tools that inject a ``FakeLLM``). Keeps the cloud per-node model names so audit/trace
    metadata is identical to pre-Phase-7 behavior."""

    def __init__(self, client: LLMClient) -> None:
        super().__init__(cloud=client, self_hosted=client)

    def resolve(
        self,
        node: Node,
        *,
        classification: ClassificationLevel | None = None,
        tenant_settings: TenantSettings | None = None,
        deployment_mode: str | None = None,
    ) -> Route:
        return Route(client=self._cloud, model=self._cloud_model(node), profile="cloud")


@lru_cache
def get_model_router() -> ModelRouter:
    """Return the configured router (cached per process).

    Builds the self-hosted profile only when ``LLM_BASE_URL`` is set; otherwise the
    router has no self-hosted profile and fails closed on any sensitive route.
    """
    self_hosted: LLMClient | None = None
    if settings.self_hosted_llm_configured:
        self_hosted = OpenAICompatibleLLM(
            base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY
        )
    return ModelRouter(cloud=get_llm(), self_hosted=self_hosted)
