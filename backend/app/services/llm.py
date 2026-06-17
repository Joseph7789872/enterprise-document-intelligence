"""LLM provider abstraction.

``LLMClient`` is the interface the agent nodes code against. ``AnthropicLLM`` calls
Claude via the official async SDK (structured outputs via ``messages.parse``,
token streaming via ``messages.stream``). ``FakeLLM`` is a deterministic, network-free
stand-in so the full multi-agent graph and the test suite run offline without an API
key. ``get_llm()`` selects one based on settings (mirrors ``get_embedder``).

Security note: callers pass already-decrypted context to the LLM in memory only;
nothing here persists prompt content.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any, Protocol, TypeVar, cast

from pydantic import BaseModel

from app.agents.state import SubQueryPlan, Verification
from app.core.config import settings

TModel = TypeVar("TModel", bound=BaseModel)

# A chat message: {"role": "user"|"assistant", "content": "..."}.
Message = dict[str, str]


class LLMClient(Protocol):
    async def complete(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> str: ...

    async def parse(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        schema: type[TModel],
        max_tokens: int,
    ) -> TModel: ...

    def stream(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str]: ...


class AnthropicLLM:
    """Anthropic Claude via the official async SDK."""

    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)

    async def complete(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> str:
        resp = await self._client.messages.create(
            model=model, max_tokens=max_tokens, system=system, messages=cast(Any, messages)
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    async def parse(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        schema: type[TModel],
        max_tokens: int,
    ) -> TModel:
        resp = await self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=cast(Any, messages),
            output_format=schema,
        )
        parsed = resp.parsed_output
        if parsed is None:  # refusal / unparseable
            raise LLMError("Model did not return a parseable structured response.")
        return parsed

    async def stream(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=model, max_tokens=max_tokens, system=system, messages=cast(Any, messages)
        ) as s:
            async for text in s.text_stream:
                yield text


class LLMError(Exception):
    """Raised on LLM failures (refusal, unparseable output)."""


class OpenAICompatibleLLM:
    """A self-hosted, OpenAI-compatible chat endpoint (vLLM / Ollama / TGI).

    Uses the OpenAI async SDK pointed at ``base_url``. Structured outputs are produced
    *portably* (no vendor-specific guided decoding): the JSON schema is appended to the
    system prompt, the response is requested as a JSON object, and the first JSON object
    in the reply is validated against the pydantic schema. Self-hosted models are smaller
    and less reliable at this, so a parse failure raises ``LLMError`` — the workflow nodes
    already degrade gracefully (planner → original question, verifier → low confidence →
    human review) rather than emitting an ungrounded answer.
    """

    def __init__(self, *, base_url: str, api_key: str = "") -> None:
        from openai import AsyncOpenAI

        # Many self-hosted servers ignore the key, but the SDK requires a non-empty value.
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key or "not-needed")

    @staticmethod
    def _chat_messages(system: str, messages: list[Message]) -> list[Message]:
        return [{"role": "system", "content": system}, *messages]

    async def complete(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=cast(Any, self._chat_messages(system, messages)),
        )
        return resp.choices[0].message.content or ""

    async def parse(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        schema: type[TModel],
        max_tokens: int,
    ) -> TModel:
        schema_text = json.dumps(schema.model_json_schema())
        guided_system = (
            f"{system}\n\nRespond with ONLY a single JSON object that conforms to this "
            f"JSON Schema (no prose, no code fences):\n{schema_text}"
        )
        resp = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=cast(Any, self._chat_messages(guided_system, messages)),
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        payload = _extract_json(content)
        if payload is None:
            raise LLMError("Self-hosted model did not return a parseable JSON object.")
        try:
            return schema.model_validate_json(payload)
        except Exception as exc:  # noqa: BLE001 - normalize to the shared LLM error
            raise LLMError(f"Self-hosted JSON did not match {schema.__name__}: {exc}") from exc

    async def stream(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=cast(Any, self._chat_messages(system, messages)),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


def _extract_json(text: str) -> str | None:
    """Return the first balanced top-level JSON object in ``text`` (tolerant of prose or
    code fences around it), or None if none is found."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class FakeLLM:
    """Deterministic, offline LLM for dev/test.

    - ``parse`` returns canned values by schema: a single sub-query equal to the
      question, and high verifier confidence unless the question contains the
      ``[lowconf]`` marker (which forces the human-review route for testing).
    - ``complete``/``stream`` emit a grounded answer that quotes the first retrieved
      source and cites it as ``[1]`` (so offline RAGAS-style scoring sees real
      grounding); when no sources are present it declines to answer.
    """

    async def complete(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> str:
        return self._answer(messages)

    async def parse(
        self,
        *,
        model: str,
        system: str,
        messages: list[Message],
        schema: type[TModel],
        max_tokens: int,
    ) -> TModel:
        question = _last_user_text(messages)
        name = schema.__name__
        if name == "SubQueryPlan":
            return cast(TModel, SubQueryPlan(subqueries=[question]))
        if name == "Verification":
            low = "[lowconf]" in question
            return cast(
                TModel,
                Verification(
                    confidence=0.1 if low else 0.95,
                    is_grounded=not low,
                    confidentiality_concern=False,
                    issues=["low confidence (fake)"] if low else [],
                ),
            )
        raise LLMError(f"FakeLLM has no canned output for schema {name!r}.")

    async def stream(
        self, *, model: str, system: str, messages: list[Message], max_tokens: int
    ) -> AsyncIterator[str]:
        for piece in self._answer(messages).split(" "):
            yield piece + " "

    @staticmethod
    def _answer(messages: list[Message]) -> str:
        """Build a deterministic, grounded answer from the synthesizer prompt.

        Quotes the first retrieved source verbatim and cites it ``[1]`` — so the answer
        is genuinely entailed by the context (good faithfulness) and on-topic. With no
        sources, it declines (matching the synthesizer's grounding instruction).
        """
        prompt = _last_user_text(messages)
        snippet = _first_source_snippet(prompt)
        if not snippet:
            return "I don't have enough information in the provided sources to answer."
        return f"According to the sources, {snippet} [1]"


# Capture the body of source [1] from a ``format_sources`` block.
_SOURCE_1_RE = re.compile(
    r"\[1\] \(file:[^)]*\)\n(.+?)(?=\n\n\[\d+\]|\n\n</sources>|</sources>|\Z)",
    re.DOTALL,
)


def _first_source_snippet(prompt: str, max_words: int = 80) -> str:
    """Extract the first ~``max_words`` words of source [1] from a synthesizer prompt."""
    if "(no sources retrieved)" in prompt:
        return ""
    match = _SOURCE_1_RE.search(prompt)
    if not match:
        return ""
    words = match.group(1).split()
    return " ".join(words[:max_words]).strip()


def _last_user_text(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


@lru_cache
def get_llm() -> LLMClient:
    """Return the configured baseline LLM client (cached per process).

    This is the "cloud"/baseline profile. The Phase 7 model router additionally builds a
    self-hosted profile from ``LLM_BASE_URL`` for classification-based routing.
    """
    provider = settings.effective_llm_provider
    if provider == "fake":
        return FakeLLM()
    if provider == "openai_compatible":
        return OpenAICompatibleLLM(
            base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY
        )
    return AnthropicLLM(api_key=settings.ANTHROPIC_API_KEY)
