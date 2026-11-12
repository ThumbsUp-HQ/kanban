"""Projects, workflow_states, project_priorities, and project_labels.

Revision ID: p1_04_projects
Revises: p1_03_principals
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_04_projects"
down_revision: str | None = "p1_03_principals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply projects, workflow_states, project_priorities, and project_labels."""
    execute_sql_file("p1_04_projects.up.sql")


def downgrade() -> None:
    """Revert projects, workflow_states, project_priorities, and project_labels."""
    execute_sql_file("p1_04_projects.down.sql")
