"""OpenAI-compatible LLM client tests (Phase 7) — offline via a fake SDK client."""

from __future__ import annotations

import pytest
from app.agents.state import SubQueryPlan
from app.services.llm import LLMError, OpenAICompatibleLLM, _extract_json


# ── A minimal fake of the OpenAI async chat-completions surface ──────────────────────
class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Resp:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


class _DeltaChoice:
    def __init__(self, content: str) -> None:
        self.delta = _Message(content)


class _Chunk:
    def __init__(self, content: str) -> None:
        self.choices = [_DeltaChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str, tokens: list[str]) -> None:
        self._content = content
        self._tokens = tokens

    async def create(self, *, stream: bool = False, **_: object):  # type: ignore[no-untyped-def]
        if stream:
            async def gen():  # type: ignore[no-untyped-def]
                for t in self._tokens:
                    yield _Chunk(t)

            return gen()
        return _Resp(self._content)


def _llm(content: str = "", tokens: list[str] | None = None) -> OpenAICompatibleLLM:
    llm = OpenAICompatibleLLM(base_url="http://fake/v1", api_key="")
    llm._client.chat.completions = _FakeCompletions(content, tokens or [])  # type: ignore[attr-defined]
    return llm


@pytest.mark.asyncio
async def test_complete_joins_message_content() -> None:
    out = await _llm(content="hello there").complete(
        model="m", system="s", messages=[{"role": "user", "content": "hi"}], max_tokens=16
    )
    assert out == "hello there"


@pytest.mark.asyncio
async def test_stream_yields_tokens() -> None:
    pieces = []
    async for tok in _llm(tokens=["a", "b", "c"]).stream(
        model="m", system="s", messages=[{"role": "user", "content": "hi"}], max_tokens=16
    ):
        pieces.append(tok)
    assert pieces == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_parse_validates_good_json() -> None:
    content = 'Sure! {"subqueries": ["one", "two"]}'
    plan = await _llm(content=content).parse(
        model="m", system="s", messages=[{"role": "user", "content": "q"}],
        schema=SubQueryPlan, max_tokens=64,
    )
    assert plan.subqueries == ["one", "two"]


@pytest.mark.asyncio
async def test_parse_raises_on_unparseable_output() -> None:
    # No JSON object at all → LLMError (the workflow nodes degrade gracefully on this).
    with pytest.raises(LLMError):
        await _llm(content="I cannot help with that.").parse(
            model="m", system="s", messages=[{"role": "user", "content": "q"}],
            schema=SubQueryPlan, max_tokens=64,
        )


def test_extract_json_finds_first_balanced_object() -> None:
    assert _extract_json('prefix {"a": {"b": 1}} suffix') == '{"a": {"b": 1}}'
    assert _extract_json("no json here") is None
    # Braces inside strings don't confuse the scanner.
    assert _extract_json('{"k": "a}b"}') == '{"k": "a}b"}'
