"""Model router tests (Phase 7) — classification/tenant/mode routing + fail-closed."""

from __future__ import annotations

import pytest
from app.errors import LLMRoutingError
from app.models.document import ClassificationLevel as CL
from app.schemas.tenant import TenantSettings
from app.services.llm import FakeLLM
from app.services.model_router import ModelRouter, _SingleClientRouter


def _router(*, with_self_hosted: bool) -> ModelRouter:
    return ModelRouter(
        cloud=FakeLLM(), self_hosted=FakeLLM() if with_self_hosted else None
    )


def test_planner_uses_cloud_baseline() -> None:
    # The planner runs pre-retrieval (no classification) → baseline/cloud profile.
    route = _router(with_self_hosted=True).resolve("planner")
    assert route.profile == "cloud"


def test_non_sensitive_stays_cloud() -> None:
    route = _router(with_self_hosted=True).resolve("verifier", classification=CL.INTERNAL)
    assert route.profile == "cloud"


def test_confidential_routes_to_self_hosted() -> None:
    route = _router(with_self_hosted=True).resolve(
        "synthesizer", classification=CL.CONFIDENTIAL
    )
    assert route.profile == "self_hosted"


def test_fail_closed_when_self_hosted_required_but_absent() -> None:
    # The headline security property: no silent cloud fallback for sensitive content.
    with pytest.raises(LLMRoutingError):
        _router(with_self_hosted=False).resolve(
            "synthesizer", classification=CL.CONFIDENTIAL
        )


def test_tenant_require_self_hosted_forces_profile() -> None:
    ts = TenantSettings(require_self_hosted_llm=True)
    # Even the planner (no classification) goes self-hosted under this policy.
    route = _router(with_self_hosted=True).resolve("planner", tenant_settings=ts)
    assert route.profile == "self_hosted"
    # And it fails closed when the profile is missing.
    with pytest.raises(LLMRoutingError):
        _router(with_self_hosted=False).resolve("planner", tenant_settings=ts)


def test_tenant_threshold_privileged_keeps_confidential_on_cloud() -> None:
    ts = TenantSettings(sensitive_classification="privileged")
    r = _router(with_self_hosted=True)
    assert r.resolve("verifier", classification=CL.CONFIDENTIAL, tenant_settings=ts).profile == "cloud"
    assert r.resolve("verifier", classification=CL.PRIVILEGED, tenant_settings=ts).profile == "self_hosted"


@pytest.mark.parametrize("mode", ["air_gapped", "private_cloud"])
def test_fully_private_modes_force_self_hosted(mode: str) -> None:
    route = _router(with_self_hosted=True).resolve(
        "planner", deployment_mode=mode, classification=CL.PUBLIC
    )
    assert route.profile == "self_hosted"


def test_single_client_router_always_returns_injected_client() -> None:
    fake = FakeLLM()
    r = _SingleClientRouter(fake)
    route = r.resolve("synthesizer", classification=CL.PRIVILEGED)
    assert route.profile == "cloud"
    assert route.client is fake
