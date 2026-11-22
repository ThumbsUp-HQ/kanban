"""Interactive API documentation and web manifest helpers (KANBA-228).

Renders CSP-safe interactive schema explorers (Swagger UI and ReDoc representations)
with zero external CDN dependencies, strict style-src 'self' and script-src 'self'
compliance, and canonical Web App Manifest (PWA) serialization.
"""

from __future__ import annotations

import html
import json
from typing import Any, Final

MANIFEST_BYTES: Final[bytes] = json.dumps(
    {
        "name": "👍kanban",
        "short_name": "👍kanban",
        "description": "Agent-First, Security-First Kanban Platform",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": "#1d4ed8",
        "background_color": "#f7f8fa",
        "icons": [
            {
                "src": "/favicon.ico",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            }
        ],
    },
    indent=2,
    ensure_ascii=False,
).encode("utf-8")

DOCS_CSS: Final[str] = """
:root {
  --primary: #1d4ed8;
  --primary-hover: #1e40af;
  --bg-canvas: #f8fafc;
  --bg-surface: #ffffff;
  --border: #e2e8f0;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --topbar-bg: #1e293b;
  --code-bg: #0f172a;
  --code-fg: #f8fafc;
  --method-get: #2563eb;
  --method-get-bg: #eff6ff;
  --method-get-border: #bfdbfe;
  --method-post: #16a34a;
  --method-post-bg: #f0fdf4;
  --method-post-border: #bbf7d0;
  --method-put: #d97706;
  --method-put-bg: #fffbeb;
  --method-put-border: #fde68a;
  --method-delete: #dc2626;
  --method-delete-bg: #fef2f2;
  --method-delete-border: #fecaca;
  --method-patch: #0d9488;
  --method-patch-bg: #f0fdfa;
  --method-patch-border: #99f6e4;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg-canvas);
  color: var(--text-main);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

code, pre {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}

a {
  color: var(--primary);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}

.swagger-topbar {
  background: var(--topbar-bg);
  color: #ffffff;
  padding: 12px 24px;
}
.swagger-topbar-wrapper {
  max-width: 1300px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.swagger-topbar .brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.25rem;
  font-weight: 700;
}
.swagger-topbar .badge {
  background: var(--primary);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}
.swagger-topbar .topbar-links {
  display: flex;
  gap: 16px;
}
.swagger-topbar .topbar-link {
  color: #cbd5e1;
  font-size: 0.875rem;
}
.swagger-topbar .topbar-link:hover {
  color: #ffffff;
  text-decoration: none;
}

.swagger-container {
  max-width: 1300px;
  margin: 24px auto;
  padding: 0 24px 60px;
}

.api-info-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 28px;
  margin-bottom: 28px;
}
.api-info-card h1 {
  font-size: 2rem;
  margin-bottom: 8px;
}
.api-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.version-badge, .url-badge {
  background: #f1f5f9;
  border: 1px solid var(--border);
  font-size: 0.8125rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.api-desc {
  font-size: 1rem;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.spec-links {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.opblock-tag-section {
  margin-bottom: 24px;
}
.opblock-tag-header {
  font-size: 1.25rem;
  font-weight: 600;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
  margin-bottom: 12px;
}
.tag-count {
  font-size: 0.875rem;
  color: var(--text-muted);
  font-weight: 400;
}

.opblock {
  border-radius: 6px;
  margin-bottom: 10px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  overflow: hidden;
}
.opblock-get { border-color: var(--method-get-border); background: var(--method-get-bg); }
.opblock-post { border-color: var(--method-post-border); background: var(--method-post-bg); }
.opblock-put { border-color: var(--method-put-border); background: var(--method-put-bg); }
.opblock-delete { border-color: var(--method-delete-border); background: var(--method-delete-bg); }
.opblock-patch { border-color: var(--method-patch-border); background: var(--method-patch-bg); }

.opblock-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}
.opblock-summary::-webkit-details-marker {
  display: none;
}

.opblock-method {
  font-size: 0.75rem;
  font-weight: 700;
  color: #ffffff;
  padding: 4px 10px;
  border-radius: 4px;
  min-width: 65px;
  text-align: center;
  text-transform: uppercase;
}
.opblock-method-get { background: var(--method-get); }
.opblock-method-post { background: var(--method-post); }
.opblock-method-put { background: var(--method-put); }
.opblock-method-delete { background: var(--method-delete); }
.opblock-method-patch { background: var(--method-patch); }

.opblock-path {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--text-main);
}
.opblock-summary-text {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-left: auto;
}

.opblock-body {
  background: var(--bg-surface);
  padding: 18px;
  border-top: 1px solid var(--border);
}
.opblock-desc {
  font-size: 0.9375rem;
  margin-bottom: 16px;
  color: var(--text-main);
}
.opblock-details-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.opblock-section h4 {
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  margin-bottom: 8px;
  color: var(--text-muted);
}

.param-table, .resp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
.param-table th, .param-table td,
.resp-table th, .resp-table td {
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
}
.param-table th, .resp-table th {
  background: #f1f5f9;
  font-weight: 600;
}

.status-badge {
  display: inline-block;
  font-weight: 700;
  font-size: 0.8125rem;
  padding: 2px 6px;
  border-radius: 4px;
}
.status-2xx { background: #dcfce7; color: #166534; }
.status-4xx { background: #fef3c7; color: #92400e; }
.status-5xx { background: #fee2e2; color: #991b1b; }

.curl-box {
  background: var(--code-bg);
  color: var(--code-fg);
  padding: 12px;
  border-radius: 6px;
  font-size: 0.8125rem;
  overflow-x: auto;
  white-space: pre-wrap;
}

.redoc-layout {
  display: flex;
  min-height: 100vh;
}
.redoc-sidebar {
  width: 280px;
  background: #0f172a;
  color: #e2e8f0;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  padding: 20px 16px;
}
.redoc-sidebar-header .brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.125rem;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 4px;
}
.version-tag {
  font-size: 0.75rem;
  color: #94a3b8;
  margin-bottom: 12px;
}
.sidebar-links {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #334155;
}
.sidebar-links a {
  color: #94a3b8;
  font-size: 0.8125rem;
}
.sidebar-links a:hover {
  color: #ffffff;
  text-decoration: none;
}
.redoc-tag-list {
  list-style: none;
}
.redoc-tag-link {
  display: block;
  padding: 6px 8px;
  color: #cbd5e1;
  font-size: 0.875rem;
  border-radius: 4px;
}
.redoc-tag-link:hover {
  background: #1e293b;
  color: #ffffff;
  text-decoration: none;
}

.redoc-content {
  flex: 1;
  padding: 32px 48px;
  max-width: 1100px;
}
.redoc-intro {
  margin-bottom: 36px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.redoc-intro h1 {
  font-size: 2.25rem;
  margin-bottom: 8px;
}
.redoc-desc {
  font-size: 1.125rem;
  color: var(--text-muted);
  margin-bottom: 16px;
}
.redoc-meta-bar {
  display: flex;
  gap: 24px;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.redoc-section {
  margin-bottom: 48px;
}
.redoc-section-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
}
.redoc-endpoint-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 20px;
}
.redoc-endpoint-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.redoc-endpoint-path {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 1rem;
  font-weight: 600;
}
.redoc-endpoint-summary {
  font-size: 1.125rem;
  margin-bottom: 8px;
}
.redoc-endpoint-desc {
  font-size: 0.9375rem;
  color: var(--text-muted);
  margin-bottom: 16px;
}
.redoc-endpoint-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.redoc-doc-column h4,
.code-box-header {
  font-size: 0.8125rem;
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-muted);
}

@media (max-width: 900px) {
  .redoc-layout {
    flex-direction: column;
  }
  .redoc-sidebar {
    width: 100%;
    height: auto;
    position: static;
  }
  .redoc-content {
    padding: 20px;
  }
  .redoc-endpoint-grid {
    grid-template-columns: 1fr;
  }
  .opblock-summary-text {
    display: none;
  }
}
"""

