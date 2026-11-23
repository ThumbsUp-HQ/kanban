# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security tests for Secret Push Protection and Taint Scanning on Importers and Custom Fields (KAN-336 / KB-REDTEAM-05)."""
# ruff: noqa: E501, TC002

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Issue,
    IssueComment,
    IssueKeyAlias,
    Project,
)
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldCreateRequest,
    CustomFieldTestExecuteRequest,
)
from kanban.custom_fields.executor import CustomFieldExecutor
from kanban.custom_fields.service import CustomFieldDefinitionService
from kanban.importer.github_importer import GitHubIssuesImporter
from kanban.importer.jira_importer import JiraImporter
from kanban.importer.linear_importer import LinearImporter

TEST_SECRET_AWS = "AKIAIOSFODNN7EXAMPLE"
EXPECTED_SECRET_CODES = ("SECRET_DETECTED_IN_PAYLOAD", "SECRET_PUSH_PROTECTED")


@pytest.fixture
async def setup_import_env(
    db_session: AsyncSession,
) -> tuple[AsyncSession, PrincipalContext]:
    """Bootstrap workspace, admin principal, and RLS context for security testing."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)

    await db_session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"p_id": admin_id, "ws_id": ws_id},
    )

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
        is_server_admin=True,
        aal_level=2,
    )
    return db_session, caller


@pytest.mark.asyncio
async def test_jira_importer_blocks_secret_in_summary(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Jira import blocks payloads containing high-confidence secrets in summary."""
    session, caller = setup_import_env
    importer = JiraImporter(session=session, caller=caller)

    jira_export = {
        "issues": [
            {
                "key": "JIRA-SEC-1",
                "fields": {
                    "summary": f"Leaked AWS Key {TEST_SECRET_AWS}",
                    "description": "Safe description",
                    "status": {"name": "Backlog"},
                    "priority": {"name": "Medium"},
                },
            }
        ]
    }

    with pytest.raises(ProblemException) as exc_info:
        await importer.run_import(jira_export, target_project_key="JIRA", dry_run=False)

    assert exc_info.value.code in EXPECTED_SECRET_CODES
    assert exc_info.value.status == 422


