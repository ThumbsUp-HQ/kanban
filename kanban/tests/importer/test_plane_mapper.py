# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for PlaneMapper (KB-MIGRATION-PLANE-DB-01)."""

from __future__ import annotations

import uuid

import pytest

from kanban.importer.plane_client import PlaneBundle, PlaneIssue, PlaneMember
from kanban.importer.plane_mapper import PlaneMapper, _DagState, compute_source_sha256


def test_rewrite_issue_references_context_aware() -> None:
    """Verify rewrite_issue_references skips code fences, inline spans, and docs/qa/ paths."""
    mapper = PlaneMapper()
    remap = {
        "KANBA-1": "KAN-101",
        "KANBA-2": "KAN-102",
        "KANBA-3": "KAN-103",
    }

    # Empty inputs
    assert mapper.rewrite_issue_references("", remap) == ""
    assert mapper.rewrite_issue_references("Prose with KANBA-1", {}) == "Prose with KANBA-1"

    input_text = """
Here is normal prose mentioning KANBA-1 and KANBA-2.
Also check docs/qa/KANBA-1/test-results.txt for proof.
Do not rewrite inline code: `KANBA-1` or `KANBA-3`.

```python
# Fenced code block with ```
def test_issue():
    key = "KANBA-1"
    other = "KANBA-2"
```

~~~bash
# Fenced code block with ~~~
cat docs/qa/KANBA-2/patch.diff
echo KANBA-3
~~~

Final prose mentioning KANBA-3 as well.
"""

    expected = """
Here is normal prose mentioning KAN-101 and KAN-102.
Also check docs/qa/KANBA-1/test-results.txt for proof.
Do not rewrite inline code: `KANBA-1` or `KANBA-3`.

```python
# Fenced code block with ```
def test_issue():
    key = "KANBA-1"
    other = "KANBA-2"
```

~~~bash
# Fenced code block with ~~~
cat docs/qa/KANBA-2/patch.diff
echo KANBA-3
~~~

Final prose mentioning KAN-103 as well.
"""

    result = mapper.rewrite_issue_references(input_text, remap)
    assert result == expected


def test_normalize_content_and_rewrite_attachments_coverage() -> None:
    """Verify attachment rewriting, post-normalization pass, and .md attachments."""
    mapper = PlaneMapper()

    # None / empty input
    assert mapper.normalize_content_and_rewrite_attachments(None, {}) == ("", 0)
    assert mapper.normalize_content_and_rewrite_attachments("", {}) == ("", 0)

    att_id = uuid.uuid4()
    url_map = {"https://minio.internal/bucket/image.png": att_id}

    # Pre-rewrite in HTML
    html_input = '<p>Image: <img src="https://minio.internal/bucket/image.png" /></p>'
    out_md, count = mapper.normalize_content_and_rewrite_attachments(html_input, url_map)
    assert f"/api/v1/attachments/{att_id}" in out_md
    assert count == 1

    # Post-normalization pass: when HTML contains entity-encoded URL that decodes in markdown
    entity_url = "https://minio.internal/bucket/doc.pdf?v=1&w=2"
    url_map_entity = {
        entity_url: att_id,
        "https://minio.internal/unmatched.png": uuid.uuid4(),  # exercises unmatched branch
    }
    raw_entity_html = (
        '<p>Doc: <a href="https://minio.internal/bucket/doc.pdf?v=1&amp;w=2">Link</a></p>'
    )
    out_entity, count_entity = mapper.normalize_content_and_rewrite_attachments(
        raw_entity_html, url_map_entity
    )
    assert f"/api/v1/attachments/{att_id}" in out_entity
    assert count_entity >= 1

    # .md attachment ingestion
    md_att = {
        "notes.md": "# Release Notes\nAll good.",
        "unused.md": "# Unused",  # exercises unused attachment branch
    }
    md_input = "<p>Refer to notes.md for details.</p>"
    out_md3, _ = mapper.normalize_content_and_rewrite_attachments(
        md_input, {}, md_attachments=md_att
    )
    assert "<details>" in out_md3
    assert "<summary>Attachment: notes.md</summary>" in out_md3
    assert "# Release Notes" in out_md3


