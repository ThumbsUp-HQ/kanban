# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501
"""LLM agent instructions (/llms.txt, /llms-full.txt), skill catalog, and onboarding interview.

Provides zero-DB, in-memory cached, zero-Host-header-injection templates and HTTP endpoints
for Claude Code, OpenAI Codex, Gemini CLI / Antigravity, and Cursor (KB-LLMS-SKILLS-01 / KAN-80).
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from typing import Final

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from kanban.api.problems import ProblemException

__all__ = [
    "ALLOWED_SKILL_SLUGS",
    "MAX_LLMS_FULL_BYTES",
    "MAX_LLMS_TXT_BYTES",
    "MAX_SKILL_BYTES",
    "ONBOARDING_PROMPT_TEMPLATE",
    "LlmsSkillDescriptor",
    "LlmsSkillsCatalogResponse",
    "SkillAsset",
    "get_llms_full_txt_content",
    "get_llms_skills_catalog",
    "get_llms_txt_content",
    "get_skill_assets",
    "mount_llms_routes",
]

MAX_LLMS_TXT_BYTES: Final[int] = 12 * 1024  # 12,288 bytes
MAX_SKILL_BYTES: Final[int] = 24 * 1024  # 24,576 bytes
MAX_LLMS_FULL_BYTES: Final[int] = 64 * 1024  # 65,536 bytes

ALLOWED_SKILL_SLUGS: Final[frozenset[str]] = frozenset(
    {
        "kanban-workflow-setup",
        "kanban-ticket",
        "kanban-agent-manager",
        "reality-checker",
    }
)

ONBOARDING_PROMPT_TEMPLATE: Final[str] = (
    "Read {origin}/llms.txt, learn 👍kanban's ticket workflow, "
    "interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), "
    "Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), "
    "and QA Rigor, and save my preferences to .agents/skills/ and AGENTS.md."
)


@dataclass(frozen=True)
class SkillAsset:
    """Immutable in-memory descriptor and canonical markdown content for an agent skill."""

    slug: str
    title: str
    summary: str
    install_path: str
    content: str

    @property
    def bytes(self) -> int:
        """Byte length of canonical markdown content."""
        return len(self.content.encode("utf-8"))

    @property
    def sha256(self) -> str:
        """SHA-256 fingerprint of canonical markdown content."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    @property
    def estimated_tokens(self) -> int:
        """Estimated token count (~4 characters per token)."""
        return max(1, len(self.content) // 4)


class LlmsSkillDescriptor(BaseModel):
    """Public metadata model for a single recommended agent skill."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="Unique skill slug identifier")
    title: str = Field(description="Human-readable skill title")
    summary: str = Field(description="One-line functional summary")
    install_path: str = Field(description="Recommended local workspace install path")
    url: str = Field(description="HTTP endpoint serving canonical markdown")
    sha256: str = Field(description="SHA-256 fingerprint of canonical markdown content")
    bytes: int = Field(description="Exact byte size of canonical markdown content")
    estimated_tokens: int = Field(description="Rough token count estimate (~4 chars per token)")


class LlmsSkillsCatalogResponse(BaseModel):
    """Public catalog response listing recommended skills and onboarding prompt."""

    model_config = ConfigDict(extra="forbid")

    llms_txt_url: str = Field(default="/llms.txt", description="URL to compact /llms.txt map")
    llms_full_url: str = Field(
        default="/llms-full.txt", description="URL to bundled /llms-full.txt"
    )
    onboarding_prompt: str = Field(description="Canonical 1-click agent onboarding prompt")
    skills: list[LlmsSkillDescriptor] = Field(description="List of recommended skill descriptors")


_SKILL_WORKFLOW_SETUP_MD: Final[str] = """---
name: kanban-workflow-setup
description: System and workstation onboarding skill for connecting AI coding harnesses (Claude Code, OpenAI Codex, Gemini CLI / Antigravity) to 👍kanban, conducting an interactive 4-axis interview with explicit Pros and Cons, and persisting user preferences to .agents/skills/ and AGENTS.md.
---

# Kanban Workflow Setup Skill

## Overview

This skill guides any AI coding harness (Claude Code, OpenAI Codex / ChatGPT, or Gemini CLI / Antigravity) through onboarding a developer workstation or project with 👍kanban.

## MANDATORY RULE: Interview Before Writing Skills

NEVER apply configurations, modify dot-directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents), install Git hooks, or create skills without completing Phases 1 and 2 first.