@pytest.mark.asyncio
async def test_jira_importer_blocks_secret_in_description(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Jira import blocks payloads containing high-confidence secrets in description."""
    session, caller = setup_import_env
    importer = JiraImporter(session=session, caller=caller)

    jira_export = {
        "issues": [
            {
                "key": "JIRA-SEC-2",
                "fields": {
                    "summary": "Safe summary",
                    "description": f"Leaked AWS key in desc: {TEST_SECRET_AWS}",
                    "status": {"name": "Backlog"},
                    "priority": {"name": "Medium"},
                },
            }
        ]
    }

    with pytest.raises(ProblemException) as exc_info:
        await importer.run_import(jira_export, target_project_key="JIRA", dry_run=False)

    assert exc_info.value.code in EXPECTED_SECRET_CODES
    assert exc_info.value.status == 422


@pytest.mark.asyncio
async def test_jira_importer_blocks_secret_in_comments(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Jira import blocks payloads containing high-confidence secrets in comments."""
    session, caller = setup_import_env
    importer = JiraImporter(session=session, caller=caller)

    jira_export = {
        "issues": [
            {
                "key": "JIRA-SEC-3",
                "fields": {
                    "summary": "Safe summary",
                    "description": "Safe description",
                    "status": {"name": "Backlog"},
                    "priority": {"name": "Medium"},
                    "comment": {
                        "comments": [
                            {
                                "id": "c-sec-1",
                                "body": f"Here is the secret token: {TEST_SECRET_AWS}",
                            }
                        ]
                    },
                },
            }
        ]
    }

    with pytest.raises(ProblemException) as exc_info:
        await importer.run_import(jira_export, target_project_key="JIRA", dry_run=False)

    assert exc_info.value.code in EXPECTED_SECRET_CODES
    assert exc_info.value.status == 422


@pytest.mark.asyncio
async def test_github_importer_blocks_secret_in_issue_and_comment(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify GitHub import blocks secrets in title, body, and comments."""
    session, caller = setup_import_env
    importer = GitHubIssuesImporter(session=session, caller=caller)

    gh_export_bad_title = [
        {
            "number": 101,
            "title": f"Secret in Title {TEST_SECRET_AWS}",
            "body": "Normal body",
            "state": "open",
        }
    ]

    with pytest.raises(ProblemException) as exc_info:
        await importer.run_import(gh_export_bad_title, target_project_key="GH", dry_run=False)
    assert exc_info.value.code in EXPECTED_SECRET_CODES

    gh_export_bad_comment = [
        {
            "number": 102,
            "title": "Clean title",
            "body": "Normal body",
            "state": "open",
            "comments": [
                {
                    "id": 5551,
                    "body": f"Leaked credentials: {TEST_SECRET_AWS}",
                }
            ],
        }
    ]

    with pytest.raises(ProblemException) as exc_info2:
        await importer.run_import(gh_export_bad_comment, target_project_key="GH", dry_run=False)
    assert exc_info2.value.code in EXPECTED_SECRET_CODES


@pytest.mark.asyncio
async def test_linear_importer_blocks_secret_in_issue_and_comment(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify Linear import blocks secrets in title, description, and comments."""
    session, caller = setup_import_env
    importer = LinearImporter(session=session, caller=caller)

    linear_export_bad_desc = [
        {
            "id": "LIN-201",
            "title": "Clean Linear Title",
            "description": f"Found key {TEST_SECRET_AWS}",
            "state": {"name": "Todo"},
        }
    ]

    with pytest.raises(ProblemException) as exc_info:
        await importer.run_import(linear_export_bad_desc, target_project_key="LIN", dry_run=False)
    assert exc_info.value.code in EXPECTED_SECRET_CODES

    linear_export_bad_comment = [
        {
            "id": "LIN-202",
            "title": "Clean Linear Title 2",
            "description": "Safe description",
            "state": {"name": "Todo"},
            "comments": [
                {
                    "id": "l-comm-1",
                    "body": f"Secret comment: {TEST_SECRET_AWS}",
                }
            ],
        }
    ]

    with pytest.raises(ProblemException) as exc_info2:
        await importer.run_import(
            linear_export_bad_comment, target_project_key="LIN", dry_run=False
        )
    assert exc_info2.value.code in EXPECTED_SECRET_CODES


@pytest.mark.asyncio
async def test_importer_provenance_tier_and_taint(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify imported issues and comments are marked with provenance_tier='imported' and is_untrusted_content=True."""
    session, caller = setup_import_env
    importer = JiraImporter(session=session, caller=caller)

    jira_export = {
        "issues": [
            {
                "key": "JIRA-PROV-1",
                "fields": {
                    "summary": "Untainted summary",
                    "description": "Untainted description",
                    "status": {"name": "Backlog"},
                    "priority": {"name": "Low"},
                    "comment": {
                        "comments": [
                            {
                                "id": "c-prov-1",
                                "body": "Untainted comment body",
                            }
                        ]
                    },
                },
            }
        ]
    }

    report = await importer.run_import(jira_export, target_project_key="JIRA", dry_run=False)
    assert report.to_create == 1

    alias_res = await session.execute(
        select(IssueKeyAlias).where(
            IssueKeyAlias.workspace_id == caller.workspace_id,
            IssueKeyAlias.legacy_key == "JIRA-PROV-1",
        )
    )
    alias = alias_res.scalar_one()

    issue_res = await session.execute(select(Issue).where(Issue.id == alias.issue_id))
    imported_issue = issue_res.scalar_one()

    assert imported_issue.provenance_tier == "imported"
    assert imported_issue.is_untrusted_content is True

    comment_res = await session.execute(
        select(IssueComment).where(IssueComment.issue_id == alias.issue_id)
    )
    imported_comment = comment_res.scalar_one()

    assert imported_comment.provenance_tier == "imported"
    assert imported_comment.is_untrusted_content is True


@pytest.mark.asyncio
async def test_custom_field_test_execute_blocks_secret_source(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify CustomFieldExecutor blocks secret material returned or evaluated by custom fields."""
    session, caller = setup_import_env

    # 1. First import a valid issue to execute against
    importer = JiraImporter(session=session, caller=caller)
    await importer.run_import(
        {
            "issues": [
                {
                    "key": "JIRA-CF-1",
                    "fields": {
                        "summary": "Target Issue For Custom Field",
                        "description": "Testing custom field execution",
                        "status": {"name": "Backlog"},
                        "priority": {"name": "Medium"},
                    },
                }
            ]
        },
        target_project_key="JIRA",
        dry_run=False,
    )

    alias_res = await session.execute(
        select(IssueKeyAlias).where(
            IssueKeyAlias.workspace_id == caller.workspace_id,
            IssueKeyAlias.legacy_key == "JIRA-CF-1",
        )
    )
    alias = alias_res.scalar_one()

    issue_res = await session.execute(select(Issue).where(Issue.id == alias.issue_id))
    target_issue = issue_res.scalar_one()

    proj_res = await session.execute(select(Project).where(Project.id == target_issue.project_id))
    target_project = proj_res.scalar_one()

    # Construct request where returned scalar contains an AWS secret token
    executor = CustomFieldExecutor(session)
    request_body = CustomFieldTestExecuteRequest(
        issue_key=f"{target_project.identifier}-{target_issue.sequence_id}",
        tier="wasm",
        output_format="text",
        output_format_metadata={"max_length": 100},
        script_source=f'scalar: "{TEST_SECRET_AWS}"',
    )

    with pytest.raises(ProblemException) as exc_info:
        await executor.test_execute(
            session=session,
            caller=caller,
            project=target_project,
            body=request_body,
        )

    assert exc_info.value.code in EXPECTED_SECRET_CODES
    assert exc_info.value.status == 422


@pytest.mark.asyncio
async def test_custom_field_definition_blocks_secret_in_name_and_source(
    setup_import_env: tuple[AsyncSession, PrincipalContext],
) -> None:
    """Verify CustomFieldDefinitionService blocks custom field definitions containing secrets."""
    session, caller = setup_import_env

    # Bootstrap target project
    importer = JiraImporter(session=session, caller=caller)
    await importer.run_import(
        {
            "issues": [
                {
                    "key": "JIRA-DEF-1",
                    "fields": {
                        "summary": "Setup Project Target",
                        "status": {"name": "Backlog"},
                    },
                }
            ]
        },
        target_project_key="JIRA",
        dry_run=False,
    )

    proj_res = await session.execute(
        select(Project).where(
            Project.workspace_id == caller.workspace_id,
            Project.identifier == "JIRA",
        )
    )
    proj = proj_res.scalar_one()

    # Try creating custom field with secret in name
    bad_name_req = CustomFieldCreateRequest(
        slug="field-secret-name",
        name=f"Field with Secret {TEST_SECRET_AWS}",
        tier="wasm",
        output_format="text",
        output_format_metadata={"max_length": 50},
        script_source="scalar: 'hello'",
    )

    with pytest.raises(ProblemException) as exc_info:
        await CustomFieldDefinitionService.create_definition(
            session=session,
            caller=caller,
            project_ref=proj.identifier,
            payload=bad_name_req,
        )
    assert exc_info.value.code in EXPECTED_SECRET_CODES

    # Try creating custom field with secret in script_source
    bad_source_req = CustomFieldCreateRequest(
        slug="field-secret-source",
        name="Field with Secret Source",
        tier="wasm",
        output_format="text",
        output_format_metadata={"max_length": 50},
        script_source=f"export default function() {{ return '{TEST_SECRET_AWS}'; }}",
    )

    with pytest.raises(ProblemException) as exc_info2:
        await CustomFieldDefinitionService.create_definition(
            session=session,
            caller=caller,
            project_ref=proj.identifier,
            payload=bad_source_req,
        )
    assert exc_info2.value.code in EXPECTED_SECRET_CODES
