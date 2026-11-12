"""Schema-wide catalog test verifying Markdown-only invariant and generated sha256 columns."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_04_markdown_only_schema_catalog(app_session: AsyncSession) -> None:
    """Verify 0 disallowed HTML/AST/JSONB prose columns exist, and every *_markdown has *_sha256."""
    disallowed_query = text(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND (
            column_name ~ '_html$'
            OR column_name ~ '_ast$'
            OR column_name ~ '^html_'
            OR (data_type = 'jsonb' AND column_name ~ '(body|description|content)')
          )
        """
    )
    disallowed_rows = (await app_session.execute(disallowed_query)).fetchall()
    msg = f"Found disallowed HTML/AST/JSONB prose columns: {disallowed_rows}"
    assert disallowed_rows == [], msg

    target_tables = ("issues", "issue_comments", "docs", "pages", "page_versions", "stickies")
    for tbl in target_tables:
        cols_query = text(
            """
            SELECT column_name, is_generated
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :tbl
            """
        )
        rows = (await app_session.execute(cols_query, {"tbl": tbl})).fetchall()
        cols = {r.column_name: r.is_generated for r in rows}

        markdown_cols = [c for c in cols if c.endswith("_markdown")]
        assert len(markdown_cols) >= 1, f"Table {tbl} must contain at least one *_markdown column"

        for md_col in markdown_cols:
            sha_col = md_col.replace("_markdown", "_sha256")
            assert sha_col in cols, f"Table {tbl} missing sibling {sha_col} for {md_col}"
            assert cols[sha_col] == "ALWAYS", f"{tbl}.{sha_col} must have is_generated = 'ALWAYS'"
