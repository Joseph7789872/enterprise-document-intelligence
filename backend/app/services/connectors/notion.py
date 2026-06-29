"""Notion connector client.

A Protocol + factory (like the URL fetcher) so the connector endpoints depend on an
interface, the real client talks to api.notion.com with the tenant's integration token,
and tests inject a ``FakeNotionClient`` via :func:`set_notion_client` — no network.

The integration-token model (NOT OAuth): a manager creates an internal Notion integration,
shares the pages they want indexed with it, and pastes the token. We ``/search`` for shared
pages and assemble each page's plain text from its top-level blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

_NOTION_VERSION = "2022-06-28"
# Block types whose rich_text we treat as body content.
_TEXT_BLOCKS = (
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "quote",
    "callout",
    "to_do",
    "toggle",
)


class NotionError(Exception):
    """A Notion API call failed (bad token, network, rate limit)."""


@dataclass(frozen=True)
class NotionPage:
    id: str
    title: str
    text: str


class NotionClient(Protocol):
    async def list_pages(self, token: str) -> list[NotionPage]: ...


class FakeNotionClient:
    """Deterministic, offline Notion client for tests."""

    def __init__(self, pages: list[NotionPage], *, valid_token: str | None = None) -> None:
        self._pages = pages
        self._valid_token = valid_token

    async def list_pages(self, token: str) -> list[NotionPage]:
        if self._valid_token is not None and token != self._valid_token:
            raise NotionError("Invalid Notion token.")
        return self._pages


def _rich_text(block: dict) -> str:
    body = block.get(block.get("type", ""), {})
    spans = body.get("rich_text", []) if isinstance(body, dict) else []
    return "".join(s.get("plain_text", "") for s in spans)


class HttpxNotionClient:
    async def list_pages(self, token: str) -> list[NotionPage]:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }
        base = settings.NOTION_API_BASE.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                search = await client.post(
                    f"{base}/search",
                    headers=headers,
                    json={"filter": {"property": "object", "value": "page"}},
                )
                search.raise_for_status()
                pages: list[NotionPage] = []
                for obj in search.json().get("results", []):
                    page_id = obj.get("id", "")
                    title = _page_title(obj) or "Untitled"
                    text = await self._page_text(client, headers, base, page_id)
                    if text:
                        pages.append(NotionPage(id=page_id, title=title, text=text))
                return pages
        except httpx.HTTPError as exc:
            raise NotionError(f"Notion API request failed: {exc}") from exc

    async def _page_text(self, client, headers, base, page_id: str) -> str:  # type: ignore[no-untyped-def]
        """Assemble plaintext from a page's top-level blocks (paginated)."""
        lines: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, str | int] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            resp = await client.get(
                f"{base}/blocks/{page_id}/children", headers=headers, params=params
            )
            resp.raise_for_status()
            payload = resp.json()
            for block in payload.get("results", []):
                if block.get("type") in _TEXT_BLOCKS:
                    line = _rich_text(block).strip()
                    if line:
                        lines.append(line)
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
        return "\n".join(lines)


def _page_title(obj: dict) -> str:
    """Pull a page title from a Notion page object's properties."""
    props = obj.get("properties", {})
    for prop in props.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return "".join(s.get("plain_text", "") for s in prop.get("title", []))
    return ""


# Test-injectable override (explicit hook; see fetcher.py for the rationale).
_override: NotionClient | None = None


def set_notion_client(client: NotionClient | None) -> None:
    global _override
    _override = client


def get_notion_client() -> NotionClient:
    return _override if _override is not None else HttpxNotionClient()
