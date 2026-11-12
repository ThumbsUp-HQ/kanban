# Dependency Evaluation: defusedxml (KANBA-65 / KB-P2-14)

## Evaluated Packages

### 1. defusedxml (Runtime Dependency)
- **Package**: `defusedxml`
- **Version**: `0.7.1` (pinned in `kanban/pyproject.toml` and `uv.lock`)
- **License**: `PSF-2.0` / `Python-2.0` (100% Permissive, Apache-2.0 compatible)
- **Cryptographic Hashes (uv.lock)**:
  - Wheel: `sha256:a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61`
  - Sdist: `sha256:1bb3032db185915b62d7c6209c5a8792be6a32ab2fedacc84e01b52c51aa3e69`
- **Purpose**: Hardened XML parser that explicitly disallows entity expansion bombs (billion laughs), DTD parameter entities, and external entity injection (XXE).

### 2. types-defusedxml (Development Typing Stubs)
- **Package**: `types-defusedxml`
- **Version**: `0.7.0.20260504` (pinned in root `pyproject.toml` dev dependency group and `uv.lock`)
- **License**: `Apache-2.0` (100% Permissive)
- **Cryptographic Hashes (uv.lock)**:
  - Wheel: `sha256:a959e3a0a43b93e464bd625d91ec9193a2703ddc10443bdd627792485fae0b10`
  - Sdist: `sha256:2ab2828a3f97111ba1c16cee273ad4124a831fc9198c41bf8368ff6ea48ad300`
- **Purpose**: Type annotations enabling strict mypy compliance (`mypy --strict kanban`) without untyped import warnings.

---

## Architectural Rationale: roxmltree vs. defusedxml

In the Authoritative Architecture and Product Specification (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` S2.5 and S5.4), `roxmltree` is referenced as a non-entity, read-only XML parser. `roxmltree` is a Rust crate with zero entity expansion support by design, but it does not provide an official Python package on PyPI.

In Python, the identical non-entity XML boundary is achieved with `defusedxml` paired with our strict pre-parse firewall:
1. **Pre-Parse Byte Scanner**: Case-insensitive regex scans raw bytes/text to reject `<!DOCTYPE`, `<!ENTITY`, `<![CDATA[`, and `<?xml-stylesheet` before any XML parsing engine executes, failing closed with `SVG_DTD_OR_ENTITY_FORBIDDEN`.
2. **defusedxml Parser Hardening**: Invoked with `forbid_dtd=True`, `forbid_entities=True`, and `forbid_external=True` to eliminate entity expansion, quadratic blowup, and external entity resolution.
3. **Pure Geometry Allowlist**: Strips all non-vector geometry tags (`<script>`, `<foreignObject>`, `<style>`, `<image>`, etc.) and `on*` event handlers.
4. **Local Acyclic DAG Validator (`svg_dag.py`)**: Enforces cycle-free references, maximum `<use>` chain depth <= 4, and maximum expanded DOM nodes <= 500.

---

## Alternatives Considered and Rejected

1. **Standard Library `xml.etree.ElementTree` alone**:
   - *Rejected*: Inherently vulnerable to XML Entity Expansion (billion laughs) and DTD parameter entity retrieval bombs. Untrusted XML must never be parsed directly by standard library parsers.
2. **`lxml` (Python bindings to C `libxml2`)**:
   - *Rejected*: Massive attack surface, complex native C library build dependencies, and a long history of memory safety vulnerabilities and CVEs in `libxml2`.
3. **Raw Regex Sanitization**:
   - *Rejected*: XML cannot be safely parsed with regular expressions alone due to nested structures, XML namespaces, comments, and CDATA boundaries.

---

## Specialist Reviews and Approvals

Pre-approved under the Swarm Board Dependency Evaluation Batch for Waves W10-W17:

1. **Systems/Backend Architect (`@arch-reviewer`, Swarm Message #116)**:
   > "SVG uploads present severe XSS and XXE attack surfaces. Standard Python xml.etree is vulnerable to XML Entity Expansion (Billion Laughs) and DTD retrieval bombs. defusedxml strictly disables entity expansion and external DTD resolution. Combined with our geometry allowlist and acyclic <use> DAG validator, it provides rock-solid SVG sanitization. Verdict: APPROVED."

2. **Application & Supply-Chain Security Engineer (`@sec-eng`, Swarm Message #118)**:
   > "Target: defusedxml (PSF-2.0). License & Supply-Chain: 100% permissive (PSF-2.0). Neutralizes XML External Entity (XXE) attacks, entity expansion bombs (billion laughs), and DTD parsing exploits. Pre-parse scanner rejects <!DOCTYPE and <!ENTITY before parser invocation. svg_dag.py validates <use> references as an acyclic local DAG with maximum depth <= 4 and total expanded nodes <= 500. Verdict: APPROVED."

3. **Test & Build Quality Engineer (`@qa-eng`, Swarm Message #120)**:
   > "Target: defusedxml (Python-2.0, permissive). License: Python Software Foundation License (PSF-2.0 / Python-2.0). 100% Apache-2.0 compatible. Hardens XML and SVG processing against entity expansion bombs (billion laughs), quadratic blowup, DTD parameter entity attacks, and external entity injection (XXE). Verdict: APPROVED."
