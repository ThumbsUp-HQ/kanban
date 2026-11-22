# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Server-side filter predicate compiler for saved views, search, and queries (S6.4, S3.4, KAN-78).

Translates bounded DSL filter expressions into parameterized SQLAlchemy WHERE clauses.
Complexity bounds:
- MAX_QUERY_LENGTH = 512 characters
- MAX_CLAUSES = 32 clauses
- MAX_TOKENS = 32 tokens
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import ColumnElement, exists, func, literal, or_, select

from database.models import (
    Cycle,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueModule,
    Module,
    Principal,
    Project,
    ProjectLabel,
    ProjectPriority,
    User,
    WorkflowState,
)
from kanban.api.problems import ProblemException

__all__ = [
    "MAX_CLAUSES",
    "MAX_QUERY_LENGTH",
    "MAX_TOKENS",
    "ParsedComparisonClause",
    "ParsedToken",
    "compile_predicate_string",
    "parse_comparison_clause",
    "sanitize_query_string",
    "split_query_clauses",
    "tokenize_predicate_string",
]

MAX_QUERY_LENGTH: Final[int] = 512
MAX_CLAUSES: Final[int] = 32
MAX_TOKENS: Final[int] = 32

SURROGATE_MIN: Final[int] = 0xD800
SURROGATE_MAX: Final[int] = 0xDFFF
ASCII_CTRL_MAX: Final[int] = 32
ASCII_DEL: Final[int] = 127
MIN_STRIP_LEN: Final[int] = 2

_UUID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ISSUE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})-(\d+)$")
_IDENT_RE: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_]+$")


@dataclass(frozen=True, slots=True)
class ParsedToken:
    """Token extracted from a predicate query string."""

    field: str | None
    value: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class ParsedComparisonClause:
    """Structured comparison clause with explicit operator."""

    field: str
    operator: str  # '=' or '!='
    value: str
    negated: bool = False


def sanitize_query_string(raw_query: str, max_length: int = MAX_QUERY_LENGTH) -> str:
    """Sanitize and validate DSL query string input.

    Strips ASCII control characters and lone UTF-16 surrogates. Enforces max length bound.
    """
    if not raw_query or not isinstance(raw_query, str):
        return ""

    if len(raw_query) > max_length:
        raise ProblemException(
            code="FILTER_TOO_COMPLEX",
            status=422,
            title="Filter Too Complex",
            detail=(
                f"Filter query length ({len(raw_query)}) exceeds maximum of {max_length} characters"
            ),
        )

    cleaned_chars: list[str] = []
    for ch in raw_query:
        code = ord(ch)
        if SURROGATE_MIN <= code <= SURROGATE_MAX:
            continue
        if 0 <= code < ASCII_CTRL_MAX and ch not in ("\t", "\n", "\r"):
            cleaned_chars.append(" ")
        elif code == ASCII_DEL:
            continue
        else:
            cleaned_chars.append(ch)

    return "".join(cleaned_chars).strip()


def _strip_quotes(s: str) -> str:
    t = s.strip()
    if len(t) >= MIN_STRIP_LEN:
        first, last = t[0], t[-1]
        if (first == '"' and last == '"') or (first == "'" and last == "'"):
            return t[1:-1]
    return t


def split_query_clauses(  # noqa: C901
    query: str, max_clauses: int = MAX_CLAUSES
) -> list[str]:
    """Split query on top-level AND outside quotes, capped at max_clauses.

    Raises ProblemException if clauses count exceeds max_clauses.
    """
    clauses: list[str] = []
    in_quote: str | None = None
    start = 0
    length = len(query)
    i = 0

    def is_ws(c: str) -> bool:
        return c in (" ", "\t", "\n", "\r")

    while i < length:
        ch = query[i]

        if in_quote is not None:
            if ch == in_quote:
                in_quote = None
            i += 1
            continue

        if ch in ('"', "'"):
            in_quote = ch
            i += 1
            continue

        # Match top-level whitespace + AND + whitespace
        if (
            is_ws(ch)
            and i + 4 < length
            and query[i + 1 : i + 4].upper() == "AND"
            and is_ws(query[i + 4])
        ):
            piece = query[start:i].strip()
            if piece:
                clauses.append(piece)
                if len(clauses) > max_clauses:
                    raise ProblemException(
                        code="FILTER_TOO_COMPLEX",
                        status=422,
                        title="Filter Too Complex",
                        detail=f"Filter clauses count exceeds maximum of {max_clauses}",
                    )
            i += 5
            while i < length and is_ws(query[i]):
                i += 1
            start = i
            continue

        i += 1

    tail = query[start:].strip()
    if tail:
        clauses.append(tail)
        if len(clauses) > max_clauses:
            raise ProblemException(
                code="FILTER_TOO_COMPLEX",
                status=422,
                title="Filter Too Complex",
                detail=f"Filter clauses count exceeds maximum of {max_clauses}",
            )

    return clauses