_HTML_CACHE: dict[str, str] = {}


def _group_operations_by_tag(
    paths: dict[str, Any],
) -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
    """Group OpenAPI operations into sorted tags map."""
    tags_map: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, methods in sorted(paths.items()):
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            op_tags = op.get("tags") or ["default"]
            for tag in op_tags:
                tags_map.setdefault(tag, []).append((method.upper(), path, op))
    return tags_map


def _render_params_table(params: list[dict[str, Any]]) -> list[str]:
    """Render parameters HTML table for an endpoint."""
    lines = [
        '            <div class="opblock-section">',
        "              <h4>Parameters</h4>",
        '              <table class="param-table">',
        (
            "                <thead><tr><th>Name</th><th>In</th>"
            "<th>Required</th><th>Type</th><th>Description</th></tr></thead>"
        ),
        "                <tbody>",
    ]
    for p in params:
        p_name = html.escape(str(p.get("name", "")))
        p_in = html.escape(str(p.get("in", "")))
        p_req = "Yes" if p.get("required") else "No"
        p_schema = html.escape(str(p.get("schema", {}).get("type", "string")))
        p_desc = html.escape(str(p.get("description", "")))
        lines.append(
            f"                  <tr><td><code>{p_name}</code></td><td>{p_in}</td>"
            f"<td>{p_req}</td><td><code>{p_schema}</code></td><td>{p_desc}</td></tr>"
        )
    lines.extend(["                </tbody>", "              </table>", "            </div>"])
    return lines