### Phase 1: Read-Only Discovery
Inspect current workstation state:
1. Check which AI harnesses are present (~/.claude, ~/.codex, ~/.gemini, ~/.agents).
2. Check existing workspace rules and skills (AGENTS.md, CLAUDE.md, .agents/skills/).
3. Check available MCP endpoints (/mcp/agent, /mcp/docs, /mcp/admin).

### Phase 2: Interactive 4-Axis Preference Interview
Present the 4 preference axes to the user with explicit Pros, Cons, Speed, and Token-Cost tradeoffs:

#### Axis 1 - Execution Topology
- [1A] Single-Threaded Agent (Solo Execution): One agent executes the entire ticket sequentially (read -> design -> code -> test -> proof -> self/clean-room QA check). Pros: Zero orchestration overhead, simplest linear context, ideal for 1-file fixes or single-thread CLI sessions. Cons: Context window bloats on multi-file features, slower wall-clock on multi-ticket backlogs, higher confirmation bias without an independent QA sub-agent.
- [1B] Teamwork (Coordinator + Specialized Sub-Agents) [Recommended]: Coordinator delegates discrete phases (specialist consultation -> implementation builder sub-agent -> passive read-only reality-checker sub-agent) and reuses persistent conversationIds (~1/100th cached input token cost). Pros: Clean coordinator context, independent clean-room QA, 2x-3x faster on multi-part tickets. Cons: Moderate handoff overhead via docs/qa/<TICKET_ID>/.
- [1C] Multi-Agent Swarm (Parallel Worktree Builders + Persistent Roster): Coordinator acts purely as a state machine on the shared board with parallel worktree builders (b-<ticket>, workspace: "share"), persistent waiting reviewers (api-spec, ui-spec, merge-ci, monitor costing 0 tokens while asleep), reusable live full-stack verifiers, and clean-room reality-checker auditors. Pros: Maximum wave velocity across 5-50+ tickets, strict branch isolation. Cons: Highest coordination and merge-gate surface; overkill for a single small fix.

#### Axis 2 - Token Budget & Model Tier Strategy
- [2A] Quota-Sipping / Cost-Optimized Tier [Recommended]: Flagship Coordinator (Gemini Argon/Pro, Claude Opus/Sonnet, Codex) + fast/lightweight workers (Gemini 3.8 Flash, Claude Haiku, GPT-4o-mini / Codex fast tier) + persistent context-cached conversations. Pros: 2x-4x+ effective quota runway, fastest per-turn latency. Cons: Requires literal, tightly scoped kanban-ticket definitions.
- [2B] Balanced Hybrid Tier: Mid/flagship coding models (Claude Sonnet, Gemini Argon/Hydrogen, GPT-4o) for architecture and complex implementation diffs + fast models (Flash, Haiku, Codex fast) for unit test expansion, linting, and reality-checker audits. Pros: Strong zero-shot depth on complex refactors while saving 50-70% of QA/test tokens. Cons: Moderate token burn on large implementation diffs.
- [2C] Unconstrained / Max-Compute Tier ("Spare No Expense"): User has abundant token budget and wants frontier flagship models (OpenAI Sol MAX, Claude Ultra / Opus, or Gemini Carbon / Neon) to execute all planning, coding, testing, and verification end-to-end (either single-threaded or across every sub-agent/swarm worker). Pros: Maximum reasoning depth on novel cryptography, concurrency, or ambiguous greenfield architecture without model-tier handoffs. Cons: Highest token consumption (4x-5x+ vs. fast tier), slower per-turn generation latency, and faster rate-limit/quota depletion.

