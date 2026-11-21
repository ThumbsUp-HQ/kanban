# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for multi-source importers: Jira, GitHub, and Linear (KB-P6-03)."""
# ruff: noqa: PLC0415, TC002, PLR0915, E501

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Issue,
    IssueComment,
    IssueKeyAlias,
    LinkKind,
    ObjectLink,
    Project,
)
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.importer.github_importer import GitHubIssuesImporter
from kanban.importer.jira_importer import JiraImporter
from kanban.importer.linear_importer import LinearImporter


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