def parse_comparison_clause(  # noqa: C901
    raw_clause: str,
) -> ParsedComparisonClause | None:
    """Parse a single clause into comparison operator if present."""
    clause = raw_clause.strip()
    negated = False
    if clause.upper().startswith("NOT "):
        negated = True
        clause = clause[4:].strip()

    in_quote: str | None = None
    neq_idx = -1
    eq_idx = -1
    length = len(clause)
    i = 0
    while i < length:
        ch = clause[i]
        if in_quote is not None:
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_quote = ch
            i += 1
            continue
        if ch == "!" and i + 1 < length and clause[i + 1] == "=":
            if neq_idx == -1:
                neq_idx = i
            i += 2
            continue
        if ch == "=":
            if eq_idx == -1:
                eq_idx = i
            i += 1
            continue
        i += 1

    if neq_idx == -1 and eq_idx == -1:
        return None

    op = "="
    split_idx = eq_idx
    if neq_idx != -1 and (eq_idx == -1 or neq_idx < eq_idx):
        op = "!="
        split_idx = neq_idx

    raw_field = clause[:split_idx].strip()
    if not raw_field or not _IDENT_RE.match(raw_field):
        return None

    raw_val = _strip_quotes(clause[split_idx + len(op) :].strip())
    return ParsedComparisonClause(
        field=raw_field.lower(),
        operator=op,
        value=raw_val,
        negated=negated,
    )


def tokenize_predicate_string(  # noqa: C901, PLR0912, PLR0915
    token_string: str, max_tokens: int = MAX_TOKENS
) -> list[ParsedToken]:
    """Tokenize a predicate string into field:value, negated tokens, and free-text words."""
    tokens: list[ParsedToken] = []
    length = len(token_string)
    i = 0
    pending_not = False

    def is_ws(c: str) -> bool:
        return c in (" ", "\t", "\n", "\r")

    def is_field_char(c: str) -> bool:
        return c.isalnum() or c == "_"

    while i < length:
        # Skip leading whitespace
        while i < length and is_ws(token_string[i]):
            i += 1
        if i >= length:
            break

        negated = False
        if token_string[i] in ("-", "!"):
            negated = True
            i += 1
            while i < length and is_ws(token_string[i]):
                i += 1
            if i >= length:
                break
        elif pending_not:
            negated = True
            pending_not = False

        # Quoted free-text token
        if i < length and token_string[i] in ('"', "'"):
            q_char = token_string[i]
            i += 1
            start = i
            while i < length and token_string[i] != q_char:
                i += 1
            val = token_string[start:i]
            if i < length and token_string[i] == q_char:
                i += 1
            tokens.append(ParsedToken(field=None, value=val, negated=negated))
            if len(tokens) > max_tokens:
                raise ProblemException(
                    code="FILTER_TOO_COMPLEX",
                    status=422,
                    title="Filter Too Complex",
                    detail=f"Filter tokens count exceeds maximum of {max_tokens}",
                )
            continue

        # Scan identifier or word up to whitespace or colon
        start = i
        while i < length and not is_ws(token_string[i]) and token_string[i] not in (":", '"', "'"):
            i += 1
        word = token_string[start:i]

        # Check if this is a field: prefix
        if word and i < length and token_string[i] == ":" and all(is_field_char(c) for c in word):
            i += 1  # skip ':'
            val = ""
            if i < length and token_string[i] in ('"', "'"):
                q_char = token_string[i]
                i += 1
                v_start = i
                while i < length and token_string[i] != q_char:
                    i += 1
                val = token_string[v_start:i]
                if i < length and token_string[i] == q_char:
                    i += 1
            else:
                v_start = i
                while i < length and not is_ws(token_string[i]):
                    i += 1
                val = _strip_quotes(token_string[v_start:i])

            tokens.append(ParsedToken(field=word.lower(), value=val, negated=negated))
            if len(tokens) > max_tokens:
                raise ProblemException(
                    code="FILTER_TOO_COMPLEX",
                    status=422,
                    title="Filter Too Complex",
                    detail=f"Filter tokens count exceeds maximum of {max_tokens}",
                )
            continue

        # Remainder of word if any
        while i < length and not is_ws(token_string[i]):
            i += 1
        full_word = _strip_quotes(token_string[start:i])
        if not negated and full_word.upper() == "NOT":
            pending_not = True
            continue
        if full_word:
            tokens.append(ParsedToken(field=None, value=full_word, negated=negated))
            if len(tokens) > max_tokens:
                raise ProblemException(
                    code="FILTER_TOO_COMPLEX",
                    status=422,
                    title="Filter Too Complex",
                    detail=f"Filter tokens count exceeds maximum of {max_tokens}",
                )

    return tokens