def _render_responses_table(responses: dict[str, Any]) -> list[str]:
    """Render responses HTML table for an endpoint."""
    lines = [
        '            <div class="opblock-section">',
        "              <h4>Responses</h4>",
        '              <table class="resp-table">',
        "                <thead><tr><th>Code</th><th>Description</th></tr></thead>",
        "                <tbody>",
    ]
    for code, r_info in sorted(responses.items()):
        r_desc = html.escape(str(r_info.get("description", ""))) if isinstance(r_info, dict) else ""
        c_badge = (
            "status-2xx"
            if str(code).startswith("2")
            else ("status-4xx" if str(code).startswith("4") else "status-5xx")
        )
        lines.append(
            f'                  <tr><td><span class="status-badge {c_badge}">'
            f"{html.escape(str(code))}</span></td><td>{r_desc}</td></tr>"
        )
    lines.extend(["                </tbody>", "              </table>", "            </div>"])
    return lines


def _render_opblock(method: str, path: str, op: dict[str, Any]) -> list[str]:
    """Render a single expandable operation block in Swagger UI."""
    m_lower = method.lower()
    summary = op.get("summary") or path
    desc = op.get("description") or ""
    params = op.get("parameters") or []
    responses = op.get("responses") or {}

    lines = [
        f'      <details class="opblock opblock-{m_lower}">',
        f'        <summary class="opblock-summary opblock-summary-{m_lower}">',
        f'          <span class="opblock-method opblock-method-{m_lower}">{method}</span>',
        f'          <span class="opblock-path">{html.escape(path)}</span>',
        f'          <span class="opblock-summary-text">{html.escape(summary)}</span>',
        "        </summary>",
        '        <div class="opblock-body">',
    ]
    if desc:
        lines.append(f'          <p class="opblock-desc">{html.escape(desc)}</p>')
    lines.append('          <div class="opblock-details-grid">')

    if params:
        lines.extend(_render_params_table(params))
    if responses:
        lines.extend(_render_responses_table(responses))

    lines.append('            <div class="opblock-section">')
    lines.append("              <h4>cURL Example</h4>")
    lines.append(
        f'              <pre class="curl-box"><code>curl -X {method} '
        f'"http://localhost:8000{html.escape(path)}" '
        f'-H "Accept: application/json"</code></pre>'
    )
    lines.append("            </div>")
    lines.extend(["          </div>", "        </div>", "      </details>"])
    return lines


def _render_security_schemes_section(security_schemes: dict[str, Any]) -> list[str]:
    """Render Authentication & Security Schemes documentation section."""
    if not security_schemes:
        return []
    lines = [
        '    <section class="opblock-tag-section" id="authentication-security-schemes">',
        (
            '      <h2 class="opblock-tag-header">Authentication &amp; Security Schemes '
            f'<span class="tag-count">({len(security_schemes)})</span></h2>'
        ),
        '      <div class="api-info-card">',
        (
            '        <p class="api-desc">Configured authentication security schemes '
            "protecting API endpoints.</p>"
        ),
        '        <table class="param-table">',
        (
            "          <thead><tr><th>Scheme Name</th><th>Type</th><th>In / Format</th>"
            "<th>Description</th></tr></thead>"
        ),
        "          <tbody>",
    ]
    for name, s_info in sorted(security_schemes.items()):
        s_type = html.escape(str(s_info.get("type", "")))
        s_in = html.escape(str(s_info.get("in", s_info.get("scheme", ""))))
        if s_info.get("name"):
            s_in += f" (<code>{html.escape(str(s_info['name']))}</code>)"
        s_desc = html.escape(str(s_info.get("description", "")))
        lines.append(
            f"            <tr><td><code>{html.escape(name)}</code></td>"
            f'<td><span class="status-badge status-2xx">{s_type}</span></td>'
            f"<td>{s_in}</td><td>{s_desc}</td></tr>"
        )
    lines.extend(
        [
            "          </tbody>",
            "        </table>",
            "      </div>",
            "    </section>",
        ]
    )
    return lines


