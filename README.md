# README update: validation and external-only persistence fixes

This README section documents the fixes applied in the feat/validation-external branch that harden the FinePrint Sherpa prototype for execution-time validation, evidence integrity, and fail-closed external-only persistence.

Summary of fixes applied

1. Execution-time validation
- All tool calls are validated at execution time using the tool schema loader (tool_schemas.yaml + jsonschema).
- The pipeline validates inputs before calling external tools and validates outputs after tool returns.
- The pipeline rejects invalid shapes or missing required fields and fails the job with structured errors.

2. External-only persistence (fail-closed)
- Documents and evidence passages are persisted only to an external terms API via the external_terms adapter.
- The adapter will refuse to operate unless TERMS_API_BASE is configured. The in-memory mock fallback is allowed only when EXTERNAL_TERMS_ALLOW_MOCK=true (explicit opt-in for testing).
- There is no silent local DB fallback; jobs fail closed when the external service is unavailable.

3. Evidence-ID verification and provenance checks
- After ingestion, the pipeline fetches the evidence passages from the authoritative store and verifies each claimed evidence ID.
- Each reported finding must include a 'provenance' mapping from evidence ID to passage text. The pipeline performs a simple substring heuristic to ensure the finding text matches the cited passage; if not, the job fails.
- Evidence IDs are validated to match the expected pattern (evi-<hex12>) to avoid trusting arbitrary strings.

4. Report schema validation
- Final reports are validated against a strict report schema. Missing required fields, missing provenance, or unsupported claims cause the job to fail.

5. Fail-closed error handling
- On any schema mismatch, missing evidence, or external service error, the job fails with a structured error payload and is not published.
- Errors are logged with stack traces for debugging but the pipeline avoids fabricating results.

6. Concurrency and safety
- In-memory job state (JOB_STATUS, JOB_REPORTS, JOB_CANCEL) is protected by a threading.Lock to prevent race conditions across concurrent jobs in the same process.

7. SSRF protections in fetch path
- The pipeline includes a conservative synchronous fetch implementation (fetch_url_sync) with redirect validation, DNS resolution checks, and private IP blocking. This is intentionally conservative for the prototype and should be replaced by the retrieval module for production.

How to run the local smoke test (simulation)
- See run_smoke_simulation.py at the repo root for an explicit self-contained simulated smoke test that uses EXTERNAL_TERMS_ALLOW_MOCK=true and avoids network calls.

Notes and next steps
- Add a robust retrieval module reuse (the dedicated retrieval.py) and ensure consistent SSRF checks across modules.
- Implement wall-clock timeouts and per-job resource budgets enforced by an external task runner for stronger isolation.
- Implement richer provenance checks (semantic matching, clause offsets) for higher assurance.
- Add integration tests against a real external terms service (e.g., Supabase or a custom API) using CI secrets.