def _split_values(val: str) -> list[str]:
    """Split comma-separated values unless empty."""
    if "," not in val:
        return [val.strip()]
    return [v.strip() for v in val.split(",") if v.strip()]


def _compile_field_predicate(  # noqa: C901, PLR0911, PLR0912, PLR0915
    field: str,
    val_str: str,
    *,
    negated: bool,
    project_id: uuid.UUID | None,
    caller_principal_id: uuid.UUID | None,
) -> ColumnElement[bool]:
    """Compile a single field filter into an injection-safe SQLAlchemy expression."""
    clean_field = field.lower().strip()
    cond: ColumnElement[bool]

    # 1. State / Status
    if clean_field in ("state", "status"):
        vals = _split_values(val_str)
        lower_vals = [v.lower() for v in vals]
        if any(v in ("actionable", "active") for v in lower_vals):
            subq = select(WorkflowState.id).where(
                WorkflowState.state_group.notin_(["completed", "cancelled"])
            )
            if project_id:
                subq = subq.where(WorkflowState.project_id == project_id)
            cond = Issue.state_id.in_(subq)
            return ~cond if negated else cond

        if any(v in ("closed", "terminal") for v in lower_vals):
            subq = select(WorkflowState.id).where(
                WorkflowState.state_group.in_(["completed", "cancelled"])
            )
            if project_id:
                subq = subq.where(WorkflowState.project_id == project_id)
            cond = Issue.state_id.in_(subq)
            return ~cond if negated else cond

        if any(v in ("all", "*") for v in lower_vals):
            return literal(value=False) if negated else literal(value=True)

        or_clauses: list[Any] = []
        uuid_matches: list[uuid.UUID] = []
        text_matches: list[str] = []
        for v in vals:
            if _UUID_RE.match(v):
                try:
                    uuid_matches.append(uuid.UUID(v))
                except ValueError:
                    text_matches.append(v.lower())
            else:
                text_matches.append(v.lower())

        if uuid_matches:
            or_clauses.append(WorkflowState.id.in_(uuid_matches))
        if text_matches:
            or_clauses.append(func.lower(WorkflowState.name).in_(text_matches))
            or_clauses.append(func.lower(WorkflowState.state_group).in_(text_matches))

        subq = select(WorkflowState.id).where(
            or_(*or_clauses) if or_clauses else literal(value=False)
        )
        if project_id:
            subq = subq.where(WorkflowState.project_id == project_id)
        cond = Issue.state_id.in_(subq)
        return ~cond if negated else cond

    # 2. State Group / Group
    if clean_field in ("state_group", "group"):
        vals = [v.lower() for v in _split_values(val_str)]
        if any(v in ("actionable", "active") for v in vals):
            subq = select(WorkflowState.id).where(
                WorkflowState.state_group.notin_(["completed", "cancelled"])
            )
        elif any(v in ("all", "*") for v in vals):
            return literal(value=False) if negated else literal(value=True)
        else:
            subq = select(WorkflowState.id).where(func.lower(WorkflowState.state_group).in_(vals))
        if project_id:
            subq = subq.where(WorkflowState.project_id == project_id)
        cond = Issue.state_id.in_(subq)
        return ~cond if negated else cond

    # 3. Priority
    if clean_field == "priority":
        vals = _split_values(val_str)
        uuid_matches = []
        text_matches = []
        for v in vals:
            if _UUID_RE.match(v):
                try:
                    uuid_matches.append(uuid.UUID(v))
                except ValueError:
                    text_matches.append(v.lower())
            else:
                text_matches.append(v.lower())

        prio_or: list[Any] = []
        if uuid_matches:
            prio_or.append(ProjectPriority.id.in_(uuid_matches))
        if text_matches:
            prio_or.append(func.lower(ProjectPriority.slug).in_(text_matches))
            prio_or.append(func.lower(ProjectPriority.label).in_(text_matches))

        subq = select(ProjectPriority.id).where(or_(*prio_or) if prio_or else literal(value=False))
        if project_id:
            subq = subq.where(ProjectPriority.project_id == project_id)
        cond = Issue.priority_id.in_(subq)
        return ~cond if negated else cond

    # 4. Assignee
    if clean_field == "assignee":
        vals = _split_values(val_str)
        asg_clauses: list[Any] = []
        for raw_v in vals:
            clean = raw_v.strip().lower()
            if clean in ("@me", "me"):
                if caller_principal_id is not None:
                    asg_clauses.append(
                        exists().where(
                            IssueAssignee.issue_id == Issue.id,
                            IssueAssignee.principal_id == caller_principal_id,
                        )
                    )
                else:
                    asg_clauses.append(literal(value=False))
            elif clean in ("unassigned", "none"):
                asg_clauses.append(~exists().where(IssueAssignee.issue_id == Issue.id))
            else:
                clean_handle = clean.lstrip("@").lower()
                compact_handle = clean_handle.replace(" ", "")
                conds: list[Any] = [
                    func.lower(IssueAssignee.free_text_assignee) == clean,
                    exists().where(
                        Principal.id == IssueAssignee.principal_id,
                        or_(
                            func.lower(Principal.display_name) == clean,
                            func.lower(func.replace(Principal.display_name, " ", ""))
                            == compact_handle,
                            exists().where(
                                User.id == Principal.id,
                                func.lower(User.email) == clean,
                            ),
                        ),
                    ),
                ]
                if _UUID_RE.match(raw_v):
                    try:
                        p_uuid = uuid.UUID(raw_v)
                        conds.append(IssueAssignee.principal_id == p_uuid)
                    except ValueError:
                        pass
                asg_clauses.append(
                    exists().where(
                        IssueAssignee.issue_id == Issue.id,
                        or_(*conds),
                    )
                )

        cond = or_(*asg_clauses) if asg_clauses else literal(value=False)
        return ~cond if negated else cond

    # 5. Label
    if clean_field == "label":
        vals = [v.lower() for v in _split_values(val_str)]
        uuid_matches = []
        text_matches = []
        for v in vals:
            if _UUID_RE.match(v):
                try:
                    uuid_matches.append(uuid.UUID(v))
                except ValueError:
                    text_matches.append(v)
            else:
                text_matches.append(v)

        lbl_or: list[Any] = []
        if uuid_matches:
            lbl_or.append(IssueLabel.label_id.in_(uuid_matches))
        if text_matches:
            lbl_or.append(
                exists().where(
                    ProjectLabel.id == IssueLabel.label_id,
                    func.lower(ProjectLabel.name).in_(text_matches),
                )
            )
        cond = exists().where(
            IssueLabel.issue_id == Issue.id,
            or_(*lbl_or) if lbl_or else literal(value=False),
        )
        return ~cond if negated else cond

    # 6. Cycle
    if clean_field == "cycle":
        vals = [v.lower() for v in _split_values(val_str)]
        cycle_clauses: list[Any] = []
        for clean in vals:
            if clean in ("none", "no-cycle"):
                cycle_clauses.append(Issue.cycle_id.is_(None))
            elif clean in ("current", "active"):
                cycle_subq = select(Cycle.id).where(Cycle.status == "active")
                if project_id:
                    cycle_subq = cycle_subq.where(Cycle.project_id == project_id)
                cycle_clauses.append(Issue.cycle_id.in_(cycle_subq))
            elif _UUID_RE.match(clean):
                try:
                    c_uuid = uuid.UUID(clean)
                    cycle_clauses.append(Issue.cycle_id == c_uuid)
                except ValueError:
                    pass
            else:
                cycle_subq = select(Cycle.id).where(func.lower(Cycle.name) == clean)
                if project_id:
                    cycle_subq = cycle_subq.where(Cycle.project_id == project_id)
                cycle_clauses.append(Issue.cycle_id.in_(cycle_subq))
        cond = or_(*cycle_clauses) if cycle_clauses else literal(value=False)
        return ~cond if negated else cond

    # 7. Module
    if clean_field == "module":
        vals = [v.lower() for v in _split_values(val_str)]
        mod_clauses: list[Any] = []
        for clean in vals:
            if clean == "none":
                mod_clauses.append(~exists().where(IssueModule.issue_id == Issue.id))
            elif _UUID_RE.match(clean):
                try:
                    m_uuid = uuid.UUID(clean)
                    mod_clauses.append(
                        exists().where(
                            IssueModule.issue_id == Issue.id,
                            IssueModule.module_id == m_uuid,
                        )
                    )
                except ValueError:
                    pass
            else:
                mod_subq = select(Module.id).where(func.lower(Module.name) == clean)
                if project_id:
                    mod_subq = mod_subq.where(Module.project_id == project_id)
                mod_clauses.append(
                    exists().where(
                        IssueModule.issue_id == Issue.id,
                        IssueModule.module_id.in_(mod_subq),
                    )
                )
        cond = or_(*mod_clauses) if mod_clauses else literal(value=False)
        return ~cond if negated else cond

    # 8. Project
    if clean_field == "project":
        vals = [v.upper() for v in _split_values(val_str)]
        cond = exists().where(
            Project.id == Issue.project_id,
            func.upper(Project.identifier).in_(vals),
        )
        return ~cond if negated else cond

    # 9. Key
    if clean_field == "key":
        vals = _split_values(val_str)
        key_clauses: list[Any] = []
        for raw_k in vals:
            m = _ISSUE_KEY_RE.match(raw_k.strip())
            if m:
                p_ident = m.group(1).upper()
                seq = int(m.group(2))
                key_clauses.append(
                    exists().where(
                        Project.id == Issue.project_id,
                        func.upper(Project.identifier) == p_ident,
                        Issue.sequence_id == seq,
                    )
                )
            elif _UUID_RE.match(raw_k.strip()):
                try:
                    iss_uuid = uuid.UUID(raw_k.strip())
                    key_clauses.append(Issue.id == iss_uuid)
                except ValueError:
                    pass
        cond = or_(*key_clauses) if key_clauses else literal(value=False)
        return ~cond if negated else cond

    # Fallback for unrecognized field: treat as text search on summary/description
    text_cond = Issue.search_tsv.op("@@")(func.websearch_to_tsquery("english", val_str))
    return ~text_cond if negated else text_cond


