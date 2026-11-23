-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.
-- Phase 6 / Jinja2 Reports: report_templates table, 3-tier governance on workspace_settings, and built-in templates (KAN-317)

-- 1. Alter workspace_settings for 3-tier governance
ALTER TABLE workspace_settings
    ADD COLUMN IF NOT EXISTS report_export_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS report_export_allowed_roles JSONB NOT NULL DEFAULT '["ADMIN", "MEMBER"]'::jsonb;

-- 2. Create report_templates table
CREATE TABLE IF NOT EXISTS report_templates (
    id                     UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id           UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id             UUID REFERENCES projects(id) ON DELETE CASCADE,
    slug                   TEXT NOT NULL,
    name                   TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    is_builtin             BOOLEAN NOT NULL DEFAULT FALSE,
    template_markdown      TEXT NOT NULL,
    parameters_schema_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    csv_columns_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_formats        JSONB NOT NULL DEFAULT '["pdf", "xlsx", "csv", "docx", "odt", "html", "md"]'::jsonb,
    created_by_user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT report_templates_slug_check CHECK (char_length(slug) BETWEEN 1 AND 80 AND slug ~ '^[a-z0-9][a-z0-9_-]*$'),
    CONSTRAINT report_templates_name_check CHECK (char_length(name) BETWEEN 1 AND 120),
    CONSTRAINT report_templates_markdown_len_check CHECK (octet_length(template_markdown) <= 131072)
);

CREATE INDEX IF NOT EXISTS idx_report_templates_ws_id ON report_templates (workspace_id);
CREATE INDEX IF NOT EXISTS idx_report_templates_proj_id ON report_templates (project_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_report_templates_ws_proj_slug ON report_templates (
    workspace_id,
    COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid),
    slug
);

-- 3. Row-Level Security
ALTER TABLE report_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_templates FORCE ROW LEVEL SECURITY;

CREATE POLICY report_templates_select_rls ON report_templates
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
        AND cardinality(app_effective_principal_set()) > 0
        AND (
            project_id IS NULL
            OR app_has_object_capability(project_id, 1)
        )
    );

CREATE POLICY report_templates_insert_rls ON report_templates
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND (
            app_principal_has_role(workspace_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
            OR (
                project_id IS NOT NULL
                AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            )
        )
    );

CREATE POLICY report_templates_update_rls ON report_templates
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
        AND NOT is_builtin
        AND (
            app_principal_has_role(workspace_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
            OR (
                project_id IS NOT NULL
                AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            )
        )
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
        AND NOT is_builtin
        AND (
            app_principal_has_role(workspace_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
            OR (
                project_id IS NOT NULL
                AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            )
        )
    );

CREATE POLICY report_templates_delete_rls ON report_templates
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
        AND NOT is_builtin
        AND (
            app_principal_has_role(workspace_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
            OR (
                project_id IS NOT NULL
                AND app_principal_has_role(project_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])
            )
        )
    );

-- 4. Set updated_at trigger
CREATE TRIGGER report_templates_set_updated_at
    BEFORE UPDATE ON report_templates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 5. Seed function for built-in report templates per workspace
