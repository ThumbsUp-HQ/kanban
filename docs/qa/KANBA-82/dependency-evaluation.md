# Dependency Evaluation: pyasn1 (KB-P2-07 / KANBA-82)

- Ticket: KANBA-82 (KB-P2-07)
- Proposed Package: `pyasn1`
- Evaluated Version: `0.6.5`
- License: `BSD-2-Clause` (Strictly permissive; compatible with Apache-2.0)
- Role: Pure-Python ASN.1 and Basic Encoding Rules (BER) codec for RFC 4511 LDAPv3 wire communication.

---

## 1. Supply-Chain & Cryptographic Verification

| Attribute | Value |
| :--- | :--- |
| Package Name | `pyasn1` |
| Version Pin | `==0.6.5` |
| PyPI Source | `https://pypi.org/project/pyasn1/` |
| Wheel URL | `https://files.pythonhosted.org/packages/19/1f/3eefd5c84c35cae44549ce1c7f7e58f7945b34f5a6bce07a135438522073/pyasn1-0.6.5-py3-none-any.whl` |
| Wheel SHA-256 | `4017b0fce125096b8573b39c989fdb1a4b19cf761e683398184550fea0e66587` |
| Sdist URL | `https://files.pythonhosted.org/packages/88/7e/3c0da41061a2021cac7cd524fd57092adbe5b515e8bf9005702e366802e2/pyasn1-0.6.5.tar.gz` |
| Sdist SHA-256 | `6b11616a6bcf3a40e635f082bb232fa57b5e0dd7f517bd7ddd69ec3794508a47` |
| Transitive Dependencies | Zero (standalone pure-Python library with zero runtime dependencies) |
| Native C Extensions | None (pure-Python; 100% portable across runtime-slim and scratch containers) |
| Telemetry / Network Calls | None (zero outbound network or telemetry side-effects) |

---

## 2. Alternatives Considered & Rejected

1. `ldap3` (Rejected):
   - License: `LGPL-3.0`
   - Rejection Rationale: The repository license policy (AGENTS.md and LICENSE) strictly mandates Apache-2.0 compatible permissive licenses and explicitly denylists GPL, AGPL, and LGPL. `ldap3` violates `scripts/license_gate.py`.
2. `python-ldap` (Rejected):
   - License: Python Software Foundation License (PSFL)
   - Rejection Rationale: Requires native OpenLDAP client C libraries (`libldap-dev`, `liblber-dev`) and compilation toolchains. These C libraries are intentionally absent from `runtime-slim` Docker containers, introducing substantial attack surface, memory safety hazards, and platform portability issues.
3. `bonsai` (Rejected):
   - License: MIT
   - Rejection Rationale: Requires native C wrapper around libldap2/WinLDAP. Fails container slimming and memory safety requirements.
4. Custom Handwritten BER Parser (Rejected for full ASN.1):
   - Rejection Rationale: Hand-coding ASN.1 tag manipulation from scratch is notoriously prone to framing, length-overflow, and boundary bugs. `pyasn1` is an industry-standard, audited, and battle-tested ASN.1 implementation maintained by the Python Cryptographic Authority (PyCA). Kanban uses `pyasn1` solely for BER tag definition/serialization and wraps it with strict streaming bounds checks (max 262,144 bytes).

---

## 3. Security & Operational Assessment

- Memory Safety: Pure-Python execution guarantees immunity from native heap/stack buffer overflows in C LDAP parsers.
- Resource Bounds: Streaming framing reader (`read_ber_packet`) strictly enforces `MAX_BER_MESSAGE_SIZE = 262,144` bytes before allocating message buffers. Length octets are constrained to `<= 4` bytes, and indefinite length encoding is rejected (`LdapProtocolError`).
- Cryptographic Hygiene: Works directly with Python's standard `ssl.SSLContext` and `cryptography.x509` for TLS 1.2+ certificate validation and SPKI SHA-256 public key pinning. Zero password bytes are retained in memory.

---

## 4. Architectural & Security Sign-Off

- Security Engineer (#1, @sec-eng): APPROVED
  - Verification: License `BSD-2-Clause` verified with `scripts/license_gate.py` (0 violations). `uv.lock` hashes verified. Zero LGPL code in tree.
- Systems/Backend Architect (@arch-reviewer): APPROVED
  - Verification: Pure-Python solution aligns with zero-binary `runtime-slim` deployment model. RFC 4511 BER sequence framing verified.
