"""EDIP MCP server — exposes four ACL-enforced tools over stdio.

Thin adapter: it authenticates the configured ``EDIP_API_KEY`` to a principal, opens a
DB session per call, and dispatches to ``app.services.mcp_tools``. All authorization,
retrieval, and auditing happen in those shared functions — the server adds no privilege.

Run (needs the optional extra):

    uv sync --extra mcp
    EDIP_API_KEY="edip_xxx.secret" uv run python -m mcp_server.server

Then point an MCP client (e.g. Claude Desktop) at this stdio command.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.db.session import SessionLocal
from app.services import api_key_service, mcp_tools
from mcp.server.fastmcp import FastMCP

server = FastMCP("edip")


def _api_key() -> str:
    key = os.environ.get("EDIP_API_KEY", "")
    if not key:
        raise RuntimeError("EDIP_API_KEY is not set; cannot authenticate MCP tool calls.")
    return key


async def _run(handler) -> Any:  # type: ignore[no-untyped-def]
    """Open a session, authenticate the API key, dispatch, commit."""
    async with SessionLocal() as db:
        principal = await api_key_service.authenticate(db, _api_key())
        if principal is None:
            raise PermissionError("Invalid or revoked API key.")
        result = await handler(db, principal)
        await db.commit()
        return result


@server.tool()
async def query_documents(question: str) -> dict[str, Any]:
    """Ask a natural-language question; returns a grounded, cited answer."""
    return await _run(lambda db, p: mcp_tools.query_documents(db, p, question=question))


@server.tool()
async def search_chunks(query: str, top_k: int = 6) -> dict[str, Any]:
    """Hybrid search for the most relevant document chunks you may access."""
    return await _run(lambda db, p: mcp_tools.search_chunks(db, p, query=query, top_k=top_k))


@server.tool()
async def list_documents() -> dict[str, Any]:
    """List the documents you have permission to view."""
    return await _run(lambda db, p: mcp_tools.list_documents(db, p))


@server.tool()
async def get_document(document_id: str) -> dict[str, Any]:
    """Fetch metadata for a single document by id (if you may view it)."""
    return await _run(
        lambda db, p: mcp_tools.get_document(db, p, document_id=uuid.UUID(document_id))
    )


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