#### Axis 3 - QA, Coverage & CI Rigor
- [3A] Pragmatic Baseline (>=80% Unit Coverage + Lightweight QA Check): Feature unit tests (>=80% target) + single verification pass before complete_work.
- [3B] Clean-Room Forensic reality-checker + Specialist Gates + >=95% Coverage [Recommended]: Mandatory UI Specialist Gate (ui-specialist-review.md), Dual API+UI Specialist Gate (api-specialist-review.md + ui-specialist-review.md), passive Clean-Room reality-checker Grade-A READY certification posted verbatim in complete_work, >=95% per-module unit coverage, zero-mock local container verification, and green Dash CI/CD verification.

#### Axis 4 - Persistence Scope
- [4A] Project Workspace Only (.agents/skills/ + AGENTS.md + CLAUDE.md -> AGENTS.md + .claude/skills -> ../.agents/skills)
- [4B] Global User Workstation (~/.agents/skills/ linked into ~/.claude/skills/, ~/.codex/skills/, ~/.gemini/skills/, ~/.gemini/config/skills/)
- [4C] Both Project & Global [Recommended]

### Phase 3: Persistence After Confirmation
Once the user confirms choices:
1. Write chosen settings into AGENTS.md and .agents/skills/.
2. Create cross-harness symlinks:
   - Project: CLAUDE.md -> AGENTS.md, .claude/skills -> ../.agents/skills
   - Global: ~/.agents/skills linked to active harness skill dirs.
3. Verify with scripts.check_no_dashes (zero em-dashes or en-dashes).
"""

_SKILL_KANBAN_TICKET_MD: Final[str] = """---
name: kanban-ticket
description: System-level standard for authoring and refining tightly scoped Kanban tickets with mandatory feature unit testing, literal Definitions of Done, and passive forensic Verification Proof packets for reality-checker.
---

# Kanban Ticket Skill

## Overview

This skill defines the mandatory structure and scoping rules for creating and updating Kanban tickets across Claude Code, OpenAI Codex, and Gemini CLI / Antigravity. Every ticket must be atomic, tightly scoped, unit-tested, and forensically auditable by the reality-checker sub-agent running on a fast, lightweight model without requiring reality-checker to run commands, execute tests, or visit live websites.

## Core Principles for Scoped Tickets

0. Deduplicate & Consult Specialists Before Creating Tickets:
   - Search First (search_tickets): Always search Backlog, Todo, and In Progress before creating a new ticket. If an existing ticket already covers the target area, update that ticket in-place (update_ticket).
   - Consult Domain Specialists in Parallel: Consult relevant specialists (UX/Frontend, Backend, Security) on fast models before finalizing ticket specifications.
   - Do Not Auto-Start Implementation: When asked to create or update tickets, stop once the tickets are created/updated and wait for explicit instruction before calling begin_work.
1. Single-Ticket Boundary (No Cross-Ticket Bleed):
   - A ticket's Definition of Done and Verification Proof must only test artifacts, files, and behaviors that exist after completing that specific ticket.
2. Literal, Non-Rhetorical Specifications:
   - Avoid figures of speech or ambiguous marketing adjectives. Specify exact file paths, functions, status codes, and byte limits.
3. Mandatory Feature Unit Testing (>=95% Project Coverage Standard):
   - Every feature or code ticket must require unit tests specifically exercising the new/modified logic introduced in that ticket, running against clean isolated database state per test (SAVEPOINT / template DB).
4. Passive Forensic Verification Proof (docs/qa/<TICKET_ID>/):
   - reality-checker does not run commands or visit URLs.
   - The Verification Proof section must mandate a self-contained forensic proof directory at docs/qa/<TICKET_ID>/ containing raw outputs (diffs, test results, build checks, specialist sign-offs, and screenshots).
5. State Machine Guard (begin_work Sort-Order Guard):
   - If calling begin_work transitions a ticket to a custom state that has sort_order=0, immediately call transition_ticket to move it to "In Progress".
6. Protected Pre-Production Instance Invariant:
   - Never modify or treat k.hackedyour.info / 192.168.1.101 ("test kanban") as a destructive test bed. Only non-destructive validation is permitted.

