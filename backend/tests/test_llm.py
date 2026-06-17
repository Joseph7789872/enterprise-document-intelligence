"""LLM client tests (FakeLLM + factory)."""

from __future__ import annotations

import pytest
from app.agents.state import SubQueryPlan, Verification
from app.services.llm import FakeLLM, get_llm


@pytest.mark.asyncio
async def test_fake_plans_single_subquery() -> None:
    llm = FakeLLM()
    plan = await llm.parse(
        model="x", system="", messages=[{"role": "user", "content": "How much vacation?"}],
        schema=SubQueryPlan, max_tokens=256,
    )
    assert plan.subqueries == ["How much vacation?"]


@pytest.mark.asyncio
async def test_fake_verifier_high_confidence_by_default() -> None:
    llm = FakeLLM()
    ver = await llm.parse(
        model="x", system="", messages=[{"role": "user", "content": "normal question"}],
        schema=Verification, max_tokens=256,
    )
    assert ver.confidence >= 0.6
    assert ver.is_grounded


@pytest.mark.asyncio
async def test_fake_verifier_low_confidence_marker() -> None:
    llm = FakeLLM()
    ver = await llm.parse(
        model="x", system="", messages=[{"role": "user", "content": "[lowconf] question"}],
        schema=Verification, max_tokens=256,
    )
    assert ver.confidence < 0.6
    assert not ver.is_grounded


# A synthesizer-shaped prompt with a delimited sources block (see prompts.format_sources).
_SYNTH_PROMPT = (
    "Question: What is the remote work policy?\n\n"
    "<sources>\n\n"
    "[1] (file: policy.txt)\nRemote work is permitted up to three days per week.\n\n"
    "</sources>"
)


@pytest.mark.asyncio
async def test_fake_complete_and_stream_cite_sources() -> None:
    llm = FakeLLM()
    messages = [{"role": "user", "content": _SYNTH_PROMPT}]
    answer = await llm.complete(model="x", system="", messages=messages, max_tokens=256)
    assert "[1]" in answer
    # The fake answer quotes the retrieved source, so it is genuinely grounded.
    assert "remote work is permitted" in answer.lower()
    streamed = "".join([t async for t in llm.stream(model="x", system="", messages=messages, max_tokens=256)])
    assert streamed.strip() == answer.strip()


@pytest.mark.asyncio
async def test_fake_declines_without_sources() -> None:
    llm = FakeLLM()
    answer = await llm.complete(
        model="x", system="", messages=[{"role": "user", "content": "Question: q\n\n<sources>\n(no sources retrieved)\n</sources>"}],
        max_tokens=256,
    )
    assert "[1]" not in answer
    assert "enough information" in answer.lower()


def test_factory_returns_fake_in_dev() -> None:
    assert isinstance(get_llm(), FakeLLM)
