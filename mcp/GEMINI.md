# MCP Module Manifest (`kanban-mcp`)

## Responsibility
Three-surface Model Context Protocol server exposing `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`. Provides OAuth 2.0 + PKCE (S256) and scoped API key authentication, EntityResolver for human-readable issue keys, Level-of-Detail (LOD) response tiers (summary, standard, full), compact InlineSafeDumper YAML serialization, and intent-based 12-tool admin catalog with two-stage confirmation. Holds zero direct PostgreSQL credentials and interacts exclusively with kanban core service over internal HTTP.

## Depends On
- `kanban` (`kanban-core` package for domain schemas, models, and HTTP client communication).

## Depended On By
- `agent` (`kanban-agent` package for agent execution against MCP tools and resources).

## Inbound Contracts
- Model Context Protocol requests over Streamable HTTP (spec version 2025-06-18) and stdio transports.
- Bearer token authentication with principal claim validation.

## Outbound Contracts
- Internal HTTP API requests to kanban core service authenticated via signed service tokens.
- Structured MCP Tool, Resource, and Prompt responses conforming to MCP specification.

## Performance Budgets
- MCP tool execution latency < 100ms excluding external task processing.
- LOD tier serialization overhead < 5ms.
- Zero PostgreSQL connection pool overhead (pure stateless HTTP proxying).

## Failure Modes
- Expired or invalid MCP bearer token returning standard MCP JSON-RPC error.
- Downstream kanban core service failure returning graceful tool error without stack trace leakage.
- Confirmation token expiration aborting two-stage destructive operations.
- Token scope deficiency rejecting unauthorized operations.