## Standard 5-Section Ticket Template

1. User Story: As a <role>, I need <capability> so that <benefit>.
2. Scoped Technical Actions: Exact target files, architectural boundaries, and implementation steps.
3. Mandatory Feature Unit Tests: Required positive, negative, and boundary test cases.
4. Scoped Definition of Done: Explicit checklist of completion criteria.
5. Forensic Verification Proof: Mandatory proof artifact bundle in docs/qa/<TICKET_ID>/.
"""

_SKILL_AGENT_MANAGER_MD: Final[str] = """---
name: kanban-agent-manager
description: System-level Agent Manager workflow for orchestrating Kanban ticket execution across sub-agents, enforcing the reality-checker forensic QA gate on a fast model, managing ticket comments/states, delegating 95% unit test coverage, and opening tickets for discovered gaps.
---

# Kanban Agent Manager Skill

## Overview

This skill defines the Agent Manager orchestration workflow for coordinating ticket execution across sub-agents, managing ticket state lifecycles, and enforcing quality gates in 👍kanban.

## Workflow Rules

1. Ticket Ownership & In Progress State:
   - The Agent Manager (or builder) marks the ticket In Progress via begin_work (or transition_ticket to In Progress if begin_work lands on sort_order=0).
   - Post an initial execution plan comment to the ticket.
2. Parallel Specialist Consultation:
   - Consult domain specialists in parallel (UX/Frontend, Backend, Security) before writing implementation code.
3. Sub-Agent Delegation & Context Isolation:
   - Delegate implementation to builder sub-agents with dedicated workspace shares or branches.
   - Maintain clean coordinator context; reuse conversationIds where supported.
4. Passive Forensic Reality-Checker Gate:
   - When implementation is complete and docs/qa/<TICKET_ID>/ is fully populated, invoke the reality-checker sub-agent on a fast model (Gemini 3.8 Flash, Claude Haiku, Codex fast).
   - reality-checker operates strictly in Passive Forensic Verification Mode: zero test execution, zero shell commands, zero browser actions.
   - Only a Grade-A READY certification permits closing the ticket.
5. Closing Work (complete_work):
   - Post the full reality-checker certification report and specialist sign-offs into ticket comments.
   - Call complete_work to transition ticket to Done.
6. Post-Completion Coverage & Gap Creation:
   - Delegate >=95% unit test coverage verification to a fast tester sub-agent.
   - Open atomic tickets for any gaps or edge cases discovered during execution.
"""

_SKILL_REALITY_CHECKER_MD: Final[str] = """---
name: reality-checker
description: Stops fantasy approvals, evidence-based certification - Default to "NEEDS WORK", requires overwhelming proof for production readiness.
---

# Integration Agent Personality & Forensic QA Auditor

You are TestingRealityChecker, a senior integration specialist who stops fantasy approvals and requires overwhelming evidence before production certification.

## Identity & Mission

- Role: Final integration testing and realistic deployment readiness assessment.
- Personality: Skeptical, thorough, evidence-obsessed, fantasy-immune.
- Default Verdict: Default to "NEEDS WORK" status unless proven otherwise by overwhelming forensic evidence.

## Passive Forensic Verification Mode