def _render_problem_schemas_section(schemas: dict[str, Any]) -> list[str]:
    """Render Canonical Error & Problem Schemas (ProblemDetails / RFC 7807) documentation."""
    lines = [
        '    <section class="opblock-tag-section" id="canonical-error-problem-schemas">',
        (
            '      <h2 class="opblock-tag-header">Canonical Error &amp; Problem Schemas '
            "(ProblemDetails / RFC 7807)</h2>"
        ),
        '      <div class="api-info-card">',
        (
            '        <p class="api-desc">Standardized RFC 7807 problem details '
            "(<code>application/problem+json</code>) returned across HTTP error responses.</p>"
        ),
        '        <table class="resp-table">',
        (
            "          <thead><tr><th>Status Code</th><th>Reason</th><th>Schema Model</th>"
            "<th>Description</th></tr></thead>"
        ),
        "          <tbody>",
        (
            '            <tr><td><span class="status-badge status-4xx">401</span></td>'
            "<td>Unauthorized</td><td><code>ProblemDetails</code></td>"
            "<td>Missing, expired, or invalid session cookie or bearer token.</td></tr>"
        ),
        (
            '            <tr><td><span class="status-badge status-4xx">412</span></td>'
            "<td>Precondition Failed</td><td><code>ProblemDetails</code></td>"
            "<td>ETag mismatch (If-Match) or optimistic concurrency conflict.</td></tr>"
        ),
        (
            '            <tr><td><span class="status-badge status-4xx">429</span></td>'
            "<td>Too Many Requests</td><td><code>ProblemDetails</code></td>"
            "<td>Rate limit or AI token cap exceeded. Includes retry-after metadata.</td></tr>"
        ),
        "          </tbody>",
        "        </table>",
    ]
    problem_schema = schemas.get("ProblemDetails") or schemas.get("Problem")
    if problem_schema and isinstance(problem_schema, dict):
        props = problem_schema.get("properties", {})
        if props:
            lines.extend(
                [
                    (
                        '        <h4 style="margin-top: 18px; margin-bottom: 8px; '
                        'font-weight: 600;">'
                        "ProblemDetails Model Specification</h4>"
                    ),
                    '        <table class="param-table">',
                    (
                        "          <thead><tr><th>Property</th><th>Type</th>"
                        "<th>Description</th></tr></thead>"
                    ),
                    "          <tbody>",
                ]
            )
            for prop_name, prop_info in sorted(props.items()):
                p_type = html.escape(str(prop_info.get("type", "string")))
                p_desc = html.escape(str(prop_info.get("description", prop_info.get("title", ""))))
                lines.append(
                    f"            <tr><td><code>{html.escape(prop_name)}</code></td>"
                    f"<td><code>{p_type}</code></td><td>{p_desc}</td></tr>"
                )
            lines.extend(
                [
                    "          </tbody>",
                    "        </table>",
                ]
            )
    lines.extend(
        [
            "      </div>",
            "    </section>",
        ]
    )
    return lines


