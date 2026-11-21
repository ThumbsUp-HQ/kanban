# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for multi-source importers: Jira, GitHub, and Linear (KB-P6-03)."""
# ruff: noqa: PLC0415, TC002, PLR0915, E501

from __future__ import annotations

from datetime import UTC
from typing import Any, cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Attachment,
    Cycle,
    ImportEntityMapping,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueKeyAlias,
    LinkKind,
    ObjectLink,
    Project,
    ProjectLabel,
)
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.content.unicode_guard import ContentNormalizeError
from kanban.importer.github_importer import GitHubIssuesImporter
from kanban.importer.jira_importer import JiraImporter
from kanban.importer.linear_importer import LinearImporter
from kanban.importer.plane_importer import ImportIntegrityError


@pytest.fixture
async def setup_multi_import_env(
    db_session: AsyncSession,
) -> tuple[AsyncSession, PrincipalContext]:
    """Bootstrap workspace and admin principal for importer tests."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)

    await db_session.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws_id), "pid": str(admin_id)},
    )

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )
    return db_session, caller


@pytest.mark.asyncio
async def test_jira_importer_adf_and_html(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Jira import with ADF / HTML descriptions, aliases, comments, and links."""
    session, caller = setup_multi_import_env

    jira_export = {
        "issues": [
            {
                "key": "JIRA-101",
                "fields": {
                    "summary": "Parent Jira Epic",
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "This is a rich "},
                                    {
                                        "type": "text",
                                        "text": "bold paragraph",
                                        "marks": [{"type": "strong"}],
                                    },
                                ],
                            }
                        ],
                    },
                    "status": {"name": "In Progress"},
                    "priority": {"name": "High"},
                    "comment": {
                        "comments": [
                            {
                                "id": "c-1",
                                "body": "First comment on JIRA-101",
                                "author": {"displayName": "Alice Admin"},
                            }
                        ]
                    },
                },
            },
            {
                "key": "JIRA-102",
                "fields": {
                    "summary": "Child Task",
                    "description": "<p>HTML description with <strong>bold</strong> text</p>",
                    "status": {"name": "Backlog"},
                    "parent": {"key": "JIRA-101"},
                    "issuelinks": [
                        {
                            "type": {
                                "name": "Blocks",
                                "inward": "is blocked by",
                                "outward": "blocks",
                            },
                            "outwardIssue": {"key": "JIRA-101"},
                        }
                    ],
                },
            },
        ]
    }

    importer = JiraImporter(session=session, caller=caller)

    # 1. Test Dry Run
    report_dry = await importer.run_import(jira_export, target_project_key="JIRA", dry_run=True)
    assert report_dry.to_create == 2
    assert report_dry.unchanged == 0

    # 2. Test Live Run
    report_live = await importer.run_import(jira_export, target_project_key="JIRA", dry_run=False)
    assert report_live.to_create == 2

    # Verify IssueKeyAlias records
    aliases_res = await session.execute(
        select(IssueKeyAlias)
        .where(IssueKeyAlias.workspace_id == caller.workspace_id)
        .order_by(IssueKeyAlias.legacy_key)
    )
    aliases = list(aliases_res.scalars().all())
    assert len(aliases) == 2
    assert aliases[0].legacy_key == "JIRA-101"
    assert aliases[0].source_system == "jira"
    assert aliases[1].legacy_key == "JIRA-102"

    # Verify Markdown conversion
    iss_res = await session.execute(select(Issue).where(Issue.id == aliases[0].issue_id))
    parent_issue = iss_res.scalar_one()
    assert "**bold paragraph**" in parent_issue.description_markdown

    # Verify DAG Parent Link
    child_res = await session.execute(select(Issue).where(Issue.id == aliases[1].issue_id))
    child_issue = child_res.scalar_one()
    assert "**bold**" in child_issue.description_markdown

    links_res = await session.execute(
        select(ObjectLink).where(
            ObjectLink.workspace_id == caller.workspace_id,
            ObjectLink.target_id == child_issue.id,
            ObjectLink.link_type == LinkKind.PARENT_OF,
        )
    )
    parent_link = links_res.scalar_one_or_none()
    assert parent_link is not None
    assert parent_link.source_id == parent_issue.id

    # Verify Cutover Audit Report
    cutover = importer.build_cutover_audit(report_live)
    assert cutover.is_consistent is True
    assert cutover.source_system == "jira"