When auditing a ticket, you MUST operate strictly in passive forensic mode:
1. DO NOT run pytest, vitest, pnpm, or git commands.
2. DO NOT start web servers or visit URLs.
3. Verify docs/qa/<TICKET_ID>/changed-files-manifest.txt using sha256sum verification.
4. Read and audit all proof files:
   - git-diff.patch: Unified diff of all modifications.
   - unit-test-results.txt: Complete stdout/stderr and exit code of test runner.
   - build-or-typecheck.txt: Full static analysis, linter, and typecheck output.
   - api-specialist-review.md: Verbatim API specialist audit and sign-off.
   - ui-specialist-review.md: Verbatim UI specialist audit and sign-off.
   - screenshots/*.png: Responsive screenshots (desktop 1440x900 light/dark, tablet 768x1024, mobile 390x844).
5. Output verbatim "# Integration Agent Reality-Based Report" with grade (A, B, C, F) and verdict (READY or NEEDS WORK).
"""

_LLMS_TXT_TEMPLATE: Final[str] = """# 👍kanban - Agent-First, Security-First Kanban Platform

> Open-source (Apache-2.0), Security-First (Priority #0), Agent-First (Priority #1) Kanban, Ticketing, and Knowledge Platform. Embedded PostgreSQL 16 with FORCE RLS, 24 low-token MCP tools across 3 isolated surfaces, canonical Markdown only, and zero SaaS AI paywalls.

## Humans

If you are a human developer configuring your workspace, either:
- Copy and paste the contents of `/llms.txt` into your AI coding agent (Claude Code, OpenAI Codex, Gemini CLI / Antigravity, Cursor), or
- Deliver this `/llms.txt` URL directly to your agent (e.g., *"Read `<this-url>` and onboard this workspace to 👍kanban"*).

## Agents

### 1. Platform & 3-Surface MCP Quick-Map

Access 👍kanban programmatically via Model Context Protocol (MCP) or REST APIs:
- Agent Surface (/mcp/agent): 9 tools for ticket workflow (ping_agent, search_tickets, read_ticket, create_ticket, update_ticket, begin_work, transition_ticket, complete_work, add_comment, link_objects).
- Docs Surface (/mcp/docs): 3 knowledge tools (search_docs, read_doc, manage_stickies, promote_sticky_to_doc).
- Admin Surface (/mcp/admin): 12 governance tools with 2-stage destructive confirmation.
- Authentication: OAuth 2.1 with PKCE (S256) or scoped personal API tokens (kb_pat_* / kb_agt_*).
- Level of Detail (LOD) Tiers: summary (strict 1,000-token cap), standard, and full.

### 2. How to Create & Approach Tickets (kanban-ticket Rules)

When authoring or executing tickets:
1. Search First: Always call search_tickets to deduplicate before creating.
2. Parallel Specialist Consultation: Consult UX, Backend, and Security specialists before drafting or coding.
3. Stop After Creation: Do not auto-start begin_work when asked to create tickets. Wait for explicit instruction.
4. Literal Specifications: Exact file paths, HTTP codes, byte budgets, and non-rhetorical criteria.
5. Mandatory Feature Unit Tests: Unit tests specifically covering new logic with clean-DB isolation (>=95% target).
6. 5-Section Ticket Template: User Story, Scoped Technical Actions, Mandatory Feature Unit Tests, Scoped Definition of Done, and Forensic Verification Proof in docs/qa/<TICKET_ID>/.
7. State Machine Guard: If begin_work lands on a custom state with sort_order=0, transition ticket to "In Progress".
8. Protected Instance Invariant: Never treat k.hackedyour.info / 192.168.1.101 as a destructive test bed.

### 3. Mandatory Interactive Onboarding Directive ("Interview Before Writing Skills")

Before writing any agent skills or changing project configs, you MUST complete:
- Phase 1: Read-only inspection of ~/.claude, ~/.codex, ~/.gemini, ~/.agents, AGENTS.md, and .agents/skills/.
- Phase 2: Interactive user interview across the 4 core preference axes:
  - Axis 1 (Execution Topology): [1A] Single-Threaded Agent (Solo Execution), [1B] Teamwork (Coordinator + Sub-Agents) [Recommended], [1C] Multi-Agent Swarm (Parallel Worktree Builders).
  - Axis 2 (Token Budget & Model Tier): [2A] Quota-Sipping Flash 3.8 / Haiku [Recommended], [2B] Balanced Hybrid (Sonnet / Argon + Flash / Haiku), [2C] Unconstrained Sol MAX / Claude Ultra / Gemini Carbon.
  - Axis 3 (QA, Coverage & CI Rigor): [3A] Pragmatic Baseline (>=80%), [3B] Clean-Room Forensic reality-checker + >=95% Coverage [Recommended].
  - Axis 4 (Persistence Scope): [4A] Project Workspace Only, [4B] Global User Workstation, [4C] Both Project & Global [Recommended].
- Phase 3: Persist confirmed selections to .agents/skills/ and AGENTS.md with cross-harness symlinks.

### 4. Recommended Skills Catalog

Install the official 👍kanban skills:
- Workflow Setup: /llms-skills/kanban-workflow-setup.md
- Ticket Authoring: /llms-skills/kanban-ticket.md
- Agent Manager: /llms-skills/kanban-agent-manager.md
- Reality-Checker QA Gate: /llms-skills/reality-checker.md
- Full Bundle: /llms-full.txt
"""


@functools.lru_cache(maxsize=1)
def get_skill_assets() -> dict[str, SkillAsset]:
    """Retrieve frozen map of all recommended agent skill assets."""
    assets = {
        "kanban-workflow-setup": SkillAsset(
            slug="kanban-workflow-setup",
            title="Kanban Workflow Setup & Interactive 4-Axis Agent Onboarding",
            summary=(
                "Workstation onboarding skill for connecting Claude Code, OpenAI Codex, and "
                "Gemini CLI / Antigravity to 👍kanban via a 4-axis preference interview."
            ),
            install_path=".agents/skills/kanban-workflow-setup/SKILL.md",
            content=_SKILL_WORKFLOW_SETUP_MD.strip() + "\n",
        ),
        "kanban-ticket": SkillAsset(
            slug="kanban-ticket",
            title="Kanban Ticket Authoring & Scoping Standard",
            summary=(
                "Standard for authoring atomic, tightly scoped Kanban tickets with mandatory "
                "feature unit testing and passive forensic verification packets."
            ),
            install_path=".agents/skills/kanban-ticket/SKILL.md",
            content=_SKILL_KANBAN_TICKET_MD.strip() + "\n",
        ),
        "kanban-agent-manager": SkillAsset(
            slug="kanban-agent-manager",
            title="Kanban Sub-Agent Manager & Fast-Model QA Orchestration",
            summary=(
                "Workflow for coordinating ticket execution across sub-agents and enforcing "
                "the reality-checker forensic QA gate on a fast model."
            ),
            install_path=".agents/skills/kanban-agent-manager/SKILL.md",
            content=_SKILL_AGENT_MANAGER_MD.strip() + "\n",
        ),
        "reality-checker": SkillAsset(
            slug="reality-checker",
            title="Reality-Checker Passive Forensic QA Gate Auditor",
            summary=(
                "Evidence-based passive forensic auditor personality that stops fantasy approvals "
                "and requires overwhelming proof for production certification."
            ),
            install_path=".agents/skills/kanban-agent-manager/references/reality-checker.md",
            content=_SKILL_REALITY_CHECKER_MD.strip() + "\n",
        ),
    }

    # Invariant: Each individual skill markdown file must not exceed byte ceiling
    for slug, asset in assets.items():
        if asset.bytes > MAX_SKILL_BYTES:
            msg = f"Skill asset '{slug}' exceeds {MAX_SKILL_BYTES} bytes ({asset.bytes} bytes)"
            raise RuntimeError(msg)

    return assets


@functools.lru_cache(maxsize=1)
def get_llms_txt_content() -> str:
    """Retrieve in-memory cached content of /llms.txt."""
    content = _LLMS_TXT_TEMPLATE.strip() + "\n"
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > MAX_LLMS_TXT_BYTES:
        msg = f"/llms.txt exceeds {MAX_LLMS_TXT_BYTES} bytes ({content_bytes} bytes)"
        raise RuntimeError(msg)
    return content


@functools.lru_cache(maxsize=1)
def get_llms_full_txt_content() -> str:
    """Retrieve concatenated bundle of /llms.txt and all recommended skill markdowns."""
    parts: list[str] = [get_llms_txt_content().rstrip(), ""]
    skills = get_skill_assets()
    for slug in sorted(skills.keys()):
        asset = skills[slug]
        parts.append(f"<!-- BEGIN SKILL: {slug} -->")
        parts.append(asset.content.rstrip())
        parts.append(f"<!-- END SKILL: {slug} -->")
        parts.append("")
    full_content = "\n".join(parts).strip() + "\n"
    full_bytes = len(full_content.encode("utf-8"))
    if full_bytes > MAX_LLMS_FULL_BYTES:
        msg = f"/llms-full.txt exceeds {MAX_LLMS_FULL_BYTES} bytes ({full_bytes} bytes)"
        raise RuntimeError(msg)
    return full_content


def get_llms_skills_catalog(
    origin: str = "https://kanban.example.com",
) -> LlmsSkillsCatalogResponse:
    """Construct public metadata catalog response for /api/v1/system/skills."""
    assets = get_skill_assets()
    skills_list: list[LlmsSkillDescriptor] = []
    for slug in sorted(assets.keys()):
        asset = assets[slug]
        skills_list.append(
            LlmsSkillDescriptor(
                slug=asset.slug,
                title=asset.title,
                summary=asset.summary,
                install_path=asset.install_path,
                url=f"/llms-skills/{asset.slug}.md",
                sha256=asset.sha256,
                bytes=asset.bytes,
                estimated_tokens=asset.estimated_tokens,
            )
        )
    clean_origin = origin.rstrip("/")
    onboarding_prompt = ONBOARDING_PROMPT_TEMPLATE.format(origin=clean_origin)
    return LlmsSkillsCatalogResponse(
        llms_txt_url="/llms.txt",
        llms_full_url="/llms-full.txt",
        onboarding_prompt=onboarding_prompt,
        skills=skills_list,
    )


def _check_host_header(request: Request) -> None:
    """Reject hostile or malformed Host headers containing control characters."""
    host = request.headers.get("host")
    if host and any(c in host for c in ("\r", "\n", "\x00")):
        raise ProblemException(
            code="BAD_REQUEST",
            status=400,
            title="Bad Request",
            detail="Host header contains invalid characters",
        )


def _serve_cached_text(
    request: Request,
    content_str: str,
    media_type: str,
) -> Response:
    """Serve cached text content with deterministic ETag, 304 evaluation, and HEAD support."""
    _check_host_header(request)
    raw_bytes = content_str.encode("utf-8")
    etag = f'"{hashlib.sha256(raw_bytes).hexdigest()}"'
    headers: dict[str, str] = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300, must-revalidate",
        "X-Content-Type-Options": "nosniff",
    }

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)

    if request.method == "HEAD":
        headers["Content-Length"] = str(len(raw_bytes))
        headers["Content-Type"] = media_type
        return Response(status_code=200, headers=headers)

    return Response(
        content=raw_bytes,
        media_type=media_type,
        headers=headers,
    )


def mount_llms_routes(app: FastAPI) -> None:
    """Mount /llms.txt, /llms-full.txt, and /llms-skills routes on FastAPI application."""
    router = APIRouter()

    @router.api_route("/llms.txt", methods=["GET", "HEAD"], include_in_schema=False)
    async def llms_txt_endpoint(request: Request) -> Response:
        return _serve_cached_text(
            request,
            get_llms_txt_content(),
            "text/plain; charset=utf-8",
        )

    @router.api_route("/llms-full.txt", methods=["GET", "HEAD"], include_in_schema=False)
    async def llms_full_txt_endpoint(request: Request) -> Response:
        return _serve_cached_text(
            request,
            get_llms_full_txt_content(),
            "text/plain; charset=utf-8",
        )

    @router.api_route(
        "/llms-skills/{skill_slug:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    async def llms_skill_endpoint(request: Request, skill_slug: str) -> Response:
        clean_slug = skill_slug.removesuffix(".md") if skill_slug.endswith(".md") else skill_slug
        assets = get_skill_assets()
        if clean_slug not in ALLOWED_SKILL_SLUGS or not skill_slug.endswith(".md"):
            raise ProblemException(
                code="NOT_FOUND",
                status=404,
                title="Not Found",
                detail=f"Skill '{skill_slug}' not found",
            )
        asset = assets[clean_slug]
        return _serve_cached_text(
            request,
            asset.content,
            "text/markdown; charset=utf-8",
        )

    app.include_router(router)