def render_swagger_ui_html(openapi_schema: dict[str, Any]) -> str:
    """Render CSP-safe interactive Swagger UI HTML schema explorer."""
    info = openapi_schema.get("info", {})
    title = info.get("title", "👍kanban API")
    version = info.get("version", "1.0.0")
    description = info.get("description", "Agent-First, Security-First Kanban Platform API.")
    paths = openapi_schema.get("paths", {})
    components = openapi_schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    schemas = components.get("schemas", {})
    tags_map = _group_operations_by_tag(paths)

    display_title = title[1:].lstrip() if title.startswith("👍") else title

    out: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8"/>',
        '  <meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"  <title>{html.escape(title)} - Swagger UI</title>",
        '  <link rel="icon" href="/favicon.ico" type="image/svg+xml"/>',
        '  <link rel="manifest" href="/manifest.json"/>',
        '  <link rel="stylesheet" href="/api/docs/docs.css"/>',
        "</head>",
        '<body class="swagger-body">',
        '  <header class="swagger-topbar">',
        '    <div class="swagger-topbar-wrapper">',
        '      <div class="brand">',
        '        <span class="logo" aria-hidden="true">👍</span>',
        f'        <span class="title">{html.escape(display_title)}</span>',
        '        <span class="badge">Swagger UI</span>',
        "      </div>",
        '      <div class="topbar-links">',
        (
            '        <a href="/api/openapi.json" class="topbar-link" target="_blank" '
            'rel="noopener">OpenAPI JSON</a>'
        ),
        '        <a href="/api/redoc" class="topbar-link">ReDoc</a>',
        '        <a href="/docs" class="topbar-link">Workspace Docs</a>',
        (
            '        <a href="/llms.txt" class="topbar-link" target="_blank" '
            'rel="noopener">Agent /llms.txt</a>'
        ),
        "      </div>",
        "    </div>",
        "  </header>",
        '  <main class="swagger-container">',
        '    <section class="api-info-card">',
        f"      <h1>{html.escape(title)}</h1>",
        '      <div class="api-meta">',
        '        <span class="version-badge">OAS 3.1.0</span>',
        f'        <span class="version-badge">v{html.escape(version)}</span>',
        '        <span class="url-badge">Base URL: /api/v1</span>',
        "      </div>",
        f'      <p class="api-desc">{html.escape(description)}</p>',
        '      <div class="spec-links">',
        (
            '        Explore: <a href="/api/openapi.json" target="_blank" '
            'rel="noopener">/api/openapi.json</a>'
        ),
        '        | Alternative Viewer: <a href="/api/redoc">ReDoc Interface</a>',
        '        | Kanban Knowledge: <a href="/docs">/docs (SPA)</a>',
        (
            '        | Agent Instructions: <a href="/llms.txt" target="_blank" '
            'rel="noopener">/llms.txt</a>'
        ),
        "      </div>",
        "    </section>",
    ]

    out.extend(_render_security_schemes_section(security_schemes))
    out.extend(_render_problem_schemas_section(schemas))

    for tag, operations in sorted(tags_map.items()):
        out.append('    <section class="opblock-tag-section">')
        out.append(
            f'      <h2 class="opblock-tag-header">{html.escape(tag)} '
            f'<span class="tag-count">({len(operations)})</span></h2>'
        )
        for method, path, op in operations:
            out.extend(_render_opblock(method, path, op))
        out.append("    </section>")

    out.extend(["  </main>", "</body>", "</html>"])
    return "\n".join(out)


def _render_redoc_endpoint_card(method: str, path: str, op: dict[str, Any]) -> list[str]:
    """Render a single ReDoc endpoint documentation card."""
    m_lower = method.lower()
    summary = op.get("summary") or path
    desc = op.get("description") or ""
    params = op.get("parameters") or []
    responses = op.get("responses") or {}

    lines = [
        '        <article class="redoc-endpoint-card">',
        '          <div class="redoc-endpoint-header">',
        f'            <span class="opblock-method opblock-method-{m_lower}">{method}</span>',
        f'            <span class="redoc-endpoint-path">{html.escape(path)}</span>',
        "          </div>",
        f'          <h3 class="redoc-endpoint-summary">{html.escape(summary)}</h3>',
    ]
    if desc:
        lines.append(f'          <p class="redoc-endpoint-desc">{html.escape(desc)}</p>')

    lines.append('          <div class="redoc-endpoint-grid">')
    lines.append('            <div class="redoc-doc-column">')
    if params:
        lines.extend(_render_params_table(params))
    if responses:
        lines.extend(_render_responses_table(responses))
    lines.append("            </div>")

    lines.append('            <div class="redoc-code-column">')
    lines.append('              <div class="code-box-header">Request Snippet</div>')
    lines.append(
        f'              <pre class="curl-box"><code>curl -X {method} \\\n'
        f'  "http://localhost:8000{html.escape(path)}" \\\n'
        f'  -H "Accept: application/json"</code></pre>'
    )
    lines.extend(["            </div>", "          </div>", "        </article>"])
    return lines


