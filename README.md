# fineprint-sherpa
Fine Print Intelligence Agent — secure document retrieval, evidence-backed contract analysis, and decision-support system.

This repository is intentionally fail-closed: it requires an external evidence store for authoritative persistence, refuses silent mock fallback in production, and validates tool inputs/outputs, evidence IDs, and report structure before reporting a finding.

Complementary inspiration

This project draws inspiration from the work in MatrixAwakens69/rag-contract-analyzer (https://github.com/MatrixAwakens69/rag-contract-analyzer) — thank you, @MatrixAwakens69. We reused the useful ideas around retrieval-assisted candidate generation, chunking, and evidence-oriented triage, while keeping the evidence model deliberate and externally authoritative.

Important: the upstream repo does not list a license in the public metadata, so we implemented the complementary pieces in a reworked, minimal form and credited the original project rather than copying large blocks of code.

What is fixed in this branch

- Strict execution-time validation of tool inputs/outputs.
- Fail-closed external persistence: no silent local database or mock fallback in production.
- Evidence-ID verification and provenance checks before a report is accepted.
- Report schema validation and rejection of unsupported claims.
- A local in-memory retrieval layer used only for candidate assistance; it is not authoritative evidence.
- Unit tests for invalid schema, unavailable service, and unknown evidence rejection.
- A smoke-test path for local verification with EXTERNAL_TERMS_ALLOW_MOCK=true.

Local smoke test

Set the explicit opt-in for tests:

  export EXTERNAL_TERMS_ALLOW_MOCK=true

Then run the local smoke simulation or pytest.

Security note

The retrieval layer is intentionally read-only and non-authoritative. Any candidate returned by the index must be checked against the external terms store via its evidence_id before it is used in a finding.

Additional notes

- The external terms service remains the source of truth for evidence.
- The vector/index layer is only a retrieval accelerator and must not replace verified evidence.
- Unsupported claims are rejected rather than warned about.
