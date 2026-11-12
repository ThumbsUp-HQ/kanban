---
id: KB-E2
title: '[Phase 2 / Epic] Auth Studio, Access Model & Sanitization/Media Shield'
type: epic
children: [KB-P2-01, KB-P2-02, KB-P2-03, KB-P2-04, KB-P2-05a, KB-P2-05b, KB-P2-06, KB-P2-07, KB-P2-08, KB-P2-09, KB-P2-10,
  KB-P2-11, KB-P2-12, KB-P2-13, KB-P2-14, KB-P2-15, KB-P2-16, KB-P2-17, KB-P2-18]
spec_sections: ['2.2', '3.2', '3.4', '3.5', '4.1', '4.2', '4.3', '5.1', '5.2', '5.4', '9.3', '15.5']
gates: [reality-checker]
state: Backlog
---

### Goal
Deliver the `kanban/` security core: FastAPI skeleton with RLS-bound request sessions, server-side sessions and CSRF, envelope-encrypted multi-card authentication (Local Admin, WebAuthn/TOTP, OIDC, LDAPS), identity linking without email auto-merge, `LOCKOUT_PREVENTED` safeguards, the permission evaluator and `access_manifest`, the first-boot setup claim, the Markdown ingestion normalizer, SVG sanitizer, attachment and media-proxy services, the outbound secret scrubber, and rate limiting.

### Scope Summary
- AuthN: `auth_provider_cards`, AES-256-GCM envelope encryption, Argon2id + pepper, WebAuthn/TOTP/recovery codes, OIDC PKCE `S256`, LDAPS/StartTLS, `user_identities`.
- Lockout prevention: DB trigger, handshake probe gate, `kanban-ctl auth emergency-unlock`.
- AuthZ: capability bitmask evaluator with OBO intersection, redacted `access_manifest`.
- Content shield: `kanban/content/normalize.py`, SVG sanitizer, attachments, `/api/v1/media-proxy`, `kanban/security/scrubber.py`.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P2-01 | FastAPI API skeleton, error model & RLS request dependency | KB-P1-17, KB-P0-10 |
| KB-P2-02 | Sessions, cookies & CSRF | KB-P2-01 |
| KB-P2-03 | `auth_provider_cards` + envelope encryption | KB-P1-17 |
| KB-P2-04 | Local Admin card: Argon2id + pepper login | KB-P2-02, KB-P2-03 |
| KB-P2-05a / KB-P2-05b | WebAuthn/Passkeys, TOTP (AAL2) & recovery codes | KB-P2-04 |
| KB-P2-06 | OIDC / OAuth2 card | KB-P2-03, KB-P2-02 |
| KB-P2-07 | LDAPS / StartTLS card | KB-P2-03, KB-P2-02 |
| KB-P2-08 | Identity linking without email auto-merge | KB-P2-06, KB-P2-07, KB-P2-05a / KB-P2-05b |
| KB-P2-09 | `LOCKOUT_PREVENTED` safeguards & emergency unlock CLI | KB-P2-03, KB-P1-12 |
| KB-P2-10 | Auth card admin API (CRUD, toggle, reorder, test) | KB-P2-09, KB-P2-06, KB-P2-07 |
| KB-P2-11 | Permission evaluator, OBO intersection & `access_manifest` | KB-P1-13, KB-P2-01 |
| KB-P2-12 | First-boot setup claim (`kb_setup_*`) | KB-P0-09, KB-P2-05a / KB-P2-05b |
| KB-P2-13 | Server Markdown ingestion normalizer | KB-P2-01 |
| KB-P2-14 | Server SVG sanitizer | KB-P2-13 |
| KB-P2-15 | Attachment upload & serving service | KB-P2-14, KB-P2-11 |
| KB-P2-16 | Media proxy `/api/v1/media-proxy` | KB-P2-01 |
| KB-P2-17 | Outbound secret scrubber library | KB-P0-01 |
| KB-P2-18 | Rate limiting service | KB-P2-01, KB-P1-18 |

### Epic Definition of Done
- [ ] All 18 child tickets (KB-P2-01 .. KB-P2-18) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 3 (Phase 2): Envelope-encrypted `OIDC`/`OAuth2`/`LDAPS`/`Local Admin` cards, `LOCKOUT_PREVENTED`, Rust `nh3` + hidden-DOM pruner, SVG scrubber, and `/api/v1/media-proxy`.
