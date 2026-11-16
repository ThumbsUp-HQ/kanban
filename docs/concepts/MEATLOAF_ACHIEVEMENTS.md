# Concept: Meatloaf Collectible Achievement System & "Crazy Ideas" State

> **Document Status:** Conceptual Back-Burner / `Crazy Ideas` State  
> **Directive:** This concept is strictly off-limits to autonomous implementation until core platform phases are stable and the lead user has finalized production artwork.

---

## 1. Executive Summary & Design Vision

The **Meatloaf Collectible Achievement System** brings warmth, delight, and tangible progression to `👍kanban` by celebrating human and agentic milestones. Centered on the platform's canine mascot, **Meatloaf** (an American Bulldog with AKC Trick Dog credentials, already immortalized in `meatloaf-bot`), the system awards collectible cards, badges, and unlockable avatar stickers upon reaching engineering and operational milestones.

### Visual Concept Progression
The art style blends clean cartoon vector aesthetics with warmth, expressive character poses, and trading-card framing.

- **Rookie Card (Account Creation / Rookie):** Meatloaf sleeping peacefully on the sofa (`assets/meatloaf-rookie-card.jpg`).
- **Training Mat (First Ticket / First Workflow):** Meatloaf on an agility training mat receiving a treat (`assets/meatloaf-training-mat.jpg`).
- **Graduation (Completed Training / Certification):** Meatloaf in cap and blue sash on a podium (`assets/meatloaf-graduation.jpg`).
- **Superhero Flying (100th Ticket / Autonomous Flow):** Meatloaf flying with red cape and AKC Trick Dog medal (`assets/meatloaf-superhero-cape.jpg`).
- **Belly-Up Relaxation (Zero Defects / Clean CI Suite):** Meatloaf rolling on his back happily (`assets/meatloaf-belly-up-sticker.jpg`).

---

## 2. The "Crazy Ideas" Workflow State Boundary

The platform defines the **`Crazy Ideas`** state within the `Unstarted` stage:
- **Description:** *"This is for items which are not yet approved, but will be used eventually or are on the 'back burner' for further development. These items are not to be touched without explicit approval from the lead user."*

### Strict Operational Boundaries for Agents
1. **Autonomous Exclusion:** Autonomous agents, swarm workers, and background task runners MUST NEVER search, select, begin work on, or transition tickets residing in `Crazy Ideas`.
2. **Query Isolation:** Default queries for actionable work items (`search_tickets` with `states: ['Todo', 'Backlog']`) strictly exclude `Crazy Ideas`.
3. **Promotion Gate:** A `Crazy Ideas` ticket can ONLY be promoted to `Backlog` or `Todo` via explicit user instruction.

---

## 3. Achievement & Milestone Taxonomy

| Category | Tier | Achievement Name | Unlock Condition | Concept Art Reference |
| :--- | :---: | :--- | :--- | :--- |
| **Onboarding** | Common | **"Rookie on the Couch"** | User registers account / completes first profile setup. | `meatloaf-rookie-card.jpg` |
| **First Steps** | Common | **"Good Boy Obedience"** | User creates first work item or passes first local test. | `meatloaf-training-mat.jpg` |
| **Certification** | Rare | **"Summa Cum Doggo"** | User completes workflow configuration & repo connection. | `meatloaf-graduation.jpg` |
| **Agent Mastery** | Epic | **"Superdog Dispatch"** | First ticket transitioned through an autonomous agent gate. | `meatloaf-superhero-cape.jpg` |
| **Security & Quality** | Rare | **"Belly-Up Bliss"** | 10 consecutive PRs pass CI and `reality-checker` with zero defects. | `meatloaf-belly-up-sticker.jpg` |
| **Enterprise Milestone** | Legendary | **"The Century Club"** | 100th ticket closed with full forensic verification packet. | Foil Holographic Meatloaf |
| **Admin Hardening** | Epic | **"Ironclad Bone"** | Admin enables WebAuthn/Passkey AAL2 and enforces zero-trust CSP. | Meatloaf at Vault Door |
| **Object Graph & CI Integration** | Rare | **"Dash-Hound Dispatcher" / "Graph Linker"** | Linked a Module to a Dash CI/CD project or bound external resource URLs for Agentic Core resolution (`KANBA-178`). | Meatloaf Retrieving Signal Flag |

---

## 4. Proposed Data Architecture (Deferred Implementation)

```sql
CREATE TABLE achievement_definitions (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    slug              TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9_-]{1,64}$'),
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    category          TEXT NOT NULL CHECK (category IN ('onboarding', 'milestone', 'agentic', 'security', 'quality')),
    rarity            TEXT NOT NULL CHECK (rarity IN ('common', 'rare', 'epic', 'legendary')),
    icon_asset_path   TEXT NOT NULL,
    criteria_rule     JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active         BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE user_achievements (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_id      UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    achievement_id    UUID NOT NULL REFERENCES achievement_definitions(id) ON DELETE CASCADE,
    workspace_id      UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    unlocked_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    transaction_ref   TEXT,
    metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (principal_id, achievement_id)
);

ALTER TABLE user_achievements ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_achievements FORCE ROW LEVEL SECURITY;
```

### Key Architectural Invariants
- **Zero Board Latency:** Evaluated asynchronously from outbox events emitted by `activity_records`.
- **Non-Intrusive UI:** Displayed in a dedicated tab on User Profile with optional celebration toasts and user preference toggle.
