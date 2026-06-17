# EDIP MCP Server

Exposes the platform to MCP-compatible AI clients (Claude Desktop, IDEs) over **stdio**,
with four ACL-enforced tools:

| Tool | What it does |
|---|---|
| `query_documents(question)` | Runs the full multi-agent workflow → grounded, cited answer |
| `search_chunks(query, top_k)` | Hybrid retrieval over documents you may **query** |
| `list_documents()` | Lists documents you may **view** |
| `get_document(document_id)` | Document metadata, if you may **view** it |

## Security model

Every call is authenticated by a **per-tenant API key** (`EDIP_API_KEY`) that acts *as a
specific user*. That user's role + document ACLs govern everything — the MCP server adds
no privilege and cannot bypass access control. Every tool call is audited
(`MCP_TOOL_CALLED`). Keys are argon2-hashed at rest, revocable, and can expire.

Issue a key (as an OWNER/ADMIN): `POST /admin/api-keys` → returns the plaintext key once.

## Run

```bash
cd backend
uv sync --extra mcp
EDIP_API_KEY="edip_xxxxxxxx.secret" uv run python -m mcp_server.server
```

The tool logic lives in `app/services/mcp_tools.py` and is unit-tested without the SDK;
this package is only the stdio transport adapter. HTTP transport is a later swap.
