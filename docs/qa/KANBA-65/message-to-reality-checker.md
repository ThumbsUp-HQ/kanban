# Reality-Checker Verification Packet: KANBA-65 (KB-P2-14)

### Metadata
- **Ticket ID**: `KANBA-65` (`KB-P2-14`)
- **Title**: `[Phase 2 / Content] Server SVG sanitizer: geometry allowlist, strip script/foreignObject/style/SMIL/on*/external href & <use> acyclic DAG guard`
- **Epic**: `KB-E2` (Phase 2 Kanban API & Core Business Engine)
- **Author**: Implementation Author (`builder-17`)
- **Target Worktree**: `/tmp/kb-wt-KANBA-65` on branch `feat/KANBA-65`
- **Base Commit**: `a8a688f95343f987d754b0972a8c02dbc7369214` (KANBA-60 merge base)

---

### Definition of Done Checklist

| DoD Requirement | Target Standard | Observed Status | Verification Reference |
| :--- | :--- | :--- | :--- |
| **1. Target Files & Core Components** | `svg_sanitizer.py`, `svg_dag.py`, `kanban/pyproject.toml`, `pyproject.toml`, `uv.lock` | All target files implemented and cleanly integrated | `git-diff.patch` |
| **2. Exported Interfaces** | `ALLOWED_SVG_ELEMENTS`, `ALLOWED_SVG_ATTRS`, `SvgSanitizeError`, `SvgSanitizeReport`, `validate_svg_use_dag`, `sanitize_svg`, `sanitize_svg_with_report` | All exported from `kanban.content` and modules | `kanban/content/__init__.py` |
| **3. Unit Test Execution & Coverage** | 8 mandatory test cases; >= 95% branch+line coverage across target files | 39/39 tests passed in 4.78s; 97.09% overall statement and branch coverage (363 stmts, 152 branches) | `unit-test-results.txt` |
| **4. Build, Type, Lint & License Cleanliness** | Zero errors across ruff, mypy strict, import-linter, license-gate, check_no_dashes | `ruff check .` (exit 0), `ruff format --check .` (exit 0), `mypy --strict kanban` (0 issues in 41 files), `lint-imports` (exit 0), `license_gate.py` (0 violations), `check_no_dashes --all` (exit 0) | `build-check.txt` |
| **5. Hostile SVG Corpus Audit** | Full audit across hostile SVG inputs showing stripped elements/attributes and rejected error codes | 27/27 test vectors passed; all active scripting, SSRF beacons, XXE attacks, and DAG bombs verified | `hostile-svg-corpus-results.json` |
| **6. Dependency Evaluation** | `defusedxml` (PSF-2.0) with sha256 hashes, S2.5/S5.4 roxmltree rationale, architect + security sign-off | Fully documented with exact wheel/sdist digests from uv.lock and citations from #116, #118, #120 | `dependency-evaluation.md` |
| **7. Screenshots** | N/A - Non-UI Ticket | Confirmed non-UI server sanitizer | N/A |

---

### Mandatory Feature Test Cases (KB-P2-14)

1. **Case 1 (Positive Clean Diagram)**: Validates Mermaid-style diagram containing `<svg>`, `<g>`, `<defs>`, `<linearGradient>`, `<clipPath>`, `<marker>`, `<rect>`, `<path>`, `<circle>`, `<text>`, `<tspan>`, and valid local `<use href="#node-box"/>` (`depth=1`, expansion `< 50`). Sanitizes cleanly and re-parses as valid XML. (`test_case_1_positive_clean_diagram`) - PASS
2. **Case 2 (Security Active Content Strip)**: Strips `<script>`, `<foreignObject>`, `<iframe>`, `<style>`, `<animate>`, `<set>`, `<a>`, and `on*` event handlers while preserving sibling `<rect>` geometry. (`test_case_2_security_active_content_strip`) - PASS
3. **Case 3 (Security External SSRF / Tracking Pixel)**: Strips `<image>` and external `href`/`fill` completely (`0` occurrences of external `http`, `169.254`, or `data:` in output). (`test_case_3_security_external_ssrf_and_tracking_pixel`) - PASS
4. **Case 4 (Security XXE & XML Billion Laughs)**: SVG with `<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>` or quadratic `<!ENTITY lol3 ...>` fails closed with `SVG_DTD_OR_ENTITY_FORBIDDEN`. (`test_case_4_security_xxe_and_entity_expansion_forbidden`) - PASS
5. **Case 5 (Security <use> Cycle)**: Direct self-reference `<g id="a"><use href="#a"/></g>` and mutual cycle `a -> b -> a` raise `SVG_USE_CYCLE`. (`test_case_5_security_use_cycle_detected`) - PASS
6. **Case 6 (Boundary <use> Depth Cap <= 4)**: Chain `u1 -> u2 -> u3 -> u4 -> rect` (`depth=4`) succeeds; adding `u0 -> u1` (`depth=5`) raises `SVG_USE_DEPTH_EXCEEDED`. (`test_case_6_boundary_use_depth_cap`) - PASS
7. **Case 7 (Boundary <use> Expansion Cap <= 500)**: Exponential branching `<use>` bomb raises `SVG_EXPANSION_LIMIT_EXCEEDED`; exactly 500 nodes succeeds; 501 nodes raises. (`test_case_7_boundary_use_expansion_cap`) - PASS
8. **Case 8 (Boundary Size, Encoding & Duplicate IDs)**: `2,097,152`-byte SVG passes; `2,097,153`-byte SVG raises `SVG_SIZE_INVALID`; UTF-16/32 BOMs raise `SVG_INVALID_UTF8`; two elements with duplicate id raise `SVG_DUPLICATE_ID`; non-SVG `<html/>` root raises `SVG_ROOT_INVALID`. (`test_case_8_boundary_size_encoding_and_duplicate_ids`) - PASS

---

### Verification Proof Artifacts

- `docs/qa/KANBA-65/git-diff.patch`
- `docs/qa/KANBA-65/unit-test-results.txt`
- `docs/qa/KANBA-65/build-check.txt`
- `docs/qa/KANBA-65/hostile-svg-corpus-results.json`
- `docs/qa/KANBA-65/dependency-evaluation.md`
- `docs/qa/KANBA-65/message-to-reality-checker.md`
