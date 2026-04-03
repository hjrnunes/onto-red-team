# nexus-mcp — AI Atlas Nexus MCP Server

MCP server providing semantic search and navigation over the AI Atlas Nexus risk knowledge graph (~600 risk entries
across 10 frameworks).

## MCP Server

Entry point: `nexus-mcp` (stdio transport, FastMCP)

8 tools: `search_risks`, `get_risk_details`, `get_related_risks`, `get_related_actions`, `list_taxonomies`,
`list_risk_groups`, `explore_risk`, `gap_analysis`

## Source Layout

```
nexus-mcp/src/nexus_mcp/
  risk_index.py   # ChromaDB semantic index over risk descriptions
  server.py       # MCP server with 8 tools
```

## Configuration

| Env var | Purpose |
|---------|---------|
| `NEXUS_BASE_DIR` | Path to ai-atlas-nexus repo (required) |
| `NEXUS_CHROMA_DIR` | ChromaDB persistent store path (default: `.chroma/`) |

## Key Design Decisions

- **`create_tool_handlers()`** — separates tool logic from MCP transport for testing
- **Lazy-singleton `_get_handlers()`** — loads AIAtlasNexus + ChromaDB on first tool call
- **`get_related_risks()`** reads five mapping attributes directly from Risk objects to preserve `mapping_type`
  (the `nexus.get_related_risks()` API flattens and loses this)
- **RiskIndex class**: ChromaDB semantic index over risk descriptions
