"""Deployment-mode + feature-flag tests (Phase 7) — the air-gapped fail-fast guarantee."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def _air_gapped(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ENVIRONMENT": "development",
        "DEPLOYMENT_MODE": "air_gapped",
        "LLM_PROVIDER": "openai_compatible",
        "LLM_BASE_URL": "http://vllm:8000/v1",
        "EMBEDDING_PROVIDER": "sentence_transformers",
        "OBSERVABILITY_PROVIDER": "fake",
        "EVALS_PROVIDER": "fake",
    }
    base.update(overrides)
    return base


def test_air_gapped_accepts_fully_self_hosted_config() -> None:
    s = Settings(**_air_gapped())
    assert s.is_air_gapped is True
    assert s.is_fully_private is True


def test_air_gapped_rejects_cloud_llm() -> None:
    with pytest.raises(ValidationError, match="anthropic"):
        Settings(**_air_gapped(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="k"))


def test_air_gapped_rejects_cloud_embeddings() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_PROVIDER"):
        Settings(**_air_gapped(EMBEDDING_PROVIDER="openai", OPENAI_API_KEY="k"))


def test_air_gapped_rejects_cloud_evals_judge() -> None:
    with pytest.raises(ValidationError, match="EVALS_PROVIDER"):
        Settings(**_air_gapped(EVALS_PROVIDER="ragas"))


def test_air_gapped_requires_self_hosted_endpoint() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(**_air_gapped(LLM_BASE_URL=""))


def test_feature_flags_report_cloud_dependencies() -> None:
    s = Settings(
        ENVIRONMENT="development",
        DEPLOYMENT_MODE="saas",
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="k",
        EMBEDDING_PROVIDER="openai",
        OPENAI_API_KEY="k",
    )
    flags = s.feature_flags
    assert flags["cloud_llm"] is True
    assert flags["cloud_embeddings"] is True
    assert flags["external_subprocessors"] is True
    assert flags["self_hosted_llm"] is False


def test_feature_flags_clean_when_self_hosted() -> None:
    s = Settings(**_air_gapped())
    flags = s.feature_flags
    assert flags["cloud_llm"] is False
    assert flags["cloud_embeddings"] is False
    assert flags["external_subprocessors"] is False
    assert flags["self_hosted_llm"] is True