@pytest.mark.asyncio
async def test_github_issues_importer(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify GitHub issues import with GH-<num> aliases, labels, and comments."""
    session, caller = setup_multi_import_env

    github_export = [
        {
            "number": 88,
            "title": "Fix memory leak in buffer pool",
            "body": "Detailed reproduction steps in markdown.\n\n- Step 1\n- Step 2",
            "state": "open",
            "labels": [{"name": "bug", "color": "d73a4a"}],
            "user": {"login": "octocat"},
            "comments_data": [
                {
                    "id": 9991,
                    "body": "Investigating this now.",
                    "user": {"login": "reviewer"},
                    "created_at": "2026-03-01T10:00:00Z",
                }
            ],
        },
        {
            "number": 89,
            "title": "Add feature flag for new dashboard",
            "body": "Feature flag specification.",
            "state": "closed",
            "labels": [{"name": "enhancement", "color": "a2eeef"}],
            "user": {"login": "octocat"},
        },
    ]

    importer = GitHubIssuesImporter(session=session, caller=caller)

    report = await importer.run_import(github_export, target_project_key="GH", dry_run=False)
    assert report.to_create == 2

    # Check GH-88 alias
    al_res = await session.execute(
        select(IssueKeyAlias).where(
            IssueKeyAlias.workspace_id == caller.workspace_id,
            IssueKeyAlias.legacy_key == "GH-88",
        )
    )
    alias_88 = al_res.scalar_one_or_none()
    assert alias_88 is not None
    assert alias_88.source_system == "github"

    # Check comment imported
    cm_res = await session.execute(
        select(IssueComment).where(IssueComment.issue_id == alias_88.issue_id)
    )
    comments = list(cm_res.scalars().all())
    assert len(comments) == 1
    assert "Investigating this now" in comments[0].body_markdown

    cutover = importer.build_cutover_audit(report)
    assert cutover.is_consistent is True
    assert cutover.source_system == "github"


@pytest.mark.asyncio
async def test_linear_importer_json_and_csv(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Linear import with JSON and CSV formats, ENG-<num> aliases, and parent links."""
    session, caller = setup_multi_import_env

    # 1. Test Linear JSON
    linear_json = {
        "issues": [
            {
                "id": "lin-parent",
                "identifier": "ENG-42",
                "number": 42,
                "title": "Infrastructure hard cutover",
                "description": "Linear parent issue description.",
                "state": {"name": "Started", "type": "started"},
                "priority": 1,
            },
            {
                "id": "lin-child",
                "identifier": "ENG-43",
                "number": 43,
                "title": "Database snapshot validation",
                "description": "Linear child issue description.",
                "state": {"name": "Triage", "type": "backlog"},
                "priority": 2,
                "parentId": "lin-parent",
            },
        ]
    }

    importer = LinearImporter(session=session, caller=caller)
    report_json = await importer.run_import(linear_json, target_project_key="ENG", dry_run=False)
    assert report_json.to_create == 2

    # Verify ENG-42 alias
    al_res = await session.execute(
        select(IssueKeyAlias).where(
            IssueKeyAlias.workspace_id == caller.workspace_id,
            IssueKeyAlias.legacy_key == "ENG-42",
        )
    )
    alias_42 = al_res.scalar_one_or_none()
    assert alias_42 is not None
    assert alias_42.source_system == "linear"

    # 2. Test Linear CSV format
    linear_csv = (
        "id,identifier,number,title,description,state,priority,parentId\n"
        "lin-csv-1,ENG-100,100,CSV Imported Task,Body from CSV,Done,3,\n"
    )

    importer_csv = LinearImporter(session=session, caller=caller)
    report_csv = await importer_csv.run_import(linear_csv, target_project_key="ENG", dry_run=False)
    assert report_csv.to_create == 1

    al_csv = await session.execute(
        select(IssueKeyAlias).where(
            IssueKeyAlias.workspace_id == caller.workspace_id,
            IssueKeyAlias.legacy_key == "ENG-100",
        )
    )
    assert al_csv.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_jira_importer_adf_full_elements_and_repeat_import(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Jira ADF comprehensive formatting, repeat unchanged, update, and API endpoint."""
    session, caller = setup_multi_import_env
    from kanban.api.v1.admin.imports import AdminGenericImportRequest, import_jira_bundle

    complex_adf_export: dict[str, Any] = {
        "issues": [
            {
                "key": "JIRA-201",
                "fields": {
                    "summary": "Rich ADF Elements Issue",
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "heading",
                                "attrs": {"level": 2},
                                "content": [{"type": "text", "text": "Header Two"}],
                            },
                            {
                                "type": "blockquote",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "A quote"}],
                                    }
                                ],
                            },
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [
                                                    {"type": "text", "text": "Bullet item"}
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "orderedList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [
                                                    {"type": "text", "text": "Numbered item"}
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "codeBlock",
                                "attrs": {"language": "python"},
                                "content": [{"type": "text", "text": "x = 42"}],
                            },
                            {"type": "rule"},
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "mention", "attrs": {"text": "@charlie"}},
                                    {"type": "date", "attrs": {"timestamp": "1710000000000"}},
                                    {
                                        "type": "text",
                                        "text": "inline code",
                                        "marks": [{"type": "code"}],
                                    },
                                    {
                                        "type": "text",
                                        "text": "strike",
                                        "marks": [{"type": "strike"}],
                                    },
                                    {
                                        "type": "text",
                                        "text": "underline",
                                        "marks": [{"type": "underline"}],
                                    },
                                    {"type": "text", "text": "italic", "marks": [{"type": "em"}]},
                                ],
                            },
                        ],
                    },
                    "status": "In Progress",
                    "priority": "Highest",
                },
            }
        ]
    }

    importer = JiraImporter(session=session, caller=caller, user_map={"jira-alice": "alice"})
    report = await importer.run_import(
        complex_adf_export, target_project_key="JIRAB", dry_run=False
    )
    assert report.to_create == 1

    # Repeat same import -> unchanged
    report_unchanged = await importer.run_import(
        complex_adf_export, target_project_key="JIRAB", dry_run=False
    )
    assert report_unchanged.unchanged == 1

    # Modify summary/description -> update
    complex_adf_export["issues"][0]["fields"]["summary"] = "Updated Rich ADF Summary"
    report_update = await importer.run_import(
        complex_adf_export, target_project_key="JIRAB", dry_run=False
    )
    assert report_update.to_update == 1

    # Empty issues warning
    empty_report = await importer.run_import(
        {"issues": []}, target_project_key="JIRAB", dry_run=False
    )
    assert len(empty_report.warnings) > 0

    # Test admin route import_jira_bundle
    req = AdminGenericImportRequest(
        bundle_data=complex_adf_export,
        project_key="JIRAB",
        dry_run=True,
    )
    api_rep = await import_jira_bundle(req, caller=caller, session=session)
    assert api_rep is not None


@pytest.mark.asyncio
async def test_github_importer_dry_run_and_repeat_and_api(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify GitHub dry run, repeat unchanged, update, and API endpoint."""
    session, caller = setup_multi_import_env
    from kanban.api.v1.admin.imports import AdminGenericImportRequest, import_github_bundle

    gh_data = [
        {
            "number": 301,
            "title": "GH Dry Run Issue",
            "body": "Markdown body content",
            "state": "open",
        }
    ]

    importer = GitHubIssuesImporter(session=session, caller=caller)
    # Dry run
    report_dry = await importer.run_import(gh_data, target_project_key="GHB", dry_run=True)
    assert report_dry.to_create == 1

    # Live run
    report_live = await importer.run_import(gh_data, target_project_key="GHB", dry_run=False)
    assert report_live.to_create == 1

    # Repeat unchanged
    report_unchanged = await importer.run_import(gh_data, target_project_key="GHB", dry_run=False)
    assert report_unchanged.unchanged == 1

    # Update
    gh_data[0]["title"] = "GH Updated Title"
    report_update = await importer.run_import(gh_data, target_project_key="GHB", dry_run=False)
    assert report_update.to_update == 1

    # Admin route
    req = AdminGenericImportRequest(
        bundle_data={"issues": gh_data}, project_key="GHB", dry_run=True
    )
    api_rep = await import_github_bundle(req, caller=caller, session=session)
    assert api_rep is not None


@pytest.mark.asyncio
async def test_linear_importer_dry_run_and_repeat_and_api(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Linear dry run, repeat unchanged, update, and API endpoint."""
    session, caller = setup_multi_import_env
    from kanban.api.v1.admin.imports import AdminGenericImportRequest, import_linear_bundle

    lin_data = {
        "issues": [
            {
                "id": "lin-repeat",
                "identifier": "ENG-501",
                "number": 501,
                "title": "Linear Repeat Test",
                "description": "Linear desc",
                "state": {"name": "In Progress", "type": "started"},
                "priority": 0,
            }
        ]
    }

    importer = LinearImporter(session=session, caller=caller)
    # Dry run
    rep_dry = await importer.run_import(lin_data, target_project_key="ENGB", dry_run=True)
    assert rep_dry.to_create == 1

    # Live
    rep_live = await importer.run_import(lin_data, target_project_key="ENGB", dry_run=False)
    assert rep_live.to_create == 1

    # Repeat unchanged
    rep_unchanged = await importer.run_import(lin_data, target_project_key="ENGB", dry_run=False)
    assert rep_unchanged.unchanged == 1

    # Update
    lin_data["issues"][0]["title"] = "Updated Linear Title"
    rep_update = await importer.run_import(lin_data, target_project_key="ENGB", dry_run=False)
    assert rep_update.to_update == 1

    # Build cutover audit
    audit = importer.build_cutover_audit(rep_live)
    assert audit.is_consistent is True
    assert audit.source_system == "linear"

    # Admin route
    req = AdminGenericImportRequest(bundle_data=lin_data, project_key="ENGB", dry_run=True)
    api_rep = await import_linear_bundle(req, caller=caller, session=session)
    assert api_rep is not None


def test_importer_unit_helpers() -> None:
    """Verify ADF parsing, status mapping, and priority mapping unit logic."""
    from kanban.importer.jira_importer import (
        _map_jira_priority,
        _map_jira_status,
        adf_to_markdown,
    )
    from kanban.importer.linear_importer import (
        _map_linear_priority,
        _map_linear_status,
    )

    # ADF conversion edge cases
    assert adf_to_markdown(None) == ""
    assert adf_to_markdown("plain text") == "plain text"
    assert adf_to_markdown(42) == "42"

    # Headings min/max clamping
    assert (
        adf_to_markdown(
            {"type": "heading", "attrs": {"level": 0}, "content": [{"type": "text", "text": "H0"}]}
        )
        == "# H0"
    )
    assert (
        adf_to_markdown(
            {"type": "heading", "attrs": {"level": 8}, "content": [{"type": "text", "text": "H8"}]}
        )
        == "###### H8"
    )

    # Marks
    marked_text = {
        "type": "text",
        "text": "Link Text",
        "marks": [
            {"type": "link", "attrs": {"href": "https://example.com"}},
            {"type": "strong"},
            {"type": "em"},
        ],
    }
    rendered = adf_to_markdown(marked_text)
    assert "[Link Text](https://example.com)" in rendered

    # Jira status & priority mapping
    assert _map_jira_status("Resolved") == "completed"
    assert _map_jira_status("Closed") == "completed"
    assert _map_jira_status("Won't Fix") == "cancelled"
    assert _map_jira_status("Rejected") == "cancelled"
    assert _map_jira_status("Custom State") == "unstarted"

    assert _map_jira_priority("Blocker") == "urgent"
    assert _map_jira_priority("Critical") == "high"
    assert _map_jira_priority("Major") == "medium"
    assert _map_jira_priority("Minor") == "low"
    assert _map_jira_priority("Trivial") == "none"
    assert _map_jira_priority("Lowest") == "none"
    assert _map_jira_priority("Normal") == "medium"

    # Linear status & priority mapping
    assert _map_linear_status({"type": "canceled"}) == "cancelled"
    assert _map_linear_status({"type": "cancelled"}) == "cancelled"
    assert _map_linear_status({"type": "backlog"}) == "backlog"
    assert _map_linear_status({"type": "unstarted"}) == "unstarted"
    assert _map_linear_status({"type": "started"}) == "started"
    assert _map_linear_status({"type": "completed"}) == "completed"
    assert _map_linear_status("triage") == "backlog"
    assert _map_linear_status("in review") == "started"
    assert _map_linear_status("duplicate") == "cancelled"
    assert _map_linear_status("unknown") == "unstarted"

    assert _map_linear_priority("1") == "urgent"
    assert _map_linear_priority("2") == "high"
    assert _map_linear_priority("3") == "medium"
    assert _map_linear_priority("4") == "low"
    assert _map_linear_priority("0") == "none"
    assert _map_linear_priority("none") == "none"
    assert _map_linear_priority("no priority") == "none"
    assert _map_linear_priority("other") == "medium"

    from datetime import datetime

    from kanban.importer.github_importer import (
        _parse_iso_datetime as g_dt,
    )
    from kanban.importer.github_importer import (
        _validate_attachment_filename as g_val,
    )
    from kanban.importer.jira_importer import (
        _parse_iso_datetime as j_dt,
    )
    from kanban.importer.jira_importer import (
        _validate_attachment_filename as j_val,
    )
    from kanban.importer.linear_importer import (
        _parse_iso_datetime as l_dt,
    )
    from kanban.importer.linear_importer import (
        _validate_attachment_filename as l_val,
    )

    for dt_fn in (j_dt, g_dt, l_dt):
        assert dt_fn(None) is None
        assert dt_fn("") is None
        assert dt_fn("invalid-date-format") is None
        now_dt = datetime.now(UTC)
        assert dt_fn(now_dt) == now_dt
        naive_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        res_dt = dt_fn(naive_dt)
        assert res_dt is not None
        assert res_dt.tzinfo == UTC
        parsed = dt_fn("2026-05-15T10:30:00Z")
        assert parsed is not None
        assert parsed.year == 2026

    for val_fn in (j_val, g_val, l_val):
        with pytest.raises(ImportIntegrityError):
            val_fn("../etc/passwd")
        with pytest.raises(ImportIntegrityError):
            val_fn("/root/file.txt")
        with pytest.raises(ImportIntegrityError):
            val_fn("dir\\file.txt")
        val_fn("safe-file.png")


@pytest.mark.asyncio
async def test_importers_edge_cases_and_error_handling(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify validation guards, error handling, relations, and admin route failures."""
    session, caller = setup_multi_import_env
    from unittest.mock import patch

    from kanban.api.problems import ProblemException
    from kanban.api.v1.admin.imports import (
        AdminGenericImportRequest,
        import_github_bundle,
        import_jira_bundle,
        import_linear_bundle,
    )
    from kanban.importer.plane_importer import ImportIntegrityError

    # 1. Missing caller workspace_id
    bad_caller = PrincipalContext(
        principal_id=caller.principal_id, workspace_id=cast("Any", None), aal_level=2
    )
    with pytest.raises(ValueError, match="workspace_id is required"):
        await JiraImporter(session=session, caller=bad_caller).run_import({}, dry_run=True)
    with pytest.raises(ValueError, match="workspace_id is required"):
        await GitHubIssuesImporter(session=session, caller=bad_caller).run_import({}, dry_run=True)
    with pytest.raises(ValueError, match="workspace_id is required"):
        await LinearImporter(session=session, caller=bad_caller).run_import({}, dry_run=True)

    # 2. GitHub importer invalid items & state_reason
    gh_importer = GitHubIssuesImporter(session=session, caller=caller)
    empty_gh = await gh_importer.run_import([], target_project_key="GHEDGE", dry_run=True)
    assert len(empty_gh.warnings) > 0

    gh_edge_data = [
        "not-a-dict",
        {"no_number": True},
        {
            "number": 991,
            "title": "Closed Not Planned",
            "body": "Issue was cancelled",
            "state": "closed",
            "state_reason": "not_planned",
        },
    ]
    gh_rep = await gh_importer.run_import(gh_edge_data, target_project_key="GHEDGE", dry_run=False)
    assert gh_rep.to_create == 1

    # 3. Linear importer relations and comments
    lin_importer = LinearImporter(session=session, caller=caller)
    empty_lin = await lin_importer.run_import([], target_project_key="LINEDGE", dry_run=True)
    assert len(empty_lin.warnings) > 0

    lin_rich_data = {
        "issues": [
            {
                "id": "lin-rel-1",
                "identifier": "LIN-701",
                "number": 701,
                "title": "Blocking task",
                "description": "Blocks child",
                "state": "Backlog",
                "priority": 1,
            },
            {
                "id": "lin-rel-2",
                "identifier": "LIN-702",
                "number": 702,
                "title": "Blocked task",
                "description": "Blocked by parent",
                "state": "In Progress",
                "priority": 2,
                "parentId": "lin-rel-1",
                "relations": [
                    {"type": "blocks", "relatedIssue": {"identifier": "lin-rel-1"}},
                    {"type": "blockedBy", "relatedIssueId": "lin-rel-1"},
                ],
                "comments": [
                    {"body": "First comment"},
                    {"body": "Second comment"},
                ],
            },
        ]
    }
    lin_rep = await lin_importer.run_import(
        lin_rich_data, target_project_key="LINEDGE", dry_run=False
    )
    assert lin_rep.to_create == 2

    # Target project ID tests
    proj_res = await session.execute(
        select(Project).where(Project.workspace_id == caller.workspace_id)
    )
    existing_proj = proj_res.scalars().first()
    assert existing_proj is not None

    jira_rich = {
        "issues": [
            {
                "key": "JIRAX-1",
                "fields": {
                    "summary": "Inward link test",
                    "status": "In Progress",
                    "priority": "P0",
                    "parent": {"key": "JIRAX-2"},
                    "issuelinks": [
                        {
                            "type": {"name": "blocks"},
                            "inwardIssue": {"key": "JIRAX-2"},
                        }
                    ],
                    "comment": [
                        {
                            "body": {
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "ADF comment"}],
                                    }
                                ],
                            }
                        }
                    ],
                },
            },
            {
                "key": "JIRAX-2",
                "fields": {
                    "summary": "Target parent",
                    "status": "Done",
                    "priority": "P4",
                },
            },
        ]
    }
    j_importer = JiraImporter(session=session, caller=caller)
    await j_importer.run_import(jira_rich, target_project_id=existing_proj.id, dry_run=False)

    gh_rich = [
        {
            "number": 8801,
            "title": "GH Target Proj",
            "body": "Body",
            "state": "open",
            "comments_data": [
                "not-a-dict",
                {"body": ""},
                {"body": "Valid body"},
            ],
        }
    ]
    await gh_importer.run_import(gh_rich, target_project_id=existing_proj.id, dry_run=False)

    lin_edge_2 = {
        "issues": [
            {
                "id": "lin-edge-tgt",
                "identifier": "LIN-9901",
                "number": 9901,
                "title": "Lin Target Proj",
                "description": "Lin Desc",
                "parentId": {"identifier": "LIN-701"},
                "comments": ["not-a-dict", {"body": ""}, {"body": "Non empty"}],
            }
        ]
    }
    await lin_importer.run_import(lin_edge_2, target_project_id=existing_proj.id, dry_run=False)

    # Linear generate_audit_report
    audit_lin = lin_importer.generate_audit_report("ws-slug", "LINEDGE", lin_rep)
    assert audit_lin is not None

    # Jira generate_audit_report
    jira_importer = JiraImporter(session=session, caller=caller)
    audit_jira = jira_importer.generate_audit_report("ws-slug", "JIRAB", lin_rep)
    assert audit_jira is not None

    # GitHub generate_audit_report
    audit_gh = gh_importer.generate_audit_report("ws-slug", "GHEDGE", gh_rep)
    assert audit_gh is not None

    # 4. Admin API error handling: ImportIntegrityError & Exception
    req_jira = AdminGenericImportRequest(
        bundle_data={"issues": []}, project_key="JIRAB", dry_run=True
    )
    with patch(
        "kanban.importer.jira_importer.JiraImporter.run_import",
        side_effect=ImportIntegrityError("Corrupt schema"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_jira_bundle(req_jira, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_INTEGRITY_FAILED"

    with patch(
        "kanban.importer.jira_importer.JiraImporter.run_import",
        side_effect=RuntimeError("Fatal error"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_jira_bundle(req_jira, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_EXECUTION_ERROR"

    req_gh = AdminGenericImportRequest(
        bundle_data={"issues": []}, project_key="GHEDGE", dry_run=True
    )
    with patch(
        "kanban.importer.github_importer.GitHubIssuesImporter.run_import",
        side_effect=ImportIntegrityError("Corrupt GitHub"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_github_bundle(req_gh, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_INTEGRITY_FAILED"

    with patch(
        "kanban.importer.github_importer.GitHubIssuesImporter.run_import",
        side_effect=RuntimeError("Fatal GH error"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_github_bundle(req_gh, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_EXECUTION_ERROR"

    req_lin = AdminGenericImportRequest(
        bundle_data={"issues": []}, project_key="LINEDGE", dry_run=True
    )
    with patch(
        "kanban.importer.linear_importer.LinearImporter.run_import",
        side_effect=ImportIntegrityError("Corrupt Linear"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_linear_bundle(req_lin, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_INTEGRITY_FAILED"

    with patch(
        "kanban.importer.linear_importer.LinearImporter.run_import",
        side_effect=RuntimeError("Fatal Linear error"),
    ):
        with pytest.raises(ProblemException) as exc_info:
            await import_linear_bundle(req_lin, caller=caller, session=session)
        assert exc_info.value.code == "IMPORT_EXECUTION_ERROR"


@pytest.mark.asyncio
async def test_importers_unseeded_project_auto_bootstraps_states_and_prio(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify importers bootstrap default workflow states and priorities when importing into an unseeded project."""
    session, caller = setup_multi_import_env

    # 1. Unseeded Project for GitHub (creates default states and priorities)
    proj_id_gh = (
        await session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'UNSEEDGH', 'Unseeded GH', :admin)"
            ),
            {"ws": caller.workspace_id, "admin": caller.principal_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'UNSEEDGH', 'Unseeded GH', 'Desc')"
        ),
        {"id": proj_id_gh, "ws": caller.workspace_id},
    )

    gh_imp = GitHubIssuesImporter(session=session, caller=caller)
    gh_rep = await gh_imp.run_import(
        [{"number": 1, "title": "Unseeded Issue", "state": "open"}],
        target_project_id=proj_id_gh,
        dry_run=False,
    )
    assert gh_rep.to_create == 1

    # 2. Unseeded Project for Jira
    proj_id_jira = (
        await session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'UNSEEDJIRA', 'Unseeded Jira', :admin)"
            ),
            {"ws": caller.workspace_id, "admin": caller.principal_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'UNSEEDJIRA', 'Unseeded Jira', 'Desc')"
        ),
        {"id": proj_id_jira, "ws": caller.workspace_id},
    )

    jira_imp = JiraImporter(session=session, caller=caller)
    jira_rep = await jira_imp.run_import(
        {
            "issues": [
                {
                    "key": "UNJ-1",
                    "fields": {"summary": "Jira Unseeded", "status": "In Progress"},
                }
            ]
        },
        target_project_id=proj_id_jira,
        dry_run=False,
    )
    assert jira_rep.to_create == 1

    # 3. Unseeded Project for Linear
    proj_id_lin = (
        await session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'UNSEEDLIN', 'Unseeded Linear', :admin)"
            ),
            {"ws": caller.workspace_id, "admin": caller.principal_id},
        )
    ).scalar_one()
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'UNSEEDLIN', 'Unseeded Linear', 'Desc')"
        ),
        {"id": proj_id_lin, "ws": caller.workspace_id},
    )

    lin_imp = LinearImporter(session=session, caller=caller)
    lin_rep = await lin_imp.run_import(
        {"issues": [{"identifier": "UNL-1", "title": "Linear Unseeded", "state": "Todo"}]},
        target_project_id=proj_id_lin,
        dry_run=False,
    )
    assert lin_rep.to_create == 1

    # 4. Helper and edge coverage
    from kanban.importer.jira_importer import (
        _map_jira_priority,
        _map_jira_status,
        adf_to_markdown,
    )
    from kanban.importer.linear_importer import _map_linear_priority, _map_linear_status

    # ADF content list
    nested_adf = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}],
    }
    assert "Hello" in adf_to_markdown(nested_adf)

    # Jira status & priority helpers
    assert _map_jira_status("Resolved") == "completed"
    assert _map_jira_status("Closed") == "completed"
    assert _map_jira_status("Unknown Status") == "unstarted"
    assert _map_jira_priority("Blocker") == "urgent"
    assert _map_jira_priority("Critical") == "high"
    assert _map_jira_priority("Major") == "medium"
    assert _map_jira_priority("Minor") == "low"
    assert _map_jira_priority("Trivial") == "none"
    assert _map_jira_priority("Lowest") == "none"
    assert _map_jira_priority("SomethingElse") == "medium"

    # Linear status & priority helpers
    assert _map_linear_status("in_progress") == "unstarted"
    assert _map_linear_status("in progress") == "started"
    assert _map_linear_status("completed") == "completed"
    assert _map_linear_status({"type": "started"}) == "started"
    assert _map_linear_status({"name": "cancelled"}) == "cancelled"
    assert _map_linear_status("cancelled") == "cancelled"
    assert _map_linear_status("triage") == "backlog"
    assert _map_linear_status("random") == "unstarted"
    assert _map_linear_priority(1) == "urgent"
    assert _map_linear_priority(2) == "high"
    assert _map_linear_priority(3) == "medium"
    assert _map_linear_priority(4) == "low"
    assert _map_linear_priority(0) == "none"
    assert _map_linear_priority("invalid") == "medium"

    # 5. Linear string json import + internal links
    import json

    lin_str_data = json.dumps(
        {
            "issues": [
                {
                    "identifier": "LINST-1",
                    "title": "Parent Task",
                    "state": "Todo",
                },
                {
                    "identifier": "LINST-2",
                    "title": "Child Task",
                    "state": "In Progress",
                    "parentId": "LINST-1",
                    "relations": [{"type": "blocks", "relatedIssueId": "LINST-1"}],
                },
            ]
        }
    )
    rep_lin_str = await lin_imp.run_import(
        lin_str_data, target_project_id=proj_id_lin, dry_run=False
    )
    assert rep_lin_str.to_create == 2


@pytest.mark.asyncio
async def test_github_importer_labels_milestones_and_sub_issues(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify GitHub importer ingests labels, milestones, and sub-issues/parent links."""
    session, caller = setup_multi_import_env

    gh_data = [
        {
            "number": 10,
            "title": "Parent Feature",
            "body": "Parent specification",
            "state": "open",
            "labels": [{"name": "backend", "color": "0052cc"}],
            "milestone": {"title": "v1.0 Milestone", "description": "Target milestone"},
        },
        {
            "number": 11,
            "title": "Child Subtask",
            "body": "Subtask specification",
            "state": "open",
            "parent": {"number": 10},
            "milestone": {"title": "v1.0 Milestone"},
        },
    ]

    importer = GitHubIssuesImporter(session=session, caller=caller)
    report = await importer.run_import(gh_data, target_project_key="GHREL", dry_run=False)
    assert report.to_create == 2

    # Verify ProjectLabel and IssueLabel
    lbl_res = await session.execute(
        select(ProjectLabel).where(
            ProjectLabel.workspace_id == caller.workspace_id,
            ProjectLabel.name == "backend",
        )
    )
    label = lbl_res.scalar_one_or_none()
    assert label is not None
    assert label.color_hex == "#0052cc"

    # Verify Cycle created for milestone
    cycle_res = await session.execute(
        select(Cycle).where(
            Cycle.workspace_id == caller.workspace_id,
            Cycle.name == "v1.0 Milestone",
        )
    )
    cycle = cycle_res.scalar_one_or_none()
    assert cycle is not None

    # Verify issues have cycle_id set
    iss_res = await session.execute(
        select(Issue).where(Issue.workspace_id == caller.workspace_id).order_by(Issue.sequence_id)
    )
    issues = list(iss_res.scalars().all())
    assert len(issues) == 2
    assert issues[0].cycle_id == cycle.id
    assert issues[1].cycle_id == cycle.id

    # Verify PARENT_OF link
    link_res = await session.execute(
        select(ObjectLink).where(
            ObjectLink.workspace_id == caller.workspace_id,
            ObjectLink.link_type == LinkKind.PARENT_OF,
        )
    )
    link = link_res.scalar_one_or_none()
    assert link is not None
    assert link.source_id == issues[0].id
    assert link.target_id == issues[1].id


@pytest.mark.asyncio
async def test_importers_hostile_input_sanitization(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify script and hidden-DOM paste-injection vectors are stripped across importers."""
    session, caller = setup_multi_import_env

    hostile_html = (
        "<script>alert('pwned')</script>"
        "<p>Visible safe text</p>"
        "<span style='display:none'>hidden paste-jacking prompt injection</span>"
    )

    # 1. Jira Importer
    jira_data = {
        "issues": [
            {
                "key": "SEC-1",
                "fields": {
                    "summary": "Security Test",
                    "description": hostile_html,
                    "status": "Open",
                },
            }
        ]
    }
    jira_imp = JiraImporter(session=session, caller=caller)
    await jira_imp.run_import(jira_data, target_project_key="SECJ", dry_run=False)

    al_res = await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "SEC-1"))
    sec_issue = (
        await session.execute(select(Issue).where(Issue.id == al_res.scalar_one().issue_id))
    ).scalar_one()
    assert "<script>" not in sec_issue.description_markdown
    assert "alert(" not in sec_issue.description_markdown
    assert "display:none" not in sec_issue.description_markdown
    assert "Visible safe text" in sec_issue.description_markdown

    # 2. GitHub Importer
    gh_data = [{"number": 99, "title": "GH Hostile", "body": hostile_html, "state": "open"}]
    gh_imp = GitHubIssuesImporter(session=session, caller=caller)
    await gh_imp.run_import(gh_data, target_project_key="SECG", dry_run=False)
    gh_al_res = await session.execute(
        select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "GH-99")
    )
    gh_issue = (
        await session.execute(select(Issue).where(Issue.id == gh_al_res.scalar_one().issue_id))
    ).scalar_one()
    assert "<script>" not in gh_issue.description_markdown
    assert "Visible safe text" in gh_issue.description_markdown

    # 3. Linear Importer
    lin_data = [
        {
            "identifier": "SECL-1",
            "title": "Lin Hostile",
            "description": hostile_html,
            "state": "Todo",
        }
    ]
    lin_imp = LinearImporter(session=session, caller=caller)
    await lin_imp.run_import(lin_data, target_project_key="SECL", dry_run=False)
    lin_al_res = await session.execute(
        select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "SECL-1")
    )
    lin_issue = (
        await session.execute(select(Issue).where(Issue.id == lin_al_res.scalar_one().issue_id))
    ).scalar_one()
    assert "<script>" not in lin_issue.description_markdown
    assert "Visible safe text" in lin_issue.description_markdown


@pytest.mark.asyncio
async def test_importers_utf16_lone_surrogate_rejection(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify UTF-16 lone surrogates are rejected fail-closed with ContentNormalizeError."""
    session, caller = setup_multi_import_env

    bad_text = "Hostile text with surrogate \ud800 payload"

    # Jira
    jira_imp = JiraImporter(session=session, caller=caller)
    with pytest.raises(ContentNormalizeError):
        await jira_imp.run_import(
            {"issues": [{"key": "SURR-1", "fields": {"summary": "Bad", "description": bad_text}}]},
            dry_run=True,
        )

    # GitHub
    gh_imp = GitHubIssuesImporter(session=session, caller=caller)
    with pytest.raises(ContentNormalizeError):
        await gh_imp.run_import(
            [{"number": 999, "title": "Bad GH", "body": bad_text}],
            dry_run=True,
        )

    # Linear
    lin_imp = LinearImporter(session=session, caller=caller)
    with pytest.raises(ContentNormalizeError):
        await lin_imp.run_import(
            [{"identifier": "SURRL-1", "title": "Bad Lin", "description": bad_text}],
            dry_run=True,
        )


@pytest.mark.asyncio
async def test_importers_attachment_path_traversal_rejection(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify attachment filenames with traversal sequences are rejected fail-closed."""
    session, caller = setup_multi_import_env

    traversal_filenames = [
        "../evil.png",
        "foo/../../bar.png",
        "/etc/passwd",
        "C:\\windows\\system32.dll",
    ]

    for bad_fn in traversal_filenames:
        jira_imp = JiraImporter(session=session, caller=caller)
        with pytest.raises(ImportIntegrityError):
            await jira_imp.run_import(
                {
                    "issues": [
                        {
                            "key": "ATT-1",
                            "fields": {
                                "summary": "Att test",
                                "attachments": [{"filename": bad_fn, "content": "dGVzdA=="}],
                            },
                        }
                    ]
                },
                dry_run=True,
            )

        gh_imp = GitHubIssuesImporter(session=session, caller=caller)
        with pytest.raises(ImportIntegrityError):
            await gh_imp.run_import(
                [
                    {
                        "number": 500,
                        "title": "Att test",
                        "attachments": [{"filename": bad_fn, "content": "dGVzdA=="}],
                    }
                ],
                dry_run=True,
            )

        lin_imp = LinearImporter(session=session, caller=caller)
        with pytest.raises(ImportIntegrityError):
            await lin_imp.run_import(
                [
                    {
                        "identifier": "ATTL-1",
                        "title": "Att test",
                        "attachments": [{"filename": bad_fn, "content": "dGVzdA=="}],
                    }
                ],
                dry_run=True,
            )


@pytest.mark.asyncio
async def test_importers_reimport_sha_update_mutation(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify re-importing issues and comments with altered SHA-256 updates database entities."""
    session, caller = setup_multi_import_env

    # 1. Initial import of Jira issue and comment
    initial_jira = {
        "issues": [
            {
                "key": "MUT-1",
                "fields": {
                    "summary": "Original Summary",
                    "description": "Original Description",
                    "status": "To Do",
                    "priority": "Low",
                    "comment": {"comments": [{"id": "cm-mut-1", "body": "Original Comment Body"}]},
                },
            }
        ]
    }

    jira_imp = JiraImporter(session=session, caller=caller)
    rep_1 = await jira_imp.run_import(initial_jira, target_project_key="MUTJ", dry_run=False)
    assert rep_1.to_create == 1
    assert rep_1.to_update == 0

    # 2. Re-import identical payload -> unchanged
    rep_same = await jira_imp.run_import(initial_jira, target_project_key="MUTJ", dry_run=False)
    assert rep_same.to_create == 0
    assert rep_same.unchanged == 1
    assert rep_same.to_update == 0

    # 3. Modified payload -> updates issue and comment
    modified_jira = {
        "issues": [
            {
                "key": "MUT-1",
                "fields": {
                    "summary": "Updated Summary Value",
                    "description": "Updated Description Value",
                    "status": "In Progress",
                    "priority": "High",
                    "comment": {"comments": [{"id": "cm-mut-1", "body": "Updated Comment Body"}]},
                },
            }
        ]
    }

    rep_mod = await jira_imp.run_import(modified_jira, target_project_key="MUTJ", dry_run=False)
    assert rep_mod.to_update == 1

    # Verify mutated issue
    al_res = await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "MUT-1"))
    mut_issue_id = al_res.scalar_one().issue_id
    mut_issue = (await session.execute(select(Issue).where(Issue.id == mut_issue_id))).scalar_one()
    assert mut_issue.summary == "Updated Summary Value"
    assert "Updated Description Value" in mut_issue.description_markdown

    # Verify mutated comment
    cm_res = await session.execute(
        select(IssueComment).where(IssueComment.issue_id == mut_issue_id)
    )
    mut_comment = cm_res.scalar_one()
    assert "Updated Comment Body" in mut_comment.body_markdown

    # Verify mapping updated with new sha
    map_res = await session.execute(
        select(ImportEntityMapping).where(
            ImportEntityMapping.workspace_id == caller.workspace_id,
            ImportEntityMapping.source_system == "jira",
            ImportEntityMapping.source_kind == "issue",
            ImportEntityMapping.source_id == "MUT-1",
        )
    )
    mapping = map_res.scalar_one()
    assert mapping.source_sha256 is not None


@pytest.mark.asyncio
async def test_importers_user_mapping_and_assignees(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify user_map resolution against database users for Jira, GitHub, and Linear."""
    session, caller = setup_multi_import_env

    # Query current user email
    user_row = (
        (
            await session.execute(
                text(
                    "SELECT email, canonical_key FROM users JOIN objects ON objects.id = users.id WHERE users.id = :id"
                ),
                {"id": caller.principal_id},
            )
        )
        .mappings()
        .first()
    )
    caller_email = user_row["email"] if user_row else "admin@example.com"
    caller_ckey = user_row["canonical_key"] if user_row else "usr-admin"

    user_map = {
        "jira-dev-email": caller_email,
        "jira-dev-uuid": str(caller.principal_id),
        "jira-dev-handle": f"@{caller_ckey}",
        "jira-unknown-target": "does-not-exist@example.com",
    }

    # 1. Jira user mapping
    jira_data = {
        "issues": [
            {
                "key": "UMAP-1",
                "fields": {
                    "summary": "Mapped by email",
                    "assignee": {"name": "jira-dev-email"},
                },
            },
            {
                "key": "UMAP-2",
                "fields": {
                    "summary": "Mapped by uuid",
                    "assignee": {"name": "jira-dev-uuid"},
                },
            },
            {
                "key": "UMAP-3",
                "fields": {
                    "summary": "Unmapped user",
                    "assignee": {"name": "unmapped-dev"},
                },
            },
            {
                "key": "UMAP-4",
                "fields": {
                    "summary": "Target not found",
                    "assignee": {"name": "jira-unknown-target"},
                },
            },
            {
                "key": "UMAP-5",
                "fields": {
                    "summary": "No assignee",
                    "assignee": None,
                },
            },
        ]
    }
    jira_imp = JiraImporter(session=session, caller=caller, user_map=user_map)
    await jira_imp.run_import(jira_data, target_project_key="UMAPJ", dry_run=False)

    # 2. GitHub user mapping
    gh_user_map = {
        "octocat": caller_email,
        "octo-uuid": str(caller.principal_id),
        "octo-handle": f"@{caller_ckey}",
        "unknown-gh": "nobody@example.com",
    }
    gh_data = {
        "issues": [
            {
                "number": 1,
                "title": "GH Mapped",
                "user": {"login": "octocat"},
                "assignees": [{"login": "octocat"}],
                "sub_issues": [2],
                "blocks": [3],
            },
            {
                "number": 2,
                "title": "GH Unmapped",
                "user": "stranger",
                "assignees": ["stranger"],
                "blocked_by": [1],
            },
            {
                "number": 3,
                "title": "GH UUID Mapped",
                "user": "octo-uuid",
                "assignees": [{"login": "octo-uuid"}],
            },
            {
                "number": 4,
                "title": "GH Handle Mapped",
                "assignees": [{"login": "octo-handle"}],
            },
            {
                "number": 5,
                "title": "GH No Assignee",
                "assignee": None,
            },
        ]
    }
    gh_imp = GitHubIssuesImporter(session=session, caller=caller, user_map=gh_user_map)
    await gh_imp.run_import(gh_data, target_project_key="UMAPG", dry_run=False)

    # 3. Linear user mapping
    lin_user_map = {
        "lin-user-1": str(caller.principal_id),
        "lin-user-email": caller_email,
        "lin-user-handle": f"@{caller_ckey}",
        "lin-user-unmapped": "nobody@example.com",
    }
    lin_data = {
        "issues": [
            {
                "id": "LIN-101",
                "title": "Linear Mapped UUID",
                "assignee": {"id": "lin-user-1"},
            },
            {
                "id": "LIN-102",
                "title": "Linear Mapped Email",
                "assignee": {"email": "lin-user-email"},
            },
            {
                "id": "LIN-103",
                "title": "Linear Mapped Handle",
                "assignee": "lin-user-handle",
            },
            {
                "id": "LIN-104",
                "title": "Linear Unmapped Target",
                "assignee": "lin-user-unmapped",
            },
            {
                "id": "LIN-105",
                "title": "Linear Direct Lookup",
                "assignee": caller_email,
            },
            {
                "id": "LIN-106",
                "title": "Linear No Assignee",
                "assignee": None,
            },
        ]
    }
    lin_imp = LinearImporter(session=session, caller=caller, user_map=lin_user_map)
    await lin_imp.run_import(lin_data, target_project_key="UMAPL", dry_run=False)

    # Assertions on Jira assignees
    al_1 = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "UMAP-1"))
    ).scalar_one()
    asgn_1 = (
        await session.execute(select(IssueAssignee).where(IssueAssignee.issue_id == al_1.issue_id))
    ).scalar_one()
    assert asgn_1.principal_id == caller.principal_id
    assert asgn_1.free_text_assignee is None

    al_3 = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "UMAP-3"))
    ).scalar_one()
    asgn_3 = (
        await session.execute(select(IssueAssignee).where(IssueAssignee.issue_id == al_3.issue_id))
    ).scalar_one()
    assert asgn_3.principal_id is None
    assert asgn_3.free_text_assignee == "unmapped-dev"


@pytest.mark.asyncio
async def test_importers_attachments_processing(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify attachments ingestion (SVG, PDF, and PNG raster) across Jira, GitHub, and Linear."""
    import base64
    import io

    from PIL import Image

    session, caller = setup_multi_import_env

    # Minimal valid PNG
    im = Image.new("RGBA", (16, 16), color=(255, 0, 0, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Minimal valid SVG
    svg_raw = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="green"/></svg>'
    svg_b64 = base64.b64encode(svg_raw.encode("utf-8")).decode("ascii")

    # Minimal valid PDF
    pdf_bytes = b"""%PDF-1.7
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
178
%%EOF"""
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    # 1. Jira import with attachments
    jira_payload = {
        "issues": [
            {
                "key": "ATT-101",
                "fields": {
                    "summary": "Jira with attachments",
                    "parent": {"key": "ATT-102"},
                    "issuelinks": [
                        {"type": {"name": "Blocks"}, "outwardIssue": {"key": "ATT-102"}}
                    ],
                    "attachment": [
                        {"filename": "chart.svg", "content": svg_b64},
                        {"filename": "doc.pdf", "data": pdf_b64},
                        {"filename": "shot.png", "data": png_b64},
                        {"filename": "raw.png", "data": buf.getvalue()},
                        {"filename": "empty.png", "data": None},
                        "not-a-dict-skipped",
                        {"filename": ""},
                    ],
                },
            },
            {
                "key": "ATT-102",
                "fields": {
                    "summary": "Jira target issue",
                },
            },
        ]
    }
    jira_imp = JiraImporter(session=session, caller=caller)
    rep_j = await jira_imp.run_import(jira_payload, target_project_key="ATTJ", dry_run=False)
    assert rep_j.to_create == 2

    al_j = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "ATT-101"))
    ).scalar_one()
    atts_j = (
        (await session.execute(select(Attachment).where(Attachment.issue_id == al_j.issue_id)))
        .scalars()
        .all()
    )
    assert len(atts_j) == 4
    filenames = {a.original_filename for a in atts_j}
    assert filenames == {"chart.svg", "doc.pdf", "shot.png", "raw.png"}

    # 2. GitHub import with attachments
    gh_payload = {
        "issues": [
            {
                "number": 10,
                "title": "GH with attachments",
                "attachments": [
                    {"filename": "vector.svg", "data": svg_raw},
                    {"name": "manual.pdf", "content": pdf_b64},
                    {"original_filename": "photo.png", "data": png_b64},
                    {"filename": "raw_gh.png", "data": buf.getvalue()},
                    {"filename": "empty_gh.png", "data": None},
                ],
            }
        ]
    }
    gh_imp = GitHubIssuesImporter(session=session, caller=caller)
    rep_gh = await gh_imp.run_import(gh_payload, target_project_key="ATTG", dry_run=False)
    assert rep_gh.to_create == 1

    al_gh = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "GH-10"))
    ).scalar_one()
    atts_gh = (
        (await session.execute(select(Attachment).where(Attachment.issue_id == al_gh.issue_id)))
        .scalars()
        .all()
    )
    assert len(atts_gh) == 4

    # 3. Linear import with attachments
    lin_payload = {
        "issues": [
            {
                "id": "LIN-201",
                "title": "Linear with attachments",
                "attachments": [
                    {"name": "diagram.svg", "data": svg_b64},
                    {"filename": "report.pdf", "data": pdf_b64},
                    {"name": "mockup.png", "data": png_b64},
                    {"filename": "raw_lin.png", "data": buf.getvalue()},
                    {"filename": "empty_lin.png", "data": None},
                ],
            }
        ]
    }
    lin_imp = LinearImporter(session=session, caller=caller)
    rep_lin = await lin_imp.run_import(lin_payload, target_project_key="ATTL", dry_run=False)
    assert rep_lin.to_create == 1

    al_lin = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "LIN-201"))
    ).scalar_one()
    atts_lin = (
        (await session.execute(select(Attachment).where(Attachment.issue_id == al_lin.issue_id)))
        .scalars()
        .all()
    )
    assert len(atts_lin) == 4


@pytest.mark.asyncio
async def test_importers_github_and_linear_reimport_mutations(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify GitHub and Linear re-import SHA-256 mutation of issues and comments."""
    session, caller = setup_multi_import_env

    # 1. GitHub initial import
    gh_init = {
        "issues": [
            {
                "number": 55,
                "title": "GH Original Title",
                "body": "GH Original Body",
                "state": "open",
                "comments_data": [{"id": "gh-cm-1", "body": "GH Comment 1 Original"}],
            }
        ]
    }
    gh_imp = GitHubIssuesImporter(session=session, caller=caller)
    rep_gh1 = await gh_imp.run_import(gh_init, target_project_key="GHMUT", dry_run=False)
    assert rep_gh1.to_create == 1

    # Repeat identical -> unchanged
    rep_gh_same = await gh_imp.run_import(gh_init, target_project_key="GHMUT", dry_run=False)
    assert rep_gh_same.unchanged == 1

    # Mutated payload -> updates issue and comment
    gh_mod = {
        "issues": [
            {
                "number": 55,
                "title": "GH Updated Title",
                "body": "GH Updated Body",
                "state": "closed",
                "state_reason": "completed",
                "comments_data": [{"id": "gh-cm-1", "body": "GH Comment 1 Updated"}],
            }
        ]
    }
    rep_gh_mod = await gh_imp.run_import(gh_mod, target_project_key="GHMUT", dry_run=False)
    assert rep_gh_mod.to_update == 1

    al_gh = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "GH-55"))
    ).scalar_one()
    iss_gh = (await session.execute(select(Issue).where(Issue.id == al_gh.issue_id))).scalar_one()
    assert iss_gh.summary == "GH Updated Title"
    assert "GH Updated Body" in iss_gh.description_markdown

    cm_gh = (
        await session.execute(select(IssueComment).where(IssueComment.issue_id == al_gh.issue_id))
    ).scalar_one()
    assert "GH Comment 1 Updated" in cm_gh.body_markdown

    # 2. Linear initial import
    lin_init = {
        "issues": [
            {
                "id": "LIN-MUT-1",
                "title": "Linear Orig Title",
                "description": "Linear Orig Desc",
                "status": "Todo",
                "priority": "Low",
                "comments": [{"id": "lin-cm-1", "body": "Linear Comment Orig"}],
            }
        ]
    }
    lin_imp = LinearImporter(session=session, caller=caller)
    rep_lin1 = await lin_imp.run_import(lin_init, target_project_key="LINMUT", dry_run=False)
    assert rep_lin1.to_create == 1

    # Repeat identical -> unchanged
    rep_lin_same = await lin_imp.run_import(lin_init, target_project_key="LINMUT", dry_run=False)
    assert rep_lin_same.unchanged == 1

    # Mutated payload -> updates issue and comment
    lin_mod = {
        "issues": [
            {
                "id": "LIN-MUT-1",
                "title": "Linear Mutated Title",
                "description": "Linear Mutated Desc",
                "status": "Done",
                "priority": "Urgent",
                "comments": [{"id": "lin-cm-1", "body": "Linear Comment Mutated"}],
            }
        ]
    }
    rep_lin_mod = await lin_imp.run_import(lin_mod, target_project_key="LINMUT", dry_run=False)
    assert rep_lin_mod.to_update == 1

    al_lin = (
        await session.execute(select(IssueKeyAlias).where(IssueKeyAlias.legacy_key == "LIN-MUT-1"))
    ).scalar_one()
    iss_lin = (await session.execute(select(Issue).where(Issue.id == al_lin.issue_id))).scalar_one()
    assert iss_lin.summary == "Linear Mutated Title"
    assert "Linear Mutated Desc" in iss_lin.description_markdown

    cm_lin = (
        await session.execute(select(IssueComment).where(IssueComment.issue_id == al_lin.issue_id))
    ).scalar_one()
    assert "Linear Comment Mutated" in cm_lin.body_markdown


@pytest.mark.asyncio
async def test_importers_edge_coverage_branches(
    setup_multi_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify edge branch coverage across Jira, GitHub, and Linear importers."""
    session, caller = setup_multi_import_env

    # 1. Jira edges
    jira_edge_payload = {
        "issues": [
            "invalid_non_dict_issue",
            {"key": ""},
            {
                "key": "EDGE-1",
                "fields": {
                    "summary": "Edge Jira 1",
                    "description": {"type": "doc", "version": 1, "content": []},
                    "parent": {"key": "EDGE-2"},
                    "issuelinks": [
                        "not_a_dict_link",
                        {"type": {"name": "blocks"}, "inwardIssue": {"key": "EDGE-2"}},
                    ],
                    "comment": [
                        "not_a_dict_comment",
                        {"id": "cm-empty", "body": "   "},
                        {"id": "cm-valid", "body": "Valid Jira Comment", "author": "unmapped_str"},
                    ],
                    "attachment": [
                        "not_a_dict_att",
                        {"filename": ""},
                        {
                            "filename": "invalid_b64.svg",
                            "data": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>',
                        },
                    ],
                },
            },
            {
                "key": "EDGE-2",
                "fields": {
                    "summary": "Edge Jira 2",
                    "assignee": "string_user_name",
                },
            },
        ]
    }
    jira_imp = JiraImporter(session=session, caller=caller)
    rep_j = await jira_imp.run_import(jira_edge_payload, target_project_key="EDGJ", dry_run=False)
    assert rep_j.to_create == 2

    # 2. GitHub edges (pre-existing label & milestone, sub_issues, relations, comment branches)
    gh_edge_1 = {
        "issues": [
            {
                "number": 100,
                "title": "GH Edge 1",
                "labels": ["shared-label"],
                "milestone": "Sprint 1",
                "comments_data": [{"id": "gh-cm-stable", "body": "Stable Comment"}],
            }
        ]
    }
    gh_user_map = {"gh-missing-in-lookup": "nobody_here@nowhere.com"}
    gh_imp = GitHubIssuesImporter(session=session, caller=caller, user_map=gh_user_map)
    await gh_imp.run_import(gh_edge_1, target_project_key="EDGG", dry_run=False)

    # Second pass hits existing label and existing cycle in database
    gh_edge_2 = {
        "issues": [
            "not_a_dict",
            {"number": None},
            {
                "number": 100,
                "title": "GH Edge 1",
                "labels": ["shared-label"],
                "milestone": "Sprint 1",
                "comments_data": [{"id": "gh-cm-stable", "body": "Stable Comment"}],
            },
            {
                "number": 101,
                "title": "GH Edge 2",
                "updated_at": "2026-01-01T12:00:00Z",
                "assignees": [{"login": "gh-missing-in-lookup"}, {}, ""],
                "labels": [{"name": "shared-label", "color": "ff0000"}, {"name": ""}],
                "milestone": {"title": "Sprint 1"},
                "parent": 100,
                "sub_issues": [102],
                "blocks": [102, 102],
                "comments_data": [
                    "bad_comment",
                    {"id": "gh-cm-empty", "body": ""},
                    {"id": "gh-cm-ok", "body": "GH comment", "user": "ghost"},
                ],
                "attachments": [
                    "not_dict",
                    {"filename": ""},
                    {
                        "filename": "gh_fallback.svg",
                        "data": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>',
                    },
                ],
            },
            {
                "number": 102,
                "title": "GH Edge 3",
                "blocked_by": [101],
            },
        ]
    }
    rep_gh2 = await gh_imp.run_import(gh_edge_2, target_project_key="EDGG", dry_run=False)
    assert rep_gh2.unchanged == 1
    assert rep_gh2.to_create == 2

    # Third pass on GH-101 updates issue title but keeps same comment to test unchanged comment branch
    gh_edge_3 = {
        "issues": [
            {
                "number": 101,
                "title": "GH Edge 2 Mutated",
                "comments_data": [
                    {"id": "gh-cm-ok", "body": "GH comment", "user": "ghost"},
                ],
            }
        ]
    }
    rep_gh3 = await gh_imp.run_import(gh_edge_3, target_project_key="EDGG", dry_run=False)
    assert rep_gh3.to_update == 1

    # 3. Linear edges (relations with relatedIssueId, invalid JSON fallback, comment branches)
    lin_imp = LinearImporter(session=session, caller=caller)
    rep_lin_empty = await lin_imp.run_import(
        "{invalid_json_without_csv", target_project_key="EDGL", dry_run=False
    )
    assert len(rep_lin_empty.warnings) > 0

    lin_edge_payload = {
        "issues": [
            "not_a_dict",
            {"id": ""},
            {
                "id": "LIN-EDG-1",
                "title": "Linear Edge 1",
                "updatedAt": "2026-01-01T12:00:00Z",
                "assignee": "11111111-1111-1111-1111-111111111111",
                "relations": [
                    "not_a_dict_rel",
                    {"type": "blocks", "relatedIssueId": "LIN-EDG-2"},
                    {"type": "blocks", "relatedIssueId": "LIN-EDG-2"},
                    {"type": "blocked_by", "relatedIssue": {"id": "LIN-EDG-2"}},
                ],
                "comments": [
                    "not_a_dict",
                    {"id": "lin-empty-cm", "body": "   "},
                    {
                        "id": "lin-ok-cm",
                        "body": "Valid Linear Comment",
                        "user": "unknown_linear_user",
                    },
                ],
                "attachments": [
                    "not_dict",
                    {"name": ""},
                    {
                        "name": "lin_bad_b64.svg",
                        "data": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>',
                    },
                ],
            },
            {
                "id": "LIN-EDG-2",
                "title": "Linear Edge 2",
            },
        ]
    }
    rep_lin = await lin_imp.run_import(lin_edge_payload, target_project_key="EDGL", dry_run=False)
    assert rep_lin.to_create == 2