CREATE OR REPLACE FUNCTION seed_builtin_report_templates(p_workspace_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    -- Security Assessment Report
    INSERT INTO report_templates (
        workspace_id, project_id, slug, name, description, is_builtin,
        template_markdown, parameters_schema_json, csv_columns_json, allowed_formats
    ) VALUES (
        p_workspace_id,
        NULL,
        'security-assessment-report',
        'Security Assessment Report',
        'Comprehensive security audit report with mission scope, boilerplate terms, table of contents, executive summary, issue summary table, details per finding, and appendix.',
        TRUE,
        '{{ mission }}
{{ boilerplate }}
{{ toc }}

# Executive Summary
{{ executive_summary }}

{{ issues_table }}

# Details
{% for issue in issues %}
## {{ issue.created_date }} - {{ issue.summary }} [{{ issue.priority | upper }}]
**Key:** {{ issue.key }} | **State:** {{ issue.state }} | **Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endfor %}

# Appendix
{{ appendix }}',
        '[{"name": "mission", "label": "Assessment Mission & Scope", "type": "textarea", "default": "Target Environment Security Assessment and Penetration Testing Review.", "required": true}, {"name": "boilerplate", "label": "Boilerplate & Legal Notice", "type": "textarea", "default": "Confidential Security Audit Document. Unauthorized reproduction or dissemination is strictly prohibited.", "required": true}, {"name": "executive_summary", "label": "Executive Summary", "type": "textarea", "default": "This assessment report provides an audit of discovered issues and security posture across the target scope.", "required": true}, {"name": "appendix", "label": "Appendix & Methodology", "type": "textarea", "default": "All findings were assessed in accordance with OWASP Top 10 and CWE guidelines.", "required": false}]'::jsonb,
        '[{"header": "Key", "expr": "issue.key"}, {"header": "Summary", "expr": "issue.summary"}, {"header": "State", "expr": "issue.state"}, {"header": "Priority", "expr": "issue.priority"}, {"header": "Assignees", "expr": "issue.assignees | join(\", \")"}, {"header": "Created Date", "expr": "issue.created_date"}]'::jsonb,
        '["pdf", "xlsx", "csv", "docx", "odt", "html", "md"]'::jsonb
    )
    ON CONFLICT DO NOTHING;

    -- Sprint & Release Notes Report
    INSERT INTO report_templates (
        workspace_id, project_id, slug, name, description, is_builtin,
        template_markdown, parameters_schema_json, csv_columns_json, allowed_formats
    ) VALUES (
        p_workspace_id,
        NULL,
        'sprint-release-notes',
        'Sprint & Release Notes Report',
        'Sprint and release summary grouping completed features, fixes, and active work with contributor metrics.',
        TRUE,
        '# {{ release_title | default("Sprint & Release Notes") }}
{{ release_notes_summary }}

{{ toc }}

{{ issues_table }}

# Features & Fixes by State
{% for issue in issues %}
### [{{ issue.state }}] {{ issue.key }}: {{ issue.summary }}
**Priority:** {{ issue.priority }} | **Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endfor %}',
        '[{"name": "release_title", "label": "Release Title", "type": "text", "default": "Sprint & Release Notes", "required": true}, {"name": "release_notes_summary", "label": "Release Summary", "type": "textarea", "default": "Summary of delivered features, fixes, and improvements in this release cycle.", "required": true}]'::jsonb,
        '[{"header": "Key", "expr": "issue.key"}, {"header": "Summary", "expr": "issue.summary"}, {"header": "State", "expr": "issue.state"}, {"header": "Priority", "expr": "issue.priority"}, {"header": "Assignees", "expr": "issue.assignees | join(\", \")"}]'::jsonb,
        '["pdf", "xlsx", "csv", "docx", "odt", "html", "md"]'::jsonb
    )
    ON CONFLICT DO NOTHING;

    -- Executive Status & Risk Report
    INSERT INTO report_templates (
        workspace_id, project_id, slug, name, description, is_builtin,
        template_markdown, parameters_schema_json, csv_columns_json, allowed_formats
    ) VALUES (
        p_workspace_id,
        NULL,
        'executive-status-risk',
        'Executive Status & Risk Report',
        'High-level executive briefing with priority distribution, blockers, timeline risk analysis, and appendix.',
        TRUE,
        '# {{ executive_title | default("Executive Status & Risk Report") }}

# Executive Briefing
{{ briefing }}

{{ toc }}

# Priority & Risk Breakdown
Total tracked issues: {{ stats.total_issues }} (Urgent: {{ stats.urgent_count }}, High: {{ stats.high_count }}, Medium: {{ stats.medium_count }}, Low: {{ stats.low_count }})

{{ issues_table }}

# Critical & High Attention Items
{% for issue in issues %}
{% if issue.priority in ["urgent", "high"] %}
### ⚠️ {{ issue.key }} - {{ issue.summary }} [{{ issue.priority | upper }}]
**State:** {{ issue.state }} | **Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endif %}
{% endfor %}

# Risk Mitigation Strategy
{{ mitigation_notes }}',
        '[{"name": "executive_title", "label": "Report Title", "type": "text", "default": "Executive Status & Risk Report", "required": true}, {"name": "briefing", "label": "Executive Briefing", "type": "textarea", "default": "Executive briefing on system operational health and project trajectory.", "required": true}, {"name": "mitigation_notes", "label": "Risk Mitigation Strategy", "type": "textarea", "default": "Continuous monitoring and triage of critical blockers to ensure project delivery.", "required": false}]'::jsonb,
        '[{"header": "Key", "expr": "issue.key"}, {"header": "Summary", "expr": "issue.summary"}, {"header": "Priority", "expr": "issue.priority"}, {"header": "State", "expr": "issue.state"}]'::jsonb,
        '["pdf", "xlsx", "csv", "docx", "odt", "html", "md"]'::jsonb
    )
    ON CONFLICT DO NOTHING;
END;
$$;

-- 6. Trigger on workspace creation
CREATE OR REPLACE FUNCTION trigger_seed_workspace_report_templates()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM seed_builtin_report_templates(NEW.id);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_seed_workspace_report_templates ON workspaces;
CREATE TRIGGER trg_seed_workspace_report_templates
    AFTER INSERT ON workspaces
    FOR EACH ROW
    EXECUTE FUNCTION trigger_seed_workspace_report_templates();

-- 7. Backfill existing workspaces
DO $$
DECLARE
    ws RECORD;
BEGIN
    FOR ws IN SELECT id FROM workspaces LOOP
        PERFORM seed_builtin_report_templates(ws.id);
    END LOOP;
END;
$$;

-- 8. Ownership and permissions
ALTER TABLE report_templates OWNER TO kanban_migrator;
ALTER FUNCTION seed_builtin_report_templates(UUID) OWNER TO kanban_migrator;
ALTER FUNCTION trigger_seed_workspace_report_templates() OWNER TO kanban_migrator;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE report_templates TO kanban_app;
GRANT SELECT ON TABLE report_templates TO app_rls_reader;
GRANT EXECUTE ON FUNCTION seed_builtin_report_templates(UUID) TO kanban_app;