def render_redoc_html(openapi_schema: dict[str, Any]) -> str:
    """Render CSP-safe interactive ReDoc HTML schema explorer."""
    info = openapi_schema.get("info", {})
    title = info.get("title", "👍kanban API")
    version = info.get("version", "1.0.0")
    description = info.get("description", "Agent-First, Security-First Kanban Platform API.")
    paths = openapi_schema.get("paths", {})
    components = openapi_schema.get("components", {})
    security_schemes = components.get("securitySchemes", {})
    schemas = components.get("schemas", {})
    tags_map = _group_operations_by_tag(paths)

    display_title = title[1:].lstrip() if title.startswith("👍") else title

    out: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8"/>',
        '  <meta name="viewport" content="width=device-width, initial-scale=1"/>',
        f"  <title>{html.escape(title)} - ReDoc</title>",
        '  <link rel="icon" href="/favicon.ico" type="image/svg+xml"/>',
        '  <link rel="manifest" href="/manifest.json"/>',
        '  <link rel="stylesheet" href="/api/docs/docs.css"/>',
        "</head>",
        '<body class="redoc-body">',
        '  <div class="redoc-layout">',
        '    <nav class="redoc-sidebar" aria-label="API Documentation Navigation">',
        '      <div class="redoc-sidebar-header">',
        '        <div class="brand">',
        '          <span class="logo" aria-hidden="true">👍</span>',
        f'          <span class="title">{html.escape(display_title)}</span>',
        "        </div>",
        f'        <div class="version-tag">ReDoc v{html.escape(version)}</div>',
        '        <div class="sidebar-links">',
        '          <a href="/api/openapi.json" target="_blank" rel="noopener">OpenAPI Spec</a>',
        '          <a href="/api/docs">Swagger UI</a>',
        '          <a href="/docs">Workspace Docs</a>',
        '          <a href="/llms.txt" target="_blank" rel="noopener">Agent /llms.txt</a>',
        "        </div>",
        "      </div>",
        '      <ul class="redoc-tag-list">',
        (
            '        <li><a href="#authentication-security-schemes" '
            'class="redoc-tag-link">Authentication &amp; Security Schemes</a></li>'
        ),
        (
            '        <li><a href="#canonical-error-problem-schemas" '
            'class="redoc-tag-link">Canonical Error &amp; Problem Schemas</a></li>'
        ),
    ]
    for tag in sorted(tags_map.keys()):
        slug = html.escape(tag.replace(" ", "-").lower())
        out.append(
            f'        <li><a href="#{slug}" class="redoc-tag-link">{html.escape(tag)}</a></li>'
        )
    out.extend(
        [
            "      </ul>",
            "    </nav>",
            '    <main class="redoc-content">',
            '      <header class="redoc-intro">',
            f"        <h1>{html.escape(title)} Reference</h1>",
            f'        <p class="redoc-desc">{html.escape(description)}</p>',
            '        <div class="redoc-meta-bar">',
            "          <span>Base URL: <code>/api/v1</code></span>",
            '          <span>Specification: <a href="/api/openapi.json">OpenAPI 3.1.0</a></span>',
            "        </div>",
            "      </header>",
        ]
    )

    out.extend(_render_security_schemes_section(security_schemes))
    out.extend(_render_problem_schemas_section(schemas))

    for tag, operations in sorted(tags_map.items()):
        slug = html.escape(tag.replace(" ", "-").lower())
        out.append(f'      <section id="{slug}" class="redoc-section">')
        out.append(f'        <h2 class="redoc-section-title">{html.escape(tag)}</h2>')
        for method, path, op in operations:
            out.extend(_render_redoc_endpoint_card(method, path, op))
        out.append("      </section>")

    out.extend(["    </main>", "  </div>", "</body>", "</html>"])
    return "\n".join(out)


def get_swagger_ui_html(openapi_schema: dict[str, Any]) -> str:
    """Retrieve or render cached Swagger UI HTML."""
    cached = _HTML_CACHE.get("swagger")
    if cached is None:
        cached = render_swagger_ui_html(openapi_schema)
        _HTML_CACHE["swagger"] = cached
    return cached


def get_redoc_html(openapi_schema: dict[str, Any]) -> str:
    """Retrieve or render cached ReDoc HTML."""
    cached = _HTML_CACHE.get("redoc")
    if cached is None:
        cached = render_redoc_html(openapi_schema)
        _HTML_CACHE["redoc"] = cached
    return cached