def test_sort_issues_topologically_cycle_and_unvisited() -> None:
    """Verify topological sorting handles valid hierarchy, cycle detection, and depth limits."""
    mapper = PlaneMapper()

    # 1. Valid hierarchy: root -> child -> grandchild
    i0 = PlaneIssue(id="i0", parent=None, sequence_id=0, name="Root")
    i1 = PlaneIssue(id="i1", parent="i0", sequence_id=1, name="Child")
    i2 = PlaneIssue(id="i2", parent="i1", sequence_id=2, name="Grandchild")

    sorted_issues, warnings = mapper.sort_issues_topologically([i2, i0, i1])
    sorted_ids = [iss.id for iss in sorted_issues]
    assert sorted_ids == ["i0", "i1", "i2"]
    assert len(warnings) == 0

    # 2. Cycle detection: i1 -> i2 -> i1
    cyc1 = PlaneIssue(id="c1", parent="c2", sequence_id=10, name="Cyc 1")
    cyc2 = PlaneIssue(id="c2", parent="c1", sequence_id=11, name="Cyc 2")

    with pytest.raises(ValueError, match="Parent-child cycle detected"):
        mapper.sort_issues_topologically([cyc1, cyc2])

    # 3. Depth limit > 6
    chain = [
        PlaneIssue(id=f"d{i}", parent=f"d{i - 1}" if i > 0 else None, sequence_id=i, name=f"D{i}")
        for i in range(8)
    ]
    with pytest.raises(ValueError, match="Parent hierarchy depth"):
        mapper.sort_issues_topologically(chain)

    # 4. Missing parent reference warning
    orphan = PlaneIssue(id="orphan", parent="nonexistent_parent", sequence_id=99, name="Orphan")
    _, warnings2 = mapper.sort_issues_topologically([orphan])
    assert len(warnings2) == 1
    assert "references missing parent nonexistent_parent" in warnings2[0]

    # 5. _DagState unvisited leaf coverage
    dag = _DagState({"root": [i1]})
    dag.traverse("leaf_without_children", 0)
    assert "leaf_without_children" not in dag.visited


def test_compute_source_sha256() -> None:
    """Verify compute_source_sha256 works on dict and BaseModel instances."""
    d1 = {"a": 1, "b": "hello"}
    h1 = compute_source_sha256(d1)
    assert len(h1) == 32
    i1 = PlaneIssue(id="i1", sequence_id=1, name="Test")
    h2 = compute_source_sha256(i1)
    assert len(h2) == 32


def test_resolve_user_handle_fallbacks() -> None:
    """Verify resolve_user_handle covers user map, bundle member lookup, and unmapped fallbacks."""
    mapper = PlaneMapper(
        user_map={"u-plane-1": "@john_doe"},
        unmapped_assignees_as_free_text=True,
    )

    bundle = PlaneBundle(
        members=[
            PlaneMember(id="u-plane-2", email="jane@example.com", display_name="Jane Doe"),
            PlaneMember(id="u-no-email", email=None, display_name="No Email"),
        ],
    )

    # 1. Empty uid
    h0, unmapped0 = mapper.resolve_user_handle(None, bundle)
    assert h0 == "system"
    assert unmapped0 is False

    # 2. User map hit
    h1, unmapped1 = mapper.resolve_user_handle("u-plane-1", bundle)
    assert h1 == "john_doe"
    assert unmapped1 is False

    # 3. Bundle member/user hit with email
    h2, unmapped2 = mapper.resolve_user_handle("u-plane-2", bundle)
    assert h2 == "plane-import-jane"
    assert unmapped2 is True

    # 4. Bundle member with no email (break statement)
    h_no_email, unmapped_no_email = mapper.resolve_user_handle("u-no-email", bundle)
    assert h_no_email == "plane-import-u-no-ema"
    assert unmapped_no_email is True

    # 5. Unknown user fallback to short ID
    h3, unmapped3 = mapper.resolve_user_handle("u-unknown-12345", bundle)
    assert h3 == "plane-import-u-unknow"
    assert unmapped3 is True
