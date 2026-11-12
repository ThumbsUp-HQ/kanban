DROP TRIGGER IF EXISTS issues_validate_biu_trg ON issues;
DROP FUNCTION IF EXISTS issues_validate_biu();
DROP FUNCTION IF EXISTS allocate_issue_sequence(uuid);
DROP TABLE IF EXISTS issues;
DROP FUNCTION IF EXISTS build_markdown_tsvector(text);
