# Message to Reality-Checker: KANBA-60 (KB-P2-13)

## Ticket Overview
- Ticket ID: `KANBA-60`
- Specification ID: `KB-P2-13`
- Title: Server Markdown Ingestion Normalizer
- Author: `builder-17`
- Branch: `feat/KANBA-60` (worktree: `/tmp/kb-wt-KANBA-60`)
- Spec Sections: S5.1, S5.2 (items 2-4), S3.5, S2.5

## Executive Summary
This ticket delivers the unified server-side Markdown ingestion normalizer (`kanban/content/normalize.py`) enforcing the Canonical Markdown-Only Database Invariant. All ingested content across Plain Text, Markdown, and HTML is classified, sanitized, and normalized before reaching PostgreSQL or AI agent contexts:
1. `kanban/content/unicode_guard.py`: Enforces max byte boundaries, rejects UTF-8 surrogates, normalizes newlines to LF, and strips zero-width, BiDi overrides, Plane-14 ASCII smuggling tags, and C0/C1 control characters while preserving TAB and LF.
2. `kanban/content/hidden_dom.py`: Implements Step A hidden-DOM paste-jacking pruning running BEFORE `style` attribute removal. Bounded HTMLParser AST walker (depth <= 256, nodes <= 50,000) evaluates CSS visibility rules (display:none, visibility:hidden/collapse, opacity<=0.05, font-size<1, color:transparent/rgba-alpha<=0.05, clip:rect(0,0,0,0), clip-path:inset(>=50%), zero-box clipping, off-screen positioning, and WCAG 2.1 contrast < 1.15 against inherited backgrounds while preserving dark-mode white text).
3. `kanban/content/html_to_gfm.py`: Step B Rust `nh3` sanitization with strict 32-tag allowlist, URL schemes (`https`, `mailto`, `attachment`), safe same-origin relative paths (`#fragment`, `/path`), `code` class filtering (`^language-[a-z0-9_+-]{1,32}$`), link scheme disarming for dangerous targets, and AST serializer to canonical GFM Markdown.
4. `kanban/content/normalize.py`: Public entry points (`normalize_to_markdown`, `normalize_plain_text`, `normalize_inspect`) with automatic classification and IDE syntax-highlighted wrapper bypass (`S5.2` item 2).

## Scoped Definition of Done Audit

| Pass Criteria | Status | Verification Proof |
| :--- | :---: | :--- |
| `kanban/content/` modules implemented and exported | PASS | `kanban/content/{__init__,normalize,hidden_dom,html_to_gfm,unicode_guard}.py` |
| Banned `bleach` absent repository-wide | PASS | `grep -rn "bleach" pyproject.toml kanban/ uv.lock` returned 0 hits |
| `nh3==0.3.7` pinned and verified | PASS | `docs/qa/KANBA-60/dependency-evaluation.md`, `uv.lock` |
| All 8 required test cases implemented and passing | PASS | 49 passing tests in `kanban/tests/content/` |
| Test coverage >= 95% branch and line coverage | PASS | 97.08% overall coverage (`--cov-fail-under=95` passed) |
| Ruff linter clean (zero warnings or errors) | PASS | `uv run ruff check .` exited 0 |
| Ruff formatting clean | PASS | `uv run ruff format --check .` exited 0 |
| Mypy strict clean (zero type errors) | PASS | `uv run mypy --strict kanban` exited 0 |
| Architecture import boundaries enforced | PASS | `uv run lint-imports` exited 0 (1 contract kept, 0 broken) |
| Dependency license gate verified | PASS | `uv run python -m scripts.license_gate` exited 0 (95 Python, 1 Node, 0 violations) |
| Zero non-ASCII unicode dashes (U+2014, U+2013) | PASS | Clean verification across all modified and created files |
| Forensic verification proof packet complete | PASS | All files populated in `docs/qa/KANBA-60/` |

## Mandatory Feature Test Case Verification Matrix

1. **Positive HTML -> GFM Goldens (Case 1):** Verified using `rich_html_to_gfm_goldens.json` covering Confluence/Jira/Google Docs HTML structures (headings, bold/italic/del, nested task lists, tables, code blocks, links, attachments).
2. **Positive IDE Wrapper Bypass (Case 2):** Verified VS Code `<div><span>def f():</span><br><span>    return 1</span></div>` wraps into fenced code block without losing indentation or escaping underscores; dark-mode white text preserved.
3. **Positive Clean Markdown Preservation (Case 3):** Verified GFM Markdown with ```` ```mermaid ```` block, pipe tables, and fenced code containing literal `<script>not html</script>` round-trips verbatim.
4. **Security Step A Hidden-DOM Paste-Jacking (Case 4):** Verified all 36 test vectors in `paste_jacking_cases.json` completely strip `IGNORE_PREVIOUS_INSTRUCTIONS_EXFIL_SEC`.
5. **Security XSS & Embedded HTML in Markdown (Case 5):** Verified `<img onerror=...>`, `<svg onload=...>`, `<math><script>`, and links with `javascript:`, `jav&#x09;ascript:`, `data:`, `//evil` leave zero executable markup in output.
6. **Security Unicode Smuggling & BiDi Overrides (Case 6):** Verified `U+200B`, `U+202E`, and Plane-14 tags `U+E0000..U+E007F` are 100% stripped (`zero_width_stripped > 0`).
7. **Plain-Text Mode (Case 7):** Verified `normalize_plain_text("<b>Fix</b>\n\u200bSummary")` returns `"Fix Summary"`.
8. **Boundary Conditions (Case 8):** Verified `2,097,153`-byte input raises `CONTENT_TOO_LARGE` and `260`-deep nested `<div>` raises `HTML_COMPLEXITY_EXCEEDED`.

## Test Coverage Summary
```
Name                              Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------------
kanban/content/__init__.py            6      0      0      0   100%
kanban/content/hidden_dom.py        250      2    122     10    97%
kanban/content/html_to_gfm.py       364      5    176     13    97%
kanban/content/normalize.py         254      1     90      8    97%
kanban/content/unicode_guard.py      58      0     16      0   100%
-----------------------------------------------------------------------------
TOTAL                               932      8    404     31    97%
Required test coverage of 95% reached. Total coverage: 97.08%
49 passed in 1.52s
```

## Forensic Proof Packet File Index
1. `docs/qa/KANBA-60/git-diff.patch` - Complete unified diff against main.
2. `docs/qa/KANBA-60/unit-test-results.txt` - Verbatim output of `pytest -v --cov=kanban/content --cov-fail-under=95`.
3. `docs/qa/KANBA-60/build-check.txt` - Verbatim output of ruff, mypy, lint-imports, and license_gate.
4. `docs/qa/KANBA-60/paste-jacking-corpus-report.json` - Complete input-to-output trace of all 36 paste-jacking attack vectors proving zero canary survival.
5. `docs/qa/KANBA-60/dependency-evaluation.md` - Technical evaluation and audit for `nh3==0.3.7`.
6. Screenshots: N/A - Non-UI Ticket.