def _compile_free_text_predicate(term: str, *, negated: bool) -> ColumnElement[bool]:
    """Compile a free-text search term using English stemming tsquery."""
    clean = term.strip()
    if not clean:
        return literal(value=True)
    cond = Issue.search_tsv.op("@@")(func.websearch_to_tsquery("english", clean))
    return ~cond if negated else cond


def compile_predicate_string(  # noqa: C901
    query_str: str,
    project: Project | uuid.UUID | None = None,
    caller_principal_id: uuid.UUID | str | None = None,
) -> list[ColumnElement[bool]]:
    """Compile a filter DSL query string into parameterized SQLAlchemy WHERE expressions.

    Enforces bounds:
    - MAX_QUERY_LENGTH = 512
    - MAX_CLAUSES = 32
    - MAX_TOKENS = 32
    """
    clean_query = sanitize_query_string(query_str, max_length=MAX_QUERY_LENGTH)
    if not clean_query:
        return []

    project_id: uuid.UUID | None = None
    if isinstance(project, Project):
        project_id = project.id
    elif isinstance(project, uuid.UUID):
        project_id = project

    caller_id: uuid.UUID | None = None
    if isinstance(caller_principal_id, uuid.UUID):
        caller_id = caller_principal_id
    elif isinstance(caller_principal_id, str) and _UUID_RE.match(caller_principal_id.strip()):
        try:
            caller_id = uuid.UUID(caller_principal_id.strip())
        except ValueError:
            caller_id = None

    clauses = split_query_clauses(clean_query, max_clauses=MAX_CLAUSES)
    predicates: list[ColumnElement[bool]] = []

    for clause in clauses:
        cmp = parse_comparison_clause(clause)
        if cmp is not None:
            is_neg = (cmp.operator == "!=") ^ cmp.negated
            predicates.append(
                _compile_field_predicate(
                    field=cmp.field,
                    val_str=cmp.value,
                    negated=is_neg,
                    project_id=project_id,
                    caller_principal_id=caller_id,
                )
            )
            continue

        tokens = tokenize_predicate_string(clause, max_tokens=MAX_TOKENS)
        for tok in tokens:
            if tok.field:
                predicates.append(
                    _compile_field_predicate(
                        field=tok.field,
                        val_str=tok.value,
                        negated=tok.negated,
                        project_id=project_id,
                        caller_principal_id=caller_id,
                    )
                )
            else:
                predicates.append(_compile_free_text_predicate(tok.value, negated=tok.negated))

    return predicates
