"""Static validation test suite for Caddyfile edge proxy configuration."""

from __future__ import annotations

import re
from pathlib import Path

from kanban.security.headers import CSP_POLICY

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CADDYFILE_PATH = REPO_ROOT / "deploy" / "caddy" / "Caddyfile"


def test_caddyfile_exists() -> None:
    """Verify Caddyfile exists in deploy/caddy/."""
    assert CADDYFILE_PATH.is_file(), f"Missing Caddyfile at {CADDYFILE_PATH}"


def test_tls13_enforcement() -> None:
    """Test Case 5a: Verify tls1.3 is enforced in site block."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "protocols tls1.3" in content


def test_protocols_h1_h2_h3() -> None:
    """Verify modern HTTP protocols h1, h2, h3 are enabled globally."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "protocols h1 h2 h3" in content


def test_flush_interval_unbuffered_streaming() -> None:
    """Test Case 5b: Verify flush_interval -1 is set inside /ws, /sse*, and /mcp/*."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    # Match handle /ws { ... flush_interval -1 ... }
    ws_pattern = re.compile(r"handle\s+/ws\s*\{[^}]*flush_interval\s+-1[^}]*\}", re.DOTALL)
    assert ws_pattern.search(content), "Missing flush_interval -1 in handle /ws"

    # Match handle /sse* { ... flush_interval -1 ... }
    sse_pattern = re.compile(r"handle\s+/sse\*\s*\{[^}]*flush_interval\s+-1[^}]*\}", re.DOTALL)
    assert sse_pattern.search(content), "Missing flush_interval -1 in handle /sse*"

    # Match handle /mcp/* { ... flush_interval -1 ... }
    mcp_pattern = re.compile(r"handle\s+/mcp/\*\s*\{[^}]*flush_interval\s+-1[^}]*\}", re.DOTALL)
    assert mcp_pattern.search(content), "Missing flush_interval -1 in handle /mcp/*"


def test_precompressed_static_serving() -> None:
    """Test Case 5c: Verify file_server precompressed br gzip is configured."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")
    assert "precompressed br gzip" in content


def test_csp_policy_matches_codebase() -> None:
    """Test Case 5d: Verify Caddy CSP matches kanban.security.headers.CSP_POLICY."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    csp_match = re.search(r'Content-Security-Policy\s+"([^"]+)"', content)
    assert csp_match is not None, "Content-Security-Policy header directive not found in Caddyfile"

    caddy_csp = csp_match.group(1)
    assert caddy_csp == CSP_POLICY, (
        f"Caddyfile CSP does not match kanban.security.headers.CSP_POLICY.\n"
        f"Caddy: {caddy_csp}\n"
        f"Python: {CSP_POLICY}"
    )


def test_security_headers_present() -> None:
    """Verify security headers are configured according to Section 5.4."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    assert 'Strict-Transport-Security "max-age=63072000; includeSubDomains"' in content
    assert 'X-Content-Type-Options "nosniff"' in content
    assert 'Referrer-Policy "no-referrer"' in content
    assert 'X-Frame-Options "DENY"' in content
    assert "-Server" in content
